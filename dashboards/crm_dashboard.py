"""
dashboards/crm_dashboard.py — RPA Suite v6.0
==============================================
Dashboard de CRM y Retención de Clientes usando Matriz RFM
(Recency, Frequency, Monetary).
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

st.set_page_config(page_title="CRM & RFM — RPA Suite", page_icon="👥", layout="wide")

st.markdown("""<style>
.kpi-card { background: white; border-radius: 12px; padding: 16px 20px; border: 1px solid #e2e8f0; }
.kpi-val { font-size: 2rem; font-weight: 700; color: #1e40af; }
.kpi-lbl { font-size: 0.8rem; color: #64748b; text-transform: uppercase; }
</style>""", unsafe_allow_html=True)

st.title("👥 CRM Analítico — Matriz RFM")
st.caption("Segmentación inteligente de clientes: Recencia (última compra), Frecuencia (visitas) y Monetario (gasto).")

with st.sidebar:
    st.markdown("### 📂 Datos de Ventas")
    archivo = st.file_uploader("Subir histórico de ventas (CSV/Excel)", type=["csv", "xlsx"], 
                               help="Debe contener: Cliente, Fecha, Importe")
    fecha_corte = st.date_input("📅 Fecha de análisis", value=date.today())

if not archivo:
    st.info("👈 Subí tu archivo histórico de ventas por cliente para generar la segmentación.")
    st.stop()

with st.spinner("Procesando histórico de clientes..."):
    if archivo.name.endswith(".csv"):
        df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1', on_bad_lines='skip')
    else:
        df = pd.read_excel(archivo)

    # Detección básica de columnas
    cols = {c.lower(): c for c in df.columns}
    col_cli = next((cols[c] for c in ['cliente', 'nombre', 'descripcion'] if c in cols), None)
    col_fec = next((cols[c] for c in ['fecha', 'date', 'emision'] if c in cols), None)
    col_imp = next((cols[c] for c in ['importe', 'total', 'venta', 'monto'] if c in cols), None)

    if not all([col_cli, col_fec, col_imp]):
        st.error(f"Faltan columnas requeridas. Encontradas: {list(df.columns)}")
        st.stop()

    df[col_fec] = pd.to_datetime(df[col_fec], errors='coerce', dayfirst=True)
    df[col_imp] = pd.to_numeric(df[col_imp].astype(str).str.replace(',', '.'), errors='coerce')
    df = df.dropna(subset=[col_fec, col_imp, col_cli])
    df = df[~df[col_cli].str.contains('Consumidor Final', case=False, na=False)]

    # Calcular RFM
    fecha_max = pd.to_datetime(fecha_corte)
    rfm = df.groupby(col_cli).agg({
        col_fec: lambda x: (fecha_max - x.max()).days,  # Recency
        col_imp: ['count', 'sum']                       # Frequency, Monetary
    }).reset_index()
    
    rfm.columns = ['Cliente', 'Recencia_Dias', 'Frecuencia', 'Monetario']
    rfm = rfm[rfm['Monetario'] > 0]

    # Scoring (1 a 4)
    rfm['R_Score'] = pd.qcut(rfm['Recencia_Dias'], 4, labels=[4, 3, 2, 1], duplicates='drop') # Menos días = mejor (4)
    rfm['F_Score'] = pd.qcut(rfm['Frecuencia'].rank(method='first'), 4, labels=[1, 2, 3, 4])  # Más compras = mejor (4)
    rfm['M_Score'] = pd.qcut(rfm['Monetario'], 4, labels=[1, 2, 3, 4], duplicates='drop')
    
    def segmentar(row):
        r, f = int(row['R_Score']), int(row['F_Score'])
        if r >= 3 and f >= 3: return "🏆 Campeones"
        if r <= 2 and f >= 3: return "⚠️ En Riesgo (Eran fieles)"
        if r >= 3 and f <= 2: return "🌱 Nuevos / Prometedores"
        return "💤 Dormidos / Perdidos"

    rfm['Segmento'] = rfm.apply(segmentar, axis=1)

k1, k2, k3, k4 = st.columns(4)
k1.markdown(f'<div class="kpi-card"><div class="kpi-val">{len(rfm)}</div><div class="kpi-lbl">Clientes Únicos</div></div>', unsafe_allow_html=True)
k2.markdown(f'<div class="kpi-card"><div class="kpi-val" style="color:#16a34a">{len(rfm[rfm["Segmento"]=="🏆 Campeones"])}</div><div class="kpi-lbl">🏆 Campeones</div></div>', unsafe_allow_html=True)
k3.markdown(f'<div class="kpi-card"><div class="kpi-val" style="color:#d97706">{len(rfm[rfm["Segmento"]=="⚠️ En Riesgo (Eran fieles)"])}</div><div class="kpi-lbl">⚠️ En Riesgo</div></div>', unsafe_allow_html=True)
k4.markdown(f'<div class="kpi-card"><div class="kpi-val" style="color:#000">${rfm["Monetario"].mean():,.0f}</div><div class="kpi-lbl">Ticket Histórico Promedio</div></div>', unsafe_allow_html=True)

st.markdown("---")
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Burbujas de Segmentación")
    fig = px.scatter(rfm, x="Recencia_Dias", y="Frecuencia", size="Monetario", color="Segmento",
                     hover_name="Cliente", size_max=40,
                     color_discrete_map={"🏆 Campeones":"#16a34a", "⚠️ En Riesgo (Eran fieles)":"#d97706", 
                                         "🌱 Nuevos / Prometedores":"#3b82f6", "💤 Dormidos / Perdidos":"#94a3b8"},
                     labels={"Recencia_Dias": "Días desde última compra (Menor es mejor)", "Frecuencia": "Cantidad de Compras"})
    fig.update_layout(height=450, plot_bgcolor='white')
    # Invertir eje X para que los "mejores" (menos días) estén a la derecha
    fig.update_xaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Acciones de Marketing")
    st.info("**🏆 Campeones:** No les des descuentos agresivos. Ofreceles productos nuevos o premium. Son tu 80/20.")
    st.warning("**⚠️ En Riesgo:** Compraban mucho y dejaron de venir. Mandales un mensaje de WhatsApp urgente con un descuento agresivo 'Te extrañamos'.")
    st.success("**🌱 Nuevos:** Vinieron hace poco. Hay que lograr su segunda compra pronto. Ofreceles un combo.")

st.subheader("📋 Base de Clientes Accionable")
st.dataframe(rfm.sort_values('Monetario', ascending=False), use_container_width=True, hide_index=True)