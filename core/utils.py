"""
utils.py — RPA Suite v5
========================
Librería central de utilidades. 
Mejoras v5:
  - Credenciales via config.py (sin hardcodeo)
  - Categorizador NLP reemplazado por Gemini IA (10k artículos)
  - Motor BI con comparación de períodos
  - Cache de categorías para no re-llamar la API innecesariamente
"""
import pandas as pd
import ctypes
import pyautogui
import os
import re
import json
import time
import hashlib
import pygetwindow as gw
from pathlib import Path
from functools import lru_cache

import requests as _requests
from config import GROQ_API_KEY, GEMINI_API_KEY, get_ssh_config

# ============================================================
# INICIALIZACIÓN GROQ
# ============================================================
def _groq_completar(prompt: str) -> str:
    """Llama a Groq y devuelve el texto generado. Lanza excepción si falla."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY no configurada en .env")
    resp = _requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "max_tokens": 800, "temperature": 0.2},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ============================================================
# 1. UTILITARIOS DE VENTANAS
# ============================================================
def enfocar_putty():
    """Busca la ventana de PuTTY y le da foco."""
    try:
        ventanas = [w for w in gw.getWindowsWithTitle('PuTTY') if 'PuTTY' in w.title]
        if ventanas:
            win = ventanas[0]
            if win.isMinimized:
                win.restore()
            try:
                win.activate()
            except Exception:
                pass
            time.sleep(1)
            return True
        return False
    except Exception:
        return False


# ============================================================
# 2. UTILITARIOS DE LIMPIEZA Y SEGURIDAD
# ============================================================
def limpiar_sku(v) -> str | None:
    """Limpia y normaliza un SKU eliminando decimales y espacios."""
    if pd.isna(v):
        return None
    try:
        s = str(v).strip()
        try:
            return str(int(float(s)))
        except Exception:
            if s.endswith('.0'):
                s = s[:-2]
            return s.lstrip('0') or '0'
    except Exception:
        return None


def f_monto(v) -> str:
    """Formatea un valor numérico como string con 2 decimales."""
    if pd.isna(v) or str(v).strip().lower() in ['nan', 'none', '']:
        return "0.00"
    try:
        valor = float(str(v).replace(',', '.'))
        return "{:.2f}".format(valor)
    except Exception:
        return "0.00"


def forzar_caps_off():
    """Fuerza CAPS LOCK apagado en Windows."""
    try:
        hllDll = ctypes.WinDLL("User32.dll")
        if hllDll.GetKeyState(0x14) & 0x0001:
            pyautogui.press('capslock')
    except Exception:
        pass


# ============================================================
# 3. ETL ORIGINALES
# ============================================================
def etl_lpcio_a_excel(ruta_csv: str, carpeta_salida: str) -> str:
    """Transforma CSV de lista de precios a Excel limpio con columnas estándar."""
    try:
        df = pd.read_csv(ruta_csv, sep=';', encoding='latin-1', header=None)
        df_limpio = df[[0, 1, 2, 3, 4]].copy()
        df_limpio.columns = ['SKU', 'DESCRIPCION', 'COSTO', 'P_SALON', 'P_MAYORISTA']
        nombre = f"{Path(ruta_csv).stem}_LIMPIO.xlsx"
        ruta_salida = os.path.join(carpeta_salida, nombre)
        df_limpio.to_excel(ruta_salida, index=False)
        return ruta_salida
    except Exception as e:
        return f"Error ETL: {e}"


def etl_ventas_a_excel(ruta_csv: str, carpeta_salida: str) -> str:
    """Agrupa ventas por SKU y genera Excel consolidado."""
    try:
        df = pd.read_csv(ruta_csv, sep=';', encoding='latin-1')
        df_limpio = df.groupby('SKU').agg({'CANTIDAD': 'sum', 'TOTAL': 'sum'}).reset_index()
        nombre = f"{Path(ruta_csv).stem}_ETL.xlsx"
        ruta_salida = os.path.join(carpeta_salida, nombre)
        df_limpio.to_excel(ruta_salida, index=False)
        return ruta_salida
    except Exception as e:
        return f"Error ETL Ventas: {e}"


def motor_bi_avanzado(lista_ventas: list, ruta_maestro: str, carpeta_salida: str, tipo_analisis: str) -> str:
    """
    Motor BI: consolida múltiples períodos de ventas contra maestro de artículos.
    lista_ventas: [{'ruta': ..., 'etiqueta': 'Enero 2025'}, ...]
    """
    try:
        df_maestro = pd.read_excel(ruta_maestro)
        df_maestro['SKU'] = df_maestro['SKU'].astype(str)
        dfs_ventas = []
        for v in lista_ventas:
            df_v = pd.read_excel(v['ruta'])
            df_v['SKU'] = df_v['SKU'].astype(str)
            df_v['ETIQUETA_TIEMPO'] = v['etiqueta']
            dfs_ventas.append(df_v)
        df_consolidado = pd.concat(dfs_ventas, ignore_index=True)
        df_final = pd.merge(df_consolidado, df_maestro, on='SKU', how='left')
        ruta_bi = os.path.join(carpeta_salida, "REPORTE_BI_GENERADO.xlsx")
        df_final.to_excel(ruta_bi, index=False)
        return ruta_bi
    except Exception as e:
        return f"Error BI: {e}"


# ============================================================
# 4. CATEGORIZADOR IA (REEMPLAZA REGEX HARDCODEADO)
# ============================================================

# Cache en disco para no re-llamar la API para los mismos artículos
_CACHE_PATH = Path(__file__).parent / "categoria_cache.json"  # cache en core/

def _cargar_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}

def _guardar_cache(cache: dict):
    try:
        _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass


def categorizar_articulos_ia(descripciones: list[str], log_func=print) -> dict[str, str]:
    """
    Categoriza una lista de descripciones de artículos usando Gemini IA.
    Usa cache en disco para evitar llamadas repetidas a la API.
    
    Retorna dict: {descripcion: categoria}
    
    Ideal para maestro de 10k artículos. Procesa en lotes de 100.
    """
    if not GROQ_API_KEY:
        log_func("⚠️ Groq no disponible. Usando categorizador NLP local.")
        return {d: _nlp_fallback(d) for d in descripciones}

    cache = _cargar_cache()
    resultado = {}
    pendientes = []

    # Separar los que ya están en cache
    for desc in descripciones:
        key = hashlib.md5(str(desc).upper().strip().encode()).hexdigest()
        if key in cache:
            resultado[desc] = cache[key]
        else:
            pendientes.append((desc, key))

    if not pendientes:
        log_func(f"✅ {len(resultado)} artículos desde cache (sin llamadas a API).")
        return resultado

    log_func(f"🤖 Categorizando {len(pendientes)} artículos nuevos con Groq/Llama...")

    # Procesar en lotes de 100 para no exceder límites de token
    BATCH = 100
    for batch_start in range(0, len(pendientes), BATCH):
        lote = pendientes[batch_start:batch_start + BATCH]
        descripciones_lote = [d for d, _ in lote]
        
        prompt = f"""Sos un experto en retail de alimentos y consumo masivo argentino.
Categorizá cada artículo de esta lista en UNA sola categoría de las siguientes:
Gaseosas | Cervezas | Vinos | Bebidas Espirituosas | Aguas y Jugos | Galletitas |
Fideos y Pastas | Arroz y Legumbres | Aceites | Lácteos | Carnes y Fiambres |
Limpieza del Hogar | Higiene Personal | Snacks | Conservas | Infusiones |
Panadería | Congelados | Golosinas | Otros

Lista de artículos (uno por línea):
{chr(10).join(f"{i+1}. {d}" for i, d in enumerate(descripciones_lote))}

Respondé ÚNICAMENTE con un JSON válido. Formato exacto:
{{"1": "Categoria", "2": "Categoria", ...}}
Sin texto adicional, sin markdown, sin explicaciones."""

        try:
            texto = _groq_completar(prompt).replace("```json", "").replace("```", "").strip()
            mapeo = json.loads(texto)
            
            for i, (desc, key) in enumerate(lote):
                cat = mapeo.get(str(i + 1), "Otros")
                resultado[desc] = cat
                cache[key] = cat
            
            log_func(f"  ✓ Lote {batch_start // BATCH + 1} procesado ({len(lote)} artículos)")
            _guardar_cache(cache)
            
        except Exception as e:
            log_func(f"  ⚠️ Error en lote {batch_start // BATCH + 1}: {e}. Usando NLP local.")
            for desc, key in lote:
                cat = _nlp_fallback(desc)
                resultado[desc] = cat
                cache[key] = cat

    log_func(f"✅ Categorización completa. {len(resultado)} artículos procesados.")
    return resultado


def _nlp_fallback(desc: str) -> str:
    """Categorizador NLP por regex como fallback cuando no hay API."""
    desc = str(desc).upper()
    patrones = [
        (r'GALLETI|OBLITA|TRAVIATA|CRIOLLITA|SURTIDO|CHOCOLINA|RUMBA|MERENGADA', 'Galletitas'),
        (r'FIDEO|TALLARIN|SPAGHETTI|MOÑO|TIRABUZON|GUISERO|MATARAZZO|LUCCHETTI|KNOOR', 'Fideos y Pastas'),
        (r'GASEOSA|COCA[ -]COLA|SPRITE|FANTA|PEPSI|7UP|SEVEN UP|PASO DE LOS TOROS|CUNNINGTON', 'Gaseosas'),
        (r'CERVEZA|BRAHMA|QUILMES|STELLA|HEINEKEN|ANDES|CORONA|AMSTEL|IMPERIAL', 'Cervezas'),
        (r'VINO|MALBEC|CABERNET|TINTO|BLANCO|CHARDONNAY|SYRAH|UVITA|TERMIDOR|BODEGA', 'Vinos'),
        (r'PAPA|CHIZITO|MANI|SNACK|DORITOS|CHEETOS|PALITO|LAY|PRINGLES|GOOD SHOW|TWISTOS', 'Snacks'),
        (r'AGUA |AGUA$|VILLAVICENCIO|SER |CEPITA|JUGO|BAGGIO|TANG', 'Aguas y Jugos'),
        (r'ARROZ|LENTEJA|GARBANZO|POROTO|HARINA', 'Arroz y Legumbres'),
        (r'ACEITE|GIRASOL|OLIVA', 'Aceites'),
        (r'LECHE|YOGUR|QUESO|MANTECA|CREMA|DANONE|SANCOR|ILOLAY', 'Lácteos'),
        (r'JABON|DETERGENTE|LAVANDINA|SUAVIZANTE|SKIP|ARIEL|MAGISTRAL', 'Limpieza del Hogar'),
        (r'SHAMPOO|DESODORANTE|CREMA DENTAL|AFEITADORA|PAPEL HIGIENICO', 'Higiene Personal'),
        (r'ATUN|SARDINA|CABALLA|CONSERVA', 'Conservas'),
        (r'CAFE|TE |MATE|YERBA|COCOA', 'Infusiones'),
        (r'WHISKY|RON|VODKA|GIN|FERNET|CAMPARI|APEROL', 'Bebidas Espirituosas'),
        (r'CHOCOLATE|CARAMELO|CHICLE|CHUPETE|GOMITA', 'Golosinas'),
    ]
    for patron, categoria in patrones:
        if re.search(patron, desc):
            return categoria
    return 'Otros'


# ============================================================
# 5. NORMALIZADOR IA (mejorado con feedback de confianza)
# ============================================================
def normalizador_ia(ruta_archivo: str, log_func=print) -> str | None:
    """
    Lee un archivo crudo (CSV/Excel), usa Gemini para mapear columnas
    al estándar BI y guarda el archivo limpio.
    Ahora incluye score de confianza por columna.
    """
    try:
        log_func(f"🤖 Iniciando Motor IA para: {Path(ruta_archivo).name}")

        if not GROQ_API_KEY:
            log_func("❌ Error: GROQ_API_KEY no configurada en .env")
            return None

        # Lectura inteligente del archivo
        if str(ruta_archivo).endswith('.csv'):
            for sep in [';', ',', '\t', '|']:
                try:
                    df = pd.read_csv(ruta_archivo, sep=sep, encoding='latin-1', on_bad_lines='skip')
                    if len(df.columns) > 1:
                        break
                except Exception:
                    continue
        else:
            df = pd.read_excel(ruta_archivo)

        columnas_sucias = list(df.columns)
        muestra_datos = df.head(3).to_dict(orient='records')

        log_func("🧠 Analizando estructura con Groq/Llama...")

        prompt = f"""Eres un experto analista de datos de retail argentino.
Tengo este archivo con columnas: {columnas_sucias}
Muestra de datos: {muestra_datos}

Mapeá las columnas a mi estándar BI:
SKU | DESCRIPCION | CANTIDAD | TOTAL_VENTA | PRECIO | FAMILIA | CANAL | FECHA | ES_OFERTA

Respondé ÚNICAMENTE con JSON. Formato:
{{"columna_original": {{"mapeo": "NOMBRE_ESTANDAR", "confianza": 0.95}}}}
Si no sirve: {{"columna_original": {{"mapeo": "OMITIR", "confianza": 1.0}}}}
Sin texto adicional."""

        texto = _groq_completar(prompt).replace("```json", "").replace("```", "").strip()
        mapeo_completo = json.loads(texto)

        # Extraer solo el mapeo y loguear la confianza
        mapeo_simple = {}
        for col_orig, info in mapeo_completo.items():
            if isinstance(info, dict):
                confianza = info.get('confianza', 1.0)
                destino = info.get('mapeo', 'OMITIR')
                if confianza < 0.7:
                    log_func(f"  ⚠️ '{col_orig}' → '{destino}' (confianza baja: {confianza:.0%})")
                else:
                    log_func(f"  ✓  '{col_orig}' → '{destino}' ({confianza:.0%})")
                mapeo_simple[col_orig] = destino
            else:
                mapeo_simple[col_orig] = str(info)

        df_renombrado = df.rename(columns=mapeo_simple)
        columnas_finales = [c for c in df_renombrado.columns if c != "OMITIR"]
        df_final = df_renombrado[columnas_finales]

        carpeta_salida = Path(ruta_archivo).parent
        nombre_base = Path(ruta_archivo).stem
        ruta_salida = str(carpeta_salida / f"INTELIGENTE_{nombre_base}.xlsx")
        df_final.to_excel(ruta_salida, index=False)

        log_func(f"💾 Archivo normalizado guardado: {ruta_salida}")
        return ruta_salida

    except Exception as e:
        log_func(f"❌ Error en Motor IA: {e}")
        return None


# ============================================================
# 6. ANALÍTICA DE CONTEO / AUDITORÍA
# ============================================================
def procesar_analitica_conteo(ruta_csv_sistema: str, ruta_excel_conteo: str, log_func=print) -> str | None:
    """Cruza inventario del sistema contra conteo físico y genera informe de auditoría."""
    try:
        log_func("⏳ Leyendo sistema (CSV)...")
        df_sis = pd.read_csv(ruta_csv_sistema, sep='\t', encoding='latin-1')
        df_sis = df_sis.iloc[:, [5, 6, 8]]
        df_sis.columns = ['sku', 'descripcion', 'cantidad_actual']
        df_sis['sku'] = df_sis['sku'].astype(str).str.strip()

        def clean_num(x):
            if pd.isna(x):
                return 0.0
            return float(str(x).replace('.', '').replace(',', '.'))

        df_sis['cantidad_actual'] = df_sis['cantidad_actual'].apply(clean_num)

        log_func("⏳ Leyendo Excel de conteo...")
        df_cnt = pd.read_excel(ruta_excel_conteo)
        df_cnt_clean = df_cnt.iloc[:, [0, -1]].copy()
        df_cnt_clean.columns = ['sku', 'cantidad_contada']
        df_cnt_clean['sku'] = df_cnt_clean['sku'].astype(str).str.strip()
        df_cnt_clean['cantidad_contada'] = df_cnt_clean['cantidad_contada'].apply(clean_num)

        log_func("🧠 Calculando auditoría...")
        df_audit = pd.merge(df_cnt_clean, df_sis, on='sku', how='left')
        df_audit['total_ajustar'] = df_audit['cantidad_contada'] - df_audit['cantidad_actual'].fillna(0)

        df_final = df_audit[['sku', 'descripcion', 'cantidad_actual', 'cantidad_contada', 'total_ajustar']]
        salida = "AUDITORIA_CONTEO_RESULTADO.xlsx"
        df_final.to_excel(salida, index=False, header=False)
        return salida

    except Exception as e:
        log_func(f"❌ Error: {e}")
        return None


# ============================================================
# 7. PUENTE SSH (ahora usa config.py)
# ============================================================
def disparar_descarga_ssh(log_func=print, proveedor=None) -> bool:
    """Dispara el robot SSH usando credenciales del .env."""
    try:
        log_func("📡 Llamando al Robot SSH...")
        from robot_ssh_report import ejecutar_descarga_reporte
        exito = ejecutar_descarga_reporte(proveedor)
        if exito:
            log_func("✅ Orden de descarga enviada satisfactoriamente.")
        else:
            log_func("❌ El Robot SSH falló. Revisá el archivo de logs.")
        return exito
    except Exception as e:
        log_func(f"🔥 Error al importar Robot SSH: {e}")
        return False


def procesar_conciliacion_imagen(ruta_img: str) -> str:
    return "Módulo de Imagen desactivado temporalmente."

# Alias de compatibilidad para robots que aún importen _get_gemini_model
def _get_gemini_model():
    """Alias de compatibilidad — ahora usa Groq internamente."""
    return None  # No se usa, _groq_completar reemplaza generate_content