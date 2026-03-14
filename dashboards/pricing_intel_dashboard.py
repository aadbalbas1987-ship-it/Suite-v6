"""
dashboards/pricing_intel_dashboard.py — RPA Suite v5.9
========================================================
Dashboard de Pricing Intelligence — Multi-fuente.
Puerto: 8506

Módulos:
  1. Búsqueda multi-fuente en tiempo real
  2. Tu precio vs mercado (cargá tu Excel de costos)
  3. Análisis masivo lista completa
  4. Mapa de posicionamiento competitivo
  5. Alertas: caros / baratos / sin margen
"""
import streamlit as st
import sys
import json
import io
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

st.set_page_config(
    page_title="Pricing Intel — RPA Suite",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──
st.markdown("""<style>
[data-testid="stAppViewContainer"]{background:#F0F4F8;}
.fuente-card{background:white;border-radius:10px;padding:14px 18px;
             border:1px solid #E2E8F0;margin-bottom:8px;
             box-shadow:0 2px 6px rgba(0,0,0,0.05);}
.precio-big{font-size:1.6rem;font-weight:800;font-family:monospace;}
.semaforo-rojo{color:#DC2626;} .semaforo-verde{color:#16A34A;}
.semaforo-amarillo{color:#D97706;} .semaforo-azul{color:#2563EB;}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;
       font-size:0.75rem;font-weight:600;}
</style>""", unsafe_allow_html=True)

try:
    from tools.pricing_multifuente import (
        comparar_precio_vs_mercado,
        analizar_lista_vs_mercado,
        leer_lista_proveedor,
        FUENTES_DISPONIBLES,
    )
    _MF_OK = True
except ImportError as e:
    _MF_OK = False

try:
    from tools.pricing_ia_search import buscar_precios_ia
    _IA_OK = True
except ImportError as e:
    _IA_OK = False
    st.warning(f"Motor IA no disponible: {e}")

# Wrapper combinado — usa TODOS los motores en paralelo
def buscar_multifuente(query, fuentes=None, listas_proveedor=None,
                       usar_matching_ia=False, log_func=None, **kwargs):
    """
    Combina pricing_multifuente (scrapers) + pricing_ia_search (VTEX APIs).
    Ambos corren en paralelo y los resultados se fusionan.
    """
    import concurrent.futures

    def _log(m):
        if log_func: log_func(m)

    resultado_base = {
        "items_por_fuente": {}, "items_todos": [], "estadisticas": {},
        "fuentes_ok": [], "fuentes_error": [], "mercado": {}
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futures = {}

        if _MF_OK:
            from tools.pricing_multifuente import buscar_multifuente as _bm
            futures["scrapers"] = ex.submit(
                _bm, query,
                fuentes=fuentes, listas_proveedor=listas_proveedor,
                usar_matching_ia=False, log_func=log_func
            )

        if _IA_OK:
            futures["vtex"] = ex.submit(
                buscar_precios_ia, query, log_func=log_func
            )

        for nombre, fut in futures.items():
            try:
                res = fut.result(timeout=20)
                # Fusionar items_por_fuente
                for fuente, items in res.get("items_por_fuente", {}).items():
                    resultado_base["items_por_fuente"].setdefault(fuente, [])
                    resultado_base["items_por_fuente"][fuente].extend(items)
                resultado_base["items_todos"].extend(res.get("items_todos", []))
                resultado_base["fuentes_ok"].extend(res.get("fuentes_ok", []))
                resultado_base["fuentes_error"].extend(res.get("fuentes_error", []))
                # Mercado del primer motor con datos
                if res.get("mercado") and not resultado_base["mercado"]:
                    resultado_base["mercado"] = res["mercado"]
            except Exception as e:
                _log(f"  Motor {nombre}: {e}")
                resultado_base["fuentes_error"].append(nombre)

    # Recalcular mercado global con todos los items fusionados
    todos = resultado_base["items_todos"]
    if todos:
        try:
            precios = sorted(p["precio"] for p in todos if p.get("precio", 0) > 0)
            if precios:
                n = len(precios)
                resultado_base["mercado"] = {
                    "min":      precios[0],
                    "max":      precios[-1],
                    "mediana":  precios[n // 2],
                    "promedio": round(sum(precios) / n, 2),
                    "n":        n,
                }
        except Exception:
            pass

    if not resultado_base["fuentes_ok"] and not resultado_base["items_todos"]:
        resultado_base["fuentes_error"].append("Sin resultados en ninguna fuente")

    return resultado_base

# ── Helpers ──
def fmt_precio(v):
    return f"${v:,.0f}" if v else "—"

def semaforo_color(estado):
    if "CARO" in estado:    return "#DC2626"
    if "BAJO" in estado:    return "#2563EB"
    if "LÍNEA" in estado or "✅" in estado: return "#16A34A"
    if "COMPETITIVO" in estado: return "#059669"
    return "#6B7280"

# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🎯 Pricing Intelligence")
    st.caption("RPA Suite v5.9 — Multi-fuente")
    st.markdown("---")

    modo = st.radio("Módulo", [
        "🔍 Búsqueda en tiempo real",
        "📊 Tu precio vs mercado",
        "📋 Análisis lista completa",
        "⚠️ Alertas de posicionamiento",
    ], label_visibility="collapsed")

    st.markdown("---")
    if _MF_OK or _IA_OK:
        n_fuentes = len(FUENTES_DISPONIBLES) if _MF_OK else 0
        n_vtex = 10 if _IA_OK else 0
        st.success(f"✅ **{n_fuentes + n_vtex} fuentes disponibles**")
        if _MF_OK:
            st.caption("🛒 **Supermercados:** Carrefour · Coto · Día · Jumbo · Changomás · Vea · Disco")
            st.caption("🏭 **Mayoristas:** Makro · Vital · MaxiConsumo")
            st.caption("🔍 Google Shopping")
        if _IA_OK:
            st.caption("⚡ **VTEX directo:** Carrefour · Día · Jumbo · Changomás · Walmart · Vea · Disco · Vital · MaxiConsumo · Diarco")
        st.markdown("---")
        if _MF_OK:
            with st.expander("⚙ Seleccionar fuentes", expanded=False):
                fuentes_sel = {}
                col1, col2 = st.columns(2)
                items = list(FUENTES_DISPONIBLES.items())
                for i, (key, (_, nombre)) in enumerate(items):
                    col = col1 if i % 2 == 0 else col2
                    fuentes_sel[key] = col.checkbox(nombre, value=(key != "google_shopping"), key=f"src_{key}")
        fuentes_sel = {}  # wrapper combinado usa todos
    else:
        st.error("❌ Sin motor de búsqueda disponible")
    fuentes_sel = {}

    st.markdown("---")
    st.markdown("**📂 Lista de proveedores**")
    proveedores_files = st.file_uploader(
        "PDF o Excel de proveedor", type=["xlsx","xls","pdf","csv"],
        accept_multiple_files=True, key="prov_files",
        help="Cargá listas de precios de tus proveedores para incluirlas en la comparación"
    )

    margen_min = st.slider("Margen mínimo objetivo (%)", 5, 50, 20, key="margen_min_intel")

if not _MF_OK and not _IA_OK:
    st.error("Sin motores de búsqueda disponibles. Verificá las dependencias.")
    st.stop()

fuentes_activas = list(FUENTES_DISPONIBLES.keys()) if _MF_OK and not _IA_OK else None

# Guardar proveedores temp
import tempfile, os
_PROV_PATHS = []
for f in (proveedores_files or []):
    with tempfile.NamedTemporaryFile(suffix=Path(f.name).suffix, delete=False) as tmp:
        tmp.write(f.read())
        _PROV_PATHS.append(tmp.name)


# ══════════════════════════════════════════════════════════════
# MÓDULO 1 — BÚSQUEDA EN TIEMPO REAL
# ══════════════════════════════════════════════════════════════
if modo == "🔍 Búsqueda en tiempo real":
    st.title("🔍 Búsqueda de precios en supermercados")
    if _IA_OK:
        st.info("🛒 **Motor VTEX activo** — Busca en Carrefour, Día, Jumbo, Changomás y Walmart via sus APIs públicas. Gratis, sin API key.", icon="🔍")
    else:
        st.caption("Buscamos el mismo producto en supermercados y tus listas de proveedor.")

    col_q, col_p, col_c = st.columns([3, 1, 1])
    query       = col_q.text_input("Producto a buscar", placeholder="Ej: Aceite Natura 900ml", key="q_rt")
    tu_precio   = col_p.number_input("Tu precio ($)", min_value=0.0, value=0.0, step=10.0, key="tp_rt")
    tu_costo    = col_c.number_input("Tu costo ($)", min_value=0.0, value=0.0, step=10.0, key="tc_rt")

    if st.button("🚀 Buscar en todas las fuentes", type="primary",
                 use_container_width=True, key="btn_rt", disabled=not query):
        log_msgs = []
        with st.spinner("🔍 Consultando supermercados en tiempo real..."):
            resultado = buscar_multifuente(
                query=query,
                fuentes=fuentes_activas,
                listas_proveedor=_PROV_PATHS,
                usar_matching_ia=False,  # IA ya filtra internamente
                log_func=lambda m: log_msgs.append(m),
            )
        st.session_state["rt_resultado"] = resultado
        st.session_state["rt_tu_precio"] = tu_precio
        st.session_state["rt_tu_costo"]  = tu_costo
        st.session_state["rt_log"]       = log_msgs

    if "rt_resultado" in st.session_state:
        res      = st.session_state["rt_resultado"]
        tp       = st.session_state.get("rt_tu_precio", 0)
        tc       = st.session_state.get("rt_tu_costo", 0)
        mercado  = res.get("mercado", {})
        est      = res.get("estadisticas", {})

        # ── Fuentes respondidas ──
        st.markdown(f"**Fuentes consultadas:** {len(res['fuentes_ok'])} OK · "
                    f"{len(res['fuentes_error'])} sin datos")

        # ── KPIs globales ──
        if mercado.get("mediana", 0) > 0:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("💰 Mediana mercado", fmt_precio(mercado["mediana"]))
            k2.metric("🔽 Mínimo", fmt_precio(mercado["min"]))
            k3.metric("🔼 Máximo", fmt_precio(mercado["max"]))
            k4.metric("📦 N° precios", mercado.get("n_total", 0))

        # ── Tu precio vs mercado ──
        if tp > 0 and mercado.get("mediana", 0) > 0:
            comp = comparar_precio_vs_mercado(tp, tc, res, margen_min)
            color = semaforo_color(comp["estado"])
            st.markdown("---")
            st.markdown(f"### Tu posición: <span style='color:{color};font-size:1.3rem'>{comp['estado']}</span>",
                        unsafe_allow_html=True)
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Tu precio",    fmt_precio(tp))
            c2.metric("Mediana mkt",  fmt_precio(comp["precio_mediana_mkt"]),
                      f"{comp['diff_pct']:+.1f}%")
            c3.metric("Margen actual",f"{comp['margen_actual_pct']:.1f}%",
                      help="Sobre precio de venta")
            c4.metric("Precio sugerido", fmt_precio(comp["precio_sugerido"]))
            if comp.get("oportunidad_subida"):
                c5.metric("🟢 Podés subir a", fmt_precio(comp["oportunidad_subida"]))
            if comp.get("perdida"):
                st.error("⛔ VENDÉS POR DEBAJO DEL COSTO — estás perdiendo plata en este producto")

        # ── Tabla comparativa por fuente ──
        st.markdown("---")
        st.markdown("#### Precios por fuente")

        import pandas as pd
        if est:
            df_est = pd.DataFrame([
                {"Fuente": f, "Mínimo": fmt_precio(d["min"]),
                 "Mediana": fmt_precio(d["mediana"]),
                 "Máximo": fmt_precio(d["max"]),
                 "Promedio": fmt_precio(d["promedio"]),
                 "N°": d["n"]}
                for f, d in est.items()
            ])
            st.dataframe(df_est, use_container_width=True, hide_index=True)

        # ── Cards por fuente ──
        st.markdown("#### Productos encontrados")
        tabs_fuentes = list(res["items_por_fuente"].keys())
        if tabs_fuentes:
            tabs = st.tabs(tabs_fuentes)
            for tab, fuente in zip(tabs, tabs_fuentes):
                with tab:
                    items_f = res["items_por_fuente"][fuente]
                    for item in items_f[:12]:
                        col_img, col_info = st.columns([1, 5])
                        if item.get("imagen"):
                            col_img.image(item["imagen"], width=60)
                        with col_info:
                            precio_str = fmt_precio(item["precio"])
                            diff = ""
                            if tp > 0 and item["precio"] > 0:
                                d = (tp - item["precio"]) / item["precio"] * 100
                                diff = f" <small style='color:{'#DC2626' if d>0 else '#16A34A'}'>{d:+.0f}% vs vos</small>"
                            st.markdown(
                                f"**{item['titulo'][:70]}** — "
                                f"<span class='precio-big'>{precio_str}</span>{diff}",
                                unsafe_allow_html=True
                            )
                            if item.get("url"):
                                st.caption(f"🔗 {item['url'][:60]}")

        # Log
        with st.expander("📋 Log de búsqueda"):
            for m in st.session_state.get("rt_log", []):
                st.caption(m)


# ══════════════════════════════════════════════════════════════
# MÓDULO 2 — TU PRECIO VS MERCADO (Excel de costos)
# ══════════════════════════════════════════════════════════════
elif modo == "📊 Tu precio vs mercado":
    st.title("📊 Tu precio vs el mercado")
    st.caption("Cargá tu Excel de costos y precios para ver dónde estás parado en cada producto.")

    archivo_costos = st.file_uploader(
        "📂 Tu Excel de costos/precios",
        type=["xlsx","xls"],
        help="Necesita al menos columnas: Descripción, Tu Precio. Opcional: Tu Costo"
    )

    if archivo_costos:
        import pandas as pd, tempfile
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(archivo_costos.read())
            tmp_path = tmp.name

        df_costos = pd.read_excel(tmp_path, engine="openpyxl")
        os.unlink(tmp_path)

        st.write(f"**{len(df_costos)} artículos cargados**")
        st.dataframe(df_costos.head(5), use_container_width=True, hide_index=True)

        # Mapeo de columnas
        col_a, col_b, col_c = st.columns(3)
        col_desc_map  = col_a.selectbox("Columna Descripción", df_costos.columns, key="cd_desc")
        col_prec_map  = col_b.selectbox("Columna Tu Precio",   df_costos.columns, key="cd_prec")
        col_costo_map = col_c.selectbox("Columna Tu Costo (opcional)",
                                         ["— sin costo —"] + list(df_costos.columns), key="cd_cost")

        col_lim, col_delay = st.columns(2)
        limite      = col_lim.slider("Artículos a analizar", 5, min(100, len(df_costos)), 20)
        delay_seg   = col_delay.slider("Pausa entre búsquedas (seg)", 0.5, 3.0, 1.0, step=0.5)

        if st.button("🚀 Analizar lista vs mercado", type="primary",
                     use_container_width=True, key="btn_vs"):
            df_proc = df_costos.head(limite)
            items_lista = []
            for _, row in df_proc.iterrows():
                costo_val = (float(row.get(col_costo_map, 0) or 0)
                             if col_costo_map != "— sin costo —" else 0.0)
                items_lista.append({
                    "descripcion": str(row[col_desc_map]),
                    "tu_precio":   float(pd.to_numeric(row[col_prec_map], errors="coerce") or 0),
                    "tu_costo":    costo_val,
                })

            log_vs = []
            progress_bar = st.progress(0, text="Analizando...")
            resultados_vs = []

            from tools.pricing_multifuente import buscar_multifuente, comparar_precio_vs_mercado
            for i, item in enumerate(items_lista):
                progress_bar.progress((i+1)/len(items_lista),
                                      text=f"[{i+1}/{len(items_lista)}] {item['descripcion'][:40]}")
                res_mf = buscar_multifuente(
                    query=item["descripcion"], fuentes=fuentes_activas,
                    listas_proveedor=_PROV_PATHS, usar_matching_ia=False,  # IA ya filtra internamente
                    log_func=lambda m: log_vs.append(m),
                )
                comp = comparar_precio_vs_mercado(
                    item["tu_precio"], item["tu_costo"], res_mf, margen_min
                )
                resultados_vs.append({
                    "Descripción":    item["descripcion"],
                    "Tu precio":      fmt_precio(item["tu_precio"]),
                    "Mediana mkt":    fmt_precio(comp.get("precio_mediana_mkt", 0)),
                    "Diff %":         f"{comp.get('diff_pct', 0):+.1f}%",
                    "Margen %":       f"{comp.get('margen_actual_pct', 0):.1f}%",
                    "Estado":         comp.get("estado", "—"),
                    "Precio sugerido":fmt_precio(comp.get("precio_sugerido", 0)),
                    "Oportunidad":    fmt_precio(comp.get("oportunidad_subida")) if comp.get("oportunidad_subida") else "—",
                    "Fuentes":        len(comp.get("fuentes_ok", res_mf.get("fuentes_ok", []))),
                    "_perdida":       comp.get("perdida", False),
                })
                import time as _t; _t.sleep(delay_seg)

            progress_bar.empty()
            st.session_state["vs_resultados"] = resultados_vs

    if "vs_resultados" in st.session_state:
        import pandas as pd
        df_res = pd.DataFrame(st.session_state["vs_resultados"])
        cols_show = [c for c in df_res.columns if not c.startswith("_")]

        # KPIs resumen
        estados = df_res["Estado"].value_counts()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("🔴 Muy caros",   estados.get("🔴 MUY CARO", 0))
        k2.metric("🟡 Algo caros",  estados.get("🟡 ALGO CARO", 0))
        k3.metric("✅ En línea",    estados.get("✅ EN LÍNEA", 0))
        k4.metric("🔵 Muy baratos", estados.get("🔵 MUY BARATO", 0))

        # Alertas críticas
        perdidas = df_res[df_res["_perdida"] == True]
        if not perdidas.empty:
            st.error(f"⛔ {len(perdidas)} artículo(s) se venden POR DEBAJO del costo")
            st.dataframe(perdidas[cols_show], use_container_width=True, hide_index=True)

        # Tabla completa
        st.markdown("---")
        filtro_estado = st.multiselect("Filtrar por estado",
                                        df_res["Estado"].unique().tolist(),
                                        default=df_res["Estado"].unique().tolist())
        df_filtrado = df_res[df_res["Estado"].isin(filtro_estado)]
        st.dataframe(df_filtrado[cols_show], use_container_width=True,
                     height=450, hide_index=True)

        # Exportar
        buf_vs = io.BytesIO()
        df_res[cols_show].to_excel(buf_vs, index=False, engine="openpyxl")
        buf_vs.seek(0)
        st.download_button("⬇️ Exportar análisis completo",
                           data=buf_vs.getvalue(),
                           file_name=f"pricing_vs_mercado_{datetime.now().strftime('%Y%m%d')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ══════════════════════════════════════════════════════════════
# MÓDULO 3 — ANÁLISIS LISTA COMPLETA
# ══════════════════════════════════════════════════════════════
elif modo == "📋 Análisis lista completa":
    st.title("📋 Análisis de lista completa")
    st.info("Usá el módulo **Tu precio vs mercado** para el análisis completo con tu Excel de costos.")


# ══════════════════════════════════════════════════════════════
# MÓDULO 4 — ALERTAS
# ══════════════════════════════════════════════════════════════
elif modo == "⚠️ Alertas de posicionamiento":
    st.title("⚠️ Alertas de posicionamiento")

    if "vs_resultados" not in st.session_state:
        st.info("Primero ejecutá un análisis en **Tu precio vs mercado** para ver alertas.")
    else:
        import pandas as pd
        df_alertas = pd.DataFrame(st.session_state["vs_resultados"])
        cols_show  = [c for c in df_alertas.columns if not c.startswith("_")]

        # Caros
        df_caros = df_alertas[df_alertas["Estado"].str.contains("CARO")]
        if not df_caros.empty:
            st.markdown(f"### 🔴 Artículos caros vs mercado ({len(df_caros)})")
            st.caption("Estás por encima de la mediana del mercado — riesgo de perder ventas")
            st.dataframe(df_caros[cols_show], use_container_width=True,
                         height=250, hide_index=True)

        # Baratos con oportunidad
        df_baj = df_alertas[(df_alertas["Estado"].str.contains("BAJO|BARATO")) &
                             (df_alertas["Oportunidad"] != "—")]
        if not df_baj.empty:
            st.markdown(f"### 🟢 Oportunidades de subir precio ({len(df_baj)})")
            st.caption("Estás por debajo de la mediana — podés subir el precio y seguir siendo competitivo")
            st.dataframe(df_baj[cols_show], use_container_width=True,
                         height=250, hide_index=True)

        # Sin margen / pérdida
        df_perd = df_alertas[df_alertas["_perdida"] == True]
        if not df_perd.empty:
            st.markdown(f"### ⛔ Vendiendo a pérdida ({len(df_perd)})")
            st.error("Estos artículos tienen precio de venta menor al costo")
            st.dataframe(df_perd[cols_show], use_container_width=True,
                         height=200, hide_index=True)

# Cleanup temp proveedor files
for p in _PROV_PATHS:
    try: os.unlink(p)
    except: pass
