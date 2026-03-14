"""
dashboards/cxc_dashboard.py — RPA Suite v5.9
==============================================
Dashboard de Cuentas por Cobrar.
Puerto: 8505
Lanzar: streamlit run dashboards/cxc_dashboard.py --server.port 8505
"""
import streamlit as st
import sys
from pathlib import Path
import io
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

st.set_page_config(
    page_title="CxC — RPA Suite",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""<style>
[data-testid="stAppViewContainer"]{background:#F8FAFC;}
.kpi-card{background:#fff;border:1px solid #E2E8F0;border-radius:12px;
          padding:16px 20px;box-shadow:0 2px 8px rgba(0,0,0,0.05);margin-bottom:8px;}
.kpi-val{font-size:1.8rem;font-weight:700;color:#1A1D23;font-family:monospace;}
.kpi-lbl{font-size:0.72rem;color:#9AA0AD;text-transform:uppercase;letter-spacing:1px;}
</style>""", unsafe_allow_html=True)

try:
    from robots.robot_cxc import procesar_cxc, exportar_cxc_excel
    _CXC_OK = True
except ImportError as e:
    _CXC_OK = False
    st.error(f"Error importando módulo CxC: {e}")

# ── Sidebar ──
with st.sidebar:
    st.markdown("## 💳 Cuentas por Cobrar")
    st.caption("RPA Suite v5.9")
    st.markdown("---")
    archivo = st.file_uploader("📂 Archivo Excel de CxC", type=["xlsx","xls"])
    fecha_corte = st.date_input("📅 Fecha de corte", value=date.today())
    st.markdown("---")
    st.markdown("**Formato esperado:**")
    st.caption("Columnas: CLIENTE, FECHA_VENCIMIENTO, IMPORTE")
    st.caption("Opcional: CUIT, COMPROBANTE, SUCURSAL")

if not _CXC_OK:
    st.stop()

if archivo is None:
    st.markdown("""
    <div style="text-align:center;padding:4rem;color:#6B7280;">
    <div style="font-size:4rem;">💳</div>
    <h2>Cuentas por Cobrar</h2>
    <p>Subí el Excel de deudores en el panel izquierdo para comenzar.</p>
    <p style="font-size:0.85rem;">Columnas mínimas: <code>CLIENTE</code>, <code>FECHA_VENCIMIENTO</code>, <code>IMPORTE</code></p>
    </div>""", unsafe_allow_html=True)
    st.stop()

# Guardar archivo temporalmente
import tempfile, os
with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
    tmp.write(archivo.read())
    tmp_path = tmp.name

def _log_st(m): pass  # streamlit no usa log_func

resultado = procesar_cxc(tmp_path, fecha_corte=fecha_corte)
os.unlink(tmp_path)

if "error" in resultado:
    st.error(f"❌ {resultado['error']}")
    st.stop()

df_ag  = resultado["df_aging"]
df_cli = resultado["df_clientes"]
res    = resultado["resumen"]

# ── KPIs ──
st.markdown(f"## 💳 Cartera al {fecha_corte.strftime('%d/%m/%Y')}")

k1, k2, k3, k4, k5 = st.columns(5)
def _kpi(col, label, val, color="#1A1D23"):
    col.markdown(f"""<div class="kpi-card">
    <div class="kpi-val" style="color:{color}">{val}</div>
    <div class="kpi-lbl">{label}</div></div>""", unsafe_allow_html=True)

_kpi(k1, "Total Cartera",  f"${resultado['total_cartera']:,.0f}")
_kpi(k2, "Total Vencido",  f"${resultado['total_vencido']:,.0f}", "#DC2626")
_kpi(k3, "% Vencido",      f"{resultado['pct_vencido']}%",
     "#DC2626" if resultado['pct_vencido'] > 30 else "#F59E0B")
_kpi(k4, "Facturas",       f"{resultado['n_facturas']:,}")
_kpi(k5, "Clientes",       f"{resultado['n_clientes']:,}")

st.markdown("---")

# ── Tabs ──
tab1, tab2, tab3 = st.tabs(["📊 Aging", "👥 Por Cliente", "⚠️ Alertas"])

with tab1:
    st.markdown("#### 📊 Distribución de Aging")

    # Resumen por banda
    import pandas as pd
    df_res = pd.DataFrame([
        {"Banda": b, "Total $": d["total"], "Facturas": d["facturas"], "Clientes": d["clientes"]}
        for b, d in sorted(res.items())
    ])
    if not df_res.empty:
        try:
            import plotly.express as px
            fig = px.pie(df_res, values="Total $", names="Banda",
                         color_discrete_sequence=["#16A34A","#EAB308","#F97316","#DC2626","#7F1D1D"],
                         hole=0.45)
            fig.update_layout(margin=dict(l=0,r=0,t=10,b=0), height=280,
                               legend=dict(font=dict(size=10)))
            col_g, col_t = st.columns([1,1])
            col_g.plotly_chart(fig, use_container_width=True)
            col_t.dataframe(df_res, use_container_width=True, hide_index=True)
        except ImportError:
            st.dataframe(df_res, use_container_width=True, hide_index=True)

    st.markdown("#### 📋 Detalle de facturas")
    filtro_banda = st.selectbox("Filtrar banda",
                                 ["Todas"] + list(res.keys()), key="banda_flt")
    filtro_cli   = st.text_input("Buscar cliente", key="cli_search")

    df_show = df_ag.copy()
    if filtro_banda != "Todas":
        df_show = df_show[df_show["BANDA"] == filtro_banda]
    if filtro_cli:
        df_show = df_show[df_show["CLIENTE"].str.contains(filtro_cli, case=False, na=False)]

    st.dataframe(df_show, use_container_width=True, height=400, hide_index=True)

with tab2:
    st.markdown("#### 👥 Ranking de clientes por saldo")
    umbral = st.slider("Mostrar clientes con saldo mayor a $", 0, 100000, 0, step=1000)
    df_c_show = df_cli[df_cli["Saldo Total"] >= umbral] if umbral > 0 else df_cli
    st.dataframe(df_c_show, use_container_width=True, height=450, hide_index=True)

with tab3:
    st.markdown("#### ⚠️ Alertas críticas")
    alertas = resultado["alertas"]
    if not alertas:
        st.success("✅ Sin alertas críticas en la cartera")
    else:
        for a in alertas:
            st.error(a)

    st.markdown("---")
    st.markdown("**Clientes con +90 días:**")
    df_criticos = df_ag[df_ag["DIAS_MORA"] > 90].groupby("CLIENTE")["IMPORTE"].sum().reset_index()
    df_criticos.columns = ["Cliente", "Deuda +90d"]
    df_criticos = df_criticos.sort_values("Deuda +90d", ascending=False)
    if df_criticos.empty:
        st.info("Sin clientes con mora mayor a 90 días ✅")
    else:
        st.dataframe(df_criticos, use_container_width=True, hide_index=True)

# ── Exportar ──
st.markdown("---")
col_ex1, col_ex2 = st.columns(2)
with col_ex1:
    if st.button("📊 Exportar Excel CxC", type="primary", use_container_width=True):
        xl = exportar_cxc_excel(resultado)
        if xl:
            st.session_state["cxc_excel"] = xl
    if "cxc_excel" in st.session_state:
        st.download_button("⬇️ Descargar Excel",
                           data=st.session_state["cxc_excel"],
                           file_name=f"cxc_{fecha_corte.isoformat()}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="dl_cxc_xl", use_container_width=True)
with col_ex2:
    buf_simple = io.BytesIO()
    df_ag.to_excel(buf_simple, index=False, engine="openpyxl")
    buf_simple.seek(0)
    st.download_button("⬇️ Aging completo (CSV)",
                       data=df_ag.to_csv(index=False).encode("utf-8"),
                       file_name=f"aging_{fecha_corte.isoformat()}.csv",
                       mime="text/csv", use_container_width=True)
