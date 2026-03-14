"""
core/prediccion.py — RPA Suite v5.9
====================================
Módulo de enlace para las funciones de predicción de quiebres.
Esto resuelve el ImportError en dashboards/quiebres_dashboard.py
reutilizando la sólida lógica ya existente en tools/prediccion_quiebres.py.
"""

from tools.prediccion_quiebres import (
    predecir_quiebres_lista,
    guardar_snapshot_ventas,
    cargar_historial_ventas,
    predecir_demanda_proximos_meses
)

# Definir lo que se expone al importar este módulo
__all__ = [
    "predecir_quiebres_lista",
    "guardar_snapshot_ventas",
    "cargar_historial_ventas",
    "predecir_demanda_proximos_meses"
]