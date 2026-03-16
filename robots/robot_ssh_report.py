"""
robot_ssh_report.py — RPA Suite v5.5
======================================
v5.5: Sin paramiko, pyautogui puro. Tiempos acelerados.
Precondición: PuTTY abierto con sesión activa en menú principal.

Secuencia: 3 → 4 → a → 16×ENTER → E → ENTER → mail (clipboard) → F5 → END×3
"""
import pyautogui
import pygetwindow as gw
import pyperclip
import time
import os
from pathlib import Path
from config import get_ssh_config

pyautogui.FAILSAFE = True

_ROOT = Path(__file__).parent.parent
LOG_PATH = _ROOT / "logs" / "debug_ssh_report.txt"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_debug(mensaje: str, modo: str = "a"):
    try:
        with open(LOG_PATH, modo, encoding='utf-8') as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {mensaje}\n")
    except Exception:
        pass


def _forzar_foco_putty(log_func) -> bool:
    for titulo in ['PuTTY', 'putty', 'SSH']:
        ventanas = gw.getWindowsWithTitle(titulo)
        if ventanas:
            try:
                ventanas[0].activate()
                time.sleep(0.5)
                log_func(f"   → Foco en: {ventanas[0].title}")
                return True
            except Exception as e:
                log_func(f"   ⚠ No se pudo activar: {e}")
    log_func("❌ No se encontró ventana PuTTY abierta.")
    return False


def _tecla(char: str, pausa: float = 0.3):
    pyautogui.write(char, interval=0.03)
    time.sleep(pausa)


def _pegar(texto: str, pausa: float = 0.3):
    """Copia al clipboard y pega con click derecho — método nativo de PuTTY."""
    pyperclip.copy(texto)
    time.sleep(0.15)
    pyautogui.click(button='right')
    time.sleep(pausa)


def _enter(n: int = 1, pausa: float = 0.2):
    for _ in range(n):
        pyautogui.press('enter')
        time.sleep(pausa)


def ejecutar_descarga_reporte(email_destino: str = None, log_func=None) -> bool:
    if log_func is None:
        log_func = lambda m: log_debug(m)

    try:
        ssh = get_ssh_config()
    except EnvironmentError as e:
        log_func(f"❌ Config SSH: {e}")
        return False

    if not email_destino:
        email_destino = ssh.default_email

    log_debug("--- INICIO: REPORTE PRECIOS v5.5 ---", modo="w")
    log_func(f"📡 Iniciando descarga → {email_destino}")

    # ── 1. FOCO PUTTY ────────────────────────────────────────────
    if not _forzar_foco_putty(log_func):
        return False

    try:
        # ── 2. NAVEGACIÓN 3 → 4 → a ──────────────────────────────
        log_func("   Navegando 3 → 4 → a...")
        _tecla('3', pausa=0.3)
        _tecla('4', pausa=0.3)
        _tecla('a', pausa=0.5)   # espera carga formulario

        # ── 3. 16 × ENTER ────────────────────────────────────────
        log_func("   16×ENTER (campos del formulario)...")
        _enter(16, pausa=0.2)
        time.sleep(0.1)

        # ── 4. TIPO SALIDA → E (siempre mayúscula) ──────────────
        log_func("   Tipo de salida → E...")
        import ctypes
        # Apagar Bloq Mayús si está activo
        if ctypes.WinDLL("User32.dll").GetKeyState(0x14) & 1:
            pyautogui.press('capslock')
            time.sleep(0.1)
        pyautogui.keyDown('shift')
        pyautogui.press('e')
        pyautogui.keyUp('shift')
        time.sleep(0.2)
        _enter(1, pausa=0.8)

        # ── 5. MAIL (clipboard) ───────────────────────────────────
        log_func(f"   Mail → {email_destino}...")
        _pegar(email_destino, pausa=0.3)

        # ── 6. F5 ─────────────────────────────────────────────────
        log_func("   F5 → procesando...")
        pyautogui.press('f5')
        time.sleep(2.0)

        # ── 7. END × 3 ────────────────────────────────────────────
        log_func("   END×3 → volviendo al menú...")
        for _ in range(3):
            pyautogui.press('end')
            time.sleep(0.3)

        log_func("✅ Listo. Revisá tu casilla de correo.")
        log_debug("--- FIN OK ---")
        return True

    except pyautogui.FailSafeException:
        log_func("🛑 FAILSAFE activado. Robot detenido.")
        return False
    except Exception as e:
        import traceback
        log_func(f"❌ Error: {e}")
        log_debug(f"EXCEPCION: {e}\n{traceback.format_exc()}")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  ROBOT SSH — DESCARGA DE PRECIOS v5.5")
    print("=" * 55)
    print("  PuTTY debe estar abierto en el menú principal.\n")
    correo = input("  Email destino (ENTER = .env): ").strip() or None
    ok = ejecutar_descarga_reporte(email_destino=correo, log_func=print)
    print("\n  ✅ Revisá tu casilla." if ok else "\n  ❌ Revisá debug_ssh_report.txt")