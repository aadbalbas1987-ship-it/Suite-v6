"""
dashboards/conciliacion_dashboard.py — RPA Suite v5.9
=======================================================
Dashboard de Conciliación Bancaria — Multi-banco.
Puerto: 8507

Flujo:
  1. Subir extracto bancario (PDF/Excel/CSV)
  2. Subir registros internos (Excel cheques/CxC/manual)
  3. Ver conciliación automática con matching inteligente
  4. Revisar pendientes, diferencias
  5. Exportar informe Excel
"""
import streamlit as st
import sys
import io
import tempfile
import os
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

st.set_page_config(
    page_title="Conciliación Bancaria — RPA Suite",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""<style>
[data-testid="stAppViewContainer"]{background:#F0F4F8;}
.estado-ok{color:#16A34A;font-weight:700;}
.estado-err{color:#DC2626;font-weight:700;}
.estado-warn{color:#D97706;font-weight:700;}
.kpi-card{background:white;border-radius:10px;padding:14px 18px;
          border:1px solid #E2E8F0;box-shadow:0 2px 6px rgba(0,0,0,.05);}
.kpi-val{font-size:1.9rem;font-weight:800;font-family:monospace;color:#1A1D23;}
.kpi-lbl{font-size:0.7rem;color:#9AA0AD;text-transform:uppercase;letter-spacing:1px;}
</style>""", unsafe_allow_html=True)

try:
    from core.conciliacion_bancaria import leer_extracto, conciliar, exportar_conciliacion_excel
    _CB_OK = True
except ImportError as e:
    _CB_OK = False
    st.error(f"Módulo de conciliación no disponible: {e}")

BANCOS = ["Auto-detectar","galicia","santander","bbva","nacion","provincia",
          "macro","icbc","patagonia","ciudad","supervielle","brubank","naranjax","mercadopago"]

def fmt_precio(v):
    if not v: return "—"
    return f"${float(v):,.2f}"

# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🏦 Conciliación Bancaria")
    st.caption("RPA Suite v5.9 — Multi-banco")
    st.markdown("---")

    st.markdown("**📂 1. Extracto bancario**")
    archivo_extracto = st.file_uploader(
        "PDF, Excel o CSV del banco",
        type=["pdf","xlsx","xls","csv"], key="f_extracto",
        help="Galicia · Santander · BBVA · Nación · Provincia · Macro · ICBC · Patagonia · Ciudad · Supervielle · Brubank · Naranja X · Mercado Pago"
    )
    banco_manual = st.selectbox("Banco (si auto-detección falla)", BANCOS)
    cuenta_id    = st.text_input("Nro. de cuenta / alias (opcional)")

    st.markdown("---")
    st.markdown("**📂 2. Registros internos (opcional)**")
    archivo_interno = st.file_uploader(
        "Excel con tus movimientos internos",
        type=["xlsx","xls","csv"], key="f_interno",
        help="Puede ser el registro del robot de cheques u otro archivo con columnas: fecha, descripcion, importe"
    )

    st.markdown("---")
    st.markdown("**⚙ Parámetros**")
    umbral      = st.slider("Umbral de matching (%)", 50, 95, 70) / 100
    tol_dias    = st.slider("Tolerancia en días", 0, 7, 3)

if not _CB_OK:
    st.stop()

# ══════════════════════════════════════════════════════════════
# PROCESAMIENTO
# ══════════════════════════════════════════════════════════════
st.title("🏦 Conciliación Bancaria")

if not archivo_extracto:
    st.markdown("""
    <div style="text-align:center;padding:4rem;color:#6B7280;">
    <div style="font-size:4rem;">🏦</div>
    <h2>Conciliación Bancaria Universal</h2>
    <p>Subí el extracto bancario en el panel izquierdo para comenzar.</p>
    <p style="font-size:0.85rem;">
    Soporta: <b>Galicia · Santander · BBVA · Nación · Provincia · Macro · ICBC</b><br>
    <b>Patagonia · Ciudad · Supervielle · Brubank · Naranja X · Mercado Pago</b>
    </p>
    <p style="font-size:0.8rem;color:#9AA0AD;">Formatos: PDF · Excel · CSV</p>
    </div>""", unsafe_allow_html=True)
    st.stop()

# Leer extracto
log_msgs = []
_log = lambda m: log_msgs.append(m)

with tempfile.NamedTemporaryFile(suffix=Path(archivo_extracto.name).suffix, delete=False) as tmp:
    tmp.write(archivo_extracto.read())
    tmp_extracto = tmp.name

banco_f = None if banco_manual == "Auto-detectar" else banco_manual
extracto = leer_extracto(tmp_extracto, banco_forzado=banco_f,
                          cuenta=cuenta_id, log_func=_log)
os.unlink(tmp_extracto)

if "error" in extracto:
    st.error(f"❌ {extracto['error']}")
    with st.expander("Log"):
        for m in log_msgs: st.caption(m)
    st.stop()

# Leer registros internos
movs_internos = []
if archivo_interno:
    with tempfile.NamedTemporaryFile(suffix=Path(archivo_interno.name).suffix, delete=False) as tmp:
        tmp.write(archivo_interno.read())
        tmp_interno = tmp.name
    try:
        import pandas as pd
        df_int = pd.read_excel(tmp_interno, engine="openpyxl") \
                 if not archivo_interno.name.endswith(".csv") \
                 else pd.read_csv(tmp_interno)
        cols_low = {c.lower(): c for c in df_int.columns}
        from core.conciliacion_bancaria import _parse_fecha, _parse_monto, _limpiar_descripcion
        col_f = next((cols_low[k] for k in ["fecha","date"] if k in cols_low), df_int.columns[0])
        col_d = next((cols_low[k] for k in ["descripcion","descripción","concepto","detalle"] if k in cols_low), df_int.columns[1] if len(df_int.columns)>1 else None)
        col_i = next((cols_low[k] for k in ["importe","monto","amount","total","credito","debito"] if k in cols_low), None)
        for _, row in df_int.iterrows():
            fecha = _parse_fecha(str(row[col_f]))
            if not fecha: continue
            movs_internos.append({
                "fecha":       fecha,
                "descripcion": _limpiar_descripcion(str(row[col_d])) if col_d else "",
                "importe":     float(pd.to_numeric(row[col_i], errors="coerce") or 0) if col_i else 0,
            })
    except Exception as e:
        st.warning(f"⚠ No se pudo leer registros internos: {e}")
    os.unlink(tmp_interno)

# Conciliar
resultado_conc = None
if movs_internos:
    resultado_conc = conciliar(extracto, movs_internos,
                                umbral_match=umbral,
                                tolerancia_dias=tol_dias,
                                log_func=_log)
else:
    resultado_conc = None

# ══════════════════════════════════════════════════════════════
# CABECERA
# ══════════════════════════════════════════════════════════════
st.markdown(f"### 🏦 {extracto['banco'].upper()} — Cuenta: `{extracto['cuenta'] or '—'}`")
st.caption(f"Período: {extracto['periodo_desde']} → {extracto['periodo_hasta']}")

k1, k2, k3, k4, k5 = st.columns(5)
def _kpi(col, label, val, color="#1A1D23"):
    col.markdown(f"""<div class="kpi-card">
    <div class="kpi-val" style="color:{color}">{val}</div>
    <div class="kpi-lbl">{label}</div></div>""", unsafe_allow_html=True)

_kpi(k1, "Movimientos",    extracto["n_movimientos"])
_kpi(k2, "Total Débitos",  fmt_precio(extracto["total_debitos"]),  "#DC2626")
_kpi(k3, "Total Créditos", fmt_precio(extracto["total_creditos"]), "#16A34A")
_kpi(k4, "Saldo Final",    fmt_precio(extracto["saldo_final"]))
if resultado_conc:
    pct = resultado_conc["resumen"]["pct_conciliado"]
    _kpi(k5, "Conciliado %", f"{pct:.0f}%",
         "#16A34A" if pct >= 90 else "#D97706" if pct >= 70 else "#DC2626")

st.markdown("---")

# ══════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════
tabs_names = ["📋 Movimientos", "🔄 Conciliación", "🔍 Diferencias", "📊 Análisis"]
tab1, tab2, tab3, tab4 = st.tabs(tabs_names)

import pandas as pd

# ── Tab 1: Movimientos del banco ──
with tab1:
    st.markdown("#### 📋 Todos los movimientos del extracto")
    df_mov = extracto["df"].copy()
    df_mov["fecha"] = df_mov["fecha"].dt.strftime("%d/%m/%Y")

    # Filtros
    col_f1, col_f2, col_f3 = st.columns(3)
    buscar  = col_f1.text_input("🔍 Buscar descripción", key="buscar_mov")
    tipo    = col_f2.selectbox("Tipo", ["Todos","Solo débitos","Solo créditos"], key="tipo_mov")
    min_imp = col_f3.number_input("Importe mínimo ($)", 0.0, step=100.0, key="min_imp")

    df_show = df_mov.copy()
    if buscar:
        df_show = df_show[df_show["descripcion"].str.contains(buscar, case=False, na=False)]
    if tipo == "Solo débitos":
        df_show = df_show[df_show["debito"] > 0]
    elif tipo == "Solo créditos":
        df_show = df_show[df_show["credito"] > 0]
    if min_imp > 0:
        df_show = df_show[df_show["importe"].abs() >= min_imp]

    st.caption(f"{len(df_show)} movimientos mostrados de {len(df_mov)}")
    cols_show = ["fecha","descripcion","debito","credito","saldo"]
    cols_show = [c for c in cols_show if c in df_show.columns]
    st.dataframe(df_show[cols_show], use_container_width=True, height=500, hide_index=True)

    # Exportar extracto limpio
    buf_ext = io.BytesIO()
    df_mov[cols_show].to_excel(buf_ext, index=False, engine="openpyxl")
    buf_ext.seek(0)
    st.download_button("⬇️ Descargar extracto normalizado",
                       data=buf_ext.getvalue(),
                       file_name=f"extracto_{extracto['banco']}_{extracto['periodo_desde']}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── Tab 2: Conciliación ──
with tab2:
    if not resultado_conc:
        st.info("Subí los registros internos en el panel izquierdo para activar la conciliación automática.")
        st.markdown("**Sin registros internos** — mostrando solo el extracto bancario.")
    else:
        res = resultado_conc["resumen"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("✅ Conciliados",      res["conciliados"])
        c2.metric("🔵 Solo en banco",    res["solo_banco"])
        c3.metric("🟡 Solo en registros",res["solo_interno"])
        c4.metric("⚠️ Con diferencia",   res["con_diferencia"])

        st.markdown("---")
        st.markdown("#### ✅ Movimientos conciliados")
        if resultado_conc["conciliados"]:
            rows_conc = []
            for par in resultado_conc["conciliados"]:
                mb = par["banco"]; mi = par["interno"]
                rows_conc.append({
                    "Fecha banco":      str(mb["fecha"]),
                    "Descripción banco":mb["descripcion"][:50],
                    "Importe banco":    fmt_precio(mb["importe"]),
                    "Fecha interno":    str(mi.get("fecha","")),
                    "Descripción int.": str(mi.get("descripcion",""))[:50],
                    "Importe interno":  fmt_precio(mi.get("importe",0)),
                    "Diferencia $":     fmt_precio(par["diff_$"]),
                    "Estado":           par["estado"],
                })
            st.dataframe(pd.DataFrame(rows_conc), use_container_width=True,
                         height=350, hide_index=True)

        st.markdown("#### 🔵 Solo en banco (sin match interno)")
        if resultado_conc["solo_banco"]:
            df_sb = pd.DataFrame(resultado_conc["solo_banco"])
            df_sb["fecha"] = df_sb["fecha"].astype(str)
            st.dataframe(df_sb[["fecha","descripcion","debito","credito"]],
                         use_container_width=True, height=250, hide_index=True)
        else:
            st.success("Sin movimientos sin match ✅")

        st.markdown("#### 🟡 Solo en registros internos (no aparece en banco)")
        if resultado_conc["solo_interno"]:
            df_si = pd.DataFrame(resultado_conc["solo_interno"])
            st.dataframe(df_si, use_container_width=True, height=200, hide_index=True)
        else:
            st.success("Todos los registros internos están en el banco ✅")

# ── Tab 3: Diferencias ──
with tab3:
    if not resultado_conc or not resultado_conc["diferencias"]:
        st.success("✅ Sin diferencias de monto en los movimientos conciliados.")
    else:
        st.warning(f"⚠️ {len(resultado_conc['diferencias'])} movimientos con diferencia de monto")
        rows_dif = []
        for par in resultado_conc["diferencias"]:
            mb = par["banco"]; mi = par["interno"]
            rows_dif.append({
                "Fecha":      str(mb["fecha"]),
                "Descripción":mb["descripcion"][:60],
                "Banco $":    mb["importe"],
                "Interno $":  mi.get("importe",0),
                "Diferencia": par["diff_$"],
            })
        st.dataframe(pd.DataFrame(rows_dif), use_container_width=True, hide_index=True)

# ── Tab 4: Análisis ──
with tab4:
    st.markdown("#### 📊 Análisis del extracto")
    df_an = extracto["df"].copy()

    # Movimientos por semana
    df_an["semana"] = df_an["fecha"].dt.to_period("W").astype(str)
    semanal = df_an.groupby("semana").agg(
        debitos=("debito","sum"), creditos=("credito","sum"), n=("importe","count")
    ).reset_index()

    try:
        import plotly.express as px
        fig = px.bar(semanal, x="semana", y=["debitos","creditos"],
                     barmode="group", title="Débitos vs Créditos por semana",
                     color_discrete_sequence=["#DC2626","#16A34A"])
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                          margin=dict(l=0,r=0,t=40,b=0), height=300,
                          legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.dataframe(semanal, use_container_width=True, hide_index=True)

    # Top movimientos más grandes
    st.markdown("#### 💰 Top 10 movimientos por monto")
    top10 = df_an.nlargest(10, "importe")[["fecha","descripcion","importe","saldo"]].copy()
    top10["fecha"] = top10["fecha"].dt.strftime("%d/%m/%Y")
    st.dataframe(top10, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════
# EXPORTAR
# ══════════════════════════════════════════════════════════════
st.markdown("---")
col_ex1, col_ex2 = st.columns(2)
with col_ex1:
    if resultado_conc:
        xl_conc = exportar_conciliacion_excel(resultado_conc, extracto)
        if xl_conc:
            st.download_button(
                "📊 Exportar informe completo Excel",
                data=xl_conc,
                file_name=f"conciliacion_{extracto['banco']}_{extracto['periodo_desde']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, type="primary",
            )
with col_ex2:
    buf_csv = io.BytesIO()
    extracto["df"].to_csv(buf_csv, index=False)
    buf_csv.seek(0)
    st.download_button(
        "📋 Exportar extracto CSV",
        data=buf_csv.getvalue(),
        file_name=f"extracto_{extracto['banco']}.csv",
        mime="text/csv",
        use_container_width=True,
    )

# Log
with st.expander("🔧 Log de procesamiento"):
    for m in log_msgs:
        st.caption(m)
