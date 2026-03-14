
"""
analisis_stock_venta.py - RPA Suite v6
======================================

Herramienta de Análisis y Machine Learning (Fase 1).

Este script realiza un análisis de correlación entre el stock cargado
y las ventas registradas, utilizando los datos centralizados en la
base de datos SQLite.

Funcionalidades:
  1. Conecta a la base de datos `rpa_suite.db`.
  2. Extrae datos de las tablas `cargas_stock` y `ventas_historicas`.
  3. Agrega los datos por SKU y por semana.
  4. Fusiona los datos para crear un DataFrame de análisis.
  5. Calcula el ratio Stock-Venta (unidades cargadas por cada unidad vendida).
  6. Identifica productos con posible sobre-stock y riesgo de quiebre.
  7. Genera un reporte en consola y un gráfico de dispersión.
"""
import pandas as pd
import os
import logging
import numpy as np
from core.database import execute_query

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    _SKLEARN_OK = True
except ImportError:
    _SKLEARN_OK = False

# --- Configuración ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
OUTPUT_DIR = "dashboards/reports"
os.makedirs(OUTPUT_DIR, exist_ok=True)
CHART_FILENAME = os.path.join(OUTPUT_DIR, "correlacion_stock_ventas.png")

# --- Funciones de Análisis ---

def get_data_from_db():
    """Obtiene los datos de stock y ventas de la BD y los devuelve como DataFrames."""
    logging.info("Conectando a la base de datos para obtener datos...")
    
    # Obtener cargas de stock
    sql_stock = "SELECT timestamp, sku, cantidad_cargada FROM cargas_stock"
    stock_data = execute_query(sql_stock)
    df_stock = pd.DataFrame(stock_data, columns=['timestamp', 'sku', 'cantidad'])
    df_stock['timestamp'] = pd.to_datetime(df_stock['timestamp'])
    logging.info(f"Se obtuvieron {len(df_stock)} registros de cargas de stock.")

    # Obtener ventas históricas
    sql_ventas = "SELECT timestamp, sku, cantidad_vendida FROM ventas_historicas"
    ventas_data = execute_query(sql_ventas)
    df_ventas = pd.DataFrame(ventas_data, columns=['timestamp', 'sku', 'cantidad'])
    df_ventas['timestamp'] = pd.to_datetime(df_ventas['timestamp'])
    logging.info(f"Se obtuvieron {len(df_ventas)} registros de ventas.")
    
    return df_stock, df_ventas

def process_data(df_stock, df_ventas):
    """Procesa y agrega los datos por SKU y semana."""
    logging.info("Procesando y agregando datos por SKU y semana...")
    
    # Asegurar que no haya datos vacíos
    df_stock.dropna(subset=['timestamp', 'sku', 'cantidad'], inplace=True)
    df_ventas.dropna(subset=['timestamp', 'sku', 'cantidad'], inplace=True)
    
    # Agregación Semanal
    df_stock['periodo'] = df_stock['timestamp'].dt.to_period('W')
    stock_agg = df_stock.groupby(['sku', 'periodo'])['cantidad'].sum().reset_index()
    stock_agg.rename(columns={'cantidad': 'total_cargado'}, inplace=True)

    df_ventas['periodo'] = df_ventas['timestamp'].dt.to_period('W')
    ventas_agg = df_ventas.groupby(['sku', 'periodo'])['cantidad'].sum().reset_index()
    ventas_agg.rename(columns={'cantidad': 'total_vendido'}, inplace=True)
    
    # Fusionar datos
    df_analisis = pd.merge(stock_agg, ventas_agg, on=['sku', 'periodo'], how='outer').fillna(0)
    logging.info(f"Datos agregados y fusionados. Total de registros de análisis: {len(df_analisis)}")
    
    return df_analisis

def perform_analysis(df_analisis):
    """Realiza el análisis, imprime reportes y genera el gráfico."""
    if df_analisis.empty:
        logging.warning("No hay datos suficientes para realizar el análisis.")
        return

    logging.info("\n" + "="*50)
    logging.info("Análisis de Correlación Stock vs. Ventas")
    logging.info("="*50)

    # Calcular ratio Stock-Venta
    # Se suma 1 a las ventas para evitar división por cero
    df_analisis['ratio_stock_venta'] = df_analisis['total_cargado'] / (df_analisis['total_vendido'] + 1)

    # Agrupar por SKU para el reporte final
    df_sku_summary = df_analisis.groupby('sku').agg({
        'total_cargado': 'sum',
        'total_vendido': 'sum'
    }).reset_index()
    
    # Evitar división por cero en el summary también
    df_sku_summary['ratio_general'] = df_sku_summary['total_cargado'] / (df_sku_summary['total_vendido'] + 1)


    # --- Reporte en Consola ---
    
    # 1. Productos con posible sobre-stock (mucho stock, pocas ventas)
    sobre_stock = df_sku_summary[
        (df_sku_summary['total_cargado'] > df_sku_summary['total_cargado'].quantile(0.75)) &
        (df_sku_summary['total_vendido'] < df_sku_summary['total_vendido'].quantile(0.25))
    ].sort_values(by='ratio_general', ascending=False)
    
    logging.info("\n--- 🚨 TOP 5 PRODUCTOS CON POSIBLE SOBRE-STOCK ---")
    if not sobre_stock.empty:
        logging.info(sobre_stock.head().to_string(index=False))
    else:
        logging.info("No se detectaron productos con claro sobre-stock.")

    # 2. Productos con posible riesgo de quiebre (pocas cargas, muchas ventas)
    riesgo_quiebre = df_sku_summary[
        (df_sku_summary['total_cargado'] < df_sku_summary['total_cargado'].quantile(0.25)) &
        (df_sku_summary['total_vendido'] > df_sku_summary['total_vendido'].quantile(0.75))
    ].sort_values(by='ratio_general', ascending=True)

    logging.info("\n--- 🔥 TOP 5 PRODUCTOS CON RIESGO DE QUIEBRE ---")
    if not riesgo_quiebre.empty:
        logging.info(riesgo_quiebre.head().to_string(index=False))
    else:
        logging.info("No se detectaron productos con claro riesgo de quiebre.")
        
    # --- Machine Learning: Detección de Anomalías (Isolation Forest) ---
    if _SKLEARN_OK and len(df_sku_summary) >= 4:
        logging.info("\n--- 🤖 Ejecutando Isolation Forest ---")
        try:
            # Transformación logarítmica para manejar valores atípicos (outliers)
            X = df_sku_summary[['total_vendido', 'total_cargado']].copy()
            X_log = np.log1p(X)
            
            # Escalar datos
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_log)
            
            # Entrenar Isolation Forest (buscamos el 5% más atípico)
            iso = IsolationForest(contamination=0.05, random_state=42)
            df_sku_summary['outlier'] = iso.fit_predict(X_scaled)
            df_sku_summary['segmento_ml'] = df_sku_summary['outlier'].map({-1: "🔴 Anomalía (Outlier)", 1: "🔵 Normal"})
            
            logging.info("Isolation Forest completado. Segmentos encontrados:")
            logging.info("\n" + df_sku_summary['segmento_ml'].value_counts().to_string())
        except Exception as e_ml:
            logging.error(f"Falló Isolation Forest: {e_ml}")
            df_sku_summary['segmento_ml'] = 'No clasificado'

    # --- Generación de Gráfico ---
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns

        logging.info(f"\nGenerando gráfico de dispersión en '{CHART_FILENAME}'...")
        plt.style.use('seaborn-v0_8_whitegrid')
        fig, ax = plt.subplots(figsize=(12, 8))
        
        if _SKLEARN_OK and 'segmento_ml' in df_sku_summary.columns:
            sns.scatterplot(
                data=df_sku_summary,
                x='total_vendido',
                y='total_cargado',
                hue='segmento_ml',
                size='ratio_general',
                sizes=(40, 400),
                alpha=0.7,
                palette={"🔴 Anomalía (Outlier)": "#ef4444", "🔵 Normal": "#94a3b8", "No clasificado": "#64748b"},
                ax=ax
            )
        else:
            sns.scatterplot(
                data=df_sku_summary,
                x='total_vendido',
                y='total_cargado',
                size='ratio_general',
                sizes=(20, 400),
                alpha=0.6,
                ax=ax
            )
        
        ax.set_title('Correlación entre Stock Cargado y Unidades Vendidas (por SKU)', fontsize=16)
        ax.set_xlabel('Total de Unidades Vendidas', fontsize=12)
        ax.set_ylabel('Total de Unidades de Stock Cargadas', fontsize=12)
        ax.loglog() # Usar escala logarítmica para manejar outliers
        
        # Añadir etiquetas para productos notables
        for i, row in riesgo_quiebre.head(2).iterrows():
            ax.text(row['total_vendido'], row['total_cargado'], f"  {row['sku']} (Riesgo)", color='red', ha='left')
        for i, row in sobre_stock.head(2).iterrows():
            ax.text(row['total_vendido'], row['total_cargado'], f"  {row['sku']} (Exceso)", color='blue', ha='left')
            
        plt.tight_layout()
        plt.savefig(CHART_FILENAME)
        plt.close()
        logging.info("Gráfico guardado con éxito.")

    except ImportError:
        logging.warning("\nNo se pudo generar el gráfico. Instala matplotlib y seaborn: pip install matplotlib seaborn")
    except Exception as e:
        logging.error(f"Error al generar el gráfico: {e}")

# --- Bloque Principal ---

def main():
    """Función principal que orquesta el análisis."""
    df_stock, df_ventas = get_data_from_db()
    
    if df_stock.empty or df_ventas.empty:
        logging.error("No hay datos en una o ambas tablas (stock, ventas). El análisis no puede continuar.")
        return
        
    df_analisis = process_data(df_stock, df_ventas)
    perform_analysis(df_analisis)
    logging.info("\nAnálisis finalizado.")

if __name__ == '__main__':
    main()
