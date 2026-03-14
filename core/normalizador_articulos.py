"""
normalizador_articulos.py — RPA Suite v5
==========================================
Robot de normalización de descripciones de artículos usando Gemini IA.

Problema que resuelve:
  - Abreviaturas del sistema MBF: "GALL RFMA FRESA 120G" → "Galletitas Rellenas Fresa 120g"
  - Orden disparejo: "TRIO GALLETITAS" y "GALLETITAS TRIO" → siempre "Galletitas Trio"
  - Formato estándar: Marca + Producto + Variante + Contenido
  - Confusión de UxB: "12x800G" → "800g" (excepto bebidas que sí venden por bulto)
  - Categorías mal asignadas o mezcladas con la descripción

Formato de salida estándar:
  [Marca] [Producto] [Variante] [Contenido]
  Ejemplos:
    Milka Galletitas Rellenas Fresa 120g
    Coca-Cola Gaseosa 2.25L (bulto x6)   ← bebidas mantienen UxB
    La Serenísima Yogur Firme Frutilla 200g
    Ariel Detergente Polvo Regular 800g

Características:
  - Lotes de 50 SKUs por llamada (balance costo/velocidad)
  - Cache en disco (articulos_cache.json) — no reprocesa lo ya normalizado
  - Confianza por fila (0.0–1.0) — marca las que necesitan revisión manual
  - Excel de revisión: original vs normalizado lado a lado
  - Reintentos automáticos ante errores de API
  - Integrado con file_manager para archivar el CSV fuente
"""

import pandas as pd
import json
import os
import time
import hashlib
import traceback
import sys
from pathlib import Path
# Asegurar que la raíz del proyecto esté en el path
_RAIZ = Path(__file__).parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))
from datetime import datetime

# ── Categorías que venden POR BULTO (mantienen UxB en la descripción) ──────
FAMILIAS_BULTO = {
    'gaseosas', 'bebidas', 'aguas', 'cervezas', 'vinos', 'jugos',
    'aguas saborizadas', 'energizantes', 'isotonicos', 'sidra',
    'fernet', 'aperitivo', 'whisky', 'vodka', 'gin', 'ron',
}

# ── Cache ───────────────────────────────────────────────────────────────────
CACHE_PATH = Path(__file__).parent / "articulos_cache.json"

def _cargar_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}

def _guardar_cache(cache: dict):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')

def _clave_cache(sku, descripcion, familia) -> str:
    texto = f"{sku}|{str(descripcion).upper().strip()}|{str(familia).upper().strip()}"
    return hashlib.md5(texto.encode()).hexdigest()


# ── Gemini ──────────────────────────────────────────────────────────────────
def _get_model():
    import google.generativeai as genai
    from config import get_gemini_key
    genai.configure(api_key=get_gemini_key())
    return genai.GenerativeModel('gemini-1.5-flash')


# ── Prompt especializado en retail argentino ────────────────────────────────
PROMPT_SISTEMA = """Sos un experto en normalización de datos de retail argentino (mayoristas y supermercados).
Tu tarea es normalizar descripciones de artículos al formato estándar:
  [Marca] [Producto] [Variante/Sabor] [Contenido]

REGLAS IMPORTANTES:
1. Formato SIEMPRE: Marca Producto Variante Contenido
   Ejemplo: "GALL RFMA FRESA 120G" → "Milka Galletitas Rellenas Fresa 120g"

2. Primera letra mayúscula en cada palabra (Title Case), excepto g/kg/ml/l/cc que van en minúscula.

3. ELIMINAR UxB del nombre EXCEPTO en bebidas (gaseosas, aguas, cervezas, vinos, jugos, etc.):
   - MAL:  "Fideos Tallarín Don Vittorio 12x400g"
   - BIEN: "Don Vittorio Fideos Tallarín 400g"
   - BEBIDAS OK: "Coca-Cola Gaseosa 2.25L" o "Quilmes Cerveza 340ml (x6)" si es por bulto

4. Orden FIJO: Marca siempre primero.
   - MAL:  "Galletitas Trio Arcor"
   - BIEN: "Arcor Galletitas Trio"

5. Inflar abreviaturas conocidas del sistema MBF/Ideafix:
   GALL=Galletitas, RFMA=Rellenas, YOG=Yogur, DESC=Descremado/a,
   DET=Detergente, LIQ=Líquido, NAT=Natural, SB=Sin TACC o Sabor Básico,
   LAV=Lavandina, SUC=Sucedáneo, AZ=Azúcar, ACE=Aceite, ARR=Arroz,
   FID=Fideos, MAY=Mayonesa, KET=Ketchup, MOS=Mostaza, VIN=Vinagre,
   JAB=Jabón, CHA=Champú/Shampoo, ACO=Acondicionador, DEO=Desodorante,
   ALP=Alpargatas, GAL=Galletitas, CHO=Chocolate, MER=Mermelada,
   MAN=Manteca o Maní (por contexto), QUE=Queso, FRE=Fresa/Frutilla,
   DUL=Dulce, PAP=Papa/Papas, HAR=Harina, PAN=Pan/Panificados

6. Para la categoría, devolvé una de estas (elegí la más específica):
   Galletitas | Fideos | Arroz | Harinas | Aceites | Azúcar y Endulzantes |
   Conservas | Lácteos | Bebidas Gaseosas | Aguas | Cervezas | Vinos |
   Jugos y Néctares | Snacks | Chocolates y Golosinas | Café y Té |
   Limpieza del Hogar | Higiene Personal | Panificados | Embutidos |
   Congelados | Condimentos | Otros Alimentos | Sin Categoría

7. Si NO podés determinar la marca con certeza, ponés el producto sin marca.

8. Confianza: 1.0=muy seguro, 0.7=razonablemente seguro, 0.5=dudoso, 0.3=muy incierto.
   Marcá como baja confianza si la abreviatura es muy ambigua o no reconocés la marca.

Respondé ÚNICAMENTE con JSON válido, sin texto adicional, sin markdown, sin backticks.
"""

PROMPT_LOTE = """Normalizá los siguientes artículos de un mayorista argentino.
La columna "es_bebida" indica si el artículo es de una categoría que se vende por bulto.

Artículos a normalizar:
{articulos_json}

Respondé con un JSON array con exactamente {n} objetos, uno por artículo, en el mismo orden:
[
  {{
    "sku": 1234,
    "descripcion_original": "texto original",
    "descripcion_normalizada": "Marca Producto Variante Contenido",
    "marca": "Nombre de la marca",
    "categoria": "Categoría estándar",
    "confianza": 0.9,
    "nota": "opcional: explicación si hay algo raro o ambiguo"
  }},
  ...
]
"""


# ── Normalización en lote ───────────────────────────────────────────────────
def _normalizar_lote(model, lote: list[dict], log_func, intento=1) -> list[dict]:
    """
    Envía un lote de artículos a Gemini y retorna los resultados normalizados.
    lote: lista de dicts con keys: sku, descripcion, familia, es_bebida
    """
    articulos_json = json.dumps(lote, ensure_ascii=False, indent=2)
    prompt = PROMPT_LOTE.format(articulos_json=articulos_json, n=len(lote))

    try:
        response = model.generate_content(
            [PROMPT_SISTEMA, prompt],
            generation_config={"temperature": 0.1, "max_output_tokens": 4096}
        )
        texto = response.text.strip()
        # Limpiar posibles backticks de markdown
        texto = texto.replace("```json", "").replace("```", "").strip()

        resultados = json.loads(texto)

        # Validar que volvió la cantidad correcta
        if len(resultados) != len(lote):
            log_func(f"  ⚠ Lote devolvió {len(resultados)} en vez de {len(lote)} — parcheando...")
            # Completar con fallback los faltantes
            skus_devueltos = {str(r.get('sku', '')) for r in resultados}
            for art in lote:
                if str(art['sku']) not in skus_devueltos:
                    resultados.append({
                        "sku": art['sku'],
                        "descripcion_original": art['descripcion'],
                        "descripcion_normalizada": art['descripcion'],
                        "marca": "",
                        "categoria": "Sin Categoría",
                        "confianza": 0.0,
                        "nota": "No retornado por la API"
                    })

        return resultados

    except json.JSONDecodeError as e:
        if intento < 3:
            log_func(f"  ⚠ Error JSON en lote (intento {intento}/3), reintentando...")
            time.sleep(2 * intento)
            return _normalizar_lote(model, lote, log_func, intento + 1)
        else:
            log_func(f"  ❌ Lote fallido tras 3 intentos: {e}")
            # Retornar fallback para todo el lote
            return [{
                "sku": art['sku'],
                "descripcion_original": art['descripcion'],
                "descripcion_normalizada": art['descripcion'],
                "marca": "",
                "categoria": "Sin Categoría",
                "confianza": 0.0,
                "nota": f"Error API: {str(e)[:80]}"
            } for art in lote]

    except Exception as e:
        if intento < 3:
            log_func(f"  ⚠ Error en lote (intento {intento}/3): {e}")
            time.sleep(3 * intento)
            return _normalizar_lote(model, lote, log_func, intento + 1)
        else:
            log_func(f"  ❌ Lote abandonado: {e}")
            return [{
                "sku": art['sku'],
                "descripcion_original": art['descripcion'],
                "descripcion_normalizada": art['descripcion'],
                "marca": "",
                "categoria": "Sin Categoría",
                "confianza": 0.0,
                "nota": f"Error: {str(e)[:80]}"
            } for art in lote]


# ── FUNCIÓN PRINCIPAL ────────────────────────────────────────────────────────
def ejecutar_normalizador(
    ruta_csv: str,
    log_func=print,
    progress_func=None,
    tam_lote: int = 50,
    forzar_reproceso: bool = False,
    stop_event=None,
) -> str | None:
    """
    Lee el CSV de artículos MBF, normaliza descripciones con Gemini
    y genera un Excel de revisión con original vs normalizado.

    Args:
        ruta_csv:        Ruta al CSV del sistema (lpcio_mbf_*.csv)
        log_func:        Función de logging (para la GUI)
        progress_func:   Función de progreso (0-100)
        tam_lote:        Artículos por llamada API (default 50)
        forzar_reproceso: Ignorar cache y reprocesar todo

    Returns:
        Ruta del Excel generado, o None si falla.
    """
    try:
        log_func(f"🤖 Normalizador de Artículos iniciado")
        log_func(f"   Archivo: {Path(ruta_csv).name}")

        # ── 1. LEER CSV ───────────────────────────────────────────
        log_func("📖 Leyendo archivo...")
        df = None
        for sep in ['\t', ';', '|', ',']:
            try:
                df_test = pd.read_csv(ruta_csv, sep=sep, encoding='latin-1',
                                      on_bad_lines='skip')
                if len(df_test.columns) >= 3:
                    df = df_test
                    break
            except Exception:
                continue

        if df is None:
            log_func("❌ No se pudo leer el archivo.")
            return None

        df.columns = df.columns.str.strip()
        log_func(f"   {len(df):,} artículos leídos | Columnas: {list(df.columns)}")

        # ── 2. DETECTAR COLUMNAS ──────────────────────────────────
        col_map = {}
        mapeo_conocido = {
            'sku':          ['articulo', 'codigo', 'sku', 'cod', 'art', 'codart'],
            'descripcion':  ['descripcion', 'descripción', 'desc', 'nombre', 'detalle'],
            'familia':      ['familia', 'rubro', 'categoria', 'desfam', 'departamento'],
            'barras':       ['barras', 'ean', 'codbar', 'barra', 'codigo_barras'],
            'precio':       ['precio', 'p_salon', 'psalon', 'pvp', 'precio_venta'],
            'oferta':       ['oferta', 'p_oferta', 'descuento', 'precio_oferta'],
        }
        for campo, candidatos in mapeo_conocido.items():
            for col in df.columns:
                if col.strip().lower() in candidatos:
                    col_map[campo] = col
                    break

        if 'sku' not in col_map or 'descripcion' not in col_map:
            log_func(f"❌ No se encontraron columnas SKU/Descripción.")
            log_func(f"   Columnas disponibles: {list(df.columns)}")
            return None

        log_func(f"   Columnas mapeadas: {col_map}")

        # ── 3. PREPARAR DATOS ─────────────────────────────────────
        df['_sku']    = pd.to_numeric(df[col_map['sku']], errors='coerce')
        df['_desc']   = df[col_map['descripcion']].astype(str).str.strip()
        df['_fam']    = df[col_map['familia']].astype(str).str.strip() if 'familia' in col_map else ''

        # Detectar si es bebida (para mantener UxB)
        df['_es_bebida'] = df['_fam'].str.lower().apply(
            lambda f: any(cat in f for cat in FAMILIAS_BULTO)
        )

        # Filtrar filas válidas
        df_valido = df.dropna(subset=['_sku']).copy()
        df_valido['_sku'] = df_valido['_sku'].astype(int)
        total = len(df_valido)
        log_func(f"   {total:,} artículos válidos para normalizar")

        # ── 4. INICIALIZAR GEMINI Y CACHE ─────────────────────────
        try:
            model = _get_model()
            log_func("✅ Gemini conectado")
        except Exception as e:
            log_func(f"❌ Error conectando Gemini: {e}")
            log_func("   Verificá GEMINI_API_KEY en tu .env")
            return None

        cache = {} if forzar_reproceso else _cargar_cache()
        cache_hits = 0
        resultados_todos = []

        # ── 5. PROCESAR EN LOTES ──────────────────────────────────
        # Separar los que ya están en cache de los que hay que procesar
        pendientes = []
        cache_resultados = {}

        for _, row in df_valido.iterrows():
            clave = _clave_cache(row['_sku'], row['_desc'], row['_fam'])
            if clave in cache and not forzar_reproceso:
                cache_resultados[row['_sku']] = cache[clave]
                cache_hits += 1
            else:
                pendientes.append({
                    'sku': int(row['_sku']),
                    'descripcion': row['_desc'],
                    'familia': row['_fam'],
                    'es_bebida': bool(row['_es_bebida']),
                    '_clave': clave,
                })

        log_func(f"   📦 Cache: {cache_hits:,} artículos ya procesados")
        log_func(f"   🔄 Pendientes de normalizar: {len(pendientes):,}")

        if pendientes:
            n_lotes = (len(pendientes) + tam_lote - 1) // tam_lote
            log_func(f"   📡 Enviando a Gemini en {n_lotes} lotes de ~{tam_lote} artículos...")
            log_func(f"   ⏱  Tiempo estimado: {n_lotes * 3}–{n_lotes * 6} segundos")

            for i in range(0, len(pendientes), tam_lote):
                # Chequear si el usuario pidió detener
                if stop_event and stop_event.is_set():
                    log_func("⏹ Normalización detenida por el usuario. El cache fue guardado.")
                    break
                lote = pendientes[i:i + tam_lote]
                num_lote = i // tam_lote + 1
                log_func(f"   Lote {num_lote}/{n_lotes} ({len(lote)} artículos)...")

                # Quitar _clave del dict antes de enviar a la API
                lote_api = [{k: v for k, v in art.items() if k != '_clave'} for art in lote]
                resultados_lote = _normalizar_lote(model, lote_api, log_func)

                # Guardar en cache
                for art, res in zip(lote, resultados_lote):
                    cache[art['_clave']] = res
                    cache_resultados[art['sku']] = res

                _guardar_cache(cache)

                # Estadísticas del lote
                confianza_prom = sum(r.get('confianza', 0) for r in resultados_lote) / len(resultados_lote)
                log_func(f"   ✓ Lote {num_lote} OK | Confianza promedio: {confianza_prom:.0%}")

                if progress_func:
                    progress_func(int((i + len(lote)) / len(pendientes) * 100))

                # Pausa entre lotes para no saturar la API
                if i + tam_lote < len(pendientes):
                    if stop_event and stop_event.is_set():
                        log_func("⏹ Normalización detenida por el usuario. El cache fue guardado.")
                        break
                    time.sleep(1.5)

        # ── 6. CONSTRUIR DATAFRAME DE RESULTADOS ─────────────────
        filas_resultado = []
        for _, row in df_valido.iterrows():
            sku = int(row['_sku'])
            res = cache_resultados.get(sku, {})

            fila = {
                'SKU': sku,
                'DESCRIPCION_ORIGINAL': row['_desc'],
                'DESCRIPCION_NORMALIZADA': res.get('descripcion_normalizada', row['_desc']),
                'MARCA': res.get('marca', ''),
                'CATEGORIA_NUEVA': res.get('categoria', ''),
                'FAMILIA_ORIGINAL': row['_fam'],
                'CONFIANZA': res.get('confianza', 0.0),
                'NOTA': res.get('nota', ''),
            }

            # Agregar columnas extra del CSV original
            if 'barras' in col_map:
                fila['BARRAS'] = row.get(col_map['barras'], '')
            if 'precio' in col_map:
                fila['PRECIO'] = row.get(col_map['precio'], '')
            if 'oferta' in col_map:
                fila['OFERTA'] = row.get(col_map['oferta'], '')

            filas_resultado.append(fila)

        df_result = pd.DataFrame(filas_resultado)

        # ── 7. ESTADÍSTICAS FINALES ───────────────────────────────
        total_procesados = len(df_result)
        confianza_alta  = (df_result['CONFIANZA'] >= 0.8).sum()
        confianza_media = ((df_result['CONFIANZA'] >= 0.5) & (df_result['CONFIANZA'] < 0.8)).sum()
        confianza_baja  = (df_result['CONFIANZA'] < 0.5).sum()
        requieren_revision = confianza_baja + confianza_media

        log_func("─" * 50)
        log_func(f"📊 RESUMEN DE NORMALIZACIÓN")
        log_func(f"   Total artículos: {total_procesados:,}")
        log_func(f"   ✅ Confianza alta  (≥80%): {confianza_alta:,} artículos")
        log_func(f"   🟡 Confianza media (50–79%): {confianza_media:,} artículos")
        log_func(f"   🔴 Requieren revisión (<50%): {confianza_baja:,} artículos")
        log_func(f"   📝 Para revisar manualmente: {requieren_revision:,} artículos")

        # Top categorías detectadas
        if 'CATEGORIA_NUEVA' in df_result.columns:
            top_cats = df_result['CATEGORIA_NUEVA'].value_counts().head(8)
            log_func("   🏷️  Top categorías detectadas:")
            for cat, cnt in top_cats.items():
                log_func(f"      {cat}: {cnt:,}")
        log_func("─" * 50)

        # ── 8. EXPORTAR EXCEL ─────────────────────────────────────
        carpeta = Path(ruta_csv).parent
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        nombre_salida = f"ARTICULOS_NORMALIZADOS_{timestamp}.xlsx"
        ruta_salida = str(carpeta / nombre_salida)

        log_func(f"💾 Generando Excel: {nombre_salida}")

        with pd.ExcelWriter(ruta_salida, engine='xlsxwriter') as writer:
            wb = writer.book

            # ── Formatos ──
            fmt_header = wb.add_format({
                'bold': True, 'bg_color': '#1E3A5F', 'font_color': 'white',
                'border': 1, 'align': 'center', 'font_size': 10,
            })
            fmt_verde   = wb.add_format({'bg_color': '#D1FAE5', 'font_size': 9})
            fmt_amarillo= wb.add_format({'bg_color': '#FEF9C3', 'font_size': 9})
            fmt_rojo    = wb.add_format({'bg_color': '#FEE2E2', 'font_size': 9})
            fmt_normal  = wb.add_format({'font_size': 9})
            fmt_pct     = wb.add_format({'num_format': '0%', 'align': 'center', 'font_size': 9})
            fmt_int     = wb.add_format({'num_format': '0', 'align': 'center', 'font_size': 9})

            # ── HOJA 1: TODOS (para importar al sistema) ──────────
            df_result.to_excel(writer, index=False, sheet_name='Normalizados')
            ws = writer.sheets['Normalizados']
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, len(df_result), len(df_result.columns) - 1)

            anchos = {
                'SKU': 10, 'DESCRIPCION_ORIGINAL': 45, 'DESCRIPCION_NORMALIZADA': 45,
                'MARCA': 20, 'CATEGORIA_NUEVA': 25, 'FAMILIA_ORIGINAL': 20,
                'CONFIANZA': 12, 'NOTA': 35, 'BARRAS': 15, 'PRECIO': 12, 'OFERTA': 12,
            }
            for col_idx, col_name in enumerate(df_result.columns):
                ws.write(0, col_idx, col_name, fmt_header)
                ws.set_column(col_idx, col_idx, anchos.get(col_name, 15))

            # Colorear filas por confianza
            idx_conf = list(df_result.columns).index('CONFIANZA')
            for row_idx, (_, row) in enumerate(df_result.iterrows(), start=1):
                conf = row.get('CONFIANZA', 0)
                if conf >= 0.8:
                    fmt_row = fmt_verde
                elif conf >= 0.5:
                    fmt_row = fmt_amarillo
                else:
                    fmt_row = fmt_rojo

                for col_idx, col_name in enumerate(df_result.columns):
                    val = row[col_name]
                    if col_name == 'CONFIANZA':
                        ws.write(row_idx, col_idx, val, fmt_pct)
                    elif col_name == 'SKU':
                        ws.write(row_idx, col_idx, val, fmt_int)
                    else:
                        ws.write(row_idx, col_idx, '' if pd.isna(val) else val, fmt_row)

            # ── HOJA 2: REVISIÓN MANUAL (confianza baja) ─────────
            df_revision = df_result[df_result['CONFIANZA'] < 0.7].copy()
            if len(df_revision) > 0:
                df_revision.to_excel(writer, index=False, sheet_name='⚠ Revisar')
                ws2 = writer.sheets['⚠ Revisar']
                ws2.freeze_panes(1, 0)
                ws2.autofilter(0, 0, len(df_revision), len(df_revision.columns) - 1)
                for col_idx, col_name in enumerate(df_revision.columns):
                    ws2.write(0, col_idx, col_name, fmt_header)
                    ws2.set_column(col_idx, col_idx, anchos.get(col_name, 15))
                log_func(f"   ⚠ Hoja '⚠ Revisar': {len(df_revision):,} artículos para revisar")

            # ── HOJA 3: ESTADÍSTICAS ──────────────────────────────
            stats_data = {
                'Métrica': [
                    'Total artículos procesados',
                    'Confianza alta (≥80%)',
                    'Confianza media (50–79%)',
                    'Requieren revisión (<50%)',
                    'Desde cache',
                    'Nuevos procesados',
                    'Fecha proceso',
                ],
                'Valor': [
                    total_procesados,
                    confianza_alta,
                    confianza_media,
                    confianza_baja,
                    cache_hits,
                    len(pendientes),
                    datetime.now().strftime('%d/%m/%Y %H:%M'),
                ]
            }
            df_stats = pd.DataFrame(stats_data)
            df_stats.to_excel(writer, index=False, sheet_name='Estadísticas')
            ws3 = writer.sheets['Estadísticas']
            ws3.set_column('A:A', 35)
            ws3.set_column('B:B', 20)

        log_func(f"✅ Excel generado con éxito: {nombre_salida}")
        log_func(f"   📂 Ubicación: {ruta_salida}")
        return ruta_salida

    except Exception as e:
        log_func(f"❌ Error crítico en normalizador: {e}")
        log_func(traceback.format_exc())
        return None


# ── EJECUCIÓN DIRECTA ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    print("\n" + "=" * 60)
    print("  NORMALIZADOR DE ARTÍCULOS — RPA Suite v5")
    print("=" * 60)

    if len(sys.argv) > 1:
        ruta = sys.argv[1]
    else:
        ruta = input("\n  Ruta del CSV (ej: lpcio_mbf_andres.csv): ").strip().strip('"')

    if not Path(ruta).exists():
        print(f"\n  ❌ Archivo no encontrado: {ruta}")
        sys.exit(1)

    forzar = input("  ¿Forzar reproceso ignorando cache? (s/N): ").strip().lower() == 's'

    resultado = ejecutar_normalizador(
        ruta_csv=ruta,
        log_func=lambda m: print(f"  {m}"),
        forzar_reproceso=forzar,
    )

    if resultado:
        print(f"\n  ✅ Listo. Excel generado en:\n  {resultado}\n")
        try:
            os.startfile(resultado)
        except Exception:
            pass
    else:
        print("\n  ❌ El proceso falló. Revisá los mensajes de error.\n")