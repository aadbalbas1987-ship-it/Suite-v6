"""
quiebres_dashboard.py — RPA Suite v5
======================================
Dashboard de Análisis de Quiebres y Sobrestock.
Carga 4 archivos de ventas semanales + stock sistema (linvalor) + stock físico + lpcio.
Genera recomendaciones de compra con explicaciones y detecta sobrestock / riesgo de vencimiento.
"""

import sys
from pathlib import Path as _Path
_RAIZ = _Path(__file__).parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
import io
import streamlit.components.v1 as components
import os
import requests

# ── Módulo de Predicción (Opcional) ───────────────────────────────────────────
try:
    from core.prediccion import predecir_quiebres_lista, guardar_snapshot_ventas, cargar_historial_ventas
    _PRED_OK = True
except ImportError:
    _PRED_OK = False

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    _SKLEARN_OK = True
except ImportError:
    _SKLEARN_OK = False

@st.cache_data(show_spinner=False)
def run_predictions(_df, _lead_time):
    """Ejecuta y cachea el motor de predicción de quiebres."""
    if not _PRED_OK:
        return pd.DataFrame()
    # La importación se hace aquí dentro para que el cache funcione correctamente
    from core.prediccion import predecir_quiebres_lista
    return predecir_quiebres_lista(
        df_stock=_df,
        lead_time_dias=_lead_time,
    )

@st.cache_data(show_spinner=False)
def run_anomaly_detection(_df):
    """Ejecuta y cachea el modelo de detección de anomalías."""
    if not _SKLEARN_OK or len(_df) < 10:
        return pd.DataFrame()

    df_ml = _df[['Codart', 'DESCRIPCION', 'UNIDADES_MES', 'STOCK_FISICO', 'DEMANDA_AJUSTADA']].copy()
    df_ml = df_ml.fillna(0)

    # Transformación logarítmica (sumando 1 para evitar log(0))
    X = df_ml[['UNIDADES_MES', 'STOCK_FISICO']].copy()
    X_log = np.log1p(X)

    # Escalar
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_log)

    # Entrenar modelo Isolation Forest (aislamos el 5% de anomalías extremas)
    iso = IsolationForest(contamination=0.05, random_state=42)
    df_ml['outlier'] = iso.fit_predict(X_scaled)

    # Etiquetar: -1 es anomalía, 1 es normal
    df_ml['Segmento ML'] = df_ml['outlier'].map({-1: "🔴 Anomalía Extrema", 1: "🔵 Comportamiento Normal"})

    return df_ml

# ── Página ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Análisis de Quiebres · RPA Suite v5",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Estilos ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap');
html,body,[data-testid="stAppViewContainer"]{background:#F0F2F5 !important;font-family:'Sora',sans-serif;}
.main .block-container{padding:1.5rem 2.5rem 3rem;max-width:1600px;}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0F1923 0%,#1A2535 100%) !important;border-right:1px solid rgba(255,255,255,0.06);}
[data-testid="stSidebar"] *{color:#CBD5E1 !important;}
.stTabs [data-baseweb="tab-list"]{gap:8px;}
.stTabs [data-baseweb="tab"]{border-radius:6px;padding:0.5rem 1rem;font-size:0.82rem;font-weight:600;}
.sec-hdr{border-left:3px solid #1E5FD4;padding-left:14px;margin:28px 0 16px 0;}
.sec-hdr h3{color:#1A1D23;margin:0;font-size:1rem;font-weight:700;}
.alerta-titulo{font-weight:700;color:#1A1D23;font-size:0.9rem;margin-bottom:4px;}
.alerta-detalle{color:#5A6070;font-size:0.8rem;line-height:1.5;}
.alert-critico{background:#FFF0F0;border-left:4px solid #E84855;border-radius:8px;padding:0.8rem 1rem;margin:0.3rem 0;font-size:0.88rem;}
.alert-warning{background:#FFFBEA;border-left:4px solid #F4A228;border-radius:8px;padding:0.8rem 1rem;margin:0.3rem 0;font-size:0.88rem;}
.alert-inmo{background:#EFF6FF;border-left:4px solid #1E5FD4;border-radius:8px;padding:0.8rem 1rem;margin:0.3rem 0;font-size:0.88rem;}
.alert-success{background:#F0FDF4;border-left:4px solid #16A34A;border-radius:8px;padding:0.8rem 1rem;margin:0.3rem 0;font-size:0.88rem;}
.tag-rojo{background:#FEE2E2;color:#991B1B;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:700;}
.tag-verde{background:#D1FAE5;color:#065F46;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:700;}
.tag-naranja{background:#FEF3C7;color:#92400E;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:700;}
.tag-azul{background:#DBEAFE;color:#1E40AF;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:700;}
.ia-box{background:linear-gradient(135deg,#0F1923 0%,#1E3A5F 100%);border-radius:14px;padding:1.4rem 1.8rem;margin:0.5rem 0 1.5rem;border:1px solid rgba(30,95,212,0.3);}
.ia-box p{color:#CBD5E1;font-size:0.91rem;line-height:1.7;margin:0.4rem 0;}
.ia-box strong{color:#93C5FD;}
</style>
""", unsafe_allow_html=True)



# ══════════════════════════════════════════════════════════════
# FUNCIONES DE PARSEO
# ══════════════════════════════════════════════════════════════

def parsear_ventas_csv(file_obj, semana: int) -> pd.DataFrame:
    """Parsea el CSV de ventas del sistema (formato pipe-delimited)."""
    rows = []
    content = file_obj.read().decode('latin-1')
    for line in content.splitlines():
        if not line.startswith('Artículo'):
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 4:
            continue
        codigo_raw = parts[1].strip()
        desc_raw   = parts[2].strip()
        total_raw  = parts[3].strip()
        try:
            codigo = int(codigo_raw)
        except:
            continue
        total_str = total_raw.replace('.', '').replace(',', '.')
        try:
            total = float(total_str)
        except:
            total = 0.0
        rows.append({'CODIGO': codigo, 'DESCRIPCION': desc_raw, 'TOTAL_PESOS': total, 'SEMANA': semana})
    return pd.DataFrame(rows)


def limpiar_num(s) -> float:
    try:
        return float(str(s).replace('.', '').replace(',', '.').strip())
    except:
        return 0.0


@st.cache_data(show_spinner=False)
def procesar_datos(
    ventas_bytes: list,      # list of bytes, one per semana
    linvalor_bytes: bytes,
    stock_fis_bytes: bytes,
    lpcio_bytes: bytes,
    lead_time_dias: int,
    factor_seg: float,
):
    """Motor principal de análisis. Cacheable."""

    # ── 1. Ventas ─────────────────────────────────────────────
    dfs = []
    for i, b in enumerate(ventas_bytes, 1):
        df = parsear_ventas_csv(io.BytesIO(b), i)
        dfs.append(df)
    df_ventas = pd.concat(dfs, ignore_index=True)

    # ── 2. LPCIO ──────────────────────────────────────────────
    lpcio = pd.read_csv(io.BytesIO(lpcio_bytes), encoding='latin-1', sep=None, engine='python')
    lpcio['Precio_num']  = lpcio['Precio'].apply(limpiar_num)
    lpcio['Oferta_num']  = lpcio['Oferta'].apply(limpiar_num)
    lpcio['en_oferta']   = lpcio['Oferta_num'] > 0

    df_ventas = df_ventas.merge(
        lpcio[['Articulo', 'Precio_num', 'Oferta_num', 'en_oferta', 'DesFam']],
        left_on='CODIGO', right_on='Articulo', how='left'
    )
    df_ventas['PRECIO_USADO'] = df_ventas.apply(
        lambda r: r['Oferta_num'] if r['en_oferta'] and r['Oferta_num'] > 0 else r['Precio_num'], axis=1
    )
    df_ventas['UNIDADES'] = np.where(
        df_ventas['PRECIO_USADO'] > 0,
        (df_ventas['TOTAL_PESOS'] / df_ventas['PRECIO_USADO']).round(0),
        0
    )

    # ── 3. Linvalor (stock sistema) ───────────────────────────
    linvalor = pd.read_csv(io.BytesIO(linvalor_bytes), encoding='latin-1', sep=None, engine='python')
    linvalor['Pvta_num'] = linvalor['Pvta'].apply(limpiar_num)

    # ── 4. Stock físico (OPCIONAL) ───────────────────────────
    if stock_fis_bytes:
        stock_fis = pd.read_excel(io.BytesIO(stock_fis_bytes))
        stock_fis.columns = [c.strip() for c in stock_fis.columns]
        stock_fis = stock_fis.rename(columns={'exis': 'STOCK_FISICO', 'Codart': 'Codart_fis', 'Descrip': 'Descrip_fis'})
        _tiene_stock_fis = True
    else:
        stock_fis = pd.DataFrame(columns=['Codart_fis', 'STOCK_FISICO'])
        _tiene_stock_fis = False

    # ── 5. Ventas por artículo (total y por semana) ───────────
    ventas_semana = df_ventas.groupby(['CODIGO', 'DESCRIPCION', 'SEMANA'])['UNIDADES'].sum().reset_index()
    ventas_total  = df_ventas.groupby('CODIGO')['UNIDADES'].sum().reset_index().rename(columns={'UNIDADES': 'UNIDADES_MES'})
    ventas_oferta = df_ventas.groupby('CODIGO')['en_oferta'].any().reset_index().rename(columns={'en_oferta': 'EN_OFERTA'})

    # Variabilidad semanal (coef. variación)
    ventas_cv = (
        ventas_semana.groupby('CODIGO')['UNIDADES']
        .agg(['mean', 'std'])
        .reset_index()
    )
    ventas_cv['CV'] = (ventas_cv['std'] / ventas_cv['mean'].replace(0, np.nan)).fillna(0)

    # ── 6. Tabla maestra ──────────────────────────────────────
    df = linvalor[['Codart', 'Descrip', 'Uxb', 'exis', 'Pvta_num', 'CodPro', 'Proveedor']].copy()
    df = df.rename(columns={'exis': 'STOCK_SISTEMA', 'Descrip': 'DESCRIPCION'})

    if _tiene_stock_fis:
        df = df.merge(stock_fis[['Codart_fis', 'STOCK_FISICO']], left_on='Codart', right_on='Codart_fis', how='left')
        df['STOCK_FISICO'] = df['STOCK_FISICO'].fillna(df['STOCK_SISTEMA'])
    else:
        # Sin conteo físico: usar stock sistema como referencia
        df['STOCK_FISICO'] = df['STOCK_SISTEMA']

    df = df.merge(ventas_total,  left_on='Codart', right_on='CODIGO', how='left')
    df = df.merge(ventas_oferta, left_on='Codart', right_on='CODIGO', how='left')
    df = df.merge(ventas_cv[['CODIGO', 'CV']], left_on='Codart', right_on='CODIGO', how='left')

    df['UNIDADES_MES'] = df['UNIDADES_MES'].fillna(0)
    df['EN_OFERTA']    = df['EN_OFERTA'].fillna(False)
    df['CV']           = df['CV'].fillna(0)

    # ── 7. Cálculo de demanda ajustada ────────────────────────
    # Si estuvo en oferta, la demanda real es ~70% de lo vendido
    FACTOR_OFERTA = 0.70
    df['DEMANDA_AJUSTADA'] = df.apply(
        lambda r: r['UNIDADES_MES'] * FACTOR_OFERTA if r['EN_OFERTA'] else r['UNIDADES_MES'],
        axis=1
    )
    df['DEMANDA_SEMANAL'] = df['DEMANDA_AJUSTADA'] / 4

    # ── 8. Stock de seguridad y punto de reorden ──────────────
    # Stock seguridad = demanda diaria × lead_time × factor
    df['DEMANDA_DIARIA']    = df['DEMANDA_AJUSTADA'] / 30
    df['STOCK_SEGURIDAD']   = (df['DEMANDA_DIARIA'] * lead_time_dias * factor_seg).round(0)
    df['PUNTO_REORDEN']     = (df['DEMANDA_DIARIA'] * lead_time_dias + df['STOCK_SEGURIDAD']).round(0)

    # ── 9. Recomendación de compra ────────────────────────────
    # Cuánto comprar para cubrir 30 días + stock de seguridad
    df['STOCK_REAL'] = df['STOCK_FISICO'].clip(lower=0)  # ignorar negativos del sistema
    df['NECESIDAD_30D'] = (df['DEMANDA_AJUSTADA'] * 1.0 + df['STOCK_SEGURIDAD']).round(0)
    df['A_PEDIR_UNIDADES'] = (df['NECESIDAD_30D'] - df['STOCK_REAL']).clip(lower=0).round(0)

    # Redondear a bultos
    df['Uxb'] = df['Uxb'].fillna(1).replace(0, 1)
    df['A_PEDIR_BULTOS'] = np.ceil(df['A_PEDIR_UNIDADES'] / df['Uxb']).astype(int)
    df['A_PEDIR_UNIDADES_REAL'] = df['A_PEDIR_BULTOS'] * df['Uxb']

    # ── 10. Clasificación ABC ─────────────────────────────────
    df_sorted = df.sort_values('DEMANDA_AJUSTADA', ascending=False).copy()
    df_sorted['ACUM_PCT'] = df_sorted['DEMANDA_AJUSTADA'].cumsum() / max(df_sorted['DEMANDA_AJUSTADA'].sum(), 1) * 100
    df_sorted['ABC'] = pd.cut(df_sorted['ACUM_PCT'], bins=[0, 80, 95, 100], labels=['A', 'B', 'C'])
    df = df.merge(df_sorted[['Codart', 'ABC']], on='Codart', how='left')

    # ── 11. Diagnósticos de sobrestock / vencimiento ──────────
    # Días de cobertura con stock actual
    df['DIAS_COBERTURA'] = np.where(
        df['DEMANDA_DIARIA'] > 0,
        (df['STOCK_REAL'] / df['DEMANDA_DIARIA']).round(0),
        999  # sin demanda = cobertura "infinita"
    )

    df['ALERTA'] = 'OK'
    df.loc[df['STOCK_REAL'] <= 0, 'ALERTA'] = 'QUIEBRE'
    df.loc[(df['STOCK_REAL'] > 0) & (df['STOCK_REAL'] <= df['PUNTO_REORDEN']), 'ALERTA'] = 'REORDEN'
    df.loc[df['DIAS_COBERTURA'] > 60, 'ALERTA'] = 'SOBRESTOCK'
    df.loc[(df['DIAS_COBERTURA'] > 90) & (df['UNIDADES_MES'] < 5), 'ALERTA'] = 'RIESGO_VENCIMIENTO'
    # Quiebre tiene prioridad
    df.loc[df['STOCK_REAL'] <= 0, 'ALERTA'] = 'QUIEBRE'

    # Discrepancia sistema vs físico
    df['DISCREPANCIA'] = df['STOCK_FISICO'] - df['STOCK_SISTEMA']
    df['DISCREPANCIA_PCT'] = np.where(
        df['STOCK_SISTEMA'] != 0,
        ((df['DISCREPANCIA'] / df['STOCK_SISTEMA'].abs()) * 100).round(1),
        0
    )

    return df, df_ventas, ventas_semana, lpcio


def groq_analizar(prompt: str, api_key: str) -> str:
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 800,
                "temperature": 0.4,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"_(IA no disponible: {e})_"


def fmt_num(n, decimals=0):
    try:
        if decimals == 0:
            return f"{int(n):,}".replace(",", ".")
        return f"{float(n):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return str(n)


# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 📦 Quiebres & Stock")
    st.markdown("---")

    st.markdown("### 📂 Archivos de ventas")
    up_s1 = st.file_uploader("Semana 1", type=["csv","txt"], key="s1")
    up_s2 = st.file_uploader("Semana 2", type=["csv","txt"], key="s2")
    up_s3 = st.file_uploader("Semana 3", type=["csv","txt"], key="s3")
    up_s4 = st.file_uploader("Semana 4", type=["csv","txt"], key="s4")

    st.markdown("### 📊 Archivos de stock")
    up_linvalor  = st.file_uploader("Linvalor (stock sistema)",  type=["csv","txt"], key="lv")
    up_stock_fis = st.file_uploader("Stock físico conteo (opcional)", type=["xlsx","xls"], key="sf",
                                    help="Si no cargás este archivo se usa el stock sistema como referencia")
    if not up_stock_fis:
        st.caption("⚠ Sin conteo físico — usando stock sistema")
    up_lpcio     = st.file_uploader("LPCIO (precios y ofertas)", type=["csv","txt"], key="lp")

    st.markdown("### ⚙️ Parámetros")
    lead_time = st.slider("Lead time proveedor (días)", 3, 21, 7)
    factor_seg = st.slider("Factor de seguridad", 1.0, 1.5, 1.2, 0.05,
                           help="1.2 = 20% de colchón sobre la demanda proyectada")
    mes_label = st.selectbox("Mes analizado", ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                                                "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"],
                              index=1)
    st.markdown("---")
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        st.success("✅ IA activa")
    else:
        groq_key = st.text_input("GROQ API Key", type="password")

    analizar_btn = st.button("🔍 Analizar", use_container_width=True, type="primary")

    st.markdown("---")
    if st.button("🛑  Cerrar este dashboard", use_container_width=True):
        import os, signal
        st.warning("Cerrando servidor Streamlit...")
        os.kill(os.getpid(), signal.SIGTERM)


# ══════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════

st.markdown(f"""
<div style="background:linear-gradient(135deg,#0F1923 0%,#1A2535 100%);border-radius:12px;padding:28px 36px;margin-bottom:28px;position:relative;overflow:hidden;">
    <div style="position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,transparent,#1E5FD4,#00C2A8,transparent);"></div>
    <h1 style="font-size:1.6rem;font-weight:700;color:#F0F4FF;margin:0 0 4px 0;">📦 Análisis de Quiebres & Sobrestock</h1>
    <p style="color:#CBD5E1;font-size:0.85rem;margin:0;">Motor de recomendación de compras · Lead time {lead_time}d · Factor seguridad ×{factor_seg} · {mes_label}</p>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# ESTADO — esperar archivos
# ══════════════════════════════════════════════════════════════

# Stock físico es OPCIONAL — los demás son requeridos
archivos_ok = all([up_s1, up_s2, up_s3, up_s4, up_linvalor, up_lpcio])

if not archivos_ok:
    faltantes = []
    if not up_s1: faltantes.append("Semana 1")
    if not up_s2: faltantes.append("Semana 2")
    if not up_s3: faltantes.append("Semana 3")
    if not up_s4: faltantes.append("Semana 4")
    if not up_linvalor:  faltantes.append("Linvalor")
    if not up_lpcio:     faltantes.append("LPCIO")
    # Stock físico NO es obligatorio — no va en faltantes

    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("""
        <div style="background:#FFFFFF;border:1px dashed #1e3a5f;border-radius:12px;padding:48px;text-align:center;margin-top:40px;">
            <div style="font-size:3rem;margin-bottom:16px;">📂</div>
            <div style="color:#1A1D23;font-size:1.1rem;font-weight:500;margin-bottom:8px;">Cargá los archivos en el panel lateral</div>
            <div style="color:#5A6070;font-size:0.82rem;line-height:1.8;">
                4 semanas de ventas (CSV del sistema)<br>
                Linvalor — stock sistema (CSV)<br>
                Stock físico conteo (Excel) — <i>opcional</i><br>
                LPCIO — precios y ofertas (CSV)
            </div>
        </div>
        """, unsafe_allow_html=True)
        if faltantes:
            st.markdown(f"<div style='text-align:center;margin-top:16px;color:#ef4444;font-size:0.8rem;'>Faltan: {', '.join(faltantes)}</div>", unsafe_allow_html=True)
    st.stop()


# ══════════════════════════════════════════════════════════════
# PROCESAMIENTO
# ══════════════════════════════════════════════════════════════

with st.spinner("Procesando datos..."):
    ventas_bytes = [up_s1.read(), up_s2.read(), up_s3.read(), up_s4.read()]
    df, df_ventas_raw, ventas_semana, lpcio = procesar_datos(
        ventas_bytes=ventas_bytes,
        linvalor_bytes=up_linvalor.read(),
        stock_fis_bytes=up_stock_fis.read() if up_stock_fis else None,
        lpcio_bytes=up_lpcio.read(),
        lead_time_dias=lead_time,
        factor_seg=factor_seg,
    )


# ══════════════════════════════════════════════════════════════
# KPIs
# ══════════════════════════════════════════════════════════════

n_total        = len(df)
n_quiebre      = (df['ALERTA'] == 'QUIEBRE').sum()
n_reorden      = (df['ALERTA'] == 'REORDEN').sum()
n_sobrestock   = (df['ALERTA'].isin(['SOBRESTOCK','RIESGO_VENCIMIENTO'])).sum()
n_ok           = (df['ALERTA'] == 'OK').sum()
total_compra   = (df['A_PEDIR_BULTOS'] * df['Pvta_num'] * df['Uxb']).sum()
discr_grandes  = (df['DISCREPANCIA'].abs() > 10).sum()

def _kpi_card(col, label, value, sub, color):
    col.markdown(f"""
<div style="background:#FFFFFF;border:1px solid #E2E6EE;border-radius:12px;
            padding:18px 20px 14px;box-shadow:0 2px 12px rgba(0,0,0,0.07);
            position:relative;overflow:hidden;height:110px;">
  <div style="position:absolute;bottom:0;left:0;right:0;height:3px;background:{color};"></div>
  <div style="font-size:0.68rem;color:#9AA0AD;text-transform:uppercase;
              letter-spacing:1px;font-weight:600;margin-bottom:6px;">{label}</div>
  <div style="font-size:1.9rem;font-weight:700;color:#1A1D23;
              font-family:'JetBrains Mono',monospace;line-height:1.1;">{value}</div>
  <div style="font-size:0.72rem;color:#5A6070;margin-top:4px;">{sub}</div>
</div>""", unsafe_allow_html=True)

_k1, _k2, _k3, _k4, _k5 = st.columns(5)
_kpi_card(_k1, "🔴 Quiebres",          n_quiebre,                  "Stock en cero · urgente",    "#E84855")
_kpi_card(_k2, "🟡 Punto de reorden",  n_reorden,                  "Stock bajo · pedir ya",      "#F4A228")
_kpi_card(_k3, "⚠️ Sobrestock/venc.",  n_sobrestock,               "+60 días cobertura",         "#F4A228")
_kpi_card(_k4, "💰 Inversión estimada",f"$ {fmt_num(total_compra)}","Pedido recomendado",         "#1E5FD4")
_kpi_card(_k5, "📦 Total artículos",   n_total,                    "En el análisis",             "#00C2A8")


# ══════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📋 Recomendación de compra",
    "🔴 Alertas críticas",
    "📈 Comportamiento semanal",
    "🔍 Discrepancias de stock",
    "🤖 Análisis IA",
    "🔮 Predicción de Quiebres",
    "🚨 Anomalías ML",
])


# ── TAB 1: RECOMENDACIÓN DE COMPRA ────────────────────────────
with tab1:
    st.markdown(f"#### 📋 Recomendación de compra — {mes_label}")

    # Tabla con todas las columnas relevantes
    df_tabla = df[[
        'Codart', 'DESCRIPCION', 'ABC',
        'STOCK_SISTEMA', 'STOCK_FISICO', 'DISCREPANCIA',
        'UNIDADES_MES', 'DEMANDA_AJUSTADA', 'EN_OFERTA',
        'DIAS_COBERTURA', 'PUNTO_REORDEN',
        'A_PEDIR_BULTOS', 'A_PEDIR_UNIDADES_REAL', 'ALERTA'
    ]].copy()

    df_tabla['EN_OFERTA'] = df_tabla['EN_OFERTA'].map({True: '🏷️ Sí', False: '—'})
    df_tabla['ALERTA_LABEL'] = df_tabla['ALERTA'].map({
        'QUIEBRE':           '🔴 QUIEBRE',
        'REORDEN':           '🟡 REORDEN',
        'SOBRESTOCK':        '🟠 SOBRESTOCK',
        'RIESGO_VENCIMIENTO':'⚠️ RIESGO VTO',
        'OK':                '✅ OK',
    })
    df_tabla['DIAS_COBERTURA'] = df_tabla['DIAS_COBERTURA'].apply(lambda x: '∞' if x == 999 else f"{int(x)}d")

    # Ordenar: quiebres primero, luego reorden, luego ABC
    orden_alerta = {'QUIEBRE': 0, 'REORDEN': 1, 'SOBRESTOCK': 2, 'RIESGO_VENCIMIENTO': 3, 'OK': 4}
    df_tabla['_ord'] = df_tabla['ALERTA'].map(orden_alerta)
    # Impacto = días sin stock × venta diaria (pesos perdidos estimados)
    df_tabla['Impacto $'] = (
        df_tabla['DIAS_COBERTURA'].apply(lambda x: 0 if x in ['∞', 'nan'] else
                                       max(0, lead_time - int(str(x).replace('d','')))
                                       if str(x).endswith('d') else 0)
        * df_tabla.get('DEMANDA_AJUSTADA', pd.Series(0, index=df_tabla.index))
        * df.get('Pvta_num', pd.Series(1, index=df.index))
    ).fillna(0).astype(int)
    df_tabla = df_tabla.sort_values(['_ord', 'Impacto $'], ascending=[True, False]).drop(columns=['_ord', 'ALERTA'])

    df_tabla = df_tabla.rename(columns={
        'Codart': 'Cód',
        'DESCRIPCION': 'Descripción',
        'ABC': 'ABC',
        'STOCK_SISTEMA': 'Stock Sis.',
        'STOCK_FISICO': 'Stock Fís.',
        'DISCREPANCIA': 'Discr.',
        'UNIDADES_MES': 'Vtas Mes',
        'DEMANDA_AJUSTADA': 'Demanda Aj.',
        'EN_OFERTA': 'Oferta',
        'DIAS_COBERTURA': 'Cobertura',
        'PUNTO_REORDEN': 'Pto. Reorden',
        'A_PEDIR_BULTOS': 'Bultos',
        'A_PEDIR_UNIDADES_REAL': 'Unidades',
        'ALERTA_LABEL': 'Estado',
    })

    st.dataframe(df_tabla, use_container_width=True, hide_index=True, height=500)

    # Explicación del método
    with st.expander("ℹ️ ¿Cómo se calcula la recomendación?"):
        st.markdown(f"""
        **Demanda ajustada**: Si el producto estuvo en oferta, aplicamos un factor corrector del 70%
        para no sobreestimar la demanda real del mes siguiente.

        **Stock de seguridad**: `Demanda diaria × {lead_time} días lead time × {factor_seg} factor seguridad`
        El factor {factor_seg} agrega un {int((factor_seg-1)*100)}% de colchón por variabilidad en la demanda.

        **Punto de reorden**: El nivel de stock en el que hay que hacer el pedido para no quedarse sin mercadería
        mientras llega el proveedor.

        **Bultos a pedir**: `(Demanda 30 días + Stock seguridad − Stock físico actual) ÷ Unidades por bulto`
        Siempre se redondea hacia arriba para no pedir fracción de bulto.

        **Cobertura actual**: Días que alcanza el stock actual al ritmo de venta del mes analizado.
        """)

    # Exportar
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df_tabla.to_excel(writer, index=False, sheet_name='Recomendación')
        df[['Codart','DESCRIPCION','UNIDADES_MES','DEMANDA_AJUSTADA','STOCK_FISICO',
            'A_PEDIR_BULTOS','A_PEDIR_UNIDADES_REAL','ALERTA','DIAS_COBERTURA']].to_excel(
            writer, index=False, sheet_name='Datos completos')
    buf.seek(0)
    col_dl, col_pdf, col_ped = st.columns([1, 1, 1])
    with col_dl:
        st.download_button(
            "⬇️ Excel",
            data=buf.getvalue(),
            file_name=f"recomendacion_compra_{mes_label.lower()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col_pdf:
        if st.button("📄 PDF Informe", use_container_width=True, key="btn_pdf_quiebres"):
            try:
                sys.path.insert(0, str(Path(__file__).parent))
                from exportar import generar_pdf
                kpis_pdf = {
                    "🔴 Quiebres":          n_quiebre,
                    "🟡 Punto de reorden":  n_reorden,
                    "⚠️ Sobrestock":        n_sobrestock,
                    "📦 Total artículos":   n_total,
                    "💰 Inversión estimada":f"$ {fmt_num(total_compra)}",
                    "📅 Período":           mes_label,
                }
                pdf_bytes = generar_pdf(
                    df=df_tabla, kpis=kpis_pdf,
                    titulo="Reporte de Quiebres de Stock",
                    periodo=mes_label,
                )
                st.session_state["quiebres_pdf"] = pdf_bytes
                st.success("✅ PDF generado")
            except Exception as e_pdf:
                st.warning(f"PDF no disponible: {e_pdf}. Instalá reportlab o fpdf2.")
        if "quiebres_pdf" in st.session_state:
            st.download_button(
                "⬇️ PDF",
                data=st.session_state["quiebres_pdf"],
                file_name=f"quiebres_{mes_label.lower().replace(' ','_')}.pdf",
                mime="application/pdf",
                key="dl_pdf_quiebres",
                use_container_width=True,
            )
    with col_ped:
        if st.button("📦 Generar archivo de pedido (carga_*.xlsx)", type="primary", use_container_width=True):
            # Filtrar solo QUIEBRE y REORDEN con bultos > 0
            df_pedir = df[
                df['ALERTA'].isin(['QUIEBRE', 'REORDEN']) &
                (df['A_PEDIR_BULTOS'] > 0)
            ][['Codart', 'A_PEDIR_UNIDADES_REAL', 'DESCRIPCION', 'A_PEDIR_BULTOS']].copy()
            df_pedir = df_pedir.rename(columns={
                'Codart':               'SKU',
                'A_PEDIR_UNIDADES_REAL':'CANTIDAD',
                'DESCRIPCION':          'DESCRIPCION',
                'A_PEDIR_BULTOS':       'BULTOS',
            })
            if df_pedir.empty:
                st.warning("No hay artículos con quiebre o reorden que pedir.")
            else:
                # Formato compatible con Robot_Putty (Stock): SKU | CANTIDAD | ... 
                # Agregar cabecera mínima requerida por el robot
                import pandas as _pd2
                from datetime import date as _date
                id_pedido  = int(_date.today().strftime("%d%m%y"))
                obs_text   = f"PEDIDO AUTO QUIEBRES {mes_label.upper()}"
                tipo_ing   = "01"  # tipo de ingreso por defecto

                cabecera = _pd2.DataFrame([
                    ["ID_PEDIDO", "", id_pedido, ""],
                    ["OBS",       "", obs_text,   ""],
                    ["TIPO",      "", tipo_ing,   ""],
                ])
                cabecera.columns = ["SKU", "CANTIDAD", "CONFIG", "EXTRA"]

                datos_robot = df_pedir[["SKU","CANTIDAD"]].copy()
                datos_robot["CONFIG"] = ""
                datos_robot["EXTRA"]  = ""

                df_export = _pd2.concat([cabecera, datos_robot], ignore_index=True)

                buf_ped = io.BytesIO()
                with _pd2.ExcelWriter(buf_ped, engine="openpyxl") as writer:
                    df_export.to_excel(writer, index=False, sheet_name="carga_pedido")
                    df_pedir.to_excel(writer, index=False, sheet_name="detalle_legible")
                buf_ped.seek(0)

                nombre_ped = f"carga_quiebres_{mes_label.lower().replace(' ','_')}.xlsx"
                st.success(f"✅ Archivo generado: {nombre_ped} — {len(df_pedir)} artículos a pedir")
                st.download_button(
                    f"⬇️ Descargar {nombre_ped}",
                    data=buf_ped.getvalue(),
                    file_name=nombre_ped,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_pedido",
                    use_container_width=True,
                )


# ── TAB 2: ALERTAS CRÍTICAS ───────────────────────────────────
with tab2:
    col_q, col_s = st.columns(2)

    with col_q:
        st.markdown(f"#### 🔴 Quiebres y puntos de reorden")
        df_criticos = df[df['ALERTA'].isin(['QUIEBRE', 'REORDEN'])].sort_values('ALERTA')

        if len(df_criticos) == 0:
            st.success("✅ Sin quiebres ni puntos de reorden")
        else:
            for _, r in df_criticos.iterrows():
                color = "alerta-quiebre" if r['ALERTA'] == 'QUIEBRE' else "alerta-sobre"
                icono = "🔴" if r['ALERTA'] == 'QUIEBRE' else "🟡"
                motivo = (
                    f"Stock físico en <b>{int(r['STOCK_FISICO'])} unidades</b>. "
                    f"Vendés <b>{fmt_num(r['DEMANDA_AJUSTADA'])} unidades/mes</b> en promedio. "
                )
                if r['ALERTA'] == 'QUIEBRE':
                    motivo += "El producto ya no tiene stock — estás perdiendo ventas ahora mismo."
                else:
                    motivo += (
                        f"El punto de reorden es <b>{int(r['PUNTO_REORDEN'])} unidades</b>. "
                        f"Con el lead time de {lead_time} días, si no pedís ahora vas a quebrarte antes de recibir mercadería."
                    )
                if r['EN_OFERTA']:
                    motivo += " ⚠️ Estuvo en oferta — la demanda ajustada es conservadora."
                pedir = f"Pedido sugerido: <b>{int(r['A_PEDIR_BULTOS'])} bultos ({int(r['A_PEDIR_UNIDADES_REAL'])} un.)</b>"
                _bg  = "#FFF0F0" if r['ALERTA'] == 'QUIEBRE' else "#FFFBEA"
                _bdr = "#E84855" if r['ALERTA'] == 'QUIEBRE' else "#F4A228"
                st.markdown(f"""
                <div style="background:{_bg};border-left:4px solid {_bdr};border-radius:8px;padding:0.8rem 1rem;margin:0.3rem 0;font-size:0.88rem;">
                    <div style="font-weight:700;color:#1A1D23;font-size:0.9rem;margin-bottom:4px;">{icono} {r['DESCRIPCION']} <span style="color:#5A6070;font-size:0.75rem;">· {r['ABC'] or '—'}</span></div>
                    <div style="color:#5A6070;font-size:0.8rem;line-height:1.5;">{motivo}</div>
                    <div style="color:#1A1D23;font-size:0.8rem;margin-top:6px;">{pedir}</div>
                </div>
                """, unsafe_allow_html=True)

    with col_s:
        st.markdown(f"#### ⚠️ Sobrestock y riesgo de vencimiento")
        df_sobre = df[df['ALERTA'].isin(['SOBRESTOCK', 'RIESGO_VENCIMIENTO'])].sort_values('DIAS_COBERTURA', ascending=False)

        if len(df_sobre) == 0:
            st.success("✅ Sin productos con sobrestock")
        else:
            for _, r in df_sobre.iterrows():
                dias = int(r['DIAS_COBERTURA']) if r['DIAS_COBERTURA'] != 999 else None
                icono = "⚠️" if r['ALERTA'] == 'RIESGO_VENCIMIENTO' else "🟠"
                cobertura_txt = f"{dias} días" if dias else "sin demanda"

                if r['ALERTA'] == 'RIESGO_VENCIMIENTO':
                    motivo = (
                        f"Cobertura actual: <b>{cobertura_txt}</b>. "
                        f"Vendiste solo <b>{fmt_num(r['UNIDADES_MES'])} unidades</b> en el mes con casi <b>{fmt_num(r['STOCK_FISICO'])} unidades</b> en stock. "
                        f"A este ritmo el producto puede vencer antes de venderse. "
                        f"<b>No pedir.</b> Considerar promoción o devolución al proveedor."
                    )
                else:
                    motivo = (
                        f"Cobertura actual: <b>{cobertura_txt}</b>. "
                        f"Tenés <b>{fmt_num(r['STOCK_FISICO'])} unidades</b> y vendés "
                        f"<b>{fmt_num(r['DEMANDA_AJUSTADA'])} unidades/mes</b>. "
                        f"El stock actual cubre más de 2 meses. <b>No pedir hasta que baje al punto de reorden "
                        f"({int(r['PUNTO_REORDEN'])} unidades).</b>"
                    )
                st.markdown(f"""
                <div style="background:#EFF6FF;border-left:4px solid #1E5FD4;border-radius:8px;padding:0.8rem 1rem;margin:0.3rem 0;font-size:0.88rem;">
                    <div style="font-weight:700;color:#1A1D23;font-size:0.9rem;margin-bottom:4px;">{icono} {r['DESCRIPCION']}</div>
                    <div style="color:#5A6070;font-size:0.8rem;line-height:1.5;">{motivo}</div>
                </div>
                """, unsafe_allow_html=True)


# ── TAB 3: COMPORTAMIENTO SEMANAL ─────────────────────────────
with tab3:
    st.markdown(f"#### 📈 Ventas semana a semana")

    # Selector de producto
    productos_disponibles = df[df['UNIDADES_MES'] > 0].sort_values('DEMANDA_AJUSTADA', ascending=False)['DESCRIPCION'].tolist()
    prod_sel = st.multiselect(
        "Seleccioná productos para comparar",
        options=productos_disponibles,
        default=productos_disponibles[:5],
        max_selections=10,
    )

    if prod_sel:
        codigos_sel = df[df['DESCRIPCION'].isin(prod_sel)]['Codart'].tolist()
        vs_filtrado = ventas_semana[ventas_semana['CODIGO'].isin(codigos_sel)].copy()
        # Evitar colisión de nombre si ventas_semana ya tiene DESCRIPCION
        if 'DESCRIPCION' in vs_filtrado.columns:
            vs_filtrado = vs_filtrado.drop(columns=['DESCRIPCION'])
        vs_filtrado = vs_filtrado.merge(df[['Codart','DESCRIPCION']], left_on='CODIGO', right_on='Codart', how='left')

        fig = px.line(
            vs_filtrado,
            x='SEMANA', y='UNIDADES', color='DESCRIPCION',
            markers=True,
            labels={'SEMANA': 'Semana', 'UNIDADES': 'Unidades vendidas', 'DESCRIPCION': ''},
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig.update_layout(
            paper_bgcolor='#F0F2F5', plot_bgcolor='#FFFFFF',
            font_color='#5A6070',
            legend=dict(bgcolor='#FFFFFF', bordercolor='#E2E6EE'),
            xaxis=dict(tickvals=[1,2,3,4], ticktext=['Sem 1','Sem 2','Sem 3','Sem 4'],
                       gridcolor='#E2E6EE'),
            yaxis=dict(gridcolor='#E2E6EE'),
            height=380,
        )
        st.plotly_chart(fig, use_container_width=True)

    # Gráfico de productos en oferta vs no oferta
    st.markdown(f"#### 🏷️ Impacto de ofertas en la demanda")

    df_oferta_cmp = df[df['UNIDADES_MES'] > 0].copy()
    df_oferta_cmp['Tipo'] = df_oferta_cmp['EN_OFERTA'].map({True: 'En oferta', False: 'Precio normal'})

    fig2 = px.bar(
        df_oferta_cmp.nlargest(20, 'UNIDADES_MES'),
        x='DESCRIPCION', y=['UNIDADES_MES', 'DEMANDA_AJUSTADA'],
        barmode='group',
        labels={'value': 'Unidades', 'variable': '', 'DESCRIPCION': ''},
        color_discrete_map={'UNIDADES_MES': '#3b82f6', 'DEMANDA_AJUSTADA': '#10b981'},
    )
    fig2.update_layout(
        paper_bgcolor='#F0F2F5', plot_bgcolor='#FFFFFF',
        font_color='#5A6070',
        xaxis_tickangle=-45,
        xaxis=dict(gridcolor='#E2E6EE'),
        yaxis=dict(gridcolor='#E2E6EE'),
        height=380,
        legend=dict(bgcolor='#FFFFFF'),
    )
    fig2.data[0].name = 'Ventas reales'
    fig2.data[1].name = 'Demanda ajustada (sin efecto oferta)'
    st.plotly_chart(fig2, use_container_width=True)

    with st.expander("ℹ️ ¿Por qué se ajusta la demanda en ofertas?"):
        st.markdown("""
        Cuando un producto está en oferta, la gente compra más de lo habitual — stockeándose o
        aprovechando el precio. Ese pico de venta **no refleja la demanda real** del mes siguiente
        si ya no está en oferta.

        Aplicamos un factor del **70%** sobre las ventas de los productos en oferta para estimar
        cuánto se vendería en condiciones normales. Así el pedido del próximo mes no se sobreestima
        y no terminás con sobrestock.
        """)


# ── TAB 4: DISCREPANCIAS DE STOCK ─────────────────────────────
with tab4:
    st.markdown(f"#### 🔍 Stock sistema vs conteo físico")

    df_disc = df[['Codart','DESCRIPCION','STOCK_SISTEMA','STOCK_FISICO','DISCREPANCIA','DISCREPANCIA_PCT']].copy()
    df_disc = df_disc.sort_values('DISCREPANCIA', key=abs, ascending=False)

    # Gráfico
    colores = ['#ef4444' if x < 0 else '#10b981' for x in df_disc['DISCREPANCIA']]
    fig3 = go.Figure(go.Bar(
        x=df_disc['DESCRIPCION'],
        y=df_disc['DISCREPANCIA'],
        marker_color=colores,
        text=df_disc['DISCREPANCIA'].apply(lambda x: f"+{int(x)}" if x > 0 else str(int(x))),
        textposition='outside',
    ))
    fig3.update_layout(
        title=dict(text="Diferencia: Conteo físico − Stock sistema", font=dict(color='#5A6070', size=13)),
        paper_bgcolor='#F0F2F5', plot_bgcolor='#FFFFFF',
        font_color='#5A6070',
        xaxis_tickangle=-45,
        xaxis=dict(gridcolor='#E2E6EE'),
        yaxis=dict(gridcolor='#E2E6EE', title='Unidades de diferencia'),
        height=400,
        shapes=[dict(type='line', x0=-0.5, x1=len(df_disc)-0.5, y0=0, y1=0,
                     line=dict(color='#475569', width=1, dash='dash'))],
    )
    st.plotly_chart(fig3, use_container_width=True)

    # Tabla
    st.dataframe(
        df_disc.rename(columns={
            'Codart': 'Cód',
            'DESCRIPCION': 'Descripción',
            'STOCK_SISTEMA': 'Stock Sistema',
            'STOCK_FISICO': 'Stock Físico',
            'DISCREPANCIA': 'Diferencia (un.)',
            'DISCREPANCIA_PCT': 'Diferencia (%)',
        }),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("ℹ️ ¿Qué significa la discrepancia?"):
        st.markdown("""
        **Diferencia positiva** (verde): El conteo físico encontró **más stock** del que dice el sistema.
        Puede ser mercadería recibida sin registrar, devoluciones no procesadas, o errores de carga.

        **Diferencia negativa** (rojo): El sistema dice que hay más de lo que encontraste.
        Puede ser merma, rotura, vencimiento no dado de baja, o faltante por hurto.

        **¿Cuál usamos para el pedido?** El conteo físico siempre. Es la realidad del depósito.
        El sistema puede estar desactualizado — por eso los valores negativos (stock sistema negativo)
        se corrigen automáticamente a cero en el cálculo de pedidos.
        """)


# ── TAB 5: ANÁLISIS IA ────────────────────────────────────────
with tab5:
    st.markdown(f"#### 🤖 Resumen ejecutivo con IA")

    if not groq_key:
        st.info("Ingresá tu GROQ API Key en el panel lateral para activar el análisis IA.")
    else:
        if st.button("Generar análisis IA", type="primary") or 'ia_analisis_quiebres' in st.session_state:
            if 'ia_analisis_quiebres' not in st.session_state:
                with st.spinner("Analizando con IA..."):
                    # Construir resumen para la IA
                    quiebres = df[df['ALERTA']=='QUIEBRE'][['DESCRIPCION','STOCK_FISICO','DEMANDA_AJUSTADA','A_PEDIR_BULTOS']].to_dict('records')
                    reorden  = df[df['ALERTA']=='REORDEN'][['DESCRIPCION','STOCK_FISICO','DIAS_COBERTURA','A_PEDIR_BULTOS']].to_dict('records')
                    sobre    = df[df['ALERTA'].isin(['SOBRESTOCK','RIESGO_VENCIMIENTO'])][['DESCRIPCION','DIAS_COBERTURA','UNIDADES_MES']].to_dict('records')
                    top5     = df.nlargest(5,'DEMANDA_AJUSTADA')[['DESCRIPCION','DEMANDA_AJUSTADA','ABC']].to_dict('records')

                    prompt = f"""Sos el analista de compras de un distribuidor de alimentos argentino.
Analizás el stock y las ventas de {mes_label} del proveedor Trio (galletitas).

QUIEBRES ACTUALES ({len(quiebres)} productos sin stock):
{quiebres}

PUNTOS DE REORDEN ({len(reorden)} productos):
{reorden}

SOBRESTOCK / RIESGO VENCIMIENTO ({len(sobre)} productos):
{sobre}

TOP 5 PRODUCTOS POR DEMANDA:
{top5}

Lead time del proveedor: {lead_time} días.
Factor de seguridad aplicado: {factor_seg}.

Escribí un resumen ejecutivo en español con:
1. Situación crítica inmediata (qué hacer HOY)
2. Productos con sobrestock y qué riesgo representan
3. Recomendación general de pedido
4. Una observación sobre el comportamiento de ventas

Sé directo y concreto. Usa pesos argentinos. Sin mencionar dólares. Máximo 400 palabras."""

                    st.session_state['ia_analisis_quiebres'] = groq_analizar(prompt, groq_key)

            st.markdown(f"""
            <div style="background:#FFFFFF;border:1px solid #1e3a5f;border-radius:10px;padding:24px;line-height:1.8;color:#1A1D23;font-size:0.88rem;white-space:pre-wrap;">
{st.session_state['ia_analisis_quiebres']}
            </div>
            """, unsafe_allow_html=True)

            if st.button("🔄 Regenerar análisis"):
                del st.session_state['ia_analisis_quiebres']
                st.rerun()

# ── TAB 6: PREDICCIÓN DE QUIEBRES ─────────────────────────────
with tab6:
    st.markdown("#### 🔮 Predicción de Quiebres — próximos 30 días")
    st.caption("Combina stock actual, demanda histórica y tendencia para anticipar quiebres antes de que ocurran.")

    if not _PRED_OK:
        st.warning("Módulo de predicción no disponible. Verificá la instalación.")
    else:
        col_p1, col_p2 = st.columns([2, 1])
        with col_p1:
            lead_pred = st.slider("Lead time días (para calcular riesgo)", 3, 21, lead_time, key="lead_pred")
        with col_p2:
            if st.button("💾 Guardar snapshot de ventas actuales", key="btn_snap"):
                try:
                    # Mapear mes_label a un entero seguro
                    meses_map = {"Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6,
                                 "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12}
                    mes_num = meses_map.get(mes_label, 1)
                    import datetime
                    guardar_snapshot_ventas(df, mes=mes_num, anio=datetime.date.today().year)
                    st.success("✅ Snapshot guardado. Usalo próximo mes para mejorar la predicción.")
                except Exception as e_snap:
                    st.error(f"Error: {e_snap}")

        hist = cargar_historial_ventas()
        if not hist:
            st.info("📊 Sin historial aún. Cargá datos de al menos 2 meses y guardá snapshots con el botón de arriba.")
            st.markdown("**Mientras tanto, predicción basada en demanda actual:**")

        df_pred = run_predictions(df, lead_pred)
        
        if df_pred.empty:
            st.info("Sin datos para predecir.")
        else:
            # KPIs predicción
            n_alto  = (df_pred["Riesgo 30d"] == "🔴 ALTO").sum()
            n_medio = (df_pred["Riesgo 30d"] == "🟡 MEDIO").sum()
            n_ok    = (df_pred["Riesgo 30d"].isin(["🟢 BAJO", "⚪ OK"])).sum()

            pa, pb, pc = st.columns(3)
            pa.metric("🔴 Riesgo alto",  n_alto,  help=f"Cobertura < {lead_pred} días")
            pb.metric("🟡 Riesgo medio", n_medio, help="Cobertura < 30 días")
            pc.metric("✅ Sin riesgo",   n_ok)

            # Filtro
            riesgo_filt = st.selectbox("Filtrar por riesgo", 
                                        ["Todos", "🔴 ALTO", "🟡 MEDIO", "🟢 BAJO"], key="pred_riesgo")
            df_show = df_pred if riesgo_filt == "Todos" else df_pred[df_pred["Riesgo 30d"] == riesgo_filt]
            st.dataframe(df_show, use_container_width=True, height=420, hide_index=True)

            # Exportar
            buf_pred = io.BytesIO()
            df_pred.to_excel(buf_pred, index=False, engine="openpyxl")
            buf_pred.seek(0)
            st.download_button("⬇️ Exportar predicción", data=buf_pred.getvalue(),
                               file_name="prediccion_quiebres.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="dl_pred")

# ── TAB 7: ANOMALÍAS ML ──────────────────────────────────────────────
with tab7:
    st.markdown("#### 🚨 Detección de Anomalías (Isolation Forest)")
    st.caption("Identifica automáticamente productos con comportamientos extremos o atípicos (outliers) entre sus ventas y su stock.")

    if not _SKLEARN_OK:
        st.warning("La librería scikit-learn no está instalada. Ejecutá `pip install scikit-learn` para usar esta función.")
    elif len(df) < 10:
        st.info("Se necesitan al menos 10 productos para detectar anomalías con precisión.")
    else:
        df_ml = run_anomaly_detection(df)

        if df_ml.empty:
            st.info("No se pudo ejecutar el modelo de anomalías.")
        else:
            # Para visualización logarítmica en Plotly sin perder los valores "0"
            # Este cálculo es rápido y puede quedar fuera de la función cacheada
            df_ml['plot_x'] = df_ml['UNIDADES_MES'].clip(lower=1)
            df_ml['plot_y'] = df_ml['STOCK_FISICO'].clip(lower=1)
            df_ml['Puntos'] = df_ml['DEMANDA_AJUSTADA'].clip(lower=2)

            # Gráfico interactivo con Plotly
            fig_ml = px.scatter(
                df_ml,
                x='plot_x',
                y='plot_y',
                color='Segmento ML',
                size='Puntos',
                hover_name='DESCRIPCION',
                hover_data={'Codart': True, 'UNIDADES_MES': ':.0f', 'STOCK_FISICO': ':.0f', 'Segmento ML': False, 'Puntos': False, 'outlier': False, 'plot_x': False, 'plot_y': False},
                color_discrete_map={
                    "🔴 Anomalía Extrema": "#ef4444",
                    "🔵 Comportamiento Normal": "#94a3b8"
                },
                title="Detección de Outliers (Isolation Forest)"
            )

            fig_ml.update_layout(
                paper_bgcolor='#F0F2F5', plot_bgcolor='#FFFFFF',
                height=550,
                xaxis=dict(type='log', title="Unidades Vendidas (Escala Log)", gridcolor='#E2E6EE'),
                yaxis=dict(type='log', title="Stock Físico (Escala Log)", gridcolor='#E2E6EE'),
                legend=dict(title="Análisis", orientation="h", y=-0.15)
            )

            st.plotly_chart(fig_ml, use_container_width=True)

            st.markdown("##### 📋 Resumen del Análisis")
            resumen_ml = df_ml.groupby('Segmento ML').agg(
                SKUs=('Codart', 'count'),
                Stock_Promedio=('STOCK_FISICO', 'mean'),
                Venta_Promedio=('UNIDADES_MES', 'mean')
            ).reset_index()

            resumen_ml['Stock_Promedio'] = resumen_ml['Stock_Promedio'].apply(lambda x: f"{x:,.0f} un.")
            resumen_ml['Venta_Promedio'] = resumen_ml['Venta_Promedio'].apply(lambda x: f"{x:,.0f} un.")

            st.dataframe(resumen_ml, use_container_width=True, hide_index=True)
