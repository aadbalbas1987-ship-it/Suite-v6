# dash_example.py
# Requerimientos: pip install dash pandas scikit-learn plotly

import dash
from dash import dcc, html, dash_table
import plotly.express as px
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# --- 1. Creación de la App Dash ---
app = dash.Dash(__name__)

# --- 2. Datos de Muestra (simulando la carga de archivos) ---
# En una app real, esto vendría de una base de datos o una carga de archivo.
data = {
    'Codart': [f'SKU-{i:03d}' for i in range(100)],
    'DESCRIPCION': [f'Producto {chr(65 + i % 26)} v{i}' for i in range(100)],
    'UNIDADES_MES': np.random.gamma(2, 150, 100).round(0),
    'STOCK_FISICO': np.random.gamma(1.8, 200, 100).round(0),
    'DEMANDA_AJUSTADA': np.random.gamma(2, 150, 100).round(0)
}
df = pd.DataFrame(data)
# Introducir algunos outliers para que el ML los detecte
df.loc[5, 'STOCK_FISICO'] = 8000
df.loc[10, 'UNIDADES_MES'] = 6000
df.loc[15, 'STOCK_FISICO'] = 10

# --- 3. Lógica de Machine Learning (idéntica a la de Streamlit) ---
df_ml = df[['Codart', 'DESCRIPCION', 'UNIDADES_MES', 'STOCK_FISICO', 'DEMANDA_AJUSTADA']].copy()
df_ml = df_ml.fillna(0)

# Transformación logarítmica y escalado
X = df_ml[['UNIDADES_MES', 'STOCK_FISICO']].copy()
X_log = np.log1p(X)
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X_log)

# Entrenamiento del modelo K-Means
kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
df_ml['cluster'] = kmeans.fit_predict(X_scaled)

# Etiquetado dinámico de clusters
cluster_labels = {}
med_global_v = X['UNIDADES_MES'].median()
med_global_c = X['STOCK_FISICO'].median()

for c in range(4):
    subset = df_ml[df_ml['cluster'] == c]
    if subset.empty:
        cluster_labels[c] = f"Cluster {c}"
        continue
    med_v = subset['UNIDADES_MES'].median()
    med_c = subset['STOCK_FISICO'].median()

    if med_v > med_global_v and med_c <= med_global_c:
        cluster_labels[c] = "🔥 Riesgo Quiebre (ML)"
    elif med_v <= med_global_v and med_c > med_global_c:
        cluster_labels[c] = "📦 Sobre-stock (ML)"
    elif med_v > med_global_v and med_c > med_global_c:
        cluster_labels[c] = "⭐ Alta Rotación"
    else:
        cluster_labels[c] = "💤 Baja Rotación"

df_ml['Segmento ML'] = df_ml['cluster'].map(cluster_labels)

# Preparación para el gráfico logarítmico
df_ml['plot_x'] = df_ml['UNIDADES_MES'].clip(lower=1)
df_ml['plot_y'] = df_ml['STOCK_FISICO'].clip(lower=1)
df_ml['Puntos'] = df_ml['DEMANDA_AJUSTADA'].clip(lower=2)

# --- 4. Creación de la Figura Plotly (idéntica a la de Streamlit) ---
fig_ml = px.scatter(
    df_ml,
    x='plot_x',
    y='plot_y',
    color='Segmento ML',
    size='Puntos',
    hover_name='DESCRIPCION',
    hover_data={'Codart': True, 'UNIDADES_MES': ':.0f', 'STOCK_FISICO': ':.0f'},
    color_discrete_map={
        "🔥 Riesgo Quiebre (ML)": "#ef4444",
        "📦 Sobre-stock (ML)": "#f59e0b",
        "⭐ Alta Rotación": "#10b981",
        "💤 Baja Rotación": "#94a3b8"
    },
    title="Correlación Stock vs Ventas (Clustering K-Means)"
)
fig_ml.update_layout(
    height=550,
    xaxis=dict(type='log', title="Unidades Vendidas (Escala Log)"),
    yaxis=dict(type='log', title="Stock Físico (Escala Log)"),
    legend=dict(title="Segmentos Detectados", orientation="h", y=-0.2, yanchor="top")
)

# --- 5. Creación de la Tabla de Resumen ---
resumen_ml = df_ml.groupby('Segmento ML').agg(
    SKUs=('Codart', 'count'),
    Stock_Promedio=('STOCK_FISICO', 'mean'),
    Venta_Promedio=('UNIDADES_MES', 'mean')
).reset_index()
resumen_ml['Stock_Promedio'] = resumen_ml['Stock_Promedio'].apply(lambda x: f"{x:,.0f} un.")
resumen_ml['Venta_Promedio'] = resumen_ml['Venta_Promedio'].apply(lambda x: f"{x:,.0f} un.")


# --- 6. Definición del Layout de la App ---
# Aquí definís la estructura HTML de tu página.
app.layout = html.Div(style={'fontFamily': 'Sora, sans-serif', 'padding': '2rem'}, children=[
    html.H4("🧩 Clustering K-Means: Segmentación de Productos", style={'color': '#1A1D23'}),
    html.P("Agrupa automáticamente los productos para detectar patrones entre ventas y stock.", style={'color': '#5A6070'}),

    # El componente dcc.Graph muestra la figura de Plotly
    dcc.Graph(
        id='scatter-plot-ml',
        figure=fig_ml
    ),

    html.H5("📋 Resumen de Segmentos", style={'marginTop': '2rem', 'color': '#1A1D23'}),

    # El componente dash_table.DataTable muestra el DataFrame de resumen
    dash_table.DataTable(
        id='summary-table',
        columns=[{"name": i, "id": i} for i in resumen_ml.columns],
        data=resumen_ml.to_dict('records'),
        style_cell={'textAlign': 'left', 'fontFamily': 'Sora'},
        style_header={
            'backgroundColor': '#1D3557',
            'color': 'white',
            'fontWeight': 'bold'
        },
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': 'rgb(248, 248, 248)'
            }
        ]
    )
])

# --- 7. Ejecución del Servidor ---
if __name__ == '__main__':
    # Para correrlo, ejecutá: python dash_example.py
    # Y abrilo en http://127.0.0.1:8050/
    app.run(debug=True)
