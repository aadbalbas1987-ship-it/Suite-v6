"""
core/putty_session.py — RPA Suite v5.9
=========================================
Gestor de sesión PuTTY con login automático vía Paramiko + PyAutoGUI.

ARQUITECTURA HÍBRIDA:
  - Paramiko: verifica conectividad SSH antes de abrir PuTTY
  - PyAutoGUI: controla la ventana PuTTY visual (necesaria para el sistema heredado)
  - Trazador: registra cada micro-paso con timestamp

FLUJO COMPLETO:
  1. [Paramiko]   Verificar que el servidor SSH está accesible
  2. [PyAutoGUI]  Abrir PuTTY con host/port desde .env (subprocess)
  3. [PyAutoGUI]  Esperar prompt de usuario → escribir user
  4. [PyAutoGUI]  Esperar prompt de password → escribir password
  5. [PyAutoGUI]  Pantalla impresora 1 → Enter
  6. [PyAutoGUI]  Pantalla impresora 2 → Enter
  7. [PyAutoGUI]  Pantalla impresora 3 → Enter
  8. [PyAutoGUI]  Pantalla impresora 4 → Enter
  9. [PyAutoGUI]  Esperar menú principal
  10. → Robot toma control

TIEMPOS: se respetan los que ya funcionaban.
"""

import time
import subprocess
import pyautogui
import pygetwindow as gw
from pathlib import Path
from typing import Optional, Callable

try:
    import paramiko
    _PARAMIKO = True
except ImportError:
    _PARAMIKO = False

from core.trazabilidad import Trazador, Estado

LogFunc = Optional[Callable[[str], None]]

# ── Tiempos (no tocar — ya funcionan) ───────────────────────
T_ARRANQUE_PUTTY  = 3.0   # segundos para que PuTTY abra
T_PROMPT_USUARIO  = 1.5   # espera antes de escribir usuario
T_PROMPT_PASS     = 1.2   # espera antes de escribir clave
T_POST_LOGIN      = 2.0   # espera después de login (carga sistema)
T_IMPRESORA       = 0.8   # pausa por cada impresora
T_MENU_PRINCIPAL  = 1.5   # espera al menú principal
T_ENTRE_TECLAS    = 0.05  # intervalo entre caracteres (velocidad)
T_NAV_TECLA       = 0.5   # pausa entre teclas de navegación

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.05


def _foco_putty(intentos: int = 5, demora: float = 0.5) -> bool:
    """
    Busca y activa la ventana PuTTY con reintentos.
    Retorna True si logró el foco.
    """
    titulos_putty = ['PuTTY', 'putty', 'SSH', 'mbf.andres']
    for _ in range(intentos):
        for titulo in titulos_putty:
            wins = gw.getWindowsWithTitle(titulo)
            if wins:
                try:
                    w = wins[0]
                    if w.isMinimized:
                        w.restore()
                    w.activate()
                    time.sleep(demora)
                    return True
                except Exception:
                    pass
        time.sleep(demora)
    return False


def _forzar_caps_off():
    """Asegura que CapsLock esté desactivado."""
    try:
        import ctypes
        if ctypes.WinDLL("User32.dll").GetKeyState(0x14) & 1:
            pyautogui.press('capslock')
            time.sleep(0.1)
    except Exception:
        pass


def verificar_ssh_paramiko(host: str, port: int, user: str, password: str,
                             trazador: Trazador = None, log_func: LogFunc = None) -> bool:
    """
    Verifica conectividad SSH con Paramiko ANTES de abrir PuTTY.
    Ventaja: detecta problemas de red/credenciales sin abrir nada visual.
    """
    def _log(m):
        if trazador: trazador.registrar_posicion(m)
        elif log_func: log_func(m)

    if not _PARAMIKO:
        _log("⚠ paramiko no instalado — saltando verificación SSH previa")
        return True

    _log(f"Verificando SSH: {host}:{port} ...")
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=host, port=port,
            username=user, password=password,
            timeout=10, banner_timeout=10,
            allow_agent=False, look_for_keys=False,
        )
        # Probar con un comando simple
        _, stdout, _ = ssh.exec_command("echo OK", timeout=5)
        resultado = stdout.read().decode().strip()
        ssh.close()
        if resultado == "OK":
            _log(f"✅ SSH verificado: {host}:{port} responde correctamente")
            return True
        else:
            _log(f"⚠ SSH conectó pero la respuesta fue inesperada: {resultado}")
            return True  # Conectó igual, seguimos
    except paramiko.AuthenticationException:
        _log(f"❌ SSH: credenciales incorrectas para {user}@{host}")
        return False
    except paramiko.ssh_exception.NoValidConnectionsError:
        _log(f"❌ SSH: no se puede conectar a {host}:{port}")
        return False
    except Exception as e:
        _log(f"⚠ SSH: verificación falló ({e}) — continuando igual")
        return True  # No bloquear si hay algún error inesperado


def abrir_putty(host: str, port: int,
                putty_exe: str = "putty",
                trazador: Trazador = None) -> bool:
    """
    Abre PuTTY apuntando al host/port desde el .env.
    Busca putty.exe en: PATH, C:\\Program Files, C:\\Windows, escritorio.
    """
    def _log(m):
        if trazador: trazador.registrar_posicion(m)

    # Buscar putty.exe
    rutas_putty = [
        putty_exe,
        r"C:\Program Files\PuTTY\putty.exe",
        r"C:\Program Files (x86)\PuTTY\putty.exe",
        r"C:\Windows\System32\putty.exe",
        str(Path.home() / "Desktop" / "putty.exe"),
        str(Path.home() / "Downloads" / "putty.exe"),
    ]
    putty_path = None
    for ruta in rutas_putty:
        if Path(ruta).exists():
            putty_path = ruta
            break

    if not putty_path:
        _log("⚠ putty.exe no encontrado en rutas estándar — intentando con 'putty' en PATH")
        putty_path = "putty"

    _log(f"Abriendo PuTTY → {host}:{port}")
    try:
        subprocess.Popen([putty_path, "-ssh", host, "-P", str(port)],
                         shell=False)
        time.sleep(T_ARRANQUE_PUTTY)
        return True
    except FileNotFoundError:
        _log("❌ PuTTY no encontrado. Asegurate de que esté instalado y en el PATH.")
        return False
    except Exception as e:
        _log(f"❌ Error abriendo PuTTY: {e}")
        return False


def login_putty_completo(
    host: str,
    port: int,
    user: str,
    password: str,
    n_impresoras: int = 4,
    trazador: Trazador = None,
    log_func: LogFunc = None,
    dry_run: bool = False,
) -> bool:
    """
    Ejecuta el login completo en PuTTY:
    usuario → password → N impresoras → menú principal.

    Cada micro-paso queda registrado en el Trazador.
    Retorna True si llegó al menú principal.
    """
    def _log(m):
        if trazador: trazador.registrar_posicion(m)
        elif log_func: log_func(m)

    if dry_run:
        _log("[DRY-RUN] Login simulado — no se abre PuTTY real")
        return True

    _forzar_caps_off()

    # ── Paso: verificar SSH ───────────────────────────────────
    if trazador:
        with trazador.etapa("VERIFICAR_SSH", f"Verificando {host}:{port} con Paramiko"):
            ok = verificar_ssh_paramiko(host, port, user, password, trazador)
            if not ok:
                return False
    else:
        ok = verificar_ssh_paramiko(host, port, user, password, log_func=log_func)
        if not ok:
            return False

    # ── Paso: abrir PuTTY ─────────────────────────────────────
    if trazador:
        with trazador.etapa("ABRIR_PUTTY", f"Ejecutando PuTTY → {host}:{port}"):
            if not abrir_putty(host, port, trazador=trazador):
                return False
    else:
        if not abrir_putty(host, port, log_func=log_func):
            return False

    # ── Paso: foco ventana ────────────────────────────────────
    _log("Buscando ventana PuTTY...")
    if not _foco_putty(intentos=8, demora=0.5):
        _log("❌ No se encontró la ventana PuTTY después de abrirla")
        return False
    _log("✅ Ventana PuTTY activa")

    # ── Paso: usuario ─────────────────────────────────────────
    if trazador:
        with trazador.etapa("USUARIO", f"Escribiendo usuario: {user}",
                             esperado="login:"):
            trazador.registrar_posicion(f"Pausa {T_PROMPT_USUARIO}s para prompt de usuario")
            time.sleep(T_PROMPT_USUARIO)
            _forzar_caps_off()
            pyautogui.write(user, interval=T_ENTRE_TECLAS)
            pyautogui.press('enter')
            trazador.registrar_posicion("Usuario enviado — esperando prompt de password")
    else:
        _log(f"Escribiendo usuario: {user}")
        time.sleep(T_PROMPT_USUARIO)
        _forzar_caps_off()
        pyautogui.write(user, interval=T_ENTRE_TECLAS)
        pyautogui.press('enter')

    # ── Paso: password ────────────────────────────────────────
    if trazador:
        with trazador.etapa("PASSWORD", "Escribiendo contraseña",
                             esperado="Password:"):
            time.sleep(T_PROMPT_PASS)
            pyautogui.write(password, interval=T_ENTRE_TECLAS)
            pyautogui.press('enter')
            trazador.registrar_posicion(f"Password enviada — esperando {T_POST_LOGIN}s login")
            time.sleep(T_POST_LOGIN)
    else:
        _log("Escribiendo contraseña")
        time.sleep(T_PROMPT_PASS)
        pyautogui.write(password, interval=T_ENTRE_TECLAS)
        pyautogui.press('enter')
        time.sleep(T_POST_LOGIN)

    # ── Pasos: impresoras ─────────────────────────────────────
    for n in range(1, n_impresoras + 1):
        if trazador:
            with trazador.etapa(f"IMPRESORA_{n}",
                                 f"Pantalla impresora {n} de {n_impresoras} — Enter",
                                 esperado=f"Impresora {n}"):
                trazador.registrar_posicion(f"Enter para impresora {n}")
                pyautogui.press('enter')
                time.sleep(T_IMPRESORA)
        else:
            _log(f"Impresora {n}/{n_impresoras} — Enter")
            pyautogui.press('enter')
            time.sleep(T_IMPRESORA)

    # ── Paso: menú principal ──────────────────────────────────
    if trazador:
        with trazador.etapa("MENU_PRINCIPAL", f"Esperando menú principal ({T_MENU_PRINCIPAL}s)"):
            time.sleep(T_MENU_PRINCIPAL)
            trazador.registrar_posicion("✅ En menú principal — robot toma control")
    else:
        _log(f"Esperando menú principal ({T_MENU_PRINCIPAL}s)...")
        time.sleep(T_MENU_PRINCIPAL)
        _log("✅ Login completo — en menú principal")

    return True


def navegar_modulo(
    secuencia: list,
    trazador: Trazador = None,
    log_func: LogFunc = None,
    dry_run: bool = False,
):
    """
    Navega al módulo usando la secuencia de teclas.
    Ej: ['3','6','1'] para Carga Stock.
    Cada tecla queda trazada individualmente.
    """
    def _log(m):
        if trazador: trazador.registrar_posicion(m)
        elif log_func: log_func(m)

    ruta = " → ".join(secuencia)
    _log(f"Navegando módulo: {ruta}")

    if dry_run:
        _log(f"[DRY-RUN] Navegación simulada: {ruta}")
        return

    for tecla in secuencia:
        if trazador:
            trazador.registrar_posicion(f"Tecla: [{tecla}]")
        pyautogui.press(tecla)
        time.sleep(T_NAV_TECLA)

    _log(f"✅ En módulo {ruta}")
