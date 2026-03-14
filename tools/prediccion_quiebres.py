"""
tools/prediccion_quiebres.py — RPA Suite v5.7
===============================================
Predicción de quiebres usando historial de ventas.
Modelo: regresión lineal simple sobre tendencia semanal + estacionalidad.
Sin dependencias de ML pesadas — solo numpy/pandas.
"""
import json
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import Optional

try:
    import numpy as np
    import pandas as pd
    _NP = True
except ImportError:
    _NP = False

try:
    from sklearn.ensemble import RandomForestRegressor
    _SKLEARN = True
except ImportError:
    _SKLEARN = False

_DATA_DIR = Path(__file__).parent.parent / "pricing_data"


# ══════════════════════════════════════════════════════════════
# PERSISTENCIA DE HISTORIAL
# ══════════════════════════════════════════════════════════════

def guardar_snapshot_ventas(df_ventas: "pd.DataFrame", mes: int, anio: int,
                             col_sku="Codart", col_unidades="UNIDADES_MES",
                             col_familia="DesFam") -> bool:
    """
    Guarda un snapshot mensual de ventas para uso futuro en predicciones.
    df_ventas: DataFrame con al menos col_sku y col_unidades.
    """
    from core.database import get_db_connection
    
    periodo_ym = f"{anio}-{mes:02d}"
    
    registros = []
    for _, row in df_ventas.iterrows():
        sku = str(row.get(col_sku, "")).strip()
        unidades = float(row.get(col_unidades, 0) or 0)
        if sku and unidades > 0:
            registros.append((f"{periodo_ym}-01 00:00:00", sku, unidades))
            
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ventas_historicas WHERE strftime('%Y-%m', timestamp) = ?", (periodo_ym,))
            cursor.executemany(
                "INSERT INTO ventas_historicas (timestamp, sku, cantidad_vendida) VALUES (?, ?, ?)",
                registros
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error guardando snapshot en SQLite: {e}")
            return False
        finally:
            conn.close()
    return False


def cargar_historial_ventas() -> list[dict]:
    from core.database import execute_query
    
    rows = execute_query(
        "SELECT strftime('%Y-%m', timestamp) as periodo, sku, sum(cantidad_vendida) as unidades "
        "FROM ventas_historicas GROUP BY periodo, sku ORDER BY periodo ASC"
    )
    
    if not rows:
        return []
        
    historial_dict = {}
    for periodo, sku, unidades in rows:
        if periodo not in historial_dict:
            historial_dict[periodo] = []
        historial_dict[periodo].append({"sku": str(sku), "unidades": float(unidades)})
        
    historial = []
    for periodo in sorted(historial_dict.keys()):
        historial.append({"periodo": periodo, "datos": historial_dict[periodo]})
        
    return historial


# ══════════════════════════════════════════════════════════════
# MOTOR DE PREDICCIÓN
# ══════════════════════════════════════════════════════════════

def predecir_demanda_proximos_meses(
    sku: str,
    historial: list[dict],
    n_meses: int = 2,
    log_func=None,
) -> dict:
    """
    Predice la demanda de un SKU para los próximos n_meses.
    Usa el historial provisto para entrenar un modelo.
    Retorna dict con predicciones y confianza.
    """
    def _log(m):
        if log_func: log_func(m)

    if not historial:
        return {"error": "Sin historial de ventas disponible"}

    # Extraer serie temporal del SKU
    serie = []
    for snap in historial:
        for item in snap["datos"]:
            if item["sku"] == sku:
                serie.append({"periodo": snap["periodo"], "unidades": item["unidades"]})
                break

    if len(serie) < 2:
        return {"error": f"SKU '{sku}' tiene menos de 2 meses de historial"}

    # ── 1. Modelo Machine Learning Avanzado (Random Forest) ──
    if _SKLEARN and _NP and len(serie) >= 6:
        try:
            X = []
            y = []
            for idx, item in enumerate(serie):
                y.append(item["unidades"])
                anio_s, mes_s = map(int, item["periodo"].split("-"))
                # Features: Índice temporal (tendencia) y Mes del año (estacionalidad)
                X.append([idx, mes_s])
                
            X = np.array(X)
            y = np.array(y)
            
            # Entrenar modelo Random Forest
            rf = RandomForestRegressor(n_estimators=100, random_state=42, max_depth=5)
            rf.fit(X, y)
            
            # Predecir futuros meses
            predicciones = []
            ultimo = historial[-1]["periodo"]
            anio_u, mes_u = map(int, ultimo.split("-"))
            
            for i in range(1, n_meses + 1):
                mes_p = mes_u + i
                anio_p = anio_u + (mes_p - 1) // 12
                mes_p  = (mes_p - 1) % 12 + 1
                
                x_future = np.array([[len(serie) - 1 + i, mes_p]])
                pred_final = max(0, round(rf.predict(x_future)[0]))
                predicciones.append({"periodo": f"{anio_p}-{mes_p:02d}", "unidades": pred_final})
                
            r2 = rf.score(X, y)
            confianza = "alta" if r2 > 0.75 else "media" if r2 > 0.4 else "baja"
            tendencia = "creciente" if (predicciones[-1]["unidades"] > y[-1] * 1.05) else "decreciente" if (predicciones[-1]["unidades"] < y[-1] * 0.95) else "estable"
            
            return {
                "sku":          sku,
                "metodo":       "random_forest_estacional",
                "serie":        serie,
                "r2":           round(r2, 3),
                "predicciones": predicciones,
                "confianza":    confianza,
                "tendencia":    tendencia,
            }
        except Exception as e_ml:
            _log(f"⚠ Falló Random Forest para {sku}: {e_ml} - Usando fallback lineal")

    # ── 2. Fallbacks Clásicos (Regresión y Promedios) ──
    if not _NP:
        # Fallback sin numpy: promedio simple + estacionalidad
        promedio = sum(s["unidades"] for s in serie) / len(serie)
        predicciones = []
        ultimo = historial[-1]["periodo"]
        anio_u, mes_u = map(int, ultimo.split("-"))
        
        for i in range(1, n_meses + 1):
            mes_p = mes_u + i
            anio_p = anio_u + (mes_p - 1) // 12
            mes_p  = (mes_p - 1) % 12 + 1
            
            factor_estacional = 1.0
            periodo_pasado = f"{anio_p - 1}-{mes_p:02d}"
            venta_pasada = next((s["unidades"] for s in serie if s["periodo"] == periodo_pasado), None)
            if venta_pasada is not None and promedio > 0:
                factor_estacional = max(0.5, min(venta_pasada / promedio, 2.0))
                
            predicciones.append({"periodo": f"{anio_p}-{mes_p:02d}", "unidades": round(promedio * factor_estacional)})

        return {
            "sku":          sku,
            "metodo":       "promedio_estacional",
            "serie":        serie,
            "predicciones": predicciones,
            "confianza":    "baja",
            "tendencia":    "estable",
        }

    # Regresión lineal
    x = np.arange(len(serie))
    y = np.array([s["unidades"] for s in serie])

    # Pesos: meses recientes valen más
    pesos = np.exp(np.linspace(0, 1, len(x)))
    pesos /= pesos.sum()

    # Ajuste lineal ponderado
    xm = np.average(x, weights=pesos)
    ym = np.average(y, weights=pesos)
    cov_xy = np.average((x - xm) * (y - ym), weights=pesos)
    var_x  = np.average((x - xm)**2, weights=pesos)
    slope  = cov_xy / var_x if var_x > 0 else 0
    intercept = ym - slope * xm

    # Promedio histórico para calcular factor de estacionalidad
    promedio_historico = np.mean(y)

    # Predicciones
    predicciones = []
    ultimo = historial[-1]["periodo"]
    anio_u, mes_u = map(int, ultimo.split("-"))
    for i in range(1, n_meses + 1):
        mes_p = mes_u + i
        anio_p = anio_u + (mes_p - 1) // 12
        mes_p  = (mes_p - 1) % 12 + 1
        
        pred_base = max(0, intercept + slope * (len(serie) - 1 + i))
        
        # Ajuste por estacionalidad (buscar mismo mes año anterior)
        factor_estacional = 1.0
        periodo_pasado = f"{anio_p - 1}-{mes_p:02d}"
        venta_pasada = next((s["unidades"] for s in serie if s["periodo"] == periodo_pasado), None)
        
        if venta_pasada is not None and promedio_historico > 0:
            # Limitamos el factor entre 0.5x y 2.0x para evitar picos distorsionados
            factor_estacional = max(0.5, min(venta_pasada / promedio_historico, 2.0))
            
        pred_final = round(pred_base * factor_estacional)
        predicciones.append({"periodo": f"{anio_p}-{mes_p:02d}", "unidades": pred_final})

    # R² para confianza
    y_pred = intercept + slope * x
    ss_res = np.sum((y - y_pred)**2)
    ss_tot = np.sum((y - ym)**2)
    r2     = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    confianza = "alta" if r2 > 0.7 else "media" if r2 > 0.4 else "baja"
    tendencia = "creciente" if slope > 0.5 else "decreciente" if slope < -0.5 else "estable"

    return {
        "sku":          sku,
        "metodo":       "regresion_lineal_estacional",
        "serie":        serie,
        "slope":        round(slope, 2),
        "r2":           round(r2, 3),
        "predicciones": predicciones,
        "confianza":    confianza,
        "tendencia":    tendencia,
    }


def predecir_quiebres_lista(
    df_stock: "pd.DataFrame",
    lead_time_dias: int = 7,
    col_sku="Codart", col_stock="STOCK_FISICO", col_demanda="DEMANDA_AJUSTADA",
    log_func=None,
) -> "pd.DataFrame":
    """
    Predice qué artículos van a quebrar en los próximos N días.
    Combina stock actual + demanda proyectada + historial.

    Retorna DataFrame con columnas:
      SKU, Stock, Demanda_Mensual, Dias_Cobertura, Riesgo_Quiebre_30d, Prediccion_Demanda, Alerta
    """
    def _log(m):
        if log_func: log_func(m)

    if not _NP:
        _log("⚠ numpy no disponible — usando cálculo simplificado")

    resultados = []
    historial  = cargar_historial_ventas()

    for _, row in df_stock.iterrows():
        sku      = str(row.get(col_sku, "")).strip()
        stock    = float(row.get(col_stock, 0) or 0)
        demanda  = float(row.get(col_demanda, 0) or 0)
        dem_dia  = demanda / 30 if demanda > 0 else 0

        # Intentar predicción con historial
        pred = None
        if historial:
            res = predecir_demanda_proximos_meses(sku, historial, n_meses=1)
            if "predicciones" in res:
                pred = res["predicciones"][0]["unidades"]
                tendencia = res.get("tendencia", "estable")
                confianza = res.get("confianza", "baja")
            else:
                pred, tendencia, confianza = None, "desconocida", "sin datos"
        else:
            tendencia, confianza = "desconocida", "sin datos"

        # Demanda proyectada: si hay predicción usarla, sino la actual
        dem_proyectada = pred if pred is not None else demanda
        dem_dia_proy   = dem_proyectada / 30 if dem_proyectada > 0 else 0

        # Días de cobertura con demanda proyectada
        dias_cob = stock / dem_dia_proy if dem_dia_proy > 0 else 999

        # Riesgo de quiebre en 30 días
        riesgo = "🔴 ALTO"   if dias_cob < lead_time_dias else \
                 "🟡 MEDIO"  if dias_cob < 30 else \
                 "🟢 BAJO"   if dias_cob < 60 else \
                 "⚪ OK"

        resultados.append({
            "SKU":                sku,
            "Descripción":        str(row.get("DESCRIPCION", row.get("Descrip", sku))),
            "Stock":              int(stock),
            "Demanda Actual":     round(demanda, 0),
            "Demanda Proyectada": round(dem_proyectada, 0),
            "Días Cobertura":     round(dias_cob, 0) if dias_cob < 999 else "∞",
            "Tendencia":          tendencia,
            "Confianza":          confianza,
            "Riesgo 30d":         riesgo,
        })

    if not resultados:
        import pandas as pd
        return pd.DataFrame()

    import pandas as pd
    df_res = pd.DataFrame(resultados)
    orden  = {"🔴 ALTO": 0, "🟡 MEDIO": 1, "🟢 BAJO": 2, "⚪ OK": 3}
    df_res["_ord"] = df_res["Riesgo 30d"].map(orden).fillna(9)
    df_res = df_res.sort_values("_ord").drop(columns=["_ord"])
    _log(f"  📊 Predicción: {(df_res['Riesgo 30d']=='🔴 ALTO').sum()} alto riesgo, "
         f"{(df_res['Riesgo 30d']=='🟡 MEDIO').sum()} medio")
    return df_res
