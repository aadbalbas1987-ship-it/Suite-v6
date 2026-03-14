"""
input_manager.py — RPA Suite v5.3
====================================
Gestión inteligente de archivos de entrada (input/).

FILOSOFÍA:
  Cada robot tiene una KEYWORD asignada. Solo procesa archivos cuyo nombre
  contenga esa keyword (case-insensitive). Si hay varios archivos válidos,
  los procesa TODOS en secuencia automáticamente.

  Ejemplo:
    - Robot Stock (putty) → keyword "carga"
      → "carga_sucursal1.xlsx", "carga marzo.xlsx"  ✅
      → "precios_trio.xlsx", "NC_ajuste.xlsx"        ❌ (ignorados)

    - Robot Ajuste        → keyword "nc"
    - Robot Precios       → keyword "precios"
    - Robot Cheques       → keyword "cheque"

USO:
    from core.input_manager import InputManager, ROBOT_KEYWORDS

    archivos = InputManager.buscar_archivos("STOCK")
    for ruta, df in InputManager.cargar_todos("STOCK", log_func=print):
        ejecutar_stock(df, ...)
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Callable, Generator, Optional
import pandas as pd

# ──────────────────────────────────────────────────────────────
# CONFIGURACIÓN CENTRAL: robot → keyword(s) que debe contener
# ──────────────────────────────────────────────────────────────
ROBOT_KEYWORDS: dict[str, list[str]] = {
    "STOCK":           ["carga"],
    "STOCK_PARAMIKO":  ["carga"],
    "AJUSTE":          ["nc"],
    "AJUSTE_PARAMIKO": ["nc"],
    "AJUSTE_ANALITICO":["nc"],          # mismo keyword que ajuste
    "PRECIOS":         ["precios"],
    "PRECIOS_PARAMIKO":["precios"],
    "CHEQUES":         ["cheque"],
}

# Extensiones válidas
EXTENSIONES_VALIDAS = {".xlsx", ".xls", ".csv", ".txt"}

# Carpeta default de input (relativa al main_gui.py / BASE_DIR)
INPUT_DIR_DEFAULT = "input"


class InputManager:
    """Gestiona búsqueda y carga múltiple de archivos por keyword."""

    # ----------------------------------------------------------
    # BÚSQUEDA
    # ----------------------------------------------------------
    @staticmethod
    def buscar_archivos(
        robot: str,
        directorio: Optional[str | Path] = None,
        base_dir: Optional[str | Path] = None,
    ) -> list[Path]:
        """
        Retorna lista de archivos en `directorio` cuyos nombres contienen
        alguna keyword del robot (case-insensitive), ordenados alfabéticamente.

        Args:
            robot:      Nombre del robot (clave en ROBOT_KEYWORDS).
            directorio: Ruta explícita. Si None, usa base_dir/input/.
            base_dir:   Raíz del proyecto (Path(main_gui.__file__).parent).
        """
        keywords = ROBOT_KEYWORDS.get(robot.upper(), [])
        if not keywords:
            return []

        if directorio:
            carpeta = Path(directorio)
        elif base_dir:
            carpeta = Path(base_dir) / INPUT_DIR_DEFAULT
        else:
            carpeta = Path.cwd() / INPUT_DIR_DEFAULT

        if not carpeta.exists():
            carpeta.mkdir(parents=True, exist_ok=True)
            return []

        archivos: list[Path] = []
        for archivo in sorted(carpeta.iterdir()):
            if archivo.suffix.lower() not in EXTENSIONES_VALIDAS:
                continue
            nombre_lower = archivo.stem.lower()
            if any(kw.lower() in nombre_lower for kw in keywords):
                archivos.append(archivo)

        return archivos

    # ----------------------------------------------------------
    # CARGA
    # ----------------------------------------------------------
    @staticmethod
    def cargar_df(ruta: Path, log_func: Callable = print) -> Optional[pd.DataFrame]:
        """Carga un archivo Excel o CSV y retorna DataFrame sin header."""
        try:
            if ruta.suffix.lower() in (".xlsx", ".xls"):
                df = pd.read_excel(ruta, header=None)
            else:
                df = pd.read_csv(ruta, header=None)
            log_func(f"   📄 {ruta.name} → {len(df)} filas leídas")
            return df
        except Exception as e:
            log_func(f"   ❌ Error leyendo {ruta.name}: {e}")
            return None

    @staticmethod
    def cargar_todos(
        robot: str,
        directorio: Optional[str | Path] = None,
        base_dir: Optional[str | Path] = None,
        log_func: Callable = print,
    ) -> Generator[tuple[Path, pd.DataFrame], None, None]:
        """
        Generator que yields (ruta, DataFrame) para cada archivo válido.
        Uso:
            for ruta, df in InputManager.cargar_todos("STOCK", base_dir=BASE_DIR):
                ejecutar_stock(df, archivo_origen=ruta, ...)
        """
        archivos = InputManager.buscar_archivos(robot, directorio, base_dir)
        if not archivos:
            log_func(f"   ⚠ No se encontraron archivos para robot {robot}")
            log_func(f"   → Keyword(s): {ROBOT_KEYWORDS.get(robot.upper(), [])}")
            log_func(f"   → Carpeta: {directorio or (str(base_dir) + '/input') if base_dir else 'input/'}")
            return

        log_func(f"   📦 {len(archivos)} archivo(s) encontrado(s) para {robot}:")
        for a in archivos:
            log_func(f"      • {a.name}")

        for ruta in archivos:
            df = InputManager.cargar_df(ruta, log_func)
            if df is not None and not df.empty:
                yield ruta, df
            else:
                log_func(f"   ⚠ Saltando {ruta.name} (vacío o error de lectura)")

    # ----------------------------------------------------------
    # UTILIDADES
    # ----------------------------------------------------------
    @staticmethod
    def listar_todos(
        base_dir: Optional[str | Path] = None,
        log_func: Callable = print,
    ) -> dict[str, list[Path]]:
        """
        Retorna dict con todos los archivos por robot encontrados en input/.
        Útil para mostrar resumen en la GUI al iniciar.
        """
        resultado: dict[str, list[Path]] = {}
        for robot in ROBOT_KEYWORDS:
            archivos = InputManager.buscar_archivos(robot, base_dir=base_dir)
            if archivos:
                resultado[robot] = archivos
        return resultado

    @staticmethod
    def resumen_input(base_dir: Optional[str | Path] = None) -> str:
        """Genera string de resumen para mostrar en log al iniciar la app."""
        todos = InputManager.listar_todos(base_dir=base_dir)
        if not todos:
            return "📂 input/ vacía — no hay archivos listos para procesar"
        lineas = ["📂 Archivos listos en input/:"]
        for robot, archivos in todos.items():
            kw = ROBOT_KEYWORDS[robot][0]
            lineas.append(f"   [{robot}] ({kw}) → {len(archivos)} archivo(s)")
            for a in archivos:
                lineas.append(f"      • {a.name}")
        return "\n".join(lineas)

    @staticmethod
    def keyword_para_robot(robot: str) -> str:
        """Retorna la keyword principal (primera) del robot."""
        kws = ROBOT_KEYWORDS.get(robot.upper(), ["?"])
        return kws[0]

    @staticmethod
    def validar_nombre(nombre: str, robot: str) -> bool:
        """True si el nombre de archivo contiene la keyword del robot."""
        keywords = ROBOT_KEYWORDS.get(robot.upper(), [])
        nombre_lower = nombre.lower()
        return any(kw.lower() in nombre_lower for kw in keywords)

def split_en_lotes(df, max_filas: int = 200, log_func=None) -> list:
    """
    Divide un DataFrame grande en lotes de max_filas.
    Preserva las filas de cabecera (primeras 3 filas de STOCK) en cada lote.
    Retorna lista de DataFrames.
    """
    import pandas as pd

    if log_func is None:
        log_func = print

    total = len(df)
    if total <= max_filas:
        return [df]

    # Detectar si tiene cabecera (Stock: primeras 3 filas son metadata)
    # Heurística: si la primera fila col[0] no es un SKU numérico
    tiene_cabecera = False
    try:
        primera = str(df.iloc[0, 0]).strip()
        if not primera.isdigit():
            tiene_cabecera = True
    except Exception:
        pass

    if tiene_cabecera:
        cabecera = df.iloc[:3].copy()
        datos    = df.iloc[3:].reset_index(drop=True)
    else:
        cabecera = None
        datos    = df

    lotes = []
    max_datos = max_filas - (3 if tiene_cabecera else 0)
    for i in range(0, len(datos), max_datos):
        chunk = datos.iloc[i:i + max_datos].copy()
        if tiene_cabecera and cabecera is not None:
            lote = pd.concat([cabecera, chunk], ignore_index=True)
        else:
            lote = chunk
        lotes.append(lote)

    log_func(f"  ✂ Archivo dividido en {len(lotes)} lotes de máx {max_filas} filas")
    for j, l in enumerate(lotes, 1):
        log_func(f"     Lote {j}: {len(l)} filas")

    return lotes
