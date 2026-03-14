"""
dashboards/pricing_dashboard.py — RPA Suite v5.9
==================================================
Dashboard de Pricing Research con motor IA.
Puerto: 8504

NUEVO v5.9:
  - Búsqueda inteligente: IA expande el término antes de consultar ML
  - Cards por producto con semáforo de competitividad
  - Thumbnails de productos ML
  - Análisis de marca completo con IA
  - Calculador de precio óptimo (costo → precio sugerido)
  - Búsqueda masiva desde Excel
  - Fix de persistencia de resultados (session_state robusto)
  - pytrends desactivado por defecto (no rompe el flujo)
"""
import sys
from pathlib import Path

_BASE = Path(__file__).parent.parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

import streamlit as st
import pandas as pd
import json
from datetime import datetime

st.set_page_config(
    page_title="Pricing Research — RPA Suite v5.9",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
  .main { background: #f8fafc; }
  .block-container { padding: 1.5rem 2rem; }
  .kpi-card {
    background: white; border-radius: 12px; padding: 16px 20px;
    border: 1px solid #e2e8f0; text-align: center; margin-bottom: 8px;
  }
  .kpi-val { font-size: 2rem; font-weight: 700; }
  .kpi-lbl { font-size: 0.8rem; color: #64748b; margin-top: 4px; }
  .product-card {
    background: white; border-radius: 12px; padding: 16px;
    border: 1px solid #e2e8f0; margin-bottom: 12px;
  }
  .semaforo-verde  { color: #16a34a; font-weight: 700; font-size: 1rem; }
  .semaforo-rojo   { color: #dc2626; font-weight: 700; font-size: 1rem; }
  .semaforo-amarillo{ color: #d97706; font-weight: 700; font-size: 1rem; }
  .semaforo-azul   { color: #2563eb; font-weight: 700; font-size: 1rem; }
  .alert-alta  { background:#fef2f2; border-left:4px solid #ef4444; padding:8px 12px; margin:4px 0; border-radius:0 8px 8px 0; }
  .alert-media { background:#fffbeb; border-left:4px solid #f59e0b; padding:8px 12px; margin:4px 0; border-radius:0 8px 8px 0; }
  .ia-box { background:#f0f9ff; border:1px solid #bae6fd; border-radius:12px; padding:20px; }
  .variante-chip {
    display:inline-block; background:#eff6ff; color:#1d4ed8;
    border-radius:20px; padding:2px 10px; margin:2px; font-size:0.78rem;
  }
  .precio-badge {
    background:#dcfce7; color:#15803d; border-radius:8px;
    padding:4px 12px; font-weight:700; font-size:1.1rem;
  }
  .thumb-row { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
  .thumb-item { text-align:center; width:90px; font-size:0.7rem; color:#64748b; }
  .thumb-item img { width:80px; height:80px; object-fit:contain; border-radius:8px; border:1px solid #e2e8f0; }
</style>
""", unsafe_allow_html=True)

# ── Import módulo ────────────────────────────────────────────
try:
    from tools.pricing_research import (
        ejecutar_market_research,
        scrape_con_expansion_ia,
        analisis_marca_ia,
        precio_optimo_ia,
        busqueda_masiva_desde_excel,
        cargar_historial_precios,
        exportar_excel,
        exportar_para_robot,
        comparar_con_snapshot_anterior,
        scrape_mercadolibre,
        scrape_multiple_queries,
        analizar_precios,
        ranking_mas_vendidos_ml,
        recomendaciones_ia,
        expansor_queries_ia,
        _PRICING_DIR,
        _HISTORY_FILE,
    )
    MODULE_OK = True
except ImportError as e:
    MODULE_OK = False
    st.error(f"Error importando módulo: {e}")

# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 💰 Pricing Research")
    st.caption("RPA Suite v5.9")
    st.markdown("---")

    modo = st.radio(
        "Módulo",
        ["🔍 Buscar Producto", "📦 Búsqueda Masiva", "📊 Análisis vs Lista",
         "🧮 Precio Óptimo", "📈 Market Research", "📉 Historial",
         "🤖 IA Avanzada", "🏷️ Motor Pricing Lista"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("**⚙ Configuración**")
    max_items    = st.slider("Resultados por búsqueda", 5, 50, 20)
    incluir_ia   = st.toggle("Motor IA (expansión + análisis)", value=True)
    contexto_neg = st.text_input("Contexto del negocio", value="distribuidora mayorista Argentina")

    st.markdown("**🎯 Filtros de resultados**")
    filtro_precio_min = st.number_input("Precio mínimo ($)", min_value=0, value=0, step=100,
                                        help="Excluir resultados por debajo de este precio")
    filtro_precio_max = st.number_input("Precio máximo ($)", min_value=0, value=0, step=1000,
                                        help="0 = sin límite superior")
    filtro_min_ventas = st.number_input("Mín. ventas (unidades)", min_value=0, value=0, step=1,
                                        help="Excluir productos con menos ventas")
    filtro_solo_meli  = st.toggle("Solo MercadoLibre Oficial", value=False,
                                   help="Filtrar solo vendedores oficiales")

    st.markdown("---")
    if _HISTORY_FILE.exists():
        try:
            hist = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
            st.caption(f"📦 {len(hist)} snapshots guardados")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# MÓDULO 1 — BUSCAR PRODUCTO (con motor IA)
# ══════════════════════════════════════════════════════════════
if modo == "🔍 Buscar Producto":
    st.title("🔍 Buscar Producto en MercadoLibre")
    st.caption("El motor IA expande tu búsqueda automáticamente para encontrar más resultados relevantes")

    col1, col2 = st.columns([3, 1])
    with col1:
        termino = st.text_input(
            "Producto o marca a buscar",
            placeholder="Ej: Manaos, aceite girasol, jabón Dove, fideos Don Vittorio...",
        )
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        buscar = st.button("🚀 Buscar", type="primary", disabled=not MODULE_OK or not termino)

    if buscar and termino:
        log_msgs = []
        with st.spinner(f"Buscando '{termino}' con motor IA..."):
            resumen = scrape_con_expansion_ia(
                termino, max_items, contexto_neg,
                log_func=lambda m: log_msgs.append(m)
            )
        st.session_state["busqueda_resultado"] = resumen
        st.session_state["busqueda_termino"]   = termino
        st.session_state["busqueda_log"]       = log_msgs

    # ── Mostrar resultados ──
    if "busqueda_resultado" in st.session_state:
        res     = st.session_state["busqueda_resultado"]
        termino = st.session_state.get("busqueda_termino", "")

        # Variantes usadas
        variantes = res.get("variantes_buscadas", [])
        if variantes:
            chips = " ".join(f'<span class="variante-chip">🔎 {v}</span>' for v in variantes)
            st.markdown(f"**Búsquedas realizadas:** {chips}", unsafe_allow_html=True)

        # KPIs
        st.markdown("")
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"""<div class="kpi-card"><div class="kpi-val" style="color:#0057A8">{res.get('total_resultados',0)}</div><div class="kpi-lbl">Productos encontrados</div></div>""", unsafe_allow_html=True)
        c2.markdown(f"""<div class="kpi-card"><div class="kpi-val" style="color:#16a34a">${res.get('precio_min',0):,.0f}</div><div class="kpi-lbl">Precio mínimo</div></div>""", unsafe_allow_html=True)
        c3.markdown(f"""<div class="kpi-card"><div class="kpi-val" style="color:#d97706">${res.get('precio_mediana',0):,.0f}</div><div class="kpi-lbl">Precio mediana</div></div>""", unsafe_allow_html=True)
        c4.markdown(f"""<div class="kpi-card"><div class="kpi-val" style="color:#7c3aed">${res.get('precio_max',0):,.0f}</div><div class="kpi-lbl">Precio máximo</div></div>""", unsafe_allow_html=True)

        items = res.get("items", [])
        if not items:
            st.warning("No se encontraron productos. Probá con otro término.")
        else:
            tab_tabla, tab_cards, tab_ia = st.tabs(["📋 Tabla", "🃏 Cards con imágenes", "🤖 Análisis IA"])

            with tab_tabla:
                rows = [{
                    "Título": i["titulo"][:65],
                    "Precio": f"${i['precio']:,.0f}",
                    "Vendedor": i["vendedor"],
                    "Vendidos": i["vendidos"],
                    "Link": i["url"],
                } for i in items]
                st.dataframe(
                    pd.DataFrame(rows), use_container_width=True, height=420,
                    column_config={"Link": st.column_config.LinkColumn("🔗")}
                )

            with tab_cards:
                # Mostrar thumbnails en grilla
                cols_per_row = 4
                for row_start in range(0, min(len(items), 16), cols_per_row):
                    cols = st.columns(cols_per_row)
                    for j, col in enumerate(cols):
                        idx = row_start + j
                        if idx >= len(items): break
                        it = items[idx]
                        with col:
                            if it.get("thumbnail"):
                                st.image(it["thumbnail"], width=100)
                            st.markdown(f"**${it['precio']:,.0f}**")
                            st.caption(it["titulo"][:50])
                            if it.get("vendidos"):
                                st.caption(f"✅ {it['vendidos']} vendidos")
                            st.markdown(f"[Ver en ML]({it['url']})")

            with tab_ia:
                if incluir_ia:
                    if st.button("🤖 Generar análisis de marca", key="btn_analisis_marca"):
                        with st.spinner("Analizando con IA..."):
                            analisis_txt = analisis_marca_ia(
                                termino, res, contexto_neg,
                                log_func=lambda m: None
                            )
                        st.session_state["analisis_marca_txt"] = analisis_txt

                    if "analisis_marca_txt" in st.session_state:
                        st.markdown(
                            f'<div class="ia-box">{st.session_state["analisis_marca_txt"]}</div>',
                            unsafe_allow_html=True
                        )
                else:
                    st.info("Activá 'Motor IA' en el sidebar para el análisis de marca.")

        # Exportar para robot
        if items:
            with st.expander("📤 Exportar para robot de precios"):
                st.caption("Generá un archivo precios_*.xlsx listo para cargar en el robot directamente desde los resultados de ML")
                precio_base  = st.number_input("Precio base (tu costo, $)", min_value=0.0, value=0.0, step=10.0, key="exp_costo")
                margen_salon = st.number_input("Margen salón (%)", 0, 200, 30, key="exp_margen_s")
                margen_may   = st.number_input("Margen mayorista (%)", 0, 200, 20, key="exp_margen_m")
                if st.button("📤 Generar precios_*.xlsx", key="btn_export_robot"):
                    if precio_base <= 0:
                        st.warning("Ingresá tu costo para calcular los precios de venta.")
                    else:
                        precio_salon_calc = round(precio_base * (1 + margen_salon/100), 2)
                        precio_may_calc   = round(precio_base * (1 + margen_may/100), 2)
                        items_robot = [{"sku": it["titulo"][:20], "costo": precio_base,
                                        "precio_salon": precio_salon_calc,
                                        "precio_mayorista": precio_may_calc,
                                        "precio_galpon": 0} for it in items[:50]]
                        path_robot = exportar_para_robot(items_robot, log_func=lambda m: None)
                        if path_robot:
                            with open(path_robot, "rb") as fr:
                                nombre_r = Path(path_robot).name
                                st.success(f"✅ {nombre_r} generado — copialo a input/ para ejecutar el robot")
                                st.download_button("⬇️ Descargar", fr.read(),
                                                   file_name=nombre_r,
                                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                                   key="dl_robot_file")

        # Log expandible
        with st.expander("📋 Log de búsqueda"):
            for msg in st.session_state.get("busqueda_log", []):
                st.text(msg)


# ══════════════════════════════════════════════════════════════
# MÓDULO 2 — BÚSQUEDA MASIVA DESDE EXCEL
# ══════════════════════════════════════════════════════════════
elif modo == "📦 Búsqueda Masiva":
    st.title("📦 Búsqueda Masiva desde Lista")
    st.caption("Subí tu lista de artículos y el sistema busca precios en ML para todos automáticamente (máx 20)")

    archivo = st.file_uploader("Lista de artículos (xlsx/csv)", type=["xlsx","csv"],
                                help="Necesitás una columna 'articulo' o 'descripcion'")
    col_nombre = st.text_input("Nombre de la columna de artículos", value="articulo")
    col_costo  = st.text_input("Nombre de la columna de costo (opcional)", value="costo")

    if archivo and st.button("🚀 Iniciar búsqueda masiva", type="primary", disabled=not MODULE_OK):
        df_in = pd.read_csv(archivo) if archivo.name.endswith(".csv") else pd.read_excel(archivo)
        if col_nombre not in df_in.columns:
            st.error(f"Columna '{col_nombre}' no encontrada. Columnas disponibles: {list(df_in.columns)}")
        else:
            log_msgs = []
            barra    = st.progress(0, "Iniciando...")
            with st.spinner("Procesando artículos..."):
                resultados = busqueda_masiva_desde_excel(
                    df_in, col_nombre, col_costo,
                    max_por_producto=min(max_items, 15),
                    usar_ia=incluir_ia, contexto=contexto_neg,
                    log_func=lambda m: log_msgs.append(m)
                )
            barra.progress(1.0, "✅ Completo")
            st.session_state["masiva_resultado"] = resultados
            st.session_state["masiva_log"]       = log_msgs

    if "masiva_resultado" in st.session_state:
        resultados = st.session_state["masiva_resultado"]
        st.success(f"✅ {len(resultados)} artículos procesados")

        # Tabla resumen
        rows = []
        for nombre, r in resultados.items():
            semaforo = "⚪ SIN DATOS" if r["total"] == 0 else "✅ Con datos"
            rows.append({
                "Artículo":        nombre,
                "Encontrados":     r["total"],
                "Precio mínimo":   f"${r['precio_min']:,.0f}" if r["precio_min"] else "—",
                "Precio mediana":  f"${r['precio_mediana']:,.0f}" if r["precio_mediana"] else "—",
                "Precio máximo":   f"${r['precio_max']:,.0f}" if r["precio_max"] else "—",
                "Variantes IA":    ", ".join(r["variantes"][:2]) + ("..." if len(r["variantes"])>2 else ""),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, height=450)

        # Detalle por artículo
        with st.expander("🔎 Ver detalle por artículo"):
            art_sel = st.selectbox("Artículo", list(resultados.keys()))
            if art_sel:
                r = resultados[art_sel]
                items = r.get("items", [])
                if items:
                    cols = st.columns(min(4, len(items[:4])))
                    for j, it in enumerate(items[:4]):
                        with cols[j]:
                            if it.get("thumbnail"): st.image(it["thumbnail"], width=90)
                            st.markdown(f"**${it['precio']:,.0f}**")
                            st.caption(it["titulo"][:45])
                            st.markdown(f"[ML]({it['url']})")

        with st.expander("📋 Log"):
            for m in st.session_state.get("masiva_log", []): st.text(m)


# ══════════════════════════════════════════════════════════════
# MÓDULO 3 — ANÁLISIS VS LISTA INTERNA
# ══════════════════════════════════════════════════════════════
elif modo == "📊 Análisis vs Lista":
    st.title("📊 Análisis de Precios vs MercadoLibre")

    col1, col2 = st.columns([2,1])
    with col1:
        queries_txt = st.text_area(
            "Productos a buscar en ML (uno por línea)",
            placeholder="Aceite de girasol\nAzúcar blanca 1kg\nFideos spaghetti 500g",
            height=120,
        )
    with col2:
        archivo_interno = st.file_uploader("Tu lista de precios (xlsx/csv)", type=["xlsx","csv"],
                                            help="Columnas: articulo/descripcion, precio_venta, costo (opcional)")
        margen_min = st.number_input("Margen mínimo (%)", 0, 100, 15)

    if st.button("🚀 Analizar", type="primary", disabled=not MODULE_OK):
        if not queries_txt.strip():
            st.warning("Ingresá al menos un producto.")
        else:
            queries     = [q.strip() for q in queries_txt.strip().splitlines() if q.strip()]
            df_interno  = None
            if archivo_interno:
                try:
                    df_interno = pd.read_csv(archivo_interno) if archivo_interno.name.endswith(".csv") else pd.read_excel(archivo_interno)
                    st.success(f"✅ Lista: {len(df_interno)} artículos")
                except Exception as e:
                    st.error(f"Error: {e}")
            log_msgs = []
            with st.spinner("Analizando..."):
                resultado = ejecutar_market_research(
                    queries=queries, df_interno=df_interno,
                    incluir_tendencias=False,
                    incluir_ia=incluir_ia and df_interno is not None,
                    max_por_query=max_items,
                    usar_expansion_ia=incluir_ia,
                    contexto=contexto_neg,
                    log_func=lambda m: log_msgs.append(m),
                )
            st.session_state["analisis_resultado"] = resultado
            st.session_state["analisis_log"]       = log_msgs

    if "analisis_resultado" in st.session_state:
        resultado = st.session_state["analisis_resultado"]
        analisis  = resultado.get("analisis", {})
        ml_data   = resultado.get("ml_data", {})

        # KPIs
        stats = analisis.get("estadisticas", {})
        if stats:
            c1,c2,c3,c4 = st.columns(4)
            for col, lbl, val, color in [
                (c1,"Artículos",    stats.get("total_articulos",0),    "#0057A8"),
                (c2,"Con datos ML", stats.get("con_comparacion_ml",0), "#107E3E"),
                (c3,"Alertas",      stats.get("alertas_total",0),      "#E9730C"),
                (c4,"Margen prom.", f"{stats.get('margen_promedio','N/D')}%", "#5B2A8A"),
            ]:
                col.markdown(f"""<div class="kpi-card"><div class="kpi-val" style="color:{color}">{val}</div><div class="kpi-lbl">{lbl}</div></div>""", unsafe_allow_html=True)
            st.markdown("")

        tab1, tab2, tab3, tab4 = st.tabs(["📋 Comparación", "🚨 Alertas", "🛒 Todos los precios ML", "🤖 IA"])

        with tab1:
            df_comp = analisis.get("comparacion")
            if df_comp is not None and not df_comp.empty:
                # Semáforo column
                st.dataframe(df_comp, use_container_width=True, height=420)
            else:
                st.info("Subí tu lista interna para ver la comparación.")
                for q, items in ml_data.items():
                    if items:
                        precios = [i["precio"] for i in items]
                        c1,c2,c3 = st.columns(3)
                        c1.metric(q[:40], f"${sum(precios)/len(precios):,.0f}", "promedio")
                        c2.metric("Mínimo",  f"${min(precios):,.0f}")
                        c3.metric("Máximo",  f"${max(precios):,.0f}")

        with tab2:
            alertas = analisis.get("alertas",[])
            if alertas:
                for a in sorted(alertas, key=lambda x: x["prioridad"]):
                    css = "alert-alta" if a["prioridad"]=="ALTA" else "alert-media"
                    st.markdown(f'<div class="{css}"><b>[{a["prioridad"]}] {a["tipo"]}</b> — {a["articulo"]}: {a["mensaje"]}</div>', unsafe_allow_html=True)
            else:
                st.success("Sin alertas críticas 🎉")

        with tab3:
            ml_rows = [{"Búsqueda":q,"Título":i["titulo"][:60],"Precio":i["precio"],
                        "Vendedor":i["vendedor"],"Vendidos":i["vendidos"],"URL":i["url"]}
                       for q, items in ml_data.items() for i in items]
            if ml_rows:
                st.dataframe(pd.DataFrame(ml_rows), use_container_width=True, height=420,
                             column_config={"URL": st.column_config.LinkColumn()})

        with tab4:
            rec = resultado.get("recomendaciones_ia","")
            if rec:
                st.markdown(f'<div class="ia-box">{rec}</div>', unsafe_allow_html=True)
            else:
                st.info("Activá 'Motor IA' y subí lista interna para ver recomendaciones.")

        if st.button("📥 Exportar a Excel"):
            path = exportar_excel(resultado)
            if path:
                with open(path,"rb") as f:
                    st.download_button("⬇️ Descargar", f, file_name=Path(path).name,
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        with st.expander("📋 Log"):
            for m in st.session_state.get("analisis_log",[]): st.text(m)


# ══════════════════════════════════════════════════════════════
# MÓDULO 4 — PRECIO ÓPTIMO
# ══════════════════════════════════════════════════════════════
elif modo == "🧮 Precio Óptimo":
    st.title("🧮 Calculador de Precio Óptimo")
    st.caption("Ingresá el producto y tu costo — la IA sugiere el precio ideal basado en la competencia en ML")

    col1, col2, col3 = st.columns([2,1,1])
    with col1:
        producto = st.text_input("Producto", placeholder="Ej: Manaos naranja 2L")
    with col2:
        costo_input = st.number_input("Tu costo ($)", min_value=0.0, value=0.0, step=10.0)
    with col3:
        margen_min_opt = st.number_input("Margen mínimo (%)", 0, 100, 20)

    if st.button("🧮 Calcular precio óptimo", type="primary",
                 disabled=not MODULE_OK or not producto or costo_input <= 0):
        log_msgs = []
        with st.spinner("Buscando en ML y calculando..."):
            resumen = scrape_con_expansion_ia(
                producto, max_items, contexto_neg,
                log_func=lambda m: log_msgs.append(m)
            )
            resultado_optimo = precio_optimo_ia(
                producto, costo_input, resumen,
                margen_min_opt / 100, contexto_neg,
                log_func=lambda m: log_msgs.append(m)
            )
        st.session_state["precio_optimo_res"]    = resultado_optimo
        st.session_state["precio_optimo_resumen"] = resumen

    if "precio_optimo_res" in st.session_state:
        r   = st.session_state["precio_optimo_res"]
        res = st.session_state["precio_optimo_resumen"]

        precio_sug = r.get("precio_sugerido", 0)
        margen_r   = r.get("margen_pct", 0)
        pos        = r.get("posicionamiento", "MEDIO")
        just       = r.get("justificacion", "")
        alerta_opt = r.get("alerta")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 Precio sugerido", f"${precio_sug:,.0f}")
        col2.metric("📈 Margen esperado", f"{margen_r:.1f}%")
        col3.metric("🎯 Posicionamiento", pos)
        col4.metric("📊 Competidores ML", res.get("total_resultados",0))

        st.info(f"**Justificación:** {just}")
        if alerta_opt:
            st.warning(f"⚠ {alerta_opt}")

        # Contexto de mercado
        st.markdown("---")
        st.subheader("Contexto del mercado")
        c1,c2,c3 = st.columns(3)
        c1.metric("ML mínimo",  f"${res.get('precio_min',0):,.0f}")
        c2.metric("ML mediana", f"${res.get('precio_mediana',0):,.0f}")
        c3.metric("ML máximo",  f"${res.get('precio_max',0):,.0f}")

        # Top productos
        items = res.get("items",[])[:6]
        if items:
            st.markdown("**Top productos en ML:**")
            grid_cols = st.columns(min(3, len(items)))
            for j, it in enumerate(items[:3]):
                with grid_cols[j]:
                    if it.get("thumbnail"): st.image(it["thumbnail"], width=80)
                    st.markdown(f"**${it['precio']:,.0f}**")
                    st.caption(it["titulo"][:40])


# ══════════════════════════════════════════════════════════════
# MÓDULO 5 — MARKET RESEARCH
# ══════════════════════════════════════════════════════════════
elif modo == "📈 Market Research":
    st.title("📈 Market Research — Tendencias y Competencia")

    categoria = st.text_input("Categoría o rubro", placeholder="Ej: almacén seco, limpieza del hogar, bebidas")
    col1, col2 = st.columns(2)
    with col1: incluir_trends = st.checkbox("Google Trends (puede fallar)", value=False)
    with col2: n_ranking = st.slider("Productos en ranking", 10, 50, 20)

    if st.button("🔬 Investigar mercado", type="primary", disabled=not categoria or not MODULE_OK):
        queries  = [w.strip() for w in categoria.split(",") if w.strip()] or [categoria]
        log_msgs = []
        with st.spinner("Investigando mercado..."):
            resultado = ejecutar_market_research(
                queries=queries, incluir_tendencias=incluir_trends,
                incluir_ia=incluir_ia, max_por_query=max_items,
                usar_expansion_ia=incluir_ia, contexto=contexto_neg,
                log_func=lambda m: log_msgs.append(m),
            )
        st.session_state["market_result"] = resultado
        st.session_state["market_log"]    = log_msgs

    if "market_result" in st.session_state:
        res = st.session_state["market_result"]
        tab1, tab2, tab3 = st.tabs(["🏆 Más vendidos", "📈 Tendencias", "💡 Insights IA"])

        with tab1:
            ranking = res.get("ranking",[])
            if ranking:
                # Cards de ranking con thumbnails
                for i in range(0, min(len(ranking), 12), 3):
                    cols = st.columns(3)
                    for j, col in enumerate(cols):
                        idx = i + j
                        if idx >= len(ranking): break
                        r = ranking[idx]
                        with col:
                            if r.get("thumbnail"): st.image(r["thumbnail"], width=90)
                            st.markdown(f"**#{r['posicion']} — ${r['precio']:,.0f}**")
                            st.caption(r["titulo"][:50])
                            if r.get("vendidos"): st.caption(f"✅ {r['vendidos']} vendidos")
                            st.markdown(f"[Ver en ML]({r['url']})")
            else:
                st.info("Sin datos de ranking.")

        with tab2:
            tendencias = res.get("tendencias",{})
            if tendencias:
                for kw, datos in tendencias.items():
                    tend = "🟢 SUBE" if datos["tendencia"]=="SUBE" else "🔴 BAJA"
                    st.metric(kw, f"{datos['promedio']:.0f}/100", tend)
            else:
                st.info("Google Trends no disponible. Activá el checkbox y probá nuevamente.")

        with tab3:
            rec = res.get("recomendaciones_ia","")
            if rec:
                st.markdown(f'<div class="ia-box">{rec}</div>', unsafe_allow_html=True)
            else:
                st.info("Activá 'Motor IA' en el sidebar.")

        with st.expander("📋 Log"):
            for m in st.session_state.get("market_log",[]): st.text(m)


# ══════════════════════════════════════════════════════════════
# MÓDULO 6 — HISTORIAL
# ══════════════════════════════════════════════════════════════
elif modo == "📉 Historial":
    st.title("📉 Evolución Histórica de Precios")

    if not _HISTORY_FILE.exists():
        st.info("Aún no hay historial. Realizá una búsqueda primero.")
    else:
        try: hist = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception: hist = []

        if not hist:
            st.info("Historial vacío.")
        else:
            todas_queries = set()
            for snap in hist:
                todas_queries.update(snap.get("datos",{}).keys())

            query_sel = st.selectbox("Producto", sorted(todas_queries))
            if query_sel:
                serie = cargar_historial_precios(query_sel)
                if serie:
                    df_hist = pd.DataFrame(serie)
                    df_hist["fecha"] = pd.to_datetime(df_hist["fecha"])

                    tab_graf, tab_delta = st.tabs(["📈 Evolución", "📊 Delta vs anterior"])

                    with tab_graf:
                        st.line_chart(df_hist.set_index("fecha")[["precio_min","precio_promedio","precio_max"]])
                        st.dataframe(df_hist, use_container_width=True)

                    with tab_delta:
                        if len(serie) >= 2:
                            ultimo  = serie[-1]
                            anterior= serie[-2]
                            delta   = ((ultimo["precio_promedio"] - anterior["precio_promedio"])
                                       / anterior["precio_promedio"] * 100) if anterior["precio_promedio"] else 0
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Precio actual",   f"${ultimo['precio_promedio']:,.0f}",
                                      f"{delta:+.1f}% vs {anterior['fecha']}")
                            c2.metric("Período anterior",f"${anterior['precio_promedio']:,.0f}",
                                      anterior["fecha"])
                            tend = "🔺 SUBE" if delta > 2 else "🔻 BAJA" if delta < -2 else "➡ ESTABLE"
                            c3.metric("Tendencia", tend)
                            df_delta = pd.DataFrame([
                                {"Fecha": s["fecha"], "Precio prom": s["precio_promedio"],
                                 "Delta %": round((s["precio_promedio"] - serie[max(0,i-1)]["precio_promedio"])
                                                  / serie[max(0,i-1)]["precio_promedio"] * 100, 1) if i > 0 else 0}
                                for i, s in enumerate(serie)
                            ])
                            st.dataframe(df_delta, use_container_width=True)
                        else:
                            st.info("Necesitás al menos 2 snapshots para ver el delta.")
                else:
                    st.info(f"Sin historial para '{query_sel}'.")


# ══════════════════════════════════════════════════════════════
# MÓDULO 7 — IA AVANZADA
# ══════════════════════════════════════════════════════════════
elif modo == "🤖 IA Avanzada":
    st.title("🤖 Recomendaciones IA Avanzadas")

    archivo  = st.file_uploader("Tu lista de precios", type=["xlsx","csv"])
    contexto = st.text_input("Descripción del negocio", value=contexto_neg)
    queries_txt = st.text_area("Productos a comparar (uno por línea)",
                                placeholder="Aceite\nAzúcar\nFideos", height=100)

    if st.button("🤖 Generar análisis IA", type="primary", disabled=not archivo or not MODULE_OK):
        df_ia = pd.read_csv(archivo) if archivo.name.endswith(".csv") else pd.read_excel(archivo)
        queries_ia = [q.strip() for q in queries_txt.strip().splitlines() if q.strip()]
        with st.spinner("Analizando y consultando IA..."):
            ml_data_ia = scrape_multiple_queries(queries_ia, 15) if queries_ia else {}
            analisis_ia = analizar_precios(df_ia, ml_data_ia) if ml_data_ia else {}
            rec_ia = recomendaciones_ia(analisis_ia, contexto) if analisis_ia else "Sin datos suficientes."
        st.session_state["ia_avanzada_rec"] = rec_ia

    if "ia_avanzada_rec" in st.session_state:
        st.markdown("### Recomendaciones")
        st.markdown(f'<div class="ia-box">{st.session_state["ia_avanzada_rec"]}</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# MÓDULO 8 — MOTOR PRICING PARA LISTA INTERNA
# ══════════════════════════════════════════════════════════════
if modo == "🏷️ Motor Pricing Lista":
    st.title("🏷️ Motor de Pricing IA — Lista completa")
    st.caption("Cargá tu lista de precios actual y la IA sugerirá precios óptimos basados en el mercado de MercadoLibre.")

    col_up, col_cfg = st.columns([2, 1])
    with col_up:
        archivo_lista = st.file_uploader(
            "📂 Tu lista de precios (Excel con SKU, Descripción, Costo, Precio actual)",
            type=["xlsx","xls"], key="motor_lista"
        )
    with col_cfg:
        margen_min_motor = st.slider("Margen mínimo (%)", 5, 60, 20, key="mg_motor")
        max_items_motor  = st.slider("Artículos a procesar", 5, 50, 20, key="max_motor")
        st.caption("⚠ Cada artículo consume ~1 búsqueda ML + 1 llamada IA")

    if archivo_lista:
        import pandas as pd, io as _io
        df_lista = pd.read_excel(archivo_lista, engine="openpyxl")
        st.write(f"📋 **{len(df_lista)} artículos** en tu lista")
        st.dataframe(df_lista.head(5), use_container_width=True, hide_index=True)

        col_a, col_b = st.columns(2)
        col_desc = col_a.selectbox("Columna Descripción", df_lista.columns.tolist(), key="mp_desc")
        col_cost = col_b.selectbox("Columna Costo", df_lista.columns.tolist(), key="mp_cost")

        if st.button("🚀 Calcular precios óptimos con IA", type="primary", use_container_width=True, key="btn_motor"):
            df_proc = df_lista.head(max_items_motor).copy()
            resultados_motor = []
            prog = st.progress(0, text="Iniciando...")
            log_motor = []

            for i, (_, row) in enumerate(df_proc.iterrows()):
                descripcion = str(row.get(col_desc, "")).strip()
                costo       = float(row.get(col_cost, 0) or 0)
                if not descripcion or costo <= 0:
                    continue
                prog.progress((i + 1) / len(df_proc), text=f"Procesando: {descripcion[:40]}...")
                try:
                    resumen_ml = scrape_con_expansion_ia(descripcion, max_items=10,
                                                          log_func=lambda m: log_motor.append(m))
                    precio_op  = precio_optimo_ia(descripcion, costo, resumen_ml,
                                                   log_func=lambda m: log_motor.append(m))
                    precio_sug = precio_op.get("precio_sugerido", round(costo * (1 + margen_min_motor/100), 2))
                    precio_ml_med = resumen_ml.get("precio_mediana", 0)
                    margen_real   = (precio_sug - costo) / costo * 100 if costo > 0 else 0
                    semaforo = "🔴" if precio_sug > precio_ml_med * 1.1 else                                "🟡" if precio_sug > precio_ml_med * 0.95 else "🟢"
                    resultados_motor.append({
                        "Descripción":    descripcion,
                        "Costo":          round(costo, 2),
                        "Precio ML med.": round(precio_ml_med, 2),
                        "Precio sugerido":round(precio_sug, 2),
                        "Margen %":       round(margen_real, 1),
                        "Estado":         semaforo,
                        "Justificación":  precio_op.get("justificacion", "")[:80],
                    })
                except Exception as e_motor:
                    resultados_motor.append({
                        "Descripción": descripcion, "Costo": costo,
                        "Precio ML med.": 0, "Precio sugerido": round(costo*(1+margen_min_motor/100),2),
                        "Margen %": margen_min_motor, "Estado": "⚪", "Justificación": f"Sin datos ML: {str(e_motor)[:40]}",
                    })
            prog.empty()
            st.session_state["motor_resultados"] = resultados_motor

        if "motor_resultados" in st.session_state and st.session_state["motor_resultados"]:
            df_motor_res = pd.DataFrame(st.session_state["motor_resultados"])
            st.markdown("---")
            st.markdown(f"### Resultados — {len(df_motor_res)} artículos")

            # KPIs
            m1, m2, m3 = st.columns(3)
            m1.metric("🟢 Competitivos",  (df_motor_res["Estado"]=="🟢").sum())
            m2.metric("🟡 Algo caros",    (df_motor_res["Estado"]=="🟡").sum())
            m3.metric("🔴 Muy caros",     (df_motor_res["Estado"]=="🔴").sum())

            st.dataframe(df_motor_res, use_container_width=True, height=350, hide_index=True)

            # Exportar para robot
            buf_motor = _io.BytesIO()
            with pd.ExcelWriter(buf_motor, engine="openpyxl") as wr:
                df_motor_res.to_excel(wr, index=False, sheet_name="Pricing IA")
            buf_motor.seek(0)
            st.download_button("⬇️ Exportar Excel con precios sugeridos",
                               data=buf_motor.getvalue(),
                               file_name="motor_pricing_ia.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="dl_motor")

            # Exportar para robot de precios
            if st.button("📤 Generar precios_*.xlsx para robot", key="btn_motor_robot"):
                items_robot = [
                    {"sku":              str(r.get("SKU", r["Descripción"][:15])),
                     "costo":            r["Costo"],
                     "precio_salon":     r["Precio sugerido"],
                     "precio_mayorista": round(r["Precio sugerido"] * 0.90, 2),
                     "precio_galpon":    0}
                    for r in st.session_state["motor_resultados"]
                ]
                path_r = exportar_para_robot(items_robot, log_func=lambda m: None)
                if path_r:
                    with open(path_r, "rb") as f_r:
                        st.success(f"✅ {Path(path_r).name} generado — copialo a input/")
                        st.download_button("⬇️ Descargar", f_r.read(),
                                           file_name=Path(path_r).name,
                                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                           key="dl_motor_robot")
    else:
        st.info("⬆️ Subí tu lista de precios para comenzar.")
