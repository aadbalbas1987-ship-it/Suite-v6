"""
auditoria_dashboard.py — RPA Suite v6.0
Dashboard de Auditoría y Control de Robots
Lee directamente de la base de datos SQLite en modo WAL.
"""

import sys
from pathlib import Path
_RAIZ = Path(__file__).parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import streamlit as st
import pandas as pd
import numpy as np
import datetime
import plotly.express as px
import sqlite3
from core.database import DB_PATH

st.set_page_config(page_title="Auditoría de Robots · RPA Suite", page_icon="🕵️", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Sora', sans-serif; }
.kpi-box { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); text-align: center; }
.kpi-title { font-size: 0.85rem; color: #64748b; text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em; }
.kpi-value { font-size: 2rem; font-weight: 700; color: #0f172a; margin-top: 5px; }
.header-container { background: linear-gradient(135deg, #0B1120 0%, #1A2535 100%); padding: 1.5rem 2rem; border-radius: 12px; color: white; margin-bottom: 1rem; border-left: 5px solid #0057A8; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-container">
    <h1 style="margin:0; font-size:1.8rem; font-weight:700;">🕵️ Data Intelligence & Auditoría de Robots</h1>
    <p style="margin:5px 0 0 0; color:#cbd5e1; font-size:0.9rem;">Trazabilidad de precios, cálculo de deltas y segmentación temporal</p>
</div>
""", unsafe_allow_html=True)

@st.cache_resource
def init_maestro():
    from core.utils import cargar_maestro_descripciones
    cargar_maestro_descripciones(_RAIZ)

init_maestro()

# ── CONEXIÓN A BASE DE DATOS ──
@st.cache_data(ttl=15)  # Refresca cada 15s para no saturar el procesador
def load_data():
    from core.utils import obtener_descripcion_maestra
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)  # Read-only para no bloquear
        
        # Precios
        df_precios = pd.read_sql_query("SELECT * FROM historial_precios_propios", conn)
        if not df_precios.empty:
            df_precios['timestamp'] = pd.to_datetime(df_precios['timestamp'])
            df_precios['Fecha'] = df_precios['timestamp'].dt.date
            df_precios['Descripcion'] = df_precios['sku'].apply(obtener_descripcion_maestra)
            
            # Lógica de Deltas (Ventana de tiempo por SKU)
            df_precios.sort_values(by=['sku', 'timestamp'], ascending=[True, True], inplace=True)
            df_precios['Precio_Anterior'] = df_precios.groupby('sku')['precio_salon'].shift(1)
            df_precios['Var_$'] = df_precios['precio_salon'] - df_precios['Precio_Anterior']
            mask_valido = (df_precios['Precio_Anterior'].notna()) & (df_precios['Precio_Anterior'] != 0)
            df_precios['Var_%'] = np.where(mask_valido, (df_precios['Var_$'] / df_precios['Precio_Anterior']) * 100, np.nan)
            
            # Motor de Alertas
            def get_alerta(v):
                if pd.isna(v): return "🔵 Registro Inicial"
                if v >= 20.0:  return "🚨 Subida Crítica (>20%)" # Posible doble IVA o hiperinflación
                if v > 5.0:    return "⬆️ Aumento Fuerte"
                if v > 0:      return "↗️ Ajuste Leve (+)"
                if v <= -10.0: return "📉 Baja Peligrosa (<10%)"
                if v < 0:      return "↘️ Baja Menor (-)"
                return "➖ Sin Cambio"
            
            df_precios['Alerta'] = df_precios['Var_%'].apply(get_alerta)
            df_precios.sort_values('timestamp', ascending=False, inplace=True)
            
        # Stock
        df_stock = pd.read_sql_query("SELECT * FROM cargas_stock ORDER BY timestamp DESC", conn)
        if not df_stock.empty:
            df_stock['timestamp'] = pd.to_datetime(df_stock['timestamp'])
            df_stock['Fecha'] = df_stock['timestamp'].dt.date
            df_stock['Descripcion'] = df_stock['sku'].apply(obtener_descripcion_maestra)
            
        conn.close()
        return df_precios, df_stock
    except Exception as e:
        st.error(f"Error conectando a la base de datos: {e}")
        return pd.DataFrame(), pd.DataFrame()

df_precios, df_stock = load_data()

if df_precios.empty and df_stock.empty:
    st.info("No hay registros en la base de datos todavía. Ejecutá los robots de Precios o Stock para empezar a recolectar historial.")
    st.stop()

# ── SIDEBAR: CALENDARIO Y FILTROS ──
with st.sidebar:
    st.markdown("### 📅 Segmentación Temporal")
    todas_fechas = pd.concat([df_precios['Fecha'] if not df_precios.empty else pd.Series(), 
                              df_stock['Fecha'] if not df_stock.empty else pd.Series()])
    if not todas_fechas.empty:
        min_d = todas_fechas.min()
        max_d = todas_fechas.max()
    else:
        min_d = max_d = datetime.date.today()
        
    rango_fechas = st.date_input("Filtrar ejecuciones por fecha", value=(max_d, max_d), min_value=min_d, max_value=max_d)
    
    if isinstance(rango_fechas, tuple):
        if len(rango_fechas) == 2:
            start_d, end_d = rango_fechas
        elif len(rango_fechas) == 1:
            start_d = end_d = rango_fechas[0]
        else:
            start_d = end_d = max_d
    else:
        start_d = end_d = rango_fechas
        
    # Filtros extra
    st.markdown("---")
    st.markdown("### 🔍 Filtros Globales")
    origen_ops = pd.concat([df_precios['robot_origen'] if not df_precios.empty else pd.Series(),
                            df_stock['robot_origen'] if not df_stock.empty else pd.Series()]).unique()
    origen_filt = st.multiselect("Origen de Ejecución (Archivo)", options=origen_ops)
    sku_filt = st.text_input("Buscar por SKU o Nombre")

# ── APLICAR FILTROS DE FECHA Y TEXTO ──
df_p_show = df_precios.copy()
df_s_show = df_stock.copy()

if start_d and end_d:
    if not df_p_show.empty: df_p_show = df_p_show[(df_p_show['Fecha'] >= start_d) & (df_p_show['Fecha'] <= end_d)]
    if not df_s_show.empty: df_s_show = df_s_show[(df_s_show['Fecha'] >= start_d) & (df_s_show['Fecha'] <= end_d)]
if origen_filt:
    if not df_p_show.empty: df_p_show = df_p_show[df_p_show['robot_origen'].isin(origen_filt)]
    if not df_s_show.empty: df_s_show = df_s_show[df_s_show['robot_origen'].isin(origen_filt)]
if sku_filt:
    if not df_p_show.empty:
        df_p_show = df_p_show[df_p_show['sku'].astype(str).str.contains(sku_filt, case=False) | 
                              df_p_show['Descripcion'].str.contains(sku_filt, case=False)]
    if not df_s_show.empty:
        df_s_show = df_s_show[df_s_show['sku'].astype(str).str.contains(sku_filt, case=False) | 
                              df_s_show['Descripcion'].str.contains(sku_filt, case=False)]

# ── KPIS DEL PERÍODO SELECCIONADO ──
c1, c2, c3, c4 = st.columns(4)
total_p = len(df_p_show)
total_s = len(df_s_show)
total_skus = len(pd.concat([df_p_show['sku'] if not df_p_show.empty else pd.Series(), 
                            df_s_show['sku'] if not df_s_show.empty else pd.Series()]).unique())

aumento_prom = f"{df_p_show['Var_%'].mean():+.1f}%" if (not df_p_show.empty and not pd.isna(df_p_show['Var_%'].mean())) else "N/A"

c1.markdown(f'<div class="kpi-box"><div class="kpi-title">Modificaciones (Período)</div><div class="kpi-value" style="color:#0057A8;">{total_p:,}</div></div>', unsafe_allow_html=True)
c2.markdown(f'<div class="kpi-box"><div class="kpi-title">Alerta Aumento Promedio</div><div class="kpi-value" style="color:#E84855;">{aumento_prom}</div></div>', unsafe_allow_html=True)
c3.markdown(f'<div class="kpi-box"><div class="kpi-title">Cargas de Stock</div><div class="kpi-value" style="color:#10b981;">{total_s:,}</div></div>', unsafe_allow_html=True)
c4.markdown(f'<div class="kpi-box"><div class="kpi-title">SKUs Únicos Procesados</div><div class="kpi-value" style="color:#8b5cf6;">{total_skus:,}</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["💰 Historial de Precios", "📦 Historial de Stock", "🔍 Verificación de Impacto"])

# ── TAB PRECIOS ──
with tab1:
    if df_p_show.empty:
        st.info("No hay registros de precios para los filtros seleccionados.")
    else:
        col_graf1, col_graf2 = st.columns([1, 2])
        
        with col_graf1:
            st.markdown("#### Distribución de Alertas")
            alertas_count = df_p_show['Alerta'].value_counts().reset_index()
            alertas_count.columns = ['Tipo', 'Cantidad']
            color_map = {
                "🚨 Subida Crítica (>20%)": "#EF4444", "⬆️ Aumento Fuerte": "#F59E0B", 
                "↗️ Ajuste Leve (+)": "#3B82F6", "📉 Baja Peligrosa (<10%)": "#7F1D1D", 
                "↘️ Baja Menor (-)": "#8B5CF6", "➖ Sin Cambio": "#94A3B8", "🔵 Registro Inicial": "#CBD5E1"
            }
            fig_pie = px.pie(alertas_count, names='Tipo', values='Cantidad', hole=0.5, 
                             color='Tipo', color_discrete_map=color_map)
            fig_pie.update_layout(margin=dict(t=10, b=10, l=0, r=0), height=300, showlegend=False)
            fig_pie.update_traces(textinfo='label+percent', textposition='outside')
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with col_graf2:
            st.markdown("#### Evolución Diaria (Volumen de Modificaciones)")
            act_precios = df_p_show.groupby('Fecha').size().reset_index(name='Actualizaciones')
            fig_p = px.line(act_precios, x='Fecha', y='Actualizaciones', markers=True, 
                            line_shape="spline", template="plotly_white")
            fig_p.update_traces(line_color='#0057A8', marker=dict(size=8), fill='tozeroy', fillcolor='rgba(0,87,168,0.1)')
            fig_p.update_layout(height=300, margin=dict(t=10, b=0, l=0, r=0), xaxis_title="")
            st.plotly_chart(fig_p, use_container_width=True)
        
        st.markdown("#### 📋 Base de Datos de Modificaciones")
        
        # Preparar tabla para visualización nativa de Streamlit con Column Config
        df_view = df_p_show[['timestamp', 'sku', 'Descripcion', 'Precio_Anterior', 'precio_salon', 'Var_$', 'Var_%', 'Alerta', 'robot_origen']].copy()
        df_view['timestamp'] = df_view['timestamp'].dt.strftime("%Y-%m-%d %H:%M:%S")
        
        st.dataframe(
            df_view,
            column_config={
                "timestamp": st.column_config.TextColumn("Fecha/Hora", width="medium"),
                "sku": st.column_config.TextColumn("SKU", width="small"),
                "Descripcion": st.column_config.TextColumn("Artículo", width="large"),
                "Precio_Anterior": st.column_config.NumberColumn("P. Anterior", format="$ %.2f", width="small"),
                "precio_salon": st.column_config.NumberColumn("P. Nuevo", format="$ %.2f", width="small"),
                "Var_$": st.column_config.NumberColumn("Variación $", format="$ %.2f", width="small"),
                "Var_%": st.column_config.NumberColumn("Variación %", format="%.1f%%", width="small"),
                "Alerta": st.column_config.TextColumn("Diagnóstico", width="medium"),
                "robot_origen": st.column_config.TextColumn("Archivo / Origen", width="medium"),
            },
            use_container_width=True, hide_index=True, height=450
        )

# ── TAB STOCK ──
with tab2:
    if df_s_show.empty:
        st.info("No hay registros de stock para los filtros seleccionados.")
    else:
        col_fs1, col_fs2 = st.columns([1, 1])
        with col_fs1:
            st.markdown("#### Línea de tiempo de cargas físicas")
            act_stock = df_s_show.groupby('Fecha')['cantidad_cargada'].sum().reset_index(name='Volumen_Total')
            fig_s = px.line(act_stock, x='Fecha', y='Volumen_Total', markers=True, 
                            line_shape="spline", template="plotly_white")
            fig_s.update_traces(line_color='#10b981', marker=dict(size=8), fill='tozeroy', fillcolor='rgba(16,185,129,0.1)')
            fig_s.update_layout(height=300, margin=dict(t=10, b=0, l=0, r=0))
            st.plotly_chart(fig_s, use_container_width=True)
            
        with col_fs2:
            st.markdown("#### 🏆 Top 10 SKUs (Mayor cantidad ingresada)")
            df_s_show['Desc_Corta'] = df_s_show['Descripcion'].apply(lambda x: str(x)[:25])
            top_skus = df_s_show.groupby(['sku', 'Desc_Corta'])['cantidad_cargada'].sum().nlargest(10).reset_index()
            fig_top = px.bar(top_skus, x='cantidad_cargada', y='Desc_Corta', orientation='h', 
                             template="plotly_white", color_discrete_sequence=['#10b981'])
            fig_top.update_layout(yaxis={'categoryorder':'total ascending', 'type':'category'}, 
                                  margin=dict(t=10, b=0, l=0, r=0), height=300, yaxis_title="")
            st.plotly_chart(fig_top, use_container_width=True)

        st.markdown("#### 📋 Registro Detallado de Ingresos de Stock")
        df_s_view = df_s_show[['timestamp', 'sku', 'Descripcion', 'cantidad_cargada', 'robot_origen']].copy()
        df_s_view['timestamp'] = df_s_view['timestamp'].dt.strftime("%Y-%m-%d %H:%M:%S")
        
        with st.container():
            st.dataframe(
                df_s_view,
                column_config={
                    "timestamp": st.column_config.TextColumn("Fecha/Hora", width="medium"),
                    "sku": st.column_config.TextColumn("SKU", width="small"),
                    "Descripcion": st.column_config.TextColumn("Artículo", width="large"),
                    "cantidad_cargada": st.column_config.NumberColumn("Unidades Ingresadas", format="%d", width="medium"),
                    "robot_origen": st.column_config.TextColumn("Archivo / Origen", width="medium"),
                },
                use_container_width=True, hide_index=True, height=400
            )

# ── TAB 3: VERIFICACIÓN DE IMPACTO ──
with tab3:
    st.markdown("#### 🔍 Verificación de Impacto de Precios")
    st.caption("Verifica si los robots impactaron correctamente los cambios cruzando el historial contra tu listado actual.")

    @st.cache_data(show_spinner=False)
    def _leer_archivo_verif(nombre, contenido_bytes):
        import io
        if nombre.lower().endswith(".csv"):
            for sep in [';', ',', '\t', '|']:
                try:
                    df_tmp = pd.read_csv(io.BytesIO(contenido_bytes), sep=sep, encoding='latin-1', on_bad_lines='skip')
                    if len(df_tmp.columns) > 1: return df_tmp
                except: continue
            return pd.read_csv(io.BytesIO(contenido_bytes), on_bad_lines='skip')
        else:
            return pd.read_excel(io.BytesIO(contenido_bytes))

    # Detectar archivo automático en la raíz
    archivo_auto = None
    for f in _RAIZ.iterdir():
        if f.is_file() and "lista de precios" in f.name.lower() and f.suffix.lower() in ['.csv', '.xlsx', '.xls']:
            archivo_auto = f
            break
            
    df_verif = None
    
    if archivo_auto:
        st.success(f"✅ Archivo maestro detectado automáticamente en la raíz: **{archivo_auto.name}**")
        with open(archivo_auto, 'rb') as f:
            df_verif = _leer_archivo_verif(archivo_auto.name, f.read()).copy()
            
        with st.expander("Subir otro archivo manualmente (Opcional)"):
            archivo_manual = st.file_uploader("Reemplazar listado", type=["csv", "xlsx", "xls"], key="up_verif_manual")
            if archivo_manual:
                df_verif = _leer_archivo_verif(archivo_manual.name, archivo_manual.getvalue()).copy()
    else:
        st.info("💡 Tip: Si dejás un archivo con 'lista de precios' en el nombre en la carpeta raíz, se cargará automáticamente aquí.")
        archivo_manual = st.file_uploader("Subir listado de precios actual (CSV o Excel)", type=["csv", "xlsx", "xls"], key="up_verif")
        if archivo_manual:
            df_verif = _leer_archivo_verif(archivo_manual.name, archivo_manual.getvalue()).copy()

    if df_verif is not None:
        try:
            # Autodetectar columnas
            cols_lower = {str(c).lower().strip(): c for c in df_verif.columns}
            col_sku = next((cols_lower[k] for k in ['sku', 'articulo', 'codigo', 'cod', 'codart'] if k in cols_lower), None)
            col_precio = next((cols_lower[k] for k in ['precio', 'p_salon', 'precio salon', 'psalon', 'precio_venta'] if k in cols_lower), None)
            col_desc = next((cols_lower[k] for k in ['descripcion', 'desc', 'detalle', 'nombre'] if k in cols_lower), None)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                sel_sku = st.selectbox("Columna SKU", df_verif.columns, index=list(df_verif.columns).index(col_sku) if col_sku else 0)
            with col2:
                sel_desc = st.selectbox("Columna Descripción (Opcional)", ["—"] + list(df_verif.columns), index=(list(df_verif.columns).index(col_desc) + 1) if col_desc else 0)
            with col3:
                sel_precio = st.selectbox("Columna Precio", df_verif.columns, index=list(df_verif.columns).index(col_precio) if col_precio else 0)

            st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
            with st.spinner("Comparando precios automáticamente..."):
                from core.pre_validador import _limpiar_sku, _to_float
                
                df_verif['sku_clean'] = df_verif[sel_sku].apply(_limpiar_sku)
                df_verif['precio_sistema'] = df_verif[sel_precio].apply(_to_float)
                
                df_v = df_verif.dropna(subset=['sku_clean', 'precio_sistema']).copy()
                df_v = df_v[df_v['sku_clean'] != "None"]
                
                if df_precios.empty:
                    st.warning("No hay historial de precios de robots en la base de datos para comparar.")
                else:
                    # Obtener el ÚLTIMO precio intentado por SKU
                    df_ultimos = df_precios.sort_values('timestamp').groupby('sku').last().reset_index()
                    
                    df_merge = pd.merge(df_v, df_ultimos[['sku', 'precio_salon', 'timestamp', 'robot_origen']], 
                                        left_on='sku_clean', right_on='sku', how='inner')
                    
                    if df_merge.empty:
                        st.warning("No se encontraron coincidencias de SKU entre tu archivo y el historial de robots.")
                    else:
                        df_merge['Diferencia_$'] = df_merge['precio_sistema'] - df_merge['precio_salon']
                        # Consideramos falla si la diferencia es mayor a $0.05
                        df_merge['Impacto'] = np.where(df_merge['Diferencia_$'].abs() > 0.05, "❌ Falló", "✅ Impactado")
                        df_fallas = df_merge[df_merge['Impacto'] == "❌ Falló"]
                        
                        # KPIs de Auditoría
                        st.markdown("##### 📊 Resumen de Impacto")
                        c_k1, c_k2, c_k3 = st.columns(3)
                        c_k1.metric("SKUs Cruzados", len(df_merge))
                        c_k2.metric("✅ Coinciden (Éxito)", len(df_merge) - len(df_fallas))
                        c_k3.metric("❌ Diferencias (Falla)", len(df_fallas))
                        
                        if df_fallas.empty:
                            st.success(f"¡Excelente! El 100% de los artículos verificados coinciden con la base de datos de los robots.")
                        else:
                            st.error(f"⚠️ Atención: Se detectaron {len(df_fallas)} artículos donde el precio del sistema NO es igual al que cargó el robot.")
                            
                        df_merge['timestamp'] = df_merge['timestamp'].dt.strftime("%Y-%m-%d %H:%M:%S")
                        desc_col = df_merge[sel_desc] if sel_desc != "—" else df_merge['sku_clean']
                        
                        df_show = pd.DataFrame({
                            'Estado': df_merge['Impacto'],
                            'SKU': df_merge['sku_clean'],
                            'Descripción': desc_col,
                            'Precio Robot': df_merge['precio_salon'],
                            'Precio Sistema': df_merge['precio_sistema'],
                            'Diferencia $': df_merge['Diferencia_$'],
                            'Última Carga': df_merge['timestamp'],
                            'Robot Origen': df_merge['robot_origen']
                        }).sort_values(by=['Estado', 'Diferencia $'], ascending=[False, False])
                        
                        st.markdown("##### 📋 Detalle Analítico: Sistema vs Robot")
                        st.dataframe(
                            df_show,
                            column_config={
                                "Precio Robot": st.column_config.NumberColumn("Precio Robot", format="$ %.2f"),
                                "Precio Sistema": st.column_config.NumberColumn("Precio Sistema", format="$ %.2f"),
                                "Diferencia $": st.column_config.NumberColumn("Diferencia $", format="$ %.2f")
                            },
                            use_container_width=True, hide_index=True, height=400
                        )
                        
                        import io
                        buf = io.BytesIO()
                        df_show.to_excel(buf, index=False, engine='openpyxl')
                        buf.seek(0)
                        st.download_button("⬇️ Descargar Reporte Completo (Excel)", data=buf, file_name="Auditoria_Impacto_Precios.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:
            st.error(f"Ocurrió un error al procesar el archivo: {e}")