"""
core/logger.py — RPA Suite v5
==============================
Logger central con rotación de archivos.
- Guarda en AppData/Local/RPASuite/logs/
- Rota cada 5MB, guarda últimos 10 archivos
- Niveles: INFO para GUI, DEBUG para archivos (trazas completas)
- Thread-safe
"""
import logging
import logging.handlers
from pathlib import Path
import sys


def _get_log_dir() -> Path:
    """Retorna el directorio de logs en AppData (Windows) o ~/.rpa_suite (otros)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home()
    log_dir = base / "RPASuite" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


import os

_LOG_DIR = _get_log_dir()
_LOG_FILE = _LOG_DIR / "rpa_suite.log"

# ── Formato ─────────────────────────────────────────────────
_FMT_FILE = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
_FMT_CON  = "[%(asctime)s] %(levelname)s: %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str = "rpa_suite") -> logging.Logger:
    """
    Retorna un logger configurado. Llamar una vez por módulo:
        from core.logger import get_logger
        log = get_logger(__name__)
    """
    logger = logging.getLogger(name)

    # Solo configurar si no tiene handlers ya (evita duplicados)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # ── Handler archivo: DEBUG, rota 5MB x 10 archivos ──
    fh = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=10,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FMT_FILE, datefmt=_DATE_FMT))

    # ── Handler consola: INFO ──
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(_FMT_CON, datefmt="%H:%M:%S"))

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


def get_log_path() -> Path:
    """Retorna la ruta del archivo de log actual."""
    return _LOG_FILE


def get_log_dir() -> Path:
    """Retorna el directorio de logs."""
    return _LOG_DIR


# Logger raíz de la suite
suite_log = get_logger("rpa_suite")
