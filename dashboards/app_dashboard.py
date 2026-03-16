"""
app_dashboard.py — RPA Suite v5.2
Mejoras v5.2:
  - Exportar a Excel (6 hojas: Resumen Ejecutivo, Datos Procesados, ABC, Familias, Ofertas, Artículos A)
  - Exportar a PDF (KPIs, análisis IA, tabla ofertas con efectividad, top artículos A)
  - Botones de exportar: panel global arriba + dentro de cada pestaña
"""

import sys
from pathlib import Path as _Path
# Asegurar raíz en sys.path (lanzado desde dashboards/)
_RAIZ = _Path(__file__).parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import re
import json
import os
import datetime

# Módulo de exportación
try:
    from exportar import generar_excel, generar_pdf
    EXPORTAR_OK = True
except ImportError as _e:
    EXPORTAR_OK = False
    _EXPORTAR_ERR = str(_e)

# API Key de Gemini — se lee del .env via config.py
try:
    from config import GEMINI_API_KEY as _GEMINI_KEY_ENV
    _GROQ_KEY_ENV = __import__("os").getenv("GROQ_API_KEY", "")
except ImportError:
    _GEMINI_KEY_ENV = os.getenv("GEMINI_API_KEY", "")

# ============================================================
# CONFIGURACIÓN
# ============================================================
st.set_page_config(
    page_title="Retail Engine BI",
    layout="wide",
    page_icon="📊",
    initial_sidebar_state="expanded",
)

_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {
    --bg-main:#F0F2F5; --bg-card:#FFFFFF; --text-dark:#1A1D23;
    --text-mid:#5A6070; --text-light:#9AA0AD; --accent:#1E5FD4;
    --accent-2:#00C2A8; --danger:#E84855; --warning:#F4A228;
    --success:#16A34A; --border:#E2E6EE;
    --shadow:0 2px 12px rgba(0,0,0,0.07);
    --font:'Sora',sans-serif; --font-mono:'JetBrains Mono',monospace;
}
.stApp { background-color:var(--bg-main); font-family:var(--font); }
.main .block-container { padding:1.5rem 2.5rem 3rem; max-width:1600px; }
[data-testid="stSidebar"] {
    background:linear-gradient(180deg,#0F1923 0%,#1A2535 100%);
    border-right:1px solid rgba(255,255,255,0.06);
}
[data-testid="stSidebar"] * { color:#CBD5E1 !important; }
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3 { color:#F0F4FF !important; }
div[data-testid="stMetric"] {
    background:var(--bg-card); border-radius:12px; padding:1.2rem 1.4rem;
    border:1px solid var(--border); box-shadow:var(--shadow);
    position:relative; overflow:hidden;
}
div[data-testid="stMetric"]::before {
    content:''; position:absolute; top:0; left:0; right:0; height:3px;
    background:linear-gradient(90deg,var(--accent),var(--accent-2));
}
[data-testid="stMetricValue"] { font-size:2rem !important; font-weight:700 !important; color:var(--text-dark) !important; }
[data-testid="stMetricLabel"] { font-size:0.72rem !important; font-weight:600 !important; color:var(--text-light) !important; text-transform:uppercase !important; letter-spacing:0.08em !important; }
.alert-critico { background:#FFF0F0; border-left:4px solid #E84855; border-radius:8px; padding:0.8rem 1rem; margin:0.3rem 0; font-size:0.88rem; }
.alert-warning  { background:#FFFBEA; border-left:4px solid #F4A228; border-radius:8px; padding:0.8rem 1rem; margin:0.3rem 0; font-size:0.88rem; }
.alert-inmo     { background:#EFF6FF; border-left:4px solid #3B82F6; border-radius:8px; padding:0.8rem 1rem; margin:0.3rem 0; font-size:0.88rem; }
.alert-success  { background:#F0FDF4; border-left:4px solid #16A34A; border-radius:8px; padding:0.8rem 1rem; margin:0.3rem 0; font-size:0.88rem; }
.section-header { display:flex; align-items:center; gap:0.6rem; margin:1.8rem 0 0.8rem; padding-bottom:0.5rem; border-bottom:2px solid var(--border); }
.section-header h3 { font-size:1rem; font-weight:700; color:var(--text-dark); margin:0; }
.stTabs [data-baseweb="tab-list"] { gap:8px; }
.stTabs [data-baseweb="tab"] { border-radius:6px; padding:0.5rem 1rem; font-size:0.82rem; font-weight:600; }
/* Bloque IA */
.ia-box {
    background: linear-gradient(135deg, #0F1923 0%, #1E3A5F 100%);
    border-radius: 14px; padding: 1.4rem 1.8rem; margin: 0.5rem 0 1.5rem;
    border: 1px solid rgba(30,95,212,0.3); position: relative;
}
.ia-box::before {
    content: '🤖 Análisis IA — Groq/Llama'; position: absolute; top: -10px; left: 20px;
    background: #1E5FD4; color: white; font-size: 0.68rem; font-weight: 700;
    padding: 2px 10px; border-radius: 20px; text-transform: uppercase; letter-spacing: 0.08em;
}
.ia-box p { color: #CBD5E1; font-size: 0.91rem; line-height: 1.7; margin: 0.4rem 0; }
.ia-box strong { color: #93C5FD; }
.ia-box .ia-accion { 
    background: rgba(30,95,212,0.2); border-left: 3px solid #1E5FD4;
    border-radius: 0 8px 8px 0; padding: 0.6rem 1rem; margin-top: 0.8rem;
    color: #BAE6FD; font-size: 0.85rem;
}
/* KPI tooltip */
.kpi-help { font-size:0.68rem; color:#9AA0AD; margin-top:0.2rem; }
/* Oferta badge */
.badge-oferta { display:inline-block; background:#FEF3C7; color:#92400E; border-radius:4px; padding:2px 8px; font-size:0.72rem; font-weight:700; }
.badge-exitosa { background:#D1FAE5; color:#065F46; }
.badge-ineficaz { background:#FEE2E2; color:#991B1B; }
/* Ranking posición */
.rank-num { font-size:1.4rem; font-weight:800; color:#1E5FD4; min-width:2rem; }
</style>
"""
try:
    st.html(_CSS)
except AttributeError:
    st.markdown(_CSS, unsafe_allow_html=True)


# ============================================================
# GROQ IA — Análisis narrativo por pestaña
# ============================================================
def _groq_analizar(prompt: str, api_key: str) -> str:
    """Llama a Groq (llama-3.3-70b) via requests. Falla silenciosamente."""
    try:
        import requests as _req
        resp = _req.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
                "temperature": 0.4,
            },
            timeout=20,
            verify=True,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"_(IA no disponible: {e})_"


def analisis_ia(titulo: str, datos_resumen: dict, api_key: str, contexto: str = "") -> None:
    """Muestra el bloque de análisis IA de una pestaña."""
    if not api_key:
        st.markdown(f"""
        <div class="ia-box">
            <p>⚙️ <strong>Configurá tu API Key de Groq</strong> en el sidebar para activar el análisis narrativo automático.</p>
            <p>Cuando esté activo, este panel explicará en lenguaje de negocio qué significan los números, qué riesgos hay y qué acciones tomar.</p>
        </div>""", unsafe_allow_html=True)
        return

    def _fmt_dato(v):
        """Formatea valores numéricos grandes a pesos argentinos legibles."""
        if isinstance(v, dict):
            return {k: _fmt_dato(val) for k, val in v.items()}
        if isinstance(v, (int, float)) and abs(v) >= 1000:
            # Formato argentino: punto como separador de miles, sin decimales
            entero = int(round(v))
            s = f"{abs(entero):,}".replace(",", ".")
            return f"{'−' if entero < 0 else ''}$ {s}"
        return v

    datos_fmt = {k: _fmt_dato(v) for k, v in datos_resumen.items()}

    cache_key = f"ia_{titulo}_{hash(str(sorted(datos_resumen.items())))}"
    if cache_key not in st.session_state:
        with st.spinner(f"🤖 Groq analizando {titulo}..."):
            prompt = f"""
Sos un analista de retail experto. Analizá estos datos de negocio y escribí un párrafo ejecutivo
conciso (máximo 5 oraciones) en español, usando lenguaje directo de negocio, sin tecnicismos.
Seguí esta estructura: 1) Situación actual (qué pasó), 2) Riesgo o complicación principal,
3) Acción recomendada concreta.

Sección analizada: {titulo}
{contexto}

Contexto del negocio: supermercado minorista en Argentina, todos los montos son en PESOS ARGENTINOS (ARS).
NUNCA menciones dólares ni uses el símbolo USD. Usá siempre "pesos" o "$" para referirte a la moneda.

Datos:
{json.dumps(datos_fmt, ensure_ascii=False, indent=2)}

Importante: Usá los montos exactamente como están escritos, con sus separadores de miles.
No uses asteriscos ni markdown. Escribí en prosa fluida.
"""
            st.session_state[cache_key] = _groq_analizar(prompt, api_key)

    texto = st.session_state[cache_key]
    # Dividir en párrafos para formatear
    parrafos = [p.strip() for p in texto.split('\n') if p.strip()]
    html_parrafos = ''.join(f'<p>{p}</p>' for p in parrafos)

    st.markdown(f'<div class="ia-box">{html_parrafos}</div>', unsafe_allow_html=True)


# ============================================================
# HELPERS
# ============================================================
def fmt_millones(v):
    v = float(v)
    if abs(v) >= 1_000_000: return f"${v/1_000_000:.1f}M"
    if abs(v) >= 1_000:     return f"${v/1_000:.1f}K"
    return f"${v:,.0f}"

def fmt_num(v):
    v = float(v)
    if abs(v) >= 1_000_000: return f"{v/1_000_000:.1f}M"
    if abs(v) >= 1_000:     return f"{v/1_000:.1f}K"
    return f"{v:,.0f}"

def delta_pct(actual, anterior):
    if not anterior or anterior == 0: return None
    return f"{((actual-anterior)/anterior)*100:+.1f}%"

def pct_bar(valor, maximo, color="#1E5FD4"):
    """Mini barra de progreso HTML."""
    pct = min(100, valor/maximo*100) if maximo else 0
    return f'<div style="background:#F0F2F5;border-radius:4px;height:6px;"><div style="background:{color};width:{pct:.0f}%;height:6px;border-radius:4px;"></div></div>'

COLORES_PLOTLY = ['#1E5FD4','#00C2A8','#F4A228','#E84855','#8B5CF6','#06B6D4','#EC4899','#84CC16']

TOOLTIPS = {
    "Venta Total": "Suma de todos los importes facturados en el período, sin devoluciones.",
    "Unidades": "Unidades vendidas calculadas como Venta_$ / Precio unitario.",
    "Bultos": "Unidades agrupadas según la unidad de carga (UxB) de cada artículo.",
    "SKUs Activos": "Cantidad de códigos de artículo distintos con al menos una venta.",
    "% en Oferta": "Porcentaje de la venta total correspondiente a artículos con precio de oferta activo.",
    "Precio Promedio": "Ticket promedio por unidad = Venta Total / Unidades totales.",
}


# ============================================================
# NLP LOCAL — Categorizador de artículos
# ============================================================
def _nlp_local(desc):
    desc = str(desc).upper()
    patrones = [
        (r'GALLETI|OBLITA|TRAVIATA|CRIOLLITA|SURTIDO|CHOCOLINA', 'Galletitas'),
        (r'FIDEO|TALLARIN|SPAGHETTI|TIRABUZON|MATARAZZO|LUCCHETTI', 'Fideos y Pastas'),
        (r'GASEOSA|COCA[ -]?COLA|SPRITE|FANTA|PEPSI|7UP|CUNNINGTON', 'Gaseosas'),
        (r'CERVEZA|BRAHMA|QUILMES|STELLA|HEINEKEN|ANDES|CORONA', 'Cervezas'),
        (r'VINO|MALBEC|CABERNET|TINTO|BLANCO|CHARDONNAY|BODEGA', 'Vinos'),
        (r'PAPA|CHIZITO|MANI|SNACK|DORITOS|CHEETOS|LAY|PRINGLES', 'Snacks'),
        (r'AGUA |AGUA$|VILLAVICENCIO|SER |CEPITA|JUGO|BAGGIO|TANG', 'Aguas y Jugos'),
        (r'ARROZ|LENTEJA|GARBANZO|POROTO|HARINA', 'Arroz y Legumbres'),
        (r'ACEITE|GIRASOL|OLIVA', 'Aceites'),
        (r'LECHE|YOGUR|QUESO|MANTECA|CREMA|DANONE|SANCOR', 'Lácteos'),
        (r'JABON|DETERGENTE|LAVANDINA|SUAVIZANTE|SKIP|ARIEL', 'Limpieza'),
        (r'WHISKY|RON|VODKA|GIN|FERNET|CAMPARI|APEROL', 'Bebidas Espirituosas'),
        (r'CHOCOLATE|CARAMELO|CHICLE|GOMITA', 'Golosinas'),
        (r'CAFE|TE |MATE|YERBA|COCOA', 'Infusiones'),
        (r'ATUN|SARDINA|CABALLA|CONSERVA', 'Conservas'),
    ]
    for pat, cat in patrones:
        if re.search(pat, desc): return cat
    return 'Otras Categorías'


# ============================================================
# ETL — Detección flexible de columnas y separadores
# ============================================================
def procesar_archivos(f_ventas, f_precios, f_valor):

    def _leer(f):
        for sep in ['|', '\t', ';', ',']:
            try:
                f.seek(0)
                df = pd.read_csv(f, sep=sep, encoding='latin-1', on_bad_lines='skip')
                if len(df.columns) >= 2:
                    df.columns = df.columns.str.strip()
                    return df
            except Exception:
                continue
        return None

    def _col(df, cands):
        m = {c.lower().strip(): c for c in df.columns}
        for c in cands:
            if c.lower() in m: return m[c.lower()]
        return None

    def _num(s):
        return pd.to_numeric(
            s.astype(str).str.strip()
             .str.replace(',', '', regex=False),
            errors='coerce'
        )

    try:
        # A. VENTAS
        df_vta = _leer(f_ventas)
        if df_vta is None:
            st.error("No se pudo leer el CSV de Ventas.")
            return None
        col_sku_v = _col(df_vta, ['CODIGO','SKU','Articulo','COD','CODART','codigo','articulo'])
        col_desc  = _col(df_vta, ['DESCRIPCION','Descripcion','DESC','NOMBRE','descripcion'])
        col_venta = _col(df_vta, ['venta','VENTA','Venta','TOTAL','Total','IMPORTE','importe'])
        if not col_sku_v or not col_venta:
            st.error(f"CSV Ventas: columnas no encontradas. Disponibles: {list(df_vta.columns)}")
            return None
        df_vta['SKU']         = df_vta[col_sku_v].astype(str).str.strip().str.lstrip('0')
        df_vta['Venta_$']     = _num(df_vta[col_venta])
        df_vta['DESCRIPCION'] = df_vta[col_desc].astype(str).str.strip() if col_desc else 'Sin descripción'
        df_vta = df_vta.dropna(subset=['Venta_$'])

        # B. PRECIOS
        df_pre = _leer(f_precios)
        if df_pre is None:
            st.error("No se pudo leer el CSV de Precios.")
            return None
        col_sku_p  = _col(df_pre, ['Articulo','CODIGO','SKU','COD','CODART','articulo'])
        col_precio = _col(df_pre, ['Precio','PRECIO','P_SALON','PVP','precio'])
        col_oferta = _col(df_pre, ['Oferta','OFERTA','P_OFERTA','oferta'])
        col_fam    = _col(df_pre, ['DesFam','Familia','FAMILIA','RUBRO','Rubro','desfam','familia'])
        if not col_sku_p:
            st.error(f"CSV Precios: columna SKU no encontrada. Disponibles: {list(df_pre.columns)}")
            return None
        df_pre['SKU']         = df_pre[col_sku_p].astype(str).str.strip().str.lstrip('0')
        df_pre['Precio_Unit'] = _num(df_pre[col_precio]) if col_precio else 0
        df_pre['Oferta_Num']  = _num(df_pre[col_oferta]).fillna(0) if col_oferta else 0
        df_pre['Es_Oferta']   = df_pre['Oferta_Num'] > 0
        df_pre['DesFam']      = df_pre[col_fam].astype(str).str.strip() if col_fam else 'Sin Categorizar'
        df_pre['Desc_Pct']    = np.where(
            (df_pre['Precio_Unit'] > 0) & (df_pre['Oferta_Num'] > 0),
            (1 - df_pre['Oferta_Num'] / df_pre['Precio_Unit']) * 100, 0
        )

        # C. UXB
        df_val = _leer(f_valor)
        if df_val is None:
            st.error("No se pudo leer el CSV de UxB.")
            return None
        col_sku_u = _col(df_val, ['Codart','CODIGO','SKU','COD','CODART','Articulo','codart'])
        col_uxb   = _col(df_val, ['Uxb','UXB','UxB','uxb'])
        if not col_sku_u:
            st.error(f"CSV UxB: columna SKU no encontrada. Disponibles: {list(df_val.columns)}")
            return None
        df_val['SKU'] = df_val[col_sku_u].astype(str).str.strip().str.lstrip('0')
        df_val['UxB'] = pd.to_numeric(df_val[col_uxb], errors='coerce').fillna(1) if col_uxb else 1

        # D. MERGE
        df_m = pd.merge(df_vta[['SKU','DESCRIPCION','Venta_$']],
                        df_pre[['SKU','DesFam','Precio_Unit','Oferta_Num','Es_Oferta','Desc_Pct']],
                        on='SKU', how='left')
        df_m = pd.merge(df_m, df_val[['SKU','UxB']], on='SKU', how='left')

        # E. CÁLCULOS
        df_m['Precio_Unit']    = df_m['Precio_Unit'].replace(0, np.nan)
        df_m['Unidades_Calc']  = (df_m['Venta_$'] / df_m['Precio_Unit']).fillna(0).round(0)
        df_m['UxB']            = df_m['UxB'].replace(0,1).fillna(1)
        df_m['Bultos_Calc']    = (df_m['Unidades_Calc'] / df_m['UxB']).round(2)
        df_m['DesFam']         = df_m['DesFam'].fillna('Sin Categorizar').str.strip()
        df_m['DESCRIPCION']    = df_m['DESCRIPCION'].str.strip()
        df_m['Categoria_IA']   = df_m['DESCRIPCION'].apply(_nlp_local)
        df_m['Es_Oferta']      = df_m['Es_Oferta'].fillna(False)
        df_m['Oferta_Num']     = df_m['Oferta_Num'].fillna(0)
        df_m['Desc_Pct']       = df_m['Desc_Pct'].fillna(0)
        df_m = df_m[(df_m['Venta_$'] > 0) & (df_m['SKU'] != '9999')]

        # F. ABC
        df_m = df_m.sort_values('Venta_$', ascending=False)
        df_m['Venta_Acum'] = df_m['Venta_$'].cumsum()
        tv = df_m['Venta_$'].sum()
        df_m['Pct_Acum'] = df_m['Venta_Acum'] / tv
        conds = [df_m['Pct_Acum'] <= 0.80, df_m['Pct_Acum'] <= 0.95, df_m['Pct_Acum'] > 0.95]
        df_m['Categoria_ABC'] = np.select(conds,
            ['A (80% Caja)','B (15% Caja)','C (5% Cola)'], default='C (5% Cola)')

        # G. RANKING por familia (para filtros dinámicos)
        fam_rank = df_m.groupby('DesFam')['Venta_$'].sum().rank(ascending=False).astype(int)
        df_m['Rank_Familia'] = df_m['DesFam'].map(fam_rank)

        return df_m

    except Exception as e:
        import traceback
        st.error(f"Error en ETL: {e}")
        st.code(traceback.format_exc())
        return None


def procesar_clientes(f_clientes):
    try:
        for sep in ['|', '\t', ';', ',']:
            try:
                f_clientes.seek(0)
                df = pd.read_csv(f_clientes, sep=sep, encoding='latin-1', on_bad_lines='skip')
                if len(df.columns) >= 2:
                    df.columns = df.columns.str.strip()
                    break
            except Exception:
                continue
        col_tot  = next((c for c in df.columns if c.lower() in ['total','venta','importe']), None)
        col_desc = next((c for c in df.columns if c.lower() in ['descripcion','nombre','cliente']), None)
        if not col_tot: return None
        venta_str = df[col_tot].astype(str).str.strip().str.replace(',', '', regex=False)
        df['Venta_$'] = pd.to_numeric(venta_str, errors='coerce')
        df = df.dropna(subset=['Venta_$'])
        if col_desc:
            df['DESCRIPCION'] = df[col_desc].astype(str).str.strip()
            # Eliminar filas sin nombre de cliente (vacío, nan, guiones, etc.)
            df = df[~df['DESCRIPCION'].isin(['', 'nan', 'NaN', 'None', '-', '--', 'N/A', 'n/a'])]
            df = df[df['DESCRIPCION'].str.len() > 0]
            for ex in ['Consumidor final','CLIENTES VARIOS','EMPLEAD']:
                df = df[~df['DESCRIPCION'].str.contains(ex, case=False, na=False)]
        return df[df['Venta_$'] > 0]
    except Exception as e:
        st.error(f"Error clientes: {e}")
        return None


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("""
    <div style="padding:1.2rem 0 0.5rem; text-align:center;">
        <div style="font-size:2rem;">📊</div>
        <div style="font-size:1.1rem; font-weight:800; color:#F0F4FF;">Retail Engine BI</div>
        <div style="font-size:0.7rem; color:#64748B; text-transform:uppercase; letter-spacing:0.1em;">Suite v5.1 · Andrés Díaz</div>
    </div>
    <hr style="border-color:rgba(255,255,255,0.08); margin:0.5rem 0 1rem;">
    """, unsafe_allow_html=True)

    st.markdown("**🏢 Contexto Operativo**")
    sucursal = st.selectbox("Sucursal", ["Crovara", "Galpón", "Ambas"])

    st.markdown("<hr style='border-color:rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
    st.markdown("**🤖 Análisis IA**")
    _groq_or_gemini = __import__("os").getenv("GROQ_API_KEY", "") or _GEMINI_KEY_ENV
    if _groq_or_gemini:
        gemini_key = _groq_or_gemini
        st.markdown('<div style="color:#4ADE80;font-size:0.75rem;">✅ IA activa (desde .env)</div>', unsafe_allow_html=True)
    else:
        gemini_key = st.text_input("API Key Groq", type="password",
                                    placeholder="gsk_...",
                                    help="Registrate gratis en console.groq.com — sin TDC")
        if gemini_key:
            st.markdown('<div style="color:#4ADE80;font-size:0.75rem;">✅ IA activa</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:#F87171;font-size:0.75rem;">⚠️ Agregá GROQ_API_KEY al .env</div>', unsafe_allow_html=True)

    st.markdown("<hr style='border-color:rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
    st.markdown("**📅 Período Actual**")
    # Botón para apagar el servidor
    st.markdown("<hr style='border-color:rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
    if st.button("⏹ Apagar Dashboard", use_container_width=True, type="secondary",
                 help="Detiene el servidor Streamlit"):
        st.warning("Cerrando servidor...")
        import time as _time
        _time.sleep(0.8)
        import os as _os
        _os.kill(_os.getpid(), 15)   # SIGTERM — cierre limpio

    periodo_actual = st.text_input("Nombre del período", "Febrero 2026")
    file_ventas   = st.file_uploader("Ventas (CSV)", type=['csv'], key="v1")
    file_precios  = st.file_uploader("Precios/Ofertas (CSV)", type=['csv'], key="p1")
    file_valor    = st.file_uploader("Bultos UxB (CSV)", type=['csv'], key="val1")
    file_clientes = st.file_uploader("Clientes (CSV) — opcional", type=['csv'], key="cli1")

    st.markdown("<hr style='border-color:rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
    activar_comparacion = st.toggle("🔀 Comparar con período anterior", value=False)
    if activar_comparacion:
        st.markdown("**📅 Período Anterior**")
        periodo_anterior = st.text_input("Período anterior", "Enero 2026", key="pa")
        file_ventas_2  = st.file_uploader("Ventas anteriores", type=['csv'], key="v2")
        file_precios_2 = st.file_uploader("Precios anteriores", type=['csv'], key="p2")
        file_valor_2   = st.file_uploader("Bultos anteriores", type=['csv'], key="val2")
    else:
        periodo_anterior = None
        file_ventas_2 = file_precios_2 = file_valor_2 = None

    st.markdown("<hr style='border-color:rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
    st.markdown("**🎛️ Filtros dinámicos**")


# ============================================================
# PANTALLA BIENVENIDA
# ============================================================
if not file_ventas or not file_precios or not file_valor:
    st.markdown("""
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:65vh;gap:1rem;">
        <div style="font-size:4rem;">📂</div>
        <div style="font-size:1.5rem;font-weight:700;color:#1A1D23;">Retail Engine BI v5.1</div>
        <div style="font-size:0.95rem;color:#6B7280;text-align:center;max-width:480px;">
            Cargá los archivos de <strong>Ventas</strong>, <strong>Precios</strong> y <strong>Bultos</strong>
            en el panel lateral. La IA (Groq/Llama) analizará automáticamente cada sección.
        </div>
        <div style="margin-top:1rem;display:flex;gap:0.8rem;flex-wrap:wrap;justify-content:center;">
            <div style="background:#EFF6FF;color:#1D4ED8;padding:0.5rem 1rem;border-radius:8px;font-size:0.82rem;font-weight:600;">📈 Ventas CSV</div>
            <div style="background:#F0FDF4;color:#166534;padding:0.5rem 1rem;border-radius:8px;font-size:0.82rem;font-weight:600;">💰 Precios CSV</div>
            <div style="background:#FFF7ED;color:#9A3412;padding:0.5rem 1rem;border-radius:8px;font-size:0.82rem;font-weight:600;">📦 Bultos CSV</div>
            <div style="background:#F5F3FF;color:#5B21B6;padding:0.5rem 1rem;border-radius:8px;font-size:0.82rem;font-weight:600;">🤖 IA Groq</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()


# ============================================================
# PROCESAMIENTO
# ============================================================
with st.spinner("⚙️ Procesando datos..."):
    df_raw = procesar_archivos(file_ventas, file_precios, file_valor)
    df_raw_2 = None
    if activar_comparacion and file_ventas_2 and file_precios_2 and file_valor_2:
        df_raw_2 = procesar_archivos(file_ventas_2, file_precios_2, file_valor_2)
    df_cli_raw = procesar_clientes(file_clientes) if file_clientes else None

if df_raw is None:
    st.error("No se pudieron procesar los archivos. Revisá los mensajes de error arriba.")
    st.stop()
else:

    # ── FILTROS DINÁMICOS ENCADENADOS ──
    # Guardados en variables con defaults para evitar crash en primer render
    with st.sidebar:
        familias_disp = sorted(df_raw['DesFam'].dropna().unique().tolist()) if df_raw is not None else []
        fam_sel = st.multiselect("Familia de producto", options=familias_disp, default=familias_disp)

        cats_disp = sorted(
            df_raw[df_raw['DesFam'].isin(fam_sel)]['Categoria_IA'].dropna().unique().tolist()
        ) if df_raw is not None and fam_sel else []
        cat_sel = st.multiselect("Categoría IA", options=cats_disp, default=cats_disp)

        abc_sel = st.multiselect("Categoría ABC",
                                  options=['A (80% Caja)', 'B (15% Caja)', 'C (5% Cola)'],
                                  default=['A (80% Caja)', 'B (15% Caja)', 'C (5% Cola)'])

        solo_oferta = st.toggle("🏷️ Solo artículos en oferta", value=False)

        venta_max = int(df_raw['Venta_$'].max()) if df_raw is not None else 100000
        venta_min_filtro = st.slider("Venta mínima por artículo ($)",
                                      min_value=0, max_value=min(venta_max, 500000),
                                      value=0, step=1000,
                                      format="$%d")

    # ── APLICAR FILTROS ──
    # Protección extra: si por alguna razón los multiselects quedan vacíos,
    # usamos todos los valores disponibles para no mostrar tabla vacía.
    fam_activas  = fam_sel  if fam_sel  else familias_disp
    cat_activas  = cat_sel  if cat_sel  else cats_disp
    abc_activos  = abc_sel  if abc_sel  else ['A (80% Caja)', 'B (15% Caja)', 'C (5% Cola)']

    mask = (
        df_raw['DesFam'].isin(fam_activas) &
        df_raw['Categoria_IA'].isin(cat_activas) &
        df_raw['Categoria_ABC'].isin(abc_activos) &
        (df_raw['Venta_$'] >= venta_min_filtro)
    )
    if solo_oferta:
        mask &= df_raw['Es_Oferta']

    df = df_raw[mask].copy()
    df_2 = df_raw_2.copy() if df_raw_2 is not None else None


    # ============================================================
    # MÉTRICAS MAESTRAS
    # ============================================================
    venta_total    = df['Venta_$'].sum()
    unidades_total = df['Unidades_Calc'].sum()
    bultos_total   = df['Bultos_Calc'].sum()
    skus_activos   = df['SKU'].nunique()
    precio_prom    = venta_total / unidades_total if unidades_total > 0 else 0
    pct_oferta     = df[df['Es_Oferta']]['Venta_$'].sum() / venta_total * 100 if venta_total > 0 else 0

    venta_2    = df_2['Venta_$'].sum() if df_2 is not None else None
    unidades_2 = df_2['Unidades_Calc'].sum() if df_2 is not None else None
    skus_2     = df_2['SKU'].nunique() if df_2 is not None else None

    # Datos para IA (resumen global)
    resumen_global = {
        "periodo": periodo_actual,
        "sucursal": sucursal,
        "venta_total": round(venta_total, 0),
        "unidades_total": round(unidades_total, 0),
        "skus_activos": skus_activos,
        "pct_oferta": round(pct_oferta, 1),
        "top3_articulos": df.groupby('DESCRIPCION')['Venta_$'].sum().nlargest(3).to_dict(),
        "top3_familias": df.groupby('DesFam')['Venta_$'].sum().nlargest(3).to_dict(),
        "skus_categoria_A": int(df[df['Categoria_ABC']=='A (80% Caja)']['SKU'].nunique()),
    }
    if venta_2:
        resumen_global["variacion_vs_anterior"] = f"{((venta_total-venta_2)/venta_2)*100:+.1f}%"
        resumen_global["periodo_anterior"] = periodo_anterior


    # ============================================================
    # ENCABEZADO
    # ============================================================
    col_h1, col_h2 = st.columns([3,1])
    with col_h1:
        filtros_activos = []
        if len(fam_sel) < len(familias_disp): filtros_activos.append(f"{len(fam_sel)} familias")
        if solo_oferta: filtros_activos.append("solo ofertas")
        if venta_min_filtro > 0: filtros_activos.append(f"venta ≥ ${venta_min_filtro:,}")
        filtro_txt = f" · Filtros: {', '.join(filtros_activos)}" if filtros_activos else ""

        st.markdown(f"""
        <div style="margin-bottom:0.5rem;">
            <span style="font-size:0.75rem;font-weight:700;color:#64748B;text-transform:uppercase;letter-spacing:0.1em;">
                Dashboard Analítico · {sucursal}{filtro_txt}
            </span>
            <h1 style="font-size:1.9rem;font-weight:800;color:#1A1D23;margin:0;line-height:1.1;">{periodo_actual}</h1>
        </div>
        """, unsafe_allow_html=True)
    with col_h2:
        st.markdown(f'<div style="text-align:right;padding-top:0.5rem;"><span style="font-size:0.7rem;color:#94A3B8;">{len(df):,} registros</span></div>', unsafe_allow_html=True)

    st.markdown("<hr style='border-color:#E2E6EE;margin:0.3rem 0 1.2rem;'>", unsafe_allow_html=True)

    # KPIs con tooltips
    m1,m2,m3,m4,m5,m6 = st.columns(6)
    m1.metric("Venta Total",    fmt_millones(venta_total),  delta=delta_pct(venta_total, venta_2) if venta_2 else None,  help=TOOLTIPS["Venta Total"])
    m2.metric("Unidades",       fmt_num(unidades_total),    delta=delta_pct(unidades_total, unidades_2) if unidades_2 else None, help=TOOLTIPS["Unidades"])
    m3.metric("Bultos",         fmt_num(bultos_total),      help=TOOLTIPS["Bultos"])
    m4.metric("SKUs Activos",   f"{skus_activos:,}",        delta=delta_pct(skus_activos, skus_2) if skus_2 else None,   help=TOOLTIPS["SKUs Activos"])
    m5.metric("Precio Prom/u",  f"${precio_prom:,.0f}",    help=TOOLTIPS["Precio Promedio"])
    m6.metric("% en Oferta",    f"{pct_oferta:.1f}%",       help=TOOLTIPS["% en Oferta"])

    if df_2 is not None and venta_2:
        variacion = venta_total - venta_2
        pct_var = (variacion/venta_2)*100
        color_v = "#16A34A" if variacion >= 0 else "#E84855"
        signo = "▲" if variacion >= 0 else "▼"
        st.markdown(f"""
        <div style="background:{'#F0FDF4' if variacion>=0 else '#FFF0F0'};border:1px solid {'#BBF7D0' if variacion>=0 else '#FECACA'};border-radius:10px;padding:0.8rem 1.2rem;margin:0.8rem 0;display:flex;align-items:center;gap:1.5rem;">
            <span style="font-weight:700;color:{color_v};font-size:1.1rem;">{signo} {abs(pct_var):.1f}%</span>
            <span style="color:#6B7280;font-size:0.85rem;">vs {periodo_anterior} &nbsp;·&nbsp; {fmt_millones(venta_2)} → {fmt_millones(venta_total)}</span>
            <span style="color:{color_v};font-size:0.85rem;font-weight:600;">{fmt_millones(abs(variacion))} {'más' if variacion>=0 else 'menos'}</span>
        </div>""", unsafe_allow_html=True)


    # ============================================================
    # HELPER: RECOLECTAR TEXTOS IA DE SESSION STATE
    # ============================================================
    def _get_texto_ia(titulo: str, datos: dict) -> str:
        """Recupera el texto IA cacheado en session_state para un título dado."""
        cache_key = f"ia_{titulo}_{hash(str(sorted(datos.items())))}"
        return st.session_state.get(cache_key, "")


    def _construir_kpis_dict():
        """Arma el dict de KPIs para exportar."""
        d = {
            "venta_total":  venta_total,
            "unidades":     unidades_total,
            "bultos":       bultos_total,
            "skus":         skus_activos,
            "pct_oferta":   pct_oferta,
            "precio_prom":  precio_prom,
        }
        if venta_2 and venta_2 > 0:
            d["variacion_pct"] = ((venta_total - venta_2) / venta_2) * 100
            d["periodo_anterior"] = periodo_anterior or ""
        return d


    def _construir_textos_ia():
        """Recolecta textos IA ya generados de session_state."""
        return {
            "overview": _get_texto_ia("Overview de Ventas", resumen_global),
            "abc":      _get_texto_ia("Análisis ABC", {
                "skus_A": int(df[df["Categoria_ABC"]=="A (80% Caja)"]["SKU"].nunique()),
                "venta_A": round(df[df["Categoria_ABC"]=="A (80% Caja)"]["Venta_$"].sum(), 0),
            }),
            "alertas":  _get_texto_ia("Alertas de Stock", {
                "articulos_A_criticos": int(df[df["Categoria_ABC"]=="A (80% Caja)"]["SKU"].nunique()),
            }),
            "ofertas":  _get_texto_ia("Análisis de Ofertas", {
                "skus_en_oferta": int(df[df["Es_Oferta"]]["SKU"].nunique()),
            }),
            "clientes": _get_texto_ia("Análisis de Clientes", {
                "n_clientes": df_cli_raw["DESCRIPCION"].nunique() if df_cli_raw is not None and "DESCRIPCION" in df_cli_raw.columns else 0,
            }),
        }


    # ============================================================
    # PANEL DE EXPORTACIÓN GLOBAL (arriba del dashboard)
    # ============================================================
    with st.expander("📤 Exportar Informe", expanded=False):
        st.markdown(
            "<small style='color:#6B7280;'>Los archivos incluyen los análisis IA que ya se generaron en las pestañas.</small>",
            unsafe_allow_html=True
        )
        exp_col1, exp_col2, exp_col3 = st.columns([2,2,3])

        with exp_col1:
            if EXPORTAR_OK:
                if st.button("📊 Generar Excel", key="btn_excel_global", use_container_width=True):
                    with st.spinner("Generando Excel..."):
                        try:
                            excel_bytes = generar_excel(
                                df=df,
                                kpis=_construir_kpis_dict(),
                                periodo=periodo_actual,
                                sucursal=sucursal,
                                texto_ia=_construir_textos_ia(),
                            )
                            st.session_state["excel_bytes"] = excel_bytes
                            st.session_state["excel_nombre"] = f"RetailBI_{periodo_actual.replace(' ','_')}.xlsx"
                            st.success("✅ Excel listo")
                        except Exception as ex:
                            st.error(f"Error: {ex}")

                if "excel_bytes" in st.session_state:
                    st.download_button(
                        label="⬇️ Descargar Excel",
                        data=st.session_state["excel_bytes"],
                        file_name=st.session_state.get("excel_nombre","RetailBI.xlsx"),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_excel_global",
                        use_container_width=True,
                    )
            else:
                st.warning(f"Módulo exportar no disponible: {_EXPORTAR_ERR}")

        with exp_col2:
            if EXPORTAR_OK:
                if st.button("📄 Generar PDF", key="btn_pdf_global", use_container_width=True):
                    with st.spinner("Generando PDF..."):
                        try:
                            pdf_bytes = generar_pdf(
                                df=df,
                                kpis=_construir_kpis_dict(),
                                periodo=periodo_actual,
                                sucursal=sucursal,
                                texto_ia=_construir_textos_ia(),
                            )
                            st.session_state["pdf_bytes"] = pdf_bytes
                            st.session_state["pdf_nombre"] = f"RetailBI_{periodo_actual.replace(' ','_')}.pdf"
                            st.success("✅ PDF listo")
                        except Exception as ex:
                            st.error(f"Error: {ex}")

                if "pdf_bytes" in st.session_state:
                    st.download_button(
                        label="⬇️ Descargar PDF",
                        data=st.session_state["pdf_bytes"],
                        file_name=st.session_state.get("pdf_nombre","RetailBI.pdf"),
                        mime="application/pdf",
                        key="dl_pdf_global",
                        use_container_width=True,
                    )

        with exp_col3:
            st.markdown("""
            <div style="font-size:0.78rem;color:#6B7280;padding:0.3rem 0;">
            <b>Excel incluye:</b> Resumen Ejecutivo + KPIs + Análisis IA · Datos Procesados · ABC · Familias · Ofertas · Artículos A<br>
            <b>PDF incluye:</b> Portada · KPIs · Narrativa IA · Tabla Ofertas con Efectividad · Top Artículos A
            </div>""", unsafe_allow_html=True)



    def _boton_exportar_tab(tab_nombre: str, key_suffix: str):
        """Muestra un mini botón de exportar dentro de cada pestaña."""
        if not EXPORTAR_OK:
            return
        with st.container():
            col_esp, col_btn_xl, col_btn_pd = st.columns([6,1,1])
            with col_btn_xl:
                if st.button("📊 Excel", key=f"btn_xl_{key_suffix}", help="Exportar informe completo a Excel"):
                    with st.spinner("..."):
                        try:
                            eb = generar_excel(df=df, kpis=_construir_kpis_dict(),
                                               periodo=periodo_actual, sucursal=sucursal,
                                               texto_ia=_construir_textos_ia())
                            st.session_state["excel_bytes"] = eb
                            st.session_state["excel_nombre"] = f"RetailBI_{periodo_actual.replace(' ','_')}.xlsx"
                        except Exception as ex:
                            st.error(str(ex))
            with col_btn_pd:
                if st.button("📄 PDF", key=f"btn_pd_{key_suffix}", help="Exportar informe completo a PDF"):
                    with st.spinner("..."):
                        try:
                            pb = generar_pdf(df=df, kpis=_construir_kpis_dict(),
                                             periodo=periodo_actual, sucursal=sucursal,
                                             texto_ia=_construir_textos_ia())
                            st.session_state["pdf_bytes"] = pb
                            st.session_state["pdf_nombre"] = f"RetailBI_{periodo_actual.replace(' ','_')}.pdf"
                        except Exception as ex:
                            st.error(str(ex))

        # Download buttons (aparecen si ya se generó)
        dl_cols = st.columns([6,1,1])
        with dl_cols[1]:
            if "excel_bytes" in st.session_state:
                st.download_button("⬇️ .xlsx", data=st.session_state["excel_bytes"],
                                   file_name=st.session_state.get("excel_nombre","RetailBI.xlsx"),
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key=f"dl_xl_{key_suffix}", use_container_width=True)
        with dl_cols[2]:
            if "pdf_bytes" in st.session_state:
                st.download_button("⬇️ .pdf", data=st.session_state["pdf_bytes"],
                                   file_name=st.session_state.get("pdf_nombre","RetailBI.pdf"),
                                   mime="application/pdf",
                                   key=f"dl_pd_{key_suffix}", use_container_width=True)
        st.markdown("<hr style='border-color:#E2E6EE;margin:0.3rem 0 1rem;'>", unsafe_allow_html=True)


    # ============================================================
    # TABS
    # ============================================================
    tab_overview, tab_abc, tab_alertas, tab_familias, tab_ofertas, tab_simulador, tab_comparacion, tab_clientes = st.tabs([
        "📊 Overview",
        "🔬 Análisis ABC",
        "⚠️ Alertas Stock",
        "🏷️ Familias",
        "🎯 Ofertas",
        "🎛️ Simulador",
        "📅 Comparación",
        "👥 Clientes",
    ])


    # ══════════════════════════════════════════════════════════════
    # TAB 1 — OVERVIEW
    # Situación: "Así estás hoy. Estos son tus números."
    # ══════════════════════════════════════════════════════════════
    with tab_overview:
        _boton_exportar_tab('Overview', 'ov')

        # ── ANÁLISIS IA ──
        analisis_ia(
            titulo="Overview de Ventas",
            datos_resumen=resumen_global,
            api_key=gemini_key,
            contexto="Esta es la vista general de ventas del período. Enfocate en la concentración de ventas, el comportamiento de las familias principales y el impacto de las ofertas."
        )

        # ── EXPLICACIÓN DE KPIs ──
        with st.expander("📖 ¿Qué significan estos KPIs?"):
            st.markdown("""
            | KPI | Qué mide | Por qué importa |
            |-----|----------|-----------------|
            | **Venta Total** | Suma de importes facturados | Tu termómetro de caja del período |
            | **Unidades** | Piezas vendidas (calculado por precio) | Volumen real de movimiento de mercadería |
            | **Bultos** | Unidades agrupadas por caja de compra | Te indica cuánto reposición necesitás |
            | **SKUs Activos** | Artículos con al menos 1 venta | Diversidad real de tu surtido |
            | **Precio Prom/u** | Ticket promedio por unidad | Indicador de mix de producto |
            | **% en Oferta** | Qué parte de la venta fue en descuento | Cuánto depende tu caja de promociones |
            """)

        col_left, col_right = st.columns([3,2])

        with col_left:
            st.markdown('<div class="section-header"><h3>💰 Top 20 Artículos por Venta</h3></div>', unsafe_allow_html=True)
            top20 = df.groupby(['SKU','DESCRIPCION'])['Venta_$'].sum().nlargest(20).reset_index()
            top20_sorted = top20.sort_values('Venta_$')
            fig = px.bar(
                top20_sorted, x='Venta_$', y='DESCRIPCION', orientation='h',
                color='Venta_$', color_continuous_scale=[[0,'#93C5FD'],[1,'#1E5FD4']],
                text=top20_sorted['Venta_$'].apply(fmt_millones),
                hover_data={'SKU': True, 'Venta_$': ':,.0f'},
                labels={'Venta_$': 'Venta ($)', 'DESCRIPCION': ''},
            )
            fig.update_layout(
                showlegend=False, coloraxis_showscale=False, plot_bgcolor='white',
                paper_bgcolor='white', margin=dict(l=0,r=80,t=10,b=0), height=480,
                xaxis_title="", yaxis_title="", yaxis=dict(tickfont=dict(size=10)),
                hoverlabel=dict(bgcolor='white', font_size=12),
            )
            fig.update_traces(textposition='outside', textfont_size=9)
            st.plotly_chart(fig, use_container_width=True)

        with col_right:
            st.markdown('<div class="section-header"><h3>🏷️ Venta por Familia</h3></div>', unsafe_allow_html=True)
            fam_vta = df.groupby('DesFam')['Venta_$'].sum().sort_values(ascending=False).head(10)
            fam_vta_df = fam_vta.reset_index()
            fam_vta_df.columns = ['DesFam', 'Venta_$']
            fig2 = px.pie(
                fam_vta_df, values='Venta_$', names='DesFam',
                color_discrete_sequence=COLORES_PLOTLY, hole=0.55,
                hover_data={'Venta_$': ':,.0f'},
            )
            fig2.update_layout(
                showlegend=True, legend=dict(font=dict(size=10)),
                margin=dict(l=0,r=0,t=10,b=0), paper_bgcolor='white', height=280,
                hoverlabel=dict(bgcolor='white'),
            )
            fig2.update_traces(textinfo='percent+label', textfont_size=9)
            st.plotly_chart(fig2, use_container_width=True)
            

            # Mini ranking de familias
            st.markdown('<div class="section-header"><h3>🏆 Ranking Familias</h3></div>', unsafe_allow_html=True)
            fam_rank_df = df.groupby('DesFam')['Venta_$'].sum().sort_values(ascending=False).head(5).reset_index()
            fam_max = fam_rank_df['Venta_$'].max()
            for i, row in fam_rank_df.iterrows():
                st.markdown(f"""
                <div style="margin-bottom:0.6rem;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:2px;">
                        <span style="font-size:0.82rem;font-weight:600;color:#1A1D23;">#{i+1} {row['DesFam']}</span>
                        <span style="font-size:0.82rem;color:#1E5FD4;font-weight:700;">{fmt_millones(row['Venta_$'])}</span>
                    </div>
                    {pct_bar(row['Venta_$'], fam_max)}
                </div>""", unsafe_allow_html=True)

        # Treemap interactivo
        st.markdown('<div class="section-header"><h3>🗂️ Mapa de Ventas por Categoría → Familia</h3></div>', unsafe_allow_html=True)
        st.caption("💡 Hacé click en una categoría para hacer zoom. Doble click para volver.")
        df_tree = df.groupby(['Categoria_IA','DesFam'])['Venta_$'].sum().reset_index()
        df_tree = df_tree[df_tree['Venta_$'] > 0]
        fig3 = px.treemap(
            df_tree, path=['Categoria_IA','DesFam'], values='Venta_$',
            color='Venta_$', color_continuous_scale='Blues',
            hover_data={'Venta_$': ':,.0f'},
            custom_data=['Venta_$'],
        )
        fig3.update_traces(
            texttemplate='<b>%{label}</b><br>%{customdata[0]:,.0f}',
            hovertemplate='<b>%{label}</b><br>Venta: $%{customdata[0]:,.0f}<extra></extra>',
        )
        fig3.update_layout(
            margin=dict(l=0,r=0,t=10,b=0), paper_bgcolor='white',
            height=380, coloraxis_showscale=False,
        )
        st.plotly_chart(fig3, use_container_width=True)


    # ══════════════════════════════════════════════════════════════
    # TAB 2 — ANÁLISIS ABC
    # Complicación: "Estos son tus artículos críticos."
    # ══════════════════════════════════════════════════════════════
    with tab_abc:
        _boton_exportar_tab('ABC', 'abc')

        abc_kpis = df.groupby('Categoria_ABC').agg(SKUs=('SKU','nunique'), Venta=('Venta_$','sum')).reset_index()
        tv_abc = abc_kpis['Venta'].sum()
        abc_kpis['Pct'] = (abc_kpis['Venta']/tv_abc*100).round(1)

        # ── ANÁLISIS IA ──
        resumen_abc = {
            "skus_A": int(df[df['Categoria_ABC']=='A (80% Caja)']['SKU'].nunique()),
            "skus_B": int(df[df['Categoria_ABC']=='B (15% Caja)']['SKU'].nunique()),
            "skus_C": int(df[df['Categoria_ABC']=='C (5% Cola)']['SKU'].nunique()),
            "venta_A": round(df[df['Categoria_ABC']=='A (80% Caja)']['Venta_$'].sum(), 0),
            "venta_B": round(df[df['Categoria_ABC']=='B (15% Caja)']['Venta_$'].sum(), 0),
            "top5_articulos_A": df[df['Categoria_ABC']=='A (80% Caja)'].groupby('DESCRIPCION')['Venta_$'].sum().nlargest(5).to_dict(),
            "familias_mas_representadas_en_A": df[df['Categoria_ABC']=='A (80% Caja)'].groupby('DesFam')['Venta_$'].sum().nlargest(3).to_dict(),
        }
        analisis_ia(
            titulo="Análisis ABC",
            datos_resumen=resumen_abc,
            api_key=gemini_key,
            contexto="El análisis ABC clasifica artículos según su contribución a la venta. A = 80% de la caja con pocos SKUs (críticos), B = siguiente 15%, C = cola larga de bajo movimiento."
        )

        with st.expander("📖 ¿Qué es el Análisis ABC y cómo usarlo?"):
            st.markdown("""
            El **Análisis ABC** es una aplicación del principio de Pareto (80/20) aplicado al retail.

            | Categoría | Regla | Qué hacés con ellos |
            |-----------|-------|---------------------|
            | **🔴 A** | 20% de SKUs = 80% de la venta | **Nunca pueden quebrarse.** Stock de seguridad alto. Reposición prioritaria. Monitoreo diario. |
            | **🟡 B** | Siguiente 30% de SKUs = 15% de la venta | Revisión semanal. Stock moderado. Son candidatos a subir a A o bajar a C. |
            | **🔵 C** | 50% de SKUs restantes = 5% de la venta | Evaluar si conviene mantenerlos. Alta rotación de catálogo. Candidatos a promoción o discontinuación. |

            **Regla de oro:** Un quiebre de stock en artículo A impacta directamente en caja. Un quiebre en C casi no se nota.
            """)

        col_a, col_b, col_c = st.columns(3)
        for col, cat, icon, color, border in zip(
            [col_a, col_b, col_c],
            ['A (80% Caja)','B (15% Caja)','C (5% Cola)'],
            ['🔴','🟡','🔵'],
            ['#FEE2E2','#FEF3C7','#DBEAFE'],
            ['#FECACA','#FDE68A','#BFDBFE']
        ):
            fila = abc_kpis[abc_kpis['Categoria_ABC']==cat]
            if not fila.empty:
                f = fila.iloc[0]
                col.markdown(f"""
                <div style="background:{color};border:1px solid {border};border-radius:12px;padding:1.2rem;text-align:center;">
                    <div style="font-size:1.8rem;">{icon}</div>
                    <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;color:#374151;margin:0.3rem 0;">{cat}</div>
                    <div style="font-size:1.8rem;font-weight:800;color:#111827;">{int(f['SKUs']):,} SKUs</div>
                    <div style="font-size:1rem;color:#374151;font-weight:600;">{fmt_millones(f['Venta'])}</div>
                    <div style="font-size:0.82rem;color:#6B7280;">{f['Pct']:.0f}% de la caja</div>
                </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        col_abc1, col_abc2 = st.columns([2,1])

        with col_abc1:
            df_p = df.sort_values('Venta_$', ascending=False).reset_index(drop=True)
            df_p['Acum_Pct'] = df_p['Venta_$'].cumsum() / df_p['Venta_$'].sum() * 100
            df_p['SKU_pct']  = (df_p.index + 1) / len(df_p) * 100

            fig_p = go.Figure()
            fig_p.add_hrect(y0=0,  y1=80, fillcolor='rgba(239,68,68,0.05)',  line_width=0, annotation_text="Zona A", annotation_position="top left")
            fig_p.add_hrect(y0=80, y1=95, fillcolor='rgba(245,158,11,0.05)', line_width=0, annotation_text="Zona B", annotation_position="top left")
            fig_p.add_hrect(y0=95, y1=100,fillcolor='rgba(59,130,246,0.05)', line_width=0, annotation_text="Zona C", annotation_position="top left")
            fig_p.add_trace(go.Scatter(
                x=df_p['SKU_pct'], y=df_p['Acum_Pct'], mode='lines',
                line=dict(color='#1E5FD4', width=2.5),
                fill='tozeroy', fillcolor='rgba(30,95,212,0.06)',
                name='Curva Pareto',
                hovertemplate='%{x:.1f}% SKUs → %{y:.1f}% venta<extra></extra>',
            ))
            for y, color, label in [(80,'#E84855','80% — Límite A'),(95,'#F4A228','95% — Límite B')]:
                fig_p.add_hline(y=y, line_dash='dash', line_color=color, line_width=1.5,
                                annotation_text=label, annotation_position='right')
            fig_p.update_layout(
                title='Curva de Pareto — Concentración de Ventas',
                plot_bgcolor='white', paper_bgcolor='white',
                height=380, margin=dict(l=0,r=80,t=40,b=0),
                xaxis_title='% de SKUs', yaxis_title='% Venta Acumulada',
                yaxis=dict(range=[0,105], gridcolor='#F0F2F5'),
                xaxis=dict(gridcolor='#F0F2F5'),
                legend=dict(font=dict(size=10)),
            )
            st.plotly_chart(fig_p, use_container_width=True)

        with col_abc2:
            # Scatter ABC × Categoría IA
            abc_d = df.groupby(['Categoria_ABC','Categoria_IA']).agg(
                Venta=('Venta_$','sum'), SKUs=('SKU','nunique')).reset_index()
            fig_b = px.scatter(
                abc_d, x='Categoria_ABC', y='Categoria_IA', size='Venta', color='Categoria_ABC',
                color_discrete_map={'A (80% Caja)':'#E84855','B (15% Caja)':'#F4A228','C (5% Cola)':'#3B82F6'},
                title='Concentración ABC por Categoría',
                hover_data={'Venta': ':,.0f', 'SKUs': True},
                size_max=50,
            )
            fig_b.update_layout(
                plot_bgcolor='white', paper_bgcolor='white', height=380,
                margin=dict(l=0,r=0,t=40,b=0), showlegend=False,
                xaxis_title='', yaxis_title='', yaxis=dict(tickfont=dict(size=9)),
            )
            st.plotly_chart(fig_b, use_container_width=True)

        # Tabla ABC interactiva
        st.markdown('<div class="section-header"><h3>📋 Detalle artículos — Top 100</h3></div>', unsafe_allow_html=True)
        abc_filtro = st.selectbox("Ver categoría", ['Todas','A (80% Caja)','B (15% Caja)','C (5% Cola)'], key='abc_filtro')
        df_tabla_abc = df.groupby(['SKU','DESCRIPCION','Categoria_ABC','DesFam','Es_Oferta'])['Venta_$'].sum().reset_index()
        if abc_filtro != 'Todas':
            df_tabla_abc = df_tabla_abc[df_tabla_abc['Categoria_ABC'] == abc_filtro]
        df_tabla_abc = df_tabla_abc.sort_values('Venta_$', ascending=False).head(100)
        df_tabla_abc['Venta_$'] = df_tabla_abc['Venta_$'].apply(lambda x: f"${x:,.0f}")
        df_tabla_abc['Es_Oferta'] = df_tabla_abc['Es_Oferta'].map({True:'🏷️ Sí', False:'—'})
        st.dataframe(
            df_tabla_abc.rename(columns={
                'DESCRIPCION':'Descripción','Categoria_ABC':'ABC',
                'DesFam':'Familia','Venta_$':'Venta','Es_Oferta':'Oferta'
            }),
            use_container_width=True, height=350, hide_index=True,
        )


    # ══════════════════════════════════════════════════════════════
    # TAB 3 — ALERTAS STOCK
    # Complicación: "Estos son tus riesgos."
    # ══════════════════════════════════════════════════════════════
    with tab_alertas:
        _boton_exportar_tab('Alertas', 'al')

        df_c      = df[df['Categoria_ABC']=='C (5% Cola)'].copy()
        umbral_c  = df['Venta_$'].quantile(0.15)
        df_c_exc  = df_c[df_c['Venta_$'] < umbral_c/2].copy()
        df_a      = df[df['Categoria_ABC']=='A (80% Caja)'].copy()

        resumen_alertas = {
            "articulos_A_criticos": int(df_a['SKU'].nunique()),
            "venta_en_riesgo_si_quiebra_A": round(df_a['Venta_$'].sum(), 0),
            "top3_A": df_a.groupby('DESCRIPCION')['Venta_$'].sum().nlargest(3).to_dict(),
            "articulos_C_baja_rotacion": int(df_c_exc['SKU'].nunique()),
            "capital_inmovilizado_estimado": round(df_c_exc['Venta_$'].sum(), 0),
            "pct_oferta_en_A": round(df_a[df_a['Es_Oferta']]['Venta_$'].sum() / df_a['Venta_$'].sum() * 100, 1) if df_a['Venta_$'].sum() > 0 else 0,
        }
        analisis_ia(
            titulo="Alertas de Stock",
            datos_resumen=resumen_alertas,
            api_key=gemini_key,
            contexto="Detectá artículos A que podrían generar un quiebre crítico de ventas, y artículos C con exceso de stock que inmovilizan capital."
        )

        with st.expander("📖 ¿Cómo leer las alertas?"):
            st.markdown("""
            - 🔴 **Artículos A — Motor de Caja**: Son los que nunca pueden faltarte. Un quiebre de stock en estos artículos impacta directamente en la recaudación del día.
            - 🟡 **Artículos B en caída**: Artículos que venían siendo B pero muestran baja reciente — posibles candidatos a problema de abastecimiento.
            - 🔵 **Capital Inmovilizado (C)**: Artículos con muy baja rotación que ocupan espacio y capital. Evaluá promoción, liquidación o discontinuación.
            """)

        ka, kb, kc = st.columns(3)
        ka.markdown(f"""<div style="background:#FFF0F0;border-radius:10px;padding:1.2rem;border:1px solid #FECACA;text-align:center;">
            <div style="font-size:0.7rem;font-weight:700;color:#991B1B;text-transform:uppercase;margin-bottom:0.5rem;">🔴 Artículos A — Motor de Caja</div>
            <div style="font-size:2rem;font-weight:800;color:#7F1D1D;">{df_a['SKU'].nunique():,}</div>
            <div style="font-size:0.9rem;color:#991B1B;font-weight:600;">{fmt_millones(df_a['Venta_$'].sum())}</div>
            <div style="font-size:0.75rem;color:#B91C1C;margin-top:0.4rem;">⚡ Prioridad MÁXIMA de reposición</div>
        </div>""", unsafe_allow_html=True)

        kb.markdown(f"""<div style="background:#FFFBEA;border-radius:10px;padding:1.2rem;border:1px solid #FDE68A;text-align:center;">
            <div style="font-size:0.7rem;font-weight:700;color:#92400E;text-transform:uppercase;margin-bottom:0.5rem;">🟡 Artículos B — Soporte</div>
            <div style="font-size:2rem;font-weight:800;color:#78350F;">{df[df['Categoria_ABC']=='B (15% Caja)']['SKU'].nunique():,}</div>
            <div style="font-size:0.9rem;color:#92400E;font-weight:600;">{fmt_millones(df[df['Categoria_ABC']=='B (15% Caja)']['Venta_$'].sum())}</div>
            <div style="font-size:0.75rem;color:#B45309;margin-top:0.4rem;">⚠️ Monitoreo frecuente</div>
        </div>""", unsafe_allow_html=True)

        kc.markdown(f"""<div style="background:#EFF6FF;border-radius:10px;padding:1.2rem;border:1px solid #BFDBFE;text-align:center;">
            <div style="font-size:0.7rem;font-weight:700;color:#1E40AF;text-transform:uppercase;margin-bottom:0.5rem;">🔵 Capital Inmovilizado</div>
            <div style="font-size:2rem;font-weight:800;color:#1E3A8A;">{df_c_exc['SKU'].nunique():,}</div>
            <div style="font-size:0.9rem;color:#1E40AF;font-weight:600;">{fmt_millones(df_c_exc['Venta_$'].sum())}</div>
            <div style="font-size:0.75rem;color:#2563EB;margin-top:0.4rem;">💡 Candidatos a promoción</div>
        </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        col_al1, col_al2 = st.columns(2)

        with col_al1:
            st.markdown("#### 🔴 Top 15 Artículos A — Nunca deben quebrarse")
            top_a = df_a.groupby(['SKU','DESCRIPCION'])['Venta_$'].sum().nlargest(15).reset_index()
            fig_a = px.bar(
                top_a.sort_values('Venta_$'), x='Venta_$', y='DESCRIPCION', orientation='h',
                color_discrete_sequence=['#E84855'],
                text=top_a.sort_values('Venta_$')['Venta_$'].apply(fmt_millones),
                hover_data={'SKU': True, 'Venta_$': ':,.0f'},
                labels={'Venta_$':'Venta ($)','DESCRIPCION':''},
            )
            fig_a.update_layout(
                plot_bgcolor='white', paper_bgcolor='white',
                margin=dict(l=0,r=80,t=5,b=0), height=400,
                xaxis_title='', yaxis_title='', showlegend=False,
                yaxis=dict(tickfont=dict(size=9)),
            )
            fig_a.update_traces(textposition='outside', textfont_size=9)
            st.plotly_chart(fig_a, use_container_width=True)

        with col_al2:
            st.markdown("#### 🔵 Artículos C — Menor Rotación (candidatos a acción)")
            if not df_c_exc.empty:
                df_cs = df_c_exc.groupby(['SKU','DESCRIPCION'])['Venta_$'].sum().nsmallest(15).reset_index()
                fig_c = px.bar(
                    df_cs, x='Venta_$', y='DESCRIPCION', orientation='h',
                    color_discrete_sequence=['#3B82F6'],
                    text=df_cs['Venta_$'].apply(lambda x: f"${x:,.0f}"),
                    labels={'Venta_$':'Venta ($)','DESCRIPCION':''},
                )
                fig_c.update_layout(
                    plot_bgcolor='white', paper_bgcolor='white',
                    margin=dict(l=0,r=80,t=5,b=0), height=400,
                    xaxis_title='', yaxis_title='', showlegend=False,
                    yaxis=dict(tickfont=dict(size=9)),
                )
                fig_c.update_traces(textposition='outside', textfont_size=9)
                st.plotly_chart(fig_c, use_container_width=True)
                st.markdown(f'<div class="alert-inmo">💡 {df_c_exc["SKU"].nunique()} artículos C con rotación muy baja. Considerá hacer una promoción o reducir el próximo pedido.</div>', unsafe_allow_html=True)
            else:
                st.info("No se detectaron artículos C con exceso de stock.")


    # ══════════════════════════════════════════════════════════════
    # TAB 4 — FAMILIAS
    # ══════════════════════════════════════════════════════════════
    with tab_familias:
        _boton_exportar_tab('Familias', 'fam')

        fam_agg = df.groupby('DesFam').agg(
            Venta=('Venta_$','sum'), SKUs=('SKU','nunique'), Bultos=('Bultos_Calc','sum')
        ).reset_index().sort_values('Venta', ascending=False)

        resumen_familias = {
            "familia_1": fam_agg.iloc[0]['DesFam'] if len(fam_agg) > 0 else "",
            "venta_familia_1": round(fam_agg.iloc[0]['Venta'], 0) if len(fam_agg) > 0 else 0,
            "top5_familias": fam_agg.head(5)[['DesFam','Venta']].to_dict('records'),
            "total_familias": len(fam_agg),
            "familias_con_mas_de_50k": int((fam_agg['Venta'] > 50000).sum()),
        }
        analisis_ia(
            titulo="Análisis por Familia",
            datos_resumen=resumen_familias,
            api_key=gemini_key,
            contexto="Analizá la concentración de ventas por familia de productos. Identificá cuáles lideran, cuáles están rezagadas y si la composición ABC dentro de cada familia es saludable."
        )

        with st.expander("📖 ¿Cómo leer el análisis por familia?"):
            st.markdown("""
            - El **gráfico de barras** muestra las familias ordenadas por venta total — te dice dónde está tu negocio hoy.
            - El **gráfico apilado ABC** revela la calidad de cada familia: una familia con muchos artículos A es sólida; una con mayoría C puede estar desactualizada.
            - La **tabla** te muestra bultos para estimar necesidades de reposición por familia.
            """)

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            fig_fb = px.bar(
                fam_agg.head(15).sort_values('Venta'), x='Venta', y='DesFam', orientation='h',
                color='Venta', color_continuous_scale=[[0,'#BAE6FD'],[1,'#0369A1']],
                text=fam_agg.head(15).sort_values('Venta')['Venta'].apply(fmt_millones),
                title='Top 15 Familias por Venta',
                hover_data={'SKUs': True, 'Venta': ':,.0f'},
                labels={'Venta':'Venta ($)','DesFam':''},
            )
            fig_fb.update_layout(
                showlegend=False, coloraxis_showscale=False, plot_bgcolor='white',
                paper_bgcolor='white', margin=dict(l=0,r=80,t=40,b=0), height=450,
                xaxis_title='', yaxis_title='',
            )
            fig_fb.update_traces(textposition='outside', textfont_size=9)
            st.plotly_chart(fig_fb, use_container_width=True)

        with col_f2:
            abc_fam = df.groupby(['DesFam','Categoria_ABC'])['Venta_$'].sum().reset_index()
            abc_fam = abc_fam[abc_fam['DesFam'].isin(fam_agg.head(10)['DesFam'])]
            fig_st = px.bar(
                abc_fam, x='Venta_$', y='DesFam', color='Categoria_ABC',
                orientation='h', barmode='stack',
                color_discrete_map={'A (80% Caja)':'#E84855','B (15% Caja)':'#F4A228','C (5% Cola)':'#3B82F6'},
                title='Composición ABC por Familia',
                labels={'Venta_$':'Venta ($)','DesFam':'','Categoria_ABC':'ABC'},
            )
            fig_st.update_layout(
                plot_bgcolor='white', paper_bgcolor='white',
                margin=dict(l=0,r=0,t=40,b=0), height=450,
                legend=dict(orientation='h', y=-0.12, font=dict(size=10)),
                xaxis_title='', yaxis_title='',
            )
            st.plotly_chart(fig_st, use_container_width=True)

        # Tabla con búsqueda
        busqueda_fam = st.text_input("🔍 Buscar familia", placeholder="Escribí para filtrar...", key="busq_fam")
        fam_show = fam_agg.copy()
        if busqueda_fam:
            fam_show = fam_show[fam_show['DesFam'].str.contains(busqueda_fam, case=False, na=False)]
        fam_show['Venta'] = fam_show['Venta'].apply(fmt_millones)
        fam_show['Bultos'] = fam_show['Bultos'].apply(lambda x: f"{x:,.0f}")
        st.dataframe(
            fam_show.rename(columns={'DesFam':'Familia','Venta':'Venta Total'}),
            use_container_width=True, height=280, hide_index=True,
        )


    # ══════════════════════════════════════════════════════════════
    # TAB 5 — ANÁLISIS DE OFERTAS  ← NUEVA PESTAÑA
    # Resolución: "Tus promociones — qué funcionó y qué no."
    # ══════════════════════════════════════════════════════════════
    with tab_ofertas:
        _boton_exportar_tab('Ofertas', 'of')

        df_of = df[df['Es_Oferta']].copy()
        df_nof = df[~df['Es_Oferta']].copy()

        if df_of.empty:
            st.markdown("""<div style="text-align:center;padding:3rem;color:#6B7280;">
                <div style="font-size:3rem;">🏷️</div>
                <div style="font-size:1.1rem;font-weight:600;">No se detectaron artículos en oferta en este período.</div>
                <div style="font-size:0.85rem;margin-top:0.5rem;">Verificá que el CSV de precios tenga la columna Oferta con valores mayores a 0.</div>
            </div>""", unsafe_allow_html=True)
        else:
            # ── MÉTRICAS DE OFERTAS ──
            venta_of      = df_of['Venta_$'].sum()
            skus_of       = df_of['SKU'].nunique()
            desc_prom     = df_of['Desc_Pct'].mean()
            of_sobre_total= venta_of / venta_total * 100 if venta_total > 0 else 0

            # Clasificación de efectividad: comparar venta promedio en oferta vs sin oferta por familia
            fam_of  = df_of.groupby('DesFam')['Venta_$'].sum().reset_index().rename(columns={'Venta_$':'Venta_Oferta'})
            fam_nof = df_nof.groupby('DesFam')['Venta_$'].sum().reset_index().rename(columns={'Venta_$':'Venta_Normal'})
            df_efect = pd.merge(fam_of, fam_nof, on='DesFam', how='left').fillna(0)
            df_efect['Ratio'] = np.where(df_efect['Venta_Normal'] > 0,
                                         df_efect['Venta_Oferta'] / df_efect['Venta_Normal'], 0)

            # Artículos en oferta con métricas
            df_of_agg = df_of.groupby(['SKU','DESCRIPCION','DesFam']).agg(
                Venta=('Venta_$','sum'),
                Unidades=('Unidades_Calc','sum'),
                Desc_Pct=('Desc_Pct','mean'),
                Precio_Normal=('Precio_Unit','mean'),
                Precio_Oferta=('Oferta_Num','mean'),
            ).reset_index().sort_values('Venta', ascending=False)

            # Venta que habrían generado a precio normal
            df_of_agg['Venta_Sin_Descuento'] = df_of_agg['Unidades'] * df_of_agg['Precio_Normal']
            df_of_agg['Costo_Descuento']     = df_of_agg['Venta_Sin_Descuento'] - df_of_agg['Venta']
            df_of_agg['Costo_Descuento']     = df_of_agg['Costo_Descuento'].clip(lower=0)

            # Efectividad: artículo exitoso si está entre top 50% por unidades de su familia
            mediana_unidades = df_of_agg['Unidades'].median()
            df_of_agg['Efectividad'] = np.where(
                df_of_agg['Unidades'] >= mediana_unidades, '✅ Exitosa', '⚠️ Revisar'
            )

            costo_total_descuentos = df_of_agg['Costo_Descuento'].sum()

            resumen_ofertas = {
                "skus_en_oferta": int(skus_of),
                "venta_total_en_oferta": round(venta_of, 0),
                "pct_sobre_venta_total": round(of_sobre_total, 1),
                "descuento_promedio_pct": round(desc_prom, 1),
                "costo_total_descuentos_estimado": round(costo_total_descuentos, 0),
                "top3_ofertas_exitosas": df_of_agg[df_of_agg['Efectividad']=='✅ Exitosa'].nlargest(3, 'Venta')[['DESCRIPCION','Venta','Desc_Pct']].to_dict('records'),
                "top3_ofertas_a_revisar": df_of_agg[df_of_agg['Efectividad']=='⚠️ Revisar'].nsmallest(3, 'Venta')[['DESCRIPCION','Venta','Desc_Pct']].to_dict('records'),
            }

            analisis_ia(
                titulo="Análisis de Ofertas",
                datos_resumen=resumen_ofertas,
                api_key=gemini_key,
                contexto="Evaluá la efectividad de las promociones. Una oferta es exitosa si generó un volumen de unidades por encima de la mediana del período. Considerá el costo del descuento vs el incremento de volumen."
            )

            with st.expander("📖 ¿Cómo leer el análisis de ofertas?"):
                st.markdown("""
                - **Venta en Oferta**: Lo que facturaste con artículos que tenían descuento activo.
                - **Costo del Descuento**: Diferencia entre lo que habrías cobrado a precio normal vs lo que cobraste. Es la "inversión" en la promoción.
                - **Oferta Exitosa** ✅: El artículo vendió más unidades que la mediana del período — la oferta generó tracción real.
                - **Oferta a Revisar** ⚠️: El artículo tuvo descuento pero no movió más unidades que el promedio — el descuento no fue la palanca correcta.
                - **Regla de oro**: Si una oferta no aumenta las unidades vendidas, el descuento solo reduce tu margen sin beneficio.
                """)

            # KPIs de Ofertas
            ko1, ko2, ko3, ko4 = st.columns(4)
            ko1.metric("SKUs en Oferta",          f"{skus_of:,}",              help="Artículos con precio de oferta activo")
            ko2.metric("Venta en Oferta",          fmt_millones(venta_of),     help="Total facturado en artículos con descuento")
            ko3.metric("% de la Venta Total",      f"{of_sobre_total:.1f}%",   help="Qué parte de tu caja provino de ofertas")
            ko4.metric("Costo Total Descuentos",   fmt_millones(costo_total_descuentos), help="Ingreso resignado por aplicar los descuentos")

            st.markdown("<br>", unsafe_allow_html=True)
            col_of1, col_of2 = st.columns([3,2])

            with col_of1:
                st.markdown('<div class="section-header"><h3>🏆 Ranking de Ofertas por Venta</h3></div>', unsafe_allow_html=True)
                top_of = df_of_agg.head(20).sort_values('Venta')
                colors = ['#16A34A' if e == '✅ Exitosa' else '#F4A228'
                          for e in top_of['Efectividad']]
                fig_of = go.Figure(go.Bar(
                    x=top_of['Venta'],
                    y=top_of['DESCRIPCION'],
                    orientation='h',
                    marker_color=colors,
                    text=top_of['Venta'].apply(fmt_millones),
                    textposition='outside',
                    textfont=dict(size=9),
                    customdata=np.stack([top_of['Desc_Pct'], top_of['Efectividad'], top_of['Unidades']], axis=-1),
                    hovertemplate=(
                        '<b>%{y}</b><br>'
                        'Venta: $%{x:,.0f}<br>'
                        'Descuento: %{customdata[0]:.1f}%<br>'
                        'Unidades: %{customdata[2]:.0f}<br>'
                        'Estado: %{customdata[1]}<extra></extra>'
                    ),
                ))
                fig_of.update_layout(
                    plot_bgcolor='white', paper_bgcolor='white',
                    margin=dict(l=0,r=80,t=10,b=0), height=500,
                    xaxis_title='', yaxis_title='',
                    yaxis=dict(tickfont=dict(size=9)),
                )
                st.plotly_chart(fig_of, use_container_width=True)

            with col_of2:
                # Scatter: Descuento % vs Unidades vendidas
                st.markdown('<div class="section-header"><h3>📊 Descuento vs Volumen</h3></div>', unsafe_allow_html=True)
                st.caption("💡 Idealmente los puntos con mayor descuento deberían estar más a la derecha (más unidades)")
                fig_sc = px.scatter(
                    df_of_agg, x='Desc_Pct', y='Unidades',
                    color='Efectividad',
                    color_discrete_map={'✅ Exitosa':'#16A34A','⚠️ Revisar':'#F4A228'},
                    size='Venta', size_max=40,
                    hover_data={'DESCRIPCION': True, 'Venta': ':,.0f', 'Desc_Pct': ':.1f', 'Unidades': ':.0f'},
                    labels={'Desc_Pct':'Descuento (%)', 'Unidades':'Unidades vendidas'},
                )
                fig_sc.add_vline(x=desc_prom, line_dash='dash', line_color='#94A3B8',
                                 annotation_text=f"Prom. {desc_prom:.0f}%", annotation_position='top right')
                fig_sc.update_layout(
                    plot_bgcolor='white', paper_bgcolor='white',
                    margin=dict(l=0,r=0,t=10,b=0), height=260,
                    legend=dict(orientation='h', y=-0.2, font=dict(size=10)),
                )
                st.plotly_chart(fig_sc, use_container_width=True)

                # Costo de descuentos por familia
                st.markdown('<div class="section-header"><h3>💸 Costo Descuentos por Familia</h3></div>', unsafe_allow_html=True)
                costo_fam = df_of_agg.groupby('DesFam')['Costo_Descuento'].sum().sort_values(ascending=False).head(8)
                fig_cd = px.bar(
                    x=costo_fam.values, y=costo_fam.index, orientation='h',
                    color_discrete_sequence=['#F59E0B'],
                    text=[fmt_millones(v) for v in costo_fam.values],
                    labels={'x':'Costo ($)','y':''},
                )
                fig_cd.update_layout(
                    plot_bgcolor='white', paper_bgcolor='white',
                    margin=dict(l=0,r=60,t=5,b=0), height=200,
                    xaxis_title='', yaxis_title='',
                    yaxis=dict(tickfont=dict(size=9)),
                )
                fig_cd.update_traces(textposition='outside', textfont_size=9)
                st.plotly_chart(fig_cd, use_container_width=True)

            # Tabla completa de ofertas
            st.markdown('<div class="section-header"><h3>📋 Detalle completo de artículos en oferta</h3></div>', unsafe_allow_html=True)

            col_fof1, col_fof2 = st.columns(2)
            with col_fof1:
                fam_of_filt = st.selectbox("Filtrar por familia", ['Todas'] + sorted(df_of_agg['DesFam'].unique().tolist()), key='fam_of')
            with col_fof2:
                efect_filt = st.selectbox("Filtrar por efectividad", ['Todas','✅ Exitosa','⚠️ Revisar'], key='efect_of')

            df_of_tabla = df_of_agg.copy()
            if fam_of_filt != 'Todas':
                df_of_tabla = df_of_tabla[df_of_tabla['DesFam'] == fam_of_filt]
            if efect_filt != 'Todas':
                df_of_tabla = df_of_tabla[df_of_tabla['Efectividad'] == efect_filt]

            df_of_show = df_of_tabla[['DESCRIPCION','DesFam','Precio_Normal','Precio_Oferta','Desc_Pct','Unidades','Venta','Costo_Descuento','Efectividad']].copy()
            df_of_show['Precio_Normal']   = df_of_show['Precio_Normal'].apply(lambda x: f"${x:,.0f}")
            df_of_show['Precio_Oferta']   = df_of_show['Precio_Oferta'].apply(lambda x: f"${x:,.0f}")
            df_of_show['Desc_Pct']        = df_of_show['Desc_Pct'].apply(lambda x: f"{x:.1f}%")
            df_of_show['Unidades']        = df_of_show['Unidades'].apply(lambda x: f"{x:,.0f}")
            df_of_show['Venta']           = df_of_show['Venta'].apply(lambda x: f"${x:,.0f}")
            df_of_show['Costo_Descuento'] = df_of_show['Costo_Descuento'].apply(lambda x: f"${x:,.0f}")

            st.dataframe(
                df_of_show.rename(columns={
                    'DESCRIPCION':'Artículo','DesFam':'Familia',
                    'Precio_Normal':'P. Normal','Precio_Oferta':'P. Oferta',
                    'Desc_Pct':'Descuento','Costo_Descuento':'Costo Desc.',
                }),
                use_container_width=True, height=380, hide_index=True,
            )


    # ══════════════════════════════════════════════════════════════
    # TAB SIMULADOR WHAT-IF
    # ══════════════════════════════════════════════════════════════
    with tab_simulador:
        _boton_exportar_tab('Simulador', 'sim')
        st.markdown('<div class="section-header"><h3>🎛️ Simulador de Escenarios (What-If)</h3></div>', unsafe_allow_html=True)
        st.caption("Proyectá el impacto en la caja al variar precios, considerando la elasticidad estimada de la demanda.")

        col_sim1, col_sim2 = st.columns([1, 3])
        with col_sim1:
            var_precio = st.slider("Variación de Precio general (%)", min_value=-30.0, max_value=50.0, value=10.0, step=1.0)
            elasticidad = st.slider("Caída de ventas por cada 1% de aumento", min_value=0.0, max_value=2.0, value=0.5, step=0.1)
            st.markdown(f"""
            <div style="background:#F0FDF4;border-left:4px solid #16A34A;padding:10px;border-radius:5px;font-size:0.85rem;">
                <b>Regla de Elasticidad:</b><br>
                Al variar el precio un <b>{var_precio:+.1f}%</b>, se asume que las unidades cambiarán un <b>{-var_precio*elasticidad:+.1f}%</b>.
            </div>
            """, unsafe_allow_html=True)

        with col_sim2:
            df_sim = df[['SKU', 'DESCRIPCION', 'DesFam', 'Precio_Unit', 'Unidades_Calc', 'Venta_$']].copy()
            df_sim = df_sim[df_sim['Precio_Unit'] > 0]
            
            var_unidades = - (var_precio * elasticidad)
            df_sim['Nuevo_Precio'] = df_sim['Precio_Unit'] * (1 + var_precio/100)
            df_sim['Nuevas_Unidades'] = (df_sim['Unidades_Calc'] * (1 + var_unidades/100)).clip(lower=0)
            df_sim['Nueva_Venta'] = df_sim['Nuevo_Precio'] * df_sim['Nuevas_Unidades']
            df_sim['Impacto_$'] = df_sim['Nueva_Venta'] - df_sim['Venta_$']
            
            total_actual = df_sim['Venta_$'].sum()
            total_nuevo = df_sim['Nueva_Venta'].sum()
            impacto_total = total_nuevo - total_actual
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Venta Proyectada", fmt_millones(total_nuevo), delta=fmt_millones(impacto_total))
            k2.metric("Unidades Proyectadas", fmt_num(df_sim['Nuevas_Unidades'].sum()), delta=f"{var_unidades:+.1f}%")
            k3.metric("Ticket Promedio Simulado", f"${total_nuevo/df_sim['Nuevas_Unidades'].sum() if df_sim['Nuevas_Unidades'].sum() else 0:,.0f}")
            
            fig_wf = go.Figure(go.Waterfall(
                name="Impacto", orientation="v", measure=["absolute", "relative", "total"],
                x=["Caja Actual", "Impacto Simulado", "Caja Proyectada"],
                y=[total_actual, impacto_total, total_nuevo],
                text=[fmt_millones(total_actual), fmt_millones(impacto_total), fmt_millones(total_nuevo)],
                textposition="outside", connector={"line":{"color":"rgb(63, 63, 63)"}}
            ))
            fig_wf.update_layout(height=300, margin=dict(t=40, b=20, l=20, r=20), plot_bgcolor='white', showlegend=False)
            st.plotly_chart(fig_wf, use_container_width=True)

        st.dataframe(
            df_sim.sort_values('Impacto_$', ascending=False).head(50).rename(columns={
                'DESCRIPCION': 'Artículo', 'DesFam': 'Familia', 'Precio_Unit': 'Precio Base',
                'Unidades_Calc': 'Unidades Base', 'Venta_$': 'Caja Base', 'Impacto_$': 'Impacto Neto'
            }),
            use_container_width=True, height=300, hide_index=True
        )

    # ══════════════════════════════════════════════════════════════
    # TAB 6 — COMPARACIÓN
    # ══════════════════════════════════════════════════════════════
    with tab_comparacion:
        if df_2 is None:
            st.markdown("""<div style="text-align:center;padding:3rem;color:#6B7280;">
                <div style="font-size:3rem;">🔀</div>
                <div style="font-size:1.1rem;font-weight:600;">Activá el toggle "Comparar con período anterior" en el sidebar.</div>
                <div style="font-size:0.85rem;margin-top:0.5rem;">Podés comparar ventas, unidades y SKUs entre dos períodos.</div>
            </div>""", unsafe_allow_html=True)
        else:
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Venta",    fmt_millones(venta_total), delta=delta_pct(venta_total, venta_2))
            mc2.metric("Unidades", fmt_num(unidades_total),   delta=delta_pct(unidades_total, unidades_2))
            mc3.metric("SKUs",     f"{skus_activos:,}",       delta=delta_pct(skus_activos, skus_2))
            mc4.metric("Prom/u",   f"${precio_prom:,.0f}")

            analisis_ia(
                titulo=f"Comparación {periodo_actual} vs {periodo_anterior}",
                datos_resumen={
                    "venta_actual": round(venta_total, 0),
                    "venta_anterior": round(venta_2, 0),
                    "variacion_pct": f"{((venta_total-venta_2)/venta_2)*100:+.1f}%",
                    "skus_actual": skus_activos,
                    "skus_anterior": int(skus_2),
                },
                api_key=gemini_key,
            )

            fam_act = df.groupby('DesFam')['Venta_$'].sum().reset_index().rename(columns={'Venta_$':'Actual'})
            fam_ant = df_2.groupby('DesFam')['Venta_$'].sum().reset_index().rename(columns={'Venta_$':'Anterior'})
            df_cmp  = pd.merge(fam_act, fam_ant, on='DesFam', how='outer').fillna(0)
            df_cmp['Var_Pct'] = np.where(
                df_cmp['Anterior'] > 0,
                (df_cmp['Actual'] - df_cmp['Anterior']) / df_cmp['Anterior'] * 100, np.nan
            )
            df_cmp = df_cmp.sort_values('Actual', ascending=False).head(15)

            fig_cmp = go.Figure()
            fig_cmp.add_trace(go.Bar(
                name=str(periodo_anterior), x=df_cmp['DesFam'], y=df_cmp['Anterior'],
                marker_color='#CBD5E1', opacity=0.8,
                hovertemplate='%{x}<br>Anterior: $%{y:,.0f}<extra></extra>',
            ))
            fig_cmp.add_trace(go.Bar(
                name=periodo_actual, x=df_cmp['DesFam'], y=df_cmp['Actual'],
                marker_color='#1E5FD4',
                hovertemplate='%{x}<br>Actual: $%{y:,.0f}<extra></extra>',
            ))
            fig_cmp.update_layout(
                barmode='group', plot_bgcolor='white', paper_bgcolor='white',
                margin=dict(l=0,r=0,t=20,b=60), height=400,
                legend=dict(orientation='h', y=-0.25),
                xaxis=dict(tickangle=-30),
            )
            st.plotly_chart(fig_cmp, use_container_width=True)

            # Waterfall de variación por familia
            df_cmp_sorted = df_cmp.sort_values('Var_Pct', ascending=False).dropna(subset=['Var_Pct'])
            colors_wf = ['#16A34A' if v >= 0 else '#E84855' for v in df_cmp_sorted['Var_Pct']]
            fig_wf = go.Figure(go.Bar(
                x=df_cmp_sorted['DesFam'],
                y=df_cmp_sorted['Var_Pct'],
                marker_color=colors_wf,
                text=[f"{v:+.1f}%" for v in df_cmp_sorted['Var_Pct']],
                textposition='outside',
                textfont=dict(size=9),
                hovertemplate='%{x}<br>Variación: %{y:+.1f}%<extra></extra>',
            ))
            fig_wf.add_hline(y=0, line_color='#374151', line_width=1)
            fig_wf.update_layout(
                title='Variación % por Familia vs período anterior',
                plot_bgcolor='white', paper_bgcolor='white',
                margin=dict(l=0,r=0,t=40,b=60), height=320,
                xaxis=dict(tickangle=-30), yaxis_title='Variación %',
            )
            st.plotly_chart(fig_wf, use_container_width=True)


    # ══════════════════════════════════════════════════════════════
    # TAB 7 — CLIENTES
    # ══════════════════════════════════════════════════════════════
    with tab_clientes:
        if df_cli_raw is None:
            st.markdown("""<div style="text-align:center;padding:3rem;color:#6B7280;">
                <div style="font-size:3rem;">👥</div>
                <div style="font-size:1.1rem;font-weight:600;">Cargá el CSV de clientes en el sidebar para ver este análisis.</div>
            </div>""", unsafe_allow_html=True)
        else:
            n_cli   = df_cli_raw['DESCRIPCION'].nunique() if 'DESCRIPCION' in df_cli_raw.columns else len(df_cli_raw)
            tv_cli  = df_cli_raw['Venta_$'].sum()
            tick_p  = tv_cli / n_cli if n_cli else 0

            ck1, ck2, ck3 = st.columns(3)
            ck1.metric("Clientes activos",  f"{n_cli:,}",             help="Clientes con al menos una compra en el período")
            ck2.metric("Venta cartera",     fmt_millones(tv_cli),     help="Total facturado a clientes identificados")
            ck3.metric("Ticket promedio",   fmt_millones(tick_p),     help="Venta promedio por cliente en el período")

            analisis_ia(
                titulo="Análisis de Clientes",
                datos_resumen={
                    "n_clientes": n_cli,
                    "venta_total_clientes": round(tv_cli, 0),
                    "ticket_promedio": round(tick_p, 0),
                    "top3_clientes": df_cli_raw.groupby('DESCRIPCION')['Venta_$'].sum().nlargest(3).to_dict() if 'DESCRIPCION' in df_cli_raw.columns else {},
                },
                api_key=gemini_key,
            )

            if 'DESCRIPCION' in df_cli_raw.columns:
                top_cli = df_cli_raw.groupby('DESCRIPCION')['Venta_$'].sum().nlargest(20).reset_index()
                fig_cli = px.bar(
                    top_cli.sort_values('Venta_$'), x='Venta_$', y='DESCRIPCION', orientation='h',
                    color='Venta_$', color_continuous_scale=[[0,'#A7F3D0'],[1,'#047857']],
                    text=top_cli.sort_values('Venta_$')['Venta_$'].apply(fmt_millones),
                    title='Top 20 Clientes por Venta',
                    labels={'Venta_$':'Venta ($)','DESCRIPCION':''},
                )
                fig_cli.update_layout(
                    showlegend=False, coloraxis_showscale=False, plot_bgcolor='white',
                    paper_bgcolor='white', margin=dict(l=0,r=80,t=40,b=0), height=450,
                    xaxis_title='', yaxis_title='', yaxis=dict(tickfont=dict(size=9)),
                )
                fig_cli.update_traces(textposition='outside', textfont_size=9)
                st.plotly_chart(fig_cli, use_container_width=True)


    # ============================================================
    # FOOTER
    # ============================================================
    st.markdown(f"""
    <div style="margin-top:3rem;padding-top:1rem;border-top:1px solid #E2E6EE;display:flex;justify-content:space-between;align-items:center;">
        <div style="font-size:0.72rem;color:#9AA0AD;">
            <strong>Retail Engine BI v5.1</strong> · Andrés Díaz · RPA Suite
        </div>
        <div style="font-size:0.72rem;color:#9AA0AD;">
            {len(df):,} registros · {sucursal} · {periodo_actual}
            {'· 🤖 IA activa' if gemini_key else '· IA desactivada'}
        </div>
    </div>""", unsafe_allow_html=True)