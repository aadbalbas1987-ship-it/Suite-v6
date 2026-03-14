"""
dashboards/normalizador_dashboard.py — RPA Suite v5.9
=======================================================
Dashboard del Normalizador Ultra de Maestro de Artículos.
Puerto: 8508
"""
import streamlit as st
import sys, io, os, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

st.set_page_config(page_title="Normalizador — RPA Suite", page_icon="📋",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""<style>
[data-testid="stAppViewContainer"]{background:#F0F4F8;}
.kpi-card{background:white;border-radius:10px;padding:14px 18px;
          border:1px solid #E2E8F0;box-shadow:0 2px 6px rgba(0,0,0,.05);}
.kpi-val{font-size:1.8rem;font-weight:800;font-family:monospace;}
.kpi-lbl{font-size:0.7rem;color:#9AA0AD;text-transform:uppercase;letter-spacing:1px;}
</style>""", unsafe_allow_html=True)

try:
    from core.normalizador_maestro import procesar_maestro, exportar_maestro_excel
    _NM_OK = True
except ImportError as e:
    _NM_OK = False
    st.error(f"Módulo no disponible: {e}")

# ── Sidebar ──
with st.sidebar:
    st.markdown("## 📋 Normalizador de Maestro")
    st.caption("RPA Suite v5.9")
    st.markdown("---")
    archivo = st.file_uploader("📂 Excel de maestro de artículos",
                                type=["xlsx","xls","csv"], key="arch_norm")
    st.markdown("---")
    st.markdown("**⚙ Opciones**")
    opt_dupl  = st.checkbox("🔍 Detectar duplicados",     value=True)
    opt_ia    = st.checkbox("🤖 Clasificar familias (IA)",value=True)
    opt_barra = st.checkbox("📊 Validar EAN / códigos de barra", value=True)
    umbral_j  = st.slider("Umbral similitud duplicados (%)", 50, 95, 70) / 100

if not _NM_OK: st.stop()

if not archivo:
    st.markdown("""
    <div style="text-align:center;padding:4rem;color:#6B7280;">
    <div style="font-size:4rem;">📋</div>
    <h2>Normalizador Ultra de Maestro</h2>
    <p>Subí tu Excel de artículos para comenzar.</p>
    <ul style="text-align:left;display:inline-block;">
    <li>Normaliza descripciones y unidades</li>
    <li>Detecta duplicados por similitud semántica</li>
    <li>Clasifica en familias/subfamilias con IA</li>
    <li>Valida códigos EAN13/EAN8</li>
    </ul>
    </div>""", unsafe_allow_html=True)
    st.stop()

import pandas as pd

with tempfile.NamedTemporaryFile(suffix=Path(archivo.name).suffix, delete=False) as tmp:
    tmp.write(archivo.read())
    tmp_path = tmp.name

try:
    df_raw = pd.read_excel(tmp_path, engine="openpyxl") \
             if not archivo.name.endswith(".csv") else pd.read_csv(tmp_path)
except Exception as e:
    st.error(f"No se pudo leer el archivo: {e}")
    os.unlink(tmp_path)
    st.stop()
os.unlink(tmp_path)

st.title("📋 Normalizador de Maestro")
st.write(f"**{len(df_raw)} artículos cargados** — {len(df_raw.columns)} columnas")
st.dataframe(df_raw.head(5), use_container_width=True, hide_index=True)

# Mapeo de columnas
st.markdown("#### Mapeo de columnas")
col_opts = ["— auto —"] + list(df_raw.columns)
c1,c2,c3,c4,c5 = st.columns(5)
col_cod  = c1.selectbox("Código",      col_opts, key="nc_cod")
col_dsc  = c2.selectbox("Descripción", col_opts, key="nc_dsc")
col_fam  = c3.selectbox("Familia",     col_opts, key="nc_fam")
col_bar  = c4.selectbox("Cód. Barras", col_opts, key="nc_bar")
col_mrc  = c5.selectbox("Marca",       col_opts, key="nc_mrc")
_none = lambda v: None if v == "— auto —" else v

if st.button("🚀 Procesar maestro", type="primary", use_container_width=True):
    log_msgs = []
    with st.spinner("Procesando maestro..."):
        resultado = procesar_maestro(
            df=df_raw,
            col_codigo=_none(col_cod), col_desc=_none(col_dsc),
            col_familia=_none(col_fam), col_barras=_none(col_bar),
            col_marca=_none(col_mrc),
            clasificar_ia=opt_ia, detectar_dupl=opt_dupl, validar_barra=opt_barra,
            log_func=lambda m: log_msgs.append(m),
        )
    st.session_state["norm_resultado"] = resultado
    st.session_state["norm_log"]       = log_msgs

if "norm_resultado" in st.session_state:
    res = st.session_state["norm_resultado"]
    if "error" in res:
        st.error(res["error"])
        st.stop()

    inf = res["informe"]
    st.markdown("---")

    # KPIs
    k1,k2,k3,k4,k5 = st.columns(5)
    def _kpi(col, label, val, color="#1A1D23"):
        col.markdown(f"""<div class="kpi-card">
        <div class="kpi-val" style="color:{color}">{val}</div>
        <div class="kpi-lbl">{label}</div></div>""", unsafe_allow_html=True)

    _kpi(k1, "Total artículos",    inf["total_articulos"])
    _kpi(k2, "Desc. normalizadas", inf["descripciones_norm"], "#2563EB")
    _kpi(k3, "Duplicados",         inf["grupos_duplicados"],
         "#DC2626" if inf["grupos_duplicados"] > 0 else "#16A34A")
    _kpi(k4, "Clasificados IA",    inf.get("clasificados_ia", "—"))
    _kpi(k5, "EAN inválidos",      inf.get("ean_invalidos", "—"),
         "#DC2626" if inf.get("ean_invalidos", 0) > 0 else "#16A34A")

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["✅ Maestro limpio","⚠️ Duplicados","📝 Cambios","🏷️ Familias IA"])

    with tab1:
        df_l = res["df_limpio"]
        buscar_norm = st.text_input("🔍 Buscar artículo", key="buscar_norm")
        if buscar_norm:
            col_desc_det = next((c for c in df_l.columns if "desc" in c.lower()), df_l.columns[0])
            df_l = df_l[df_l[col_desc_det].str.contains(buscar_norm, case=False, na=False)]
        st.dataframe(df_l, use_container_width=True, height=450, hide_index=True)

    with tab2:
        duplicados = res["duplicados"]
        if not duplicados:
            st.success("✅ Sin duplicados detectados en el maestro.")
        else:
            st.warning(f"⚠️ {len(duplicados)} grupo(s) de duplicados — {inf['arts_duplicados']} artículos afectados")
            for i, grp in enumerate(duplicados, 1):
                with st.expander(f"Grupo {i} — {grp['tipo']} (score: {grp['score']:.0%}) — {len(grp['items'])} artículos"):
                    for item in grp["items"]:
                        st.markdown(f"  `{item['codigo']}` — {item['descripcion']}")

    with tab3:
        cambios = res["cambios"]
        if not cambios:
            st.info("Sin cambios aplicados.")
        else:
            st.caption(f"{len(cambios)} cambio(s) aplicados")
            df_c = pd.DataFrame(cambios)
            st.dataframe(df_c, use_container_width=True, height=350, hide_index=True)

    with tab4:
        df_l2 = res["df_limpio"]
        if "Familia_IA" in df_l2.columns:
            fam_counts = df_l2["Familia_IA"].value_counts().reset_index()
            fam_counts.columns = ["Familia", "Artículos"]
            try:
                import plotly.express as px
                fig = px.bar(fam_counts.head(15), x="Artículos", y="Familia",
                             orientation="h", color_discrete_sequence=["#1D3557"])
                fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                                  margin=dict(l=0,r=0,t=10,b=0), height=400,
                                  yaxis=dict(tickfont=dict(size=9)))
                st.plotly_chart(fig, use_container_width=True)
            except ImportError:
                st.dataframe(fam_counts, use_container_width=True, hide_index=True)
        else:
            st.info("Activá 'Clasificar familias (IA)' en el panel izquierdo.")

    # Exportar
    st.markdown("---")
    xl = exportar_maestro_excel(res)
    if xl:
        st.download_button("📊 Exportar maestro limpio + informe Excel",
                           data=xl,
                           file_name="maestro_normalizado.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           type="primary", use_container_width=True)

    with st.expander("🔧 Log"):
        for m in st.session_state.get("norm_log", []):
            st.caption(m)
