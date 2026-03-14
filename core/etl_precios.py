"""
etl_precios.py — RPA Suite v5
================================
ETL de lista de precios desde CSV/TSV de PuTTY a Excel limpio.

Mejoras v5 sobre el original:
  - Detección automática del separador (tab, punto y coma, pipe)
  - Detección automática de columnas con fallback a Gemini IA
  - Soporte para múltiples formatos de precio argentino:
      1.250,50  →  1250.50
      1250.50   →  1250.50  (ya correcto)
      1250,50   →  1250.50
  - Columnas opcionales: Costo, P_Mayorista, Oferta, Familia
  - Reporte de calidad: filas descartadas, SKUs duplicados, precios en cero
  - Excel de salida con formato profesional (color por precio cero / oferta)
  - Archivado automático en /procesados/ETL_PRECIOS/ al terminar
  - Mantiene 100% compatibilidad con el comportamiento original
"""
import sys
from pathlib import Path as _Path
_RAIZ = _Path(__file__).parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import pandas as pd
import os
import re
from pathlib import Path
from datetime import datetime


# ============================================================
# LIMPIADORES
# ============================================================

def _limpiar_precio(val) -> float:
    """
    Convierte cualquier formato de precio argentino a float.
      '1.250,50'  → 1250.50
      '1250.50'   → 1250.50
      '1250,50'   → 1250.50
      '$1.250,50' → 1250.50
      ''  / nan   → 0.0
    """
    if pd.isna(val):
        return 0.0
    val = str(val).strip().replace('$', '').replace(' ', '')
    if not val or val.lower() == 'nan':
        return 0.0

    # Caso: tiene coma Y punto → punto = miles, coma = decimal  → '1.250,50'
    if ',' in val and '.' in val:
        val = val.replace('.', '').replace(',', '.')
    # Caso: solo coma → coma = decimal  → '1250,50'
    elif ',' in val and '.' not in val:
        val = val.replace(',', '.')
    # Caso: solo punto → puede ser decimal o miles
    # Si hay exactamente 3 dígitos después del punto → miles  → '1.250'
    # Si hay 1 o 2 dígitos → decimal  → '12.5'
    elif '.' in val and ',' not in val:
        partes = val.split('.')
        if len(partes) == 2 and len(partes[1]) == 3:
            val = val.replace('.', '')  # miles sin decimal
        # else: ya es decimal correcto

    try:
        return float(val)
    except ValueError:
        return 0.0


def _limpiar_sku(val) -> int | None:
    """Convierte SKU a entero limpio. Retorna None si no es válido."""
    if pd.isna(val):
        return None
    try:
        s = str(val).strip().lstrip('0')
        if not s:
            return None
        return int(float(s))
    except (ValueError, OverflowError):
        return None


# ============================================================
# DETECTOR DE COLUMNAS
# ============================================================

_ALIAS_SKU         = ['articulo', 'sku', 'codigo', 'cod', 'art', 'id']
_ALIAS_DESC        = ['descripcion', 'descripción', 'desc', 'nombre', 'detalle', 'producto']
_ALIAS_PRECIO      = ['precio', 'price', 'p_salon', 'salon', 'venta', 'p_venta', 'pventa']
_ALIAS_COSTO       = ['costo', 'cost', 'p_costo', 'pcosto']
_ALIAS_MAYORISTA   = ['mayorista', 'p_mayorista', 'pmayorista', 'mayor']
_ALIAS_OFERTA      = ['oferta', 'promo', 'promocion', 'descuento']
_ALIAS_FAMILIA     = ['familia', 'rubro', 'categoria', 'departamento', 'seccion', 'desfam']


def _detectar_columna(columnas: list[str], aliases: list[str]) -> str | None:
    """Busca la primera columna que coincida con algún alias (case-insensitive)."""
    cols_lower = {c.lower().strip(): c for c in columnas}
    for alias in aliases:
        if alias in cols_lower:
            return cols_lower[alias]
    return None


def _detectar_columnas_con_ia(df: pd.DataFrame, log_func) -> dict:
    """
    Usa Gemini para detectar columnas cuando la detección por alias falla.
    Retorna dict con las columnas detectadas.
    """
    try:
        from config import GROQ_API_KEY
        import requests as _req
        import json
        if not GROQ_API_KEY:
            return {}

        muestra = df.head(3).to_dict(orient='records')
        prompt = f"""Analizá estas columnas de un CSV de lista de precios de retail argentino:
Columnas: {list(df.columns)}
Muestra: {muestra}

Identificá qué columna corresponde a cada campo. Respondé SOLO con JSON:
{{"sku": "nombre_columna_o_null",
  "descripcion": "nombre_columna_o_null",
  "precio": "nombre_columna_o_null",
  "costo": "nombre_columna_o_null",
  "mayorista": "nombre_columna_o_null",
  "oferta": "nombre_columna_o_null",
  "familia": "nombre_columna_o_null"}}
Si no existe esa columna, poné null. Sin texto extra."""

        r = _req.post('https://api.groq.com/openai/v1/chat/completions',
            headers={'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'},
            json={'model':'llama-3.3-70b-versatile','messages':[{'role':'user','content':prompt}],'max_tokens':800,'temperature':0.2},
            timeout=30)
        r.raise_for_status()
        texto = r.json()['choices'][0]['message']['content'].strip().replace('```json', '').replace('```', '').strip()
        return json.loads(texto)
    except Exception as e:
        log_func(f"  ⚠ Detección IA no disponible: {e}")
        return {}


# ============================================================
# ETL PRINCIPAL
# ============================================================

def procesar_lista_precios_mbf(ruta_archivo: str, log_func=print) -> str | None:
    """
    ETL de lista de precios desde CSV/TSV de PuTTY.

    Genera un Excel limpio con:
      - SKU (entero)
      - DESCRIPCION
      - PRECIO (formato moneda)
      - COSTO, P_MAYORISTA, OFERTA, FAMILIA  (si existen en el origen)

    Retorna la ruta del Excel generado, o None si falló.
    """
    try:
        nombre_archivo = os.path.basename(ruta_archivo)
        log_func(f"⏳ Iniciando ETL de Precios: {nombre_archivo}")

        # ── 1. LECTURA CON DETECCIÓN DE SEPARADOR ────────────────
        df = None
        for sep in ['\t', ';', '|', ',']:
            try:
                df_test = pd.read_csv(ruta_archivo, sep=sep,
                                      encoding='latin-1', dtype=str)
                if len(df_test.columns) >= 2:
                    df = df_test
                    log_func(f"  → Separador detectado: {repr(sep)} | "
                             f"{len(df.columns)} columnas | {len(df)} filas")
                    break
            except Exception:
                continue

        if df is None:
            log_func("❌ No se pudo leer el archivo con ningún separador conocido.")
            return None

        df.columns = df.columns.str.strip()
        filas_originales = len(df)

        # ── 2. DETECCIÓN DE COLUMNAS ─────────────────────────────
        cols = list(df.columns)
        log_func(f"  → Columnas encontradas: {cols}")

        col_sku   = _detectar_columna(cols, _ALIAS_SKU)
        col_desc  = _detectar_columna(cols, _ALIAS_DESC)
        col_precio = _detectar_columna(cols, _ALIAS_PRECIO)

        # Si faltan columnas clave, intentamos con IA
        if not all([col_sku, col_desc, col_precio]):
            log_func("  🤖 Columnas clave no detectadas, consultando Gemini IA...")
            mapa_ia = _detectar_columnas_con_ia(df, log_func)
            if mapa_ia:
                col_sku    = col_sku    or mapa_ia.get('sku')
                col_desc   = col_desc   or mapa_ia.get('descripcion')
                col_precio = col_precio or mapa_ia.get('precio')

        # Validación de columnas mínimas
        faltantes = []
        if not col_sku:    faltantes.append('SKU/Articulo')
        if not col_desc:   faltantes.append('Descripcion')
        if not col_precio: faltantes.append('Precio')

        if faltantes:
            log_func(f"❌ Columnas requeridas no encontradas: {faltantes}")
            log_func(f"   Columnas disponibles: {cols}")
            return None

        log_func(f"  ✓ SKU={col_sku} | Desc={col_desc} | Precio={col_precio}")

        # Columnas opcionales
        col_costo     = _detectar_columna(cols, _ALIAS_COSTO)
        col_mayorista = _detectar_columna(cols, _ALIAS_MAYORISTA)
        col_oferta    = _detectar_columna(cols, _ALIAS_OFERTA)
        col_familia   = _detectar_columna(cols, _ALIAS_FAMILIA)

        extras = [c for c in [col_costo, col_mayorista, col_oferta, col_familia] if c]
        if extras:
            log_func(f"  ✓ Columnas adicionales detectadas: {extras}")

        # ── 3. LIMPIEZA ───────────────────────────────────────────
        df = df.dropna(subset=[col_sku, col_precio])

        df['SKU']   = df[col_sku].apply(_limpiar_sku)
        df['PRECIO'] = df[col_precio].apply(_limpiar_precio)

        # Columnas opcionales
        if col_costo:
            df['COSTO'] = df[col_costo].apply(_limpiar_precio)
        if col_mayorista:
            df['P_MAYORISTA'] = df[col_mayorista].apply(_limpiar_precio)
        if col_oferta:
            df['OFERTA'] = df[col_oferta].apply(_limpiar_precio)
        if col_familia:
            df['FAMILIA'] = df[col_familia].astype(str).str.strip()

        df['DESCRIPCION'] = df[col_desc].astype(str).str.strip()

        # Descartar filas con SKU inválido
        df = df.dropna(subset=['SKU'])
        df['SKU'] = df['SKU'].astype(int)

        filas_descartadas = filas_originales - len(df)

        # ── 4. REPORTE DE CALIDAD ─────────────────────────────────
        duplicados = df['SKU'].duplicated().sum()
        precio_cero = (df['PRECIO'] == 0).sum()

        log_func(f"  📊 Reporte de calidad:")
        log_func(f"     Filas originales : {filas_originales:,}")
        log_func(f"     Filas válidas    : {len(df):,}")
        log_func(f"     Filas descartadas: {filas_descartadas:,}")
        log_func(f"     SKUs duplicados  : {duplicados:,}"
                 + (" ⚠" if duplicados > 0 else " ✓"))
        log_func(f"     Precios en $0    : {precio_cero:,}"
                 + (" ⚠" if precio_cero > 0 else " ✓"))

        # ── 5. ARMAR DATAFRAME FINAL ──────────────────────────────
        columnas_salida = ['SKU', 'DESCRIPCION', 'PRECIO']
        if col_costo:      columnas_salida.append('COSTO')
        if col_mayorista:  columnas_salida.append('P_MAYORISTA')
        if col_oferta:     columnas_salida.append('OFERTA')
        if col_familia:    columnas_salida.append('FAMILIA')

        df_final = df[columnas_salida].copy()
        df_final = df_final.sort_values('SKU').reset_index(drop=True)

        # ── 6. GUARDAR EXCEL CON FORMATO ─────────────────────────
        carpeta = os.path.dirname(ruta_archivo)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        nombre_base = Path(ruta_archivo).stem
        nombre_salida = f"PRECIOS_LIMPIOS_{nombre_base}_{timestamp}.xlsx"
        ruta_salida = os.path.join(carpeta, nombre_salida)

        with pd.ExcelWriter(ruta_salida, engine='xlsxwriter') as writer:
            df_final.to_excel(writer, index=False, sheet_name='Precios')

            wb  = writer.book
            ws  = writer.sheets['Precios']

            # ── Formatos ──
            fmt_header = wb.add_format({
                'bold': True, 'bg_color': '#1E3A5F', 'font_color': 'white',
                'border': 1, 'align': 'center', 'valign': 'vcenter',
            })
            fmt_sku = wb.add_format({
                'num_format': '0', 'align': 'center',
            })
            fmt_desc = wb.add_format({'align': 'left'})
            fmt_money = wb.add_format({
                'num_format': '$ #,##0.00', 'align': 'right',
            })
            fmt_money_cero = wb.add_format({
                'num_format': '$ #,##0.00', 'align': 'right',
                'bg_color': '#FFF0F0', 'font_color': '#CC0000',
            })
            fmt_oferta = wb.add_format({
                'num_format': '$ #,##0.00', 'align': 'right',
                'bg_color': '#F0FFF0', 'font_color': '#006600',
            })

            # ── Encabezados con color ──
            for col_idx, col_nombre in enumerate(df_final.columns):
                ws.write(0, col_idx, col_nombre, fmt_header)

            # ── Anchos de columna ──
            ws.set_column('A:A', 12, fmt_sku)    # SKU
            ws.set_column('B:B', 52, fmt_desc)   # DESCRIPCION
            ws.set_column('C:C', 16, fmt_money)  # PRECIO

            # Columnas opcionales dinámicas
            col_letra_idx = 3  # D en adelante
            for col_extra in ['COSTO', 'P_MAYORISTA', 'OFERTA', 'FAMILIA']:
                if col_extra in df_final.columns:
                    letra = chr(ord('D') + (col_letra_idx - 3))
                    if col_extra == 'FAMILIA':
                        ws.set_column(f'{letra}:{letra}', 25)
                    else:
                        ws.set_column(f'{letra}:{letra}', 16, fmt_money)
                    col_letra_idx += 1

            # ── Colorear filas con precio $0 (fila a fila) ──
            for row_idx, row in df_final.iterrows():
                excel_row = row_idx + 1  # +1 por encabezado
                if row['PRECIO'] == 0:
                    ws.write(excel_row, 2, row['PRECIO'], fmt_money_cero)
                if col_oferta and 'OFERTA' in df_final.columns:
                    oferta_col_idx = list(df_final.columns).index('OFERTA')
                    if row.get('OFERTA', 0) > 0:
                        ws.write(excel_row, oferta_col_idx,
                                 row['OFERTA'], fmt_oferta)

            # ── Freeze encabezado y filtros ──
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, len(df_final), len(df_final.columns) - 1)

            # ── Hoja de resumen de calidad ──
            ws_qc = wb.add_worksheet('Calidad')
            fmt_titulo = wb.add_format({'bold': True, 'font_size': 13,
                                         'bg_color': '#1E3A5F', 'font_color': 'white'})
            fmt_ok  = wb.add_format({'bg_color': '#F0FFF0', 'font_color': '#166534'})
            fmt_warn = wb.add_format({'bg_color': '#FFF7ED', 'font_color': '#9A3412'})

            ws_qc.write(0, 0, 'REPORTE DE CALIDAD — ETL PRECIOS', fmt_titulo)
            ws_qc.write(0, 1, '', fmt_titulo)
            ws_qc.set_column('A:A', 30)
            ws_qc.set_column('B:B', 15)

            calidad = [
                ('Archivo origen',      nombre_archivo,     None),
                ('Fecha procesado',     datetime.now().strftime('%d/%m/%Y %H:%M'), None),
                ('Filas originales',    filas_originales,   None),
                ('Filas válidas',       len(df_final),      None),
                ('Filas descartadas',   filas_descartadas,  filas_descartadas > 0),
                ('SKUs duplicados',     duplicados,         duplicados > 0),
                ('Precios en $0',       precio_cero,        precio_cero > 0),
                ('Columnas detectadas', ', '.join(columnas_salida), None),
            ]

            for i, (label, valor, es_warn) in enumerate(calidad, start=2):
                ws_qc.write(i, 0, label)
                fmt_val = fmt_warn if es_warn else (fmt_ok if es_warn is False else None)
                ws_qc.write(i, 1, valor, fmt_val)

        log_func(f"✅ Excel generado: {nombre_salida}")
        log_func(f"   → {len(df_final):,} artículos | "
                 f"{len(columnas_salida)} columnas | "
                 f"{'⚠ Revisá hoja Calidad' if duplicados > 0 or precio_cero > 0 else '✓ Sin observaciones'}")

        # ── 7. ARCHIVAR EN /procesados/ ──────────────────────────
        try:
            from file_manager import archivar_procesado
            archivar_procesado(
                ruta_archivo=ruta_archivo,
                robot_nombre="ETL_PRECIOS",
                filas_procesadas=len(df_final),
                filas_error=filas_descartadas,
                dry_run=False,
                log_func=log_func,
            )
        except Exception as e:
            log_func(f"  ⚠ Archivado omitido: {e}")

        return ruta_salida

    except Exception as e:
        import traceback
        log_func(f"❌ Error en ETL de Precios: {e}")
        log_func(traceback.format_exc())
        return None