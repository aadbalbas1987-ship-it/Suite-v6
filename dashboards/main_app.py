import streamlit as st
import toml
from pathlib import Path

# Configuración global de la página (debe ser la primera instrucción)
st.set_page_config(page_title="RPA Suite - Portal", layout="wide", page_icon="📈")

# Leer configuración de dashboards
config_path = Path(__file__).parent.parent / "config.toml"
try:
    config = toml.load(config_path)
except Exception:
    config = {}
dashboards_config = config.get("dashboards", {})

# Definir las páginas apuntando a los archivos existentes
pg_bi = st.Page("app_dashboard.py", title="Business Intelligence", icon="📊", default=True)
pg_quiebres = st.Page("quiebres_dashboard.py", title="Quiebres de Stock", icon="📉")
pg_pricing = st.Page("pricing_dashboard.py", title="Pricing & Research", icon="💰")
pg_conciliacion = st.Page("conciliacion_dashboard.py", title="Conciliación Bancaria", icon="🏦")
pg_normalizador = st.Page("normalizador_dashboard.py", title="Normalizador Maestro", icon="📋")
pg_crm = st.Page("crm_dashboard.py", title="Análisis CRM", icon="👥")
pg_auditoria = st.Page("auditoria_dashboard.py", title="Auditoría de Robots", icon="🕵️")
pg_cxc = st.Page("cxc_dashboard.py", title="Cuentas por Cobrar", icon="💳")

# Listas de páginas por sección
operaciones_ventas = [pg_bi, pg_quiebres, pg_crm]
estrategia_precios = [pg_pricing]
finanzas_maestros = [pg_conciliacion, pg_cxc, pg_normalizador, pg_auditoria]

if dashboards_config.get("pricing_intelligence", True):
    pg_pricing_intel = st.Page("pricing_intel_dashboard.py", title="Pricing Intelligence", icon="🎯")
    estrategia_precios.append(pg_pricing_intel)

# Estructurar la navegación en el menú lateral
pg = st.navigation({
    "Operaciones y Ventas": operaciones_ventas,
    "Estrategia de Precios": estrategia_precios,
    "Finanzas, Maestros y Control": finanzas_maestros
})

# Encabezado estético en el menú lateral para todas las páginas
st.sidebar.markdown(
    '<div style="text-align:center; padding-bottom: 15px;">'
    '<h2 style="margin-bottom: 0;">Retail Engine</h2>'
    '<p style="color: gray; font-size: 0.8em; margin-top: 0;">Suite Unificada v6.0</p></div>',
    unsafe_allow_html=True
)

# Ejecutar la página seleccionada
pg.run()
