"""
Precios_V2.py — RPA Suite v5.2
================================
Robot de actualización masiva de precios (módulo 3-4-2).

Mejoras v5.2 (paridad con Stock, Ajuste y Cheques):
  - Dry-Run: simulá la carga antes de ejecutarla en el sistema
  - Checkpoint: si se corta, reanudá desde donde quedó
  - Watchdog: detección de ventanas inesperadas y pérdida de foco
  - archivar_procesado: registra el archivo en /procesados/PRECIOS/
  - archivo_origen: parámetro estándar igual al resto de robots

Lógica de carga (sin cambios respecto a v2):
  Estructura Excel esperada:
    Col A (0): SKU
    Col B (1): Costo
    Col C (2): Precio Salon
    Col D (3): Precio Mayorista
    Col E (4): Precio Galpon (opcional — si hay valor, usa secuencia G)

  Secuencia por fila:
    SKU -> 5 ENTERs (hijo: 6) -> Costo -> 3 ENTERs ->
    Salon -> [si galpon: 2 ENTERs -> Galpon -> ENTER -> Mayorista -> ENTER -> 'G']
             [si no:     3 ENTERs -> Mayorista -> ENTER -> 'N']
    -> F5
"""
import pyautogui
import time
import os
from pathlib import Path
from core.utils import forzar_caps_off, limpiar_sku, f_monto
from core.checkpoint import ContextoEjecucion
from core.file_manager import archivar_procesado
from core.database import execute_query


# ============================================================
# HELPERS INTERNOS
# ============================================================
def _cargar_hijos() -> set:
    """
    Carga SKUs hijo desde hijos.txt.
    Busca en orden:
      1. Raiz del proyecto  (RPA_Suite_v5/hijos.txt)  <- recomendado
      2. Carpeta robots/    (robots/hijos.txt)
      3. CWD como fallback
    """
    _robot_dir = Path(__file__).parent
    _root_dir  = _robot_dir.parent
    candidatos = [
        _root_dir / "hijos.txt",
        _robot_dir / "hijos.txt",
        Path("hijos.txt"),
    ]
    for ruta in candidatos:
        if ruta.exists():
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    hijos = {line.strip() for line in f if line.strip()}
                return hijos
            except Exception:
                pass
    return set()


def _parsear_fila(fila) -> dict | None:
    """
    Parsea una fila del DataFrame y retorna dict con los campos necesarios,
    o None si la fila no es procesable (SKU vacio o datos invalidos).
    """
    sku = limpiar_sku(fila.iloc[0])
    if not sku or sku in ("None", "nan", ""):
        return None

    try:
        costo       = f_monto(fila.iloc[1])
        p_salon     = f_monto(fila.iloc[2])
        p_mayorista = f_monto(fila.iloc[3])
    except Exception:
        return None

    # Columna E (indice 4) es opcional
    p_galpon_raw = str(fila.iloc[4]).strip() if len(fila) > 4 else ""
    tiene_galpon = p_galpon_raw.lower() not in ('0.00', '0', '', 'nan', 'none')
    p_galpon     = f_monto(fila.iloc[4]) if tiene_galpon and len(fila) > 4 else "0.00"

    return {
        "sku":          sku,
        "costo":        costo,
        "p_salon":      p_salon,
        "p_mayorista":  p_mayorista,
        "p_galpon":     p_galpon,
        "tiene_galpon": tiene_galpon,
    }


# ============================================================
# ROBOT PRINCIPAL
# ============================================================
def ejecutar_precios_v2(
    df,
    total,
    log_func,
    progress_func,
    velocidad,
    dry_run: bool = False,
    archivo_origen: str = None,
):
    """
    ROBOT PRECIOS v5.2 — Actualizacion masiva de precios (3-4-2).

    Args:
        df:             DataFrame con los precios a cargar.
        total:          Total de filas (para progress bar).
        log_func:       Funcion de logging de la GUI.
        progress_func:  Funcion de progreso (0.0-1.0).
        velocidad:      Intervalo entre teclas en pyautogui.write().
        dry_run:        Si True, simula sin tocar el sistema.
        archivo_origen: Ruta del archivo fuente (para archivar al terminar).
    """
    log_func("Iniciando Precios V2 (3-4-2)...")

    forzar_caps_off()
    pyautogui.FAILSAFE = True

    # Cargar hijos una sola vez antes del loop
    _robot_dir = Path(__file__).parent
    _root_dir  = _robot_dir.parent
    _candidatos = [_root_dir / "hijos.txt", _robot_dir / "hijos.txt", Path("hijos.txt")]
    _hijos_path = next((p for p in _candidatos if p.exists()), None)

    listado_hijos = _cargar_hijos()
    if listado_hijos:
        log_func(f"  {len(listado_hijos)} SKUs hijo cargados desde: {_hijos_path}")
    else:
        buscados = " | ".join(str(p) for p in _candidatos)
        log_func(f"  AVISO: hijos.txt no encontrado.")
        log_func(f"  Buscado en: {buscados}")
        log_func(f"  -> Todos los SKUs se cargan como PRINCIPALES (5 ENTERs)")
        log_func(f"  -> Copiá hijos.txt a: {_root_dir / 'hijos.txt'}")

    with ContextoEjecucion(
        robot_nombre="PRECIOS",
        archivo_origen=str(archivo_origen or df.shape),
        total_filas=total,
        dry_run=dry_run,
        log_func=log_func,
        progress_func=progress_func,
    ) as ctx:
        try:
            # -- NAVEGACION AL MODULO ---
            if not dry_run:
                log_func("Navegando a Modulo 3-4-2...")
                for tecla in ['3', '4', '2']:
                    pyautogui.press(tecla)
                    time.sleep(0.4)
                time.sleep(0.6)
            else:
                log_func("   [SIM] Navegacion -> 3 -> 4 -> 2 (modulo de precios)")

            # -- BUCLE MAESTRO ---
            log_func("Iniciando bucle de precios...")

            for i, fila in ctx.iterar(df):

                datos = _parsear_fila(fila)
                if datos is None:
                    ctx.registrar_error(i, "Fila completa", "Datos no válidos o SKU vacío")
                    continue

                # --- NUEVO: REGISTRO EN BASE DE DATOS ---
                if not dry_run:
                    try:
                        sql = """INSERT INTO historial_precios_propios
                                 (sku, costo, precio_salon, precio_mayorista, precio_galpon, robot_origen)
                                 VALUES (?, ?, ?, ?, ?, ?)"""
                        params = (
                            datos["sku"],
                            float(datos["costo"].replace(",", ".")),
                            float(datos["p_salon"].replace(",", ".")),
                            float(datos["p_mayorista"].replace(",", ".")),
                            float(datos["p_galpon"].replace(",", ".")),
                            "Precios_V2"
                        )
                        execute_query(sql, params, is_commit=True)
                    except Exception as db_error:
                        log_func(f"  ⚠️ Error al registrar precios en BD para SKU {datos['sku']}: {db_error}")


                sku          = datos["sku"]
                costo        = datos["costo"]
                p_salon      = datos["p_salon"]
                p_mayorista  = datos["p_mayorista"]
                p_galpon     = datos["p_galpon"]
                tiene_galpon = datos["tiene_galpon"]
                es_hijo      = sku in listado_hijos
                enters_ini   = 6 if es_hijo else 5

                tipo_sec = "Galpon (G)" if tiene_galpon else "Normal (N)"
                descripcion = (
                    f"SKU={sku} | Costo={costo} | Salon={p_salon} | "
                    f"Mayor={p_mayorista}"
                    + (f" | Galpon={p_galpon}" if tiene_galpon else "")
                    + f" | {'Hijo' if es_hijo else 'Principal'} | {tipo_sec}"
                )
                log_func(f"  {descripcion}")

                def accion_precios(
                    s=sku, co=costo, ps=p_salon, pm=p_mayorista, pg=p_galpon,
                    tg=tiene_galpon, ei=enters_ini, v=velocidad
                ):
                    # A. SKU + ENTERs de posicionamiento en Costo
                    pyautogui.write(s, interval=v)
                    for _ in range(ei):
                        pyautogui.press('enter')
                        time.sleep(0.05)
                    time.sleep(0.2)  # latencia de carga del articulo

                    # B. Costo + 3 ENTERs
                    pyautogui.write(co, interval=v)
                    for _ in range(3):
                        pyautogui.press('enter')
                        time.sleep(0.05)

                    # C. Precio Salon
                    pyautogui.write(ps, interval=v)

                    # D. Logica condicional de saltos
                    if tg:
                        # Secuencia Galpon: 2 ENTERs -> Galpon -> ENTER -> Mayorista -> ENTER -> 'G'
                        for _ in range(2):
                            pyautogui.press('enter')
                        pyautogui.write(pg, interval=v)
                        pyautogui.press('enter')
                        pyautogui.write(pm, interval=v)
                        pyautogui.press('enter')
                        pyautogui.write('G', interval=v)
                    else:
                        # Secuencia Normal: 3 ENTERs -> Mayorista -> ENTER -> 'N'
                        for _ in range(3):
                            pyautogui.press('enter')
                        pyautogui.write(pm, interval=v)
                        pyautogui.press('enter')
                        pyautogui.write('N', interval=v)

                    # E. Guardar fila
                    pyautogui.press('enter')
                    pyautogui.press('f5')
                    time.sleep(0.3)

                ctx.simular_o_ejecutar(descripcion, accion_precios, fila_idx=i)

                if (i + 1) % 10 == 0:
                    log_func(f"  {i + 1}/{total} precios procesados")

            # -- CIERRE MAESTRO ---
            if not dry_run:
                log_func("Grabando y saliendo...")
                pyautogui.press('f5')
                time.sleep(1.5)
                for t in ['end', 'end', 'end']:
                    pyautogui.press(t)
                    time.sleep(0.3)
            else:
                log_func("   [SIM] Cierre maestro: F5 -> end x3")
        except Exception as e:
            log_func(f"❌ Error: {e}")
    log_func("Robot Precios finalizado.")

    if archivo_origen:
        archivar_procesado(
            ruta_archivo=archivo_origen,
            robot_nombre="PRECIOS",
            filas_procesadas=total,
            dry_run=dry_run,
            log_func=log_func,
        )