"""
robots/robot_facturacion.py — RPA Suite v5.7
=============================================
Robot de facturación automática vía PuTTY.
Navega al módulo de facturación del sistema y carga facturas desde Excel.

Estructura del Excel de entrada (keyword: "factura"):
  Columna A: CUIT del cliente
  Columna B: Código de artículo (SKU)
  Columna C: Cantidad
  Columna D: Precio unitario
  Columna E: % Descuento (opcional)

Precondición: PuTTY abierto en menú principal.
"""
import pyautogui
import pygetwindow as gw
import pyperclip
import time
from pathlib import Path
from datetime import date

pyautogui.FAILSAFE = True


# ══════════════════════════════════════════════════════════════
# HELPERS (reutilizados del Robot_Putty)
# ══════════════════════════════════════════════════════════════

def _foco_putty(log_func) -> bool:
    for titulo in ['PuTTY', 'putty', 'SSH']:
        wins = gw.getWindowsWithTitle(titulo)
        if wins:
            try:
                wins[0].activate(); time.sleep(0.5); return True
            except Exception: pass
    log_func("❌ PuTTY no encontrado")
    return False

def _t(char, pausa=0.3):
    pyautogui.write(char, interval=0.03); time.sleep(pausa)

def _enter(n=1, pausa=0.25):
    for _ in range(n): pyautogui.press('enter'); time.sleep(pausa)

def _paste(txt, pausa=0.25):
    pyperclip.copy(txt); time.sleep(0.1)
    pyautogui.click(button='right'); time.sleep(pausa)

def _caps_off():
    import ctypes
    if ctypes.WinDLL("User32.dll").GetKeyState(0x14) & 1:
        pyautogui.press('capslock'); time.sleep(0.1)


# ══════════════════════════════════════════════════════════════
# VALIDACIÓN DEL ARCHIVO
# ══════════════════════════════════════════════════════════════

def validar_archivo_factura(df, log_func) -> tuple[bool, str]:
    """Valida estructura mínima del Excel de facturación."""
    if len(df) < 1:
        return False, "Archivo vacío"
    if df.shape[1] < 4:
        return False, f"Se necesitan al menos 4 columnas (CUIT, SKU, CANTIDAD, PRECIO). Encontradas: {df.shape[1]}"

    # Verificar que CANTIDAD y PRECIO sean numéricos
    try:
        import pandas as pd
        cant  = pd.to_numeric(df.iloc[:, 2], errors='coerce')
        prec  = pd.to_numeric(df.iloc[:, 3], errors='coerce')
        if cant.isna().any():
            return False, "Columna CANTIDAD tiene valores no numéricos"
        if prec.isna().any():
            return False, "Columna PRECIO tiene valores no numéricos"
    except Exception as e:
        return False, f"Error validando: {e}"

    return True, f"Archivo válido — {len(df)} línea(s) de factura"


# ══════════════════════════════════════════════════════════════
# SECUENCIA DE FACTURACIÓN
# ══════════════════════════════════════════════════════════════

def _navegar_modulo_factura(log_func, nav_path: list = None):
    """
    Navega al módulo de facturación.
    nav_path: lista de teclas para llegar al módulo (configurable).
    Default: ['4', '1'] (Módulo 4 → submenú 1 — ajustar según tu sistema)
    """
    path = nav_path or ['4', '1']
    log_func(f"  📂 Navegando módulo facturación: {' → '.join(path)}")
    for tecla in path:
        _t(tecla, pausa=0.8)
    _enter(1, pausa=1.0)


def _cargar_linea_factura(sku: str, cantidad: int, precio: float,
                            descuento: float, log_func):
    """Carga una línea de artículo en la factura."""
    _caps_off()
    _paste(str(sku), pausa=0.3)
    _enter(1, pausa=0.4)
    _paste(str(cantidad), pausa=0.3)
    _enter(1, pausa=0.3)
    _paste(f"{precio:.2f}", pausa=0.3)
    _enter(1, pausa=0.3)
    if descuento and descuento > 0:
        _paste(f"{descuento:.1f}", pausa=0.3)
    _enter(1, pausa=0.4)


def ejecutar_facturacion(
    df,
    total_filas: int,
    log_func,
    progress_func,
    velocidad: float = 0.04,
    dry_run: bool = False,
    archivo_origen=None,
    nav_path: list = None,
) -> bool:
    """
    Ejecuta la carga de factura en PuTTY.

    Args:
        df:           DataFrame con columnas CUIT, SKU, CANTIDAD, PRECIO, DESC (opcional)
        total_filas:  cantidad de filas (pasado por el caller)
        log_func:     función de logging
        progress_func:función de progreso (0.0 a 1.0)
        velocidad:    pausa entre pulsaciones
        dry_run:      si True, simula sin tocar el teclado
        nav_path:     teclas para navegar al módulo (ej: ['4','1'])
    """
    import pandas as pd

    ok, msg = validar_archivo_factura(df, log_func)
    if not ok:
        log_func(f"❌ Archivo inválido: {msg}"); return False
    log_func(f"✅ {msg}")

    if not dry_run and not _foco_putty(log_func):
        return False

    log_func(f"🧾 Iniciando facturación — {total_filas} línea(s) {'[DRY RUN]' if dry_run else ''}")

    try:
        if not dry_run:
            _navegar_modulo_factura(log_func, nav_path)

        # Cabecera: CUIT del primer registro (se asume una factura por archivo)
        cuit_cli = str(df.iloc[0, 0]).strip()
        if not dry_run:
            log_func(f"  👤 Cliente CUIT: {cuit_cli}")
            _paste(cuit_cli, pausa=0.5)
            _enter(2, pausa=0.4)   # confirmar cliente
        else:
            log_func(f"  [SIM] Cliente CUIT: {cuit_cli}")

        # Líneas de artículos
        for i, row in df.iterrows():
            sku      = str(row.iloc[1]).strip()
            cantidad = int(float(row.iloc[2]))
            precio   = float(row.iloc[3])
            descuento= float(row.iloc[4]) if df.shape[1] > 4 and pd.notna(row.iloc[4]) else 0.0

            progress_func(i / total_filas)
            log_func(f"  [{i+1}/{total_filas}] SKU {sku} × {cantidad} @ ${precio:.2f}"
                     f"{f' ({descuento}% desc.)' if descuento else ''}")

            if not dry_run:
                _cargar_linea_factura(sku, cantidad, precio, descuento, log_func)
            time.sleep(velocidad)

        # Confirmar factura
        if not dry_run:
            log_func("  ✅ Confirmando factura...")
            pyautogui.press('f5')     # F5 = confirmar (ajustar según sistema)
            time.sleep(1.5)
            _enter(1, pausa=0.5)
            pyautogui.press('end')    # volver al menú
            time.sleep(0.5)

        progress_func(1.0)
        log_func("✅ Facturación completada.")
        return True

    except pyautogui.FailSafeException:
        log_func("🛑 FAILSAFE activado — robot detenido.")
        return False
    except Exception as e:
        import traceback
        log_func(f"❌ Error: {e}")
        log_func(traceback.format_exc())
        return False
