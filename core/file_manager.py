"""
file_manager.py — RPA Suite v5
================================
Gestión centralizada de archivos procesados.
Después de cada ejecución exitosa, el archivo origen se mueve
a la carpeta /procesados/ con timestamp y metadata del proceso.

Estructura generada:
  RPA_Suite_v5/
  └── procesados/
      ├── STOCK/
      │   └── 2026-03-06_14-32_stock_febrero.xlsx
      ├── AJUSTE/
      │   └── 2026-03-06_15-10_ajuste_inventario.xlsx
      ├── PRECIOS/
      ├── CHEQUES/
      └── _registro.json   ← historial completo de todos los procesos
"""
import shutil
import json
import os
from pathlib import Path
from datetime import datetime


# Carpeta raíz de procesados (siempre relativa a la suite)
# core/ está dentro del proyecto → subir un nivel para procesados/ en raíz
_BASE = Path(__file__).parent.parent
PROCESADOS_DIR = _BASE / "procesados"


def _get_carpeta_robot(robot_nombre: str) -> Path:
    """Retorna (y crea si no existe) la subcarpeta del robot."""
    carpeta = PROCESADOS_DIR / robot_nombre.upper()
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _get_registro() -> list:
    """Lee el historial de procesos."""
    registro_path = PROCESADOS_DIR / "_registro.json"
    if registro_path.exists():
        try:
            return json.loads(registro_path.read_text(encoding='utf-8'))
        except Exception:
            return []
    return []


def _guardar_registro(registro: list):
    """Persiste el historial."""
    PROCESADOS_DIR.mkdir(parents=True, exist_ok=True)
    registro_path = PROCESADOS_DIR / "_registro.json"
    registro_path.write_text(
        json.dumps(registro, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )


def archivar_procesado(
    ruta_archivo: str,
    robot_nombre: str,
    filas_procesadas: int,
    filas_error: int = 0,
    dry_run: bool = False,
    log_func=print,
) -> str | None:
    """
    Mueve el archivo procesado a /procesados/<ROBOT>/ con timestamp.
    Registra la operación en _registro.json para auditoría.

    Args:
        ruta_archivo:     Ruta del archivo origen que usó el robot.
        robot_nombre:     Nombre del robot (STOCK, AJUSTE, PRECIOS, CHEQUES, etc.)
        filas_procesadas: Cantidad de filas procesadas exitosamente.
        filas_error:      Cantidad de filas con error.
        dry_run:          Si True, no mueve el archivo (solo registra la simulación).
        log_func:         Función de logging de la GUI.

    Returns:
        Ruta destino del archivo archivado, o None si falló.
    """
    try:
        ruta_origen = Path(ruta_archivo)
        if not ruta_origen.exists():
            log_func(f"⚠️ Archivo no encontrado para archivar: {ruta_archivo}")
            return None

        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
        nombre_destino = f"{timestamp}_{ruta_origen.name}"

        if dry_run:
            # En dry-run: solo registramos, no movemos
            ruta_destino = _get_carpeta_robot(robot_nombre) / f"[SIMULADO]_{nombre_destino}"
            log_func(f"   [DRY-RUN] Archivo se archivaría como: {ruta_destino.name}")
        else:
            carpeta_destino = _get_carpeta_robot(robot_nombre)
            ruta_destino = carpeta_destino / nombre_destino

            # Si ya existe un archivo con ese nombre (raro pero posible), agregar segundos
            if ruta_destino.exists():
                ts_full = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                ruta_destino = carpeta_destino / f"{ts_full}_{ruta_origen.name}"

            shutil.move(str(ruta_origen), str(ruta_destino))
            log_func(f"📁 Archivo archivado → procesados/{robot_nombre.upper()}/{ruta_destino.name}")

        # Registrar en historial
        registro = _get_registro()
        registro.append({
            "timestamp":        datetime.now().isoformat(),
            "robot":            robot_nombre.upper(),
            "archivo_origen":   ruta_origen.name,
            "archivo_destino":  str(ruta_destino.name),
            "filas_procesadas": filas_procesadas,
            "filas_error":      filas_error,
            "dry_run":          dry_run,
            "estado":           "SIMULADO" if dry_run else "PROCESADO",
        })
        _guardar_registro(registro)

        return str(ruta_destino)

    except Exception as e:
        log_func(f"⚠️ No se pudo archivar el archivo: {e}")
        return None


def obtener_historial(robot_nombre: str = None, ultimos_n: int = 50) -> list:
    """
    Retorna el historial de archivos procesados.
    Si robot_nombre es None, retorna todos.
    """
    registro = _get_registro()
    if robot_nombre:
        registro = [r for r in registro if r.get('robot') == robot_nombre.upper()]
    return registro[-ultimos_n:]


def listar_procesados(robot_nombre: str = None) -> dict:
    """
    Retorna un diccionario con los archivos en cada carpeta de procesados.
    Útil para mostrar en la GUI.
    """
    resultado = {}
    if not PROCESADOS_DIR.exists():
        return resultado

    robots = [robot_nombre.upper()] if robot_nombre else [
        d.name for d in PROCESADOS_DIR.iterdir() if d.is_dir()
    ]

    for robot in robots:
        carpeta = PROCESADOS_DIR / robot
        if carpeta.exists():
            archivos = sorted(carpeta.glob("*"), key=os.path.getmtime, reverse=True)
            resultado[robot] = [
                {
                    "nombre": f.name,
                    "tamaño_kb": round(f.stat().st_size / 1024, 1),
                    "fecha": datetime.fromtimestamp(f.stat().st_mtime).strftime('%d/%m/%Y %H:%M'),
                }
                for f in archivos
            ]

    return resultado