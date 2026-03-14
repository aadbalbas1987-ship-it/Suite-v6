"""
watchdog.py — RPA Suite v5
===========================
Sistema de vigilancia (watchdog) para los robots de automatización.

Detecta tres tipos de desvío:
  1. Ventana emergente inesperada — cartel del sistema que no debería estar
  2. Pantalla congelada — PuTTY dejó de cambiar (timeout configurable)
  3. Desvío de foco — la ventana activa ya no es PuTTY

Cuando detecta un problema:
  - Pausa el robot (flag global)
  - Lanza un messagebox de Windows con descripción del problema
  - Loguea el evento con timestamp
  - Le da al usuario tres opciones: Reintentar / Ignorar / Detener robot

Uso en un robot:
    from watchdog import WatchdogPuTTY

    with WatchdogPuTTY(robot_nombre="STOCK", log_func=log_func) as wd:
        for i, fila in ctx.iterar(df):
            wd.latido()          # llamar en cada iteración del bucle
            ...tu lógica...
"""

import threading
import time
import ctypes
import datetime
import traceback
from typing import Callable, Optional

# pyautogui es el único import externo necesario
try:
    import pyautogui
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False

# win32gui para inspeccionar ventanas activas (opcional pero ideal)
try:
    import win32gui
    import win32process
    WIN32_OK = True
except ImportError:
    WIN32_OK = False

# Pillow para comparar screenshots
try:
    from PIL import Image, ImageChops
    import io
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False


# ============================================================
# CONSTANTES DE CONFIGURACIÓN
# ============================================================

# Títulos de ventanas que NUNCA deberían aparecer mientras corre el robot
VENTANAS_PROHIBIDAS = [
    # Errores del sistema Windows
    "error",
    "problema",
    "ha dejado de funcionar",
    "no responde",
    "acceso denegado",
    # Errores de red / sesión
    "connection",
    "conexión",
    "disconnect",
    "desconect",
    "network error",
    "timeout",
    # Carteles del sistema ERP (ajustar según el sistema)
    "advertencia del sistema",
    "alerta",
    "aviso de sesión",
    "sesión expirada",
    "clave incorrecta",
    "usuario bloqueado",
    # Otros programas que no deberían tener el foco
    "microsoft word",
    "microsoft excel",
    # "google chrome",  # permitido — puede estar abierto el dashboard BI
    # "firefox",        # permitido
    "whatsapp",
    "telegram",
]

# Títulos de ventanas SIEMPRE permitidas (nunca disparan alerta aunque estén abiertas)
VENTANAS_PERMITIDAS = [
    "google chrome",
    "firefox",
    "edge",
    "streamlit",
    "rpa suite",
    "watchdog",
]

# Títulos que confirman que PuTTY tiene el foco correcto
TITULOS_PUTTY_VALIDOS = [
    "putty",
    "ssh",
    "telnet",
    # Si tu PuTTY muestra el nombre del servidor en el título, agregalo acá:
    # "192.168.",
    # "servidor-erp",
]

# Segundos sin cambio de pantalla para considerar congelamiento
TIMEOUT_CONGELA_SEG = 30

# Segundos entre cada check del watchdog en segundo plano
INTERVALO_CHECK_SEG = 3

# Máximo de alertas ignoradas antes de sugerir detener
MAX_IGNORADAS = 3


# ============================================================
# MESSAGEBOX WINDOWS (sin dependencias extras)
# ============================================================

MB_OK            = 0x0
MB_OKCANCEL      = 0x1
MB_ABORTRETRYIGNORE = 0x2
MB_YESNOCANCEL   = 0x3
MB_RETRYCANCEL   = 0x5
MB_ICONWARNING   = 0x30
MB_ICONERROR     = 0x10
MB_ICONINFO      = 0x40
MB_SYSTEMMODAL   = 0x1000   # Aparece sobre todo, incluso sobre pantalla completa
MB_TOPMOST       = 0x40000  # Siempre encima

IDOK     = 1
IDCANCEL = 2
IDABORT  = 3
IDRETRY  = 4
IDIGNORE = 5
IDYES    = 6
IDNO     = 7


def _messagebox(titulo: str, mensaje: str, flags: int = MB_OK | MB_ICONWARNING | MB_SYSTEMMODAL) -> int:
    """
    Muestra un cuadro de diálogo de Windows nativo.
    Retorna el ID del botón presionado.
    Funciona sin ninguna dependencia extra — usa ctypes puro.
    """
    try:
        return ctypes.windll.user32.MessageBoxW(
            0,
            str(mensaje),
            str(titulo),
            flags
        )
    except Exception:
        # Fallback si no corre en Windows (ej: durante testing)
        print(f"\n⚠️  ALERTA WATCHDOG: {titulo}\n{mensaje}\n")
        return IDOK


def alerta_desvio(robot_nombre: str, tipo: str, detalle: str,
                  log_func: Callable = print) -> str:
    """
    Muestra messagebox de alerta con 3 opciones:
      [Reintentar]  → el robot intenta continuar desde el último punto
      [Ignorar]     → registra el evento y sigue
      [Detener]     → señal de parada limpia al robot

    Retorna: 'reintentar' | 'ignorar' | 'detener'
    """
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")

    titulo = f"⚠️  Alerta — Robot {robot_nombre}"
    mensaje = (
        f"🤖  Robot: {robot_nombre}\n"
        f"🕐  Hora:   {timestamp}\n"
        f"⚠️  Tipo:   {tipo}\n\n"
        f"{detalle}\n\n"
        f"─────────────────────────────────────\n"
        f"¿Qué hacemos?\n\n"
        f"  [Reintentar]  Esperá, resolvé el problema y el robot continúa.\n"
        f"  [Ignorar]     Registra el evento y sigue igual (puede fallar).\n"
        f"  [Cancelar]    Detiene el robot de forma limpia."
    )

    log_func(f"🚨 WATCHDOG [{timestamp}] {tipo}: {detalle}")

    resultado = _messagebox(
        titulo, mensaje,
        MB_ABORTRETRYIGNORE | MB_ICONWARNING | MB_SYSTEMMODAL | MB_TOPMOST
    )

    # MB_ABORTRETRYIGNORE: Abort=3, Retry=4, Ignore=5
    # Lo remapeamos a términos del robot:
    #   "Abort" (3)  → Detener
    #   "Retry" (4)  → Reintentar
    #   "Ignore" (5) → Ignorar
    if resultado == IDABORT:
        log_func(f"🛑 WATCHDOG: Usuario eligió DETENER el robot.")
        return 'detener'
    elif resultado == IDRETRY:
        log_func(f"🔄 WATCHDOG: Usuario eligió REINTENTAR.")
        return 'reintentar'
    else:
        log_func(f"⏩ WATCHDOG: Usuario eligió IGNORAR.")
        return 'ignorar'


# ============================================================
# CLASE PRINCIPAL — WatchdogPuTTY
# ============================================================

class WatchdogPuTTY:
    """
    Vigilante de robots PuTTY. Se usa como context manager:

        with WatchdogPuTTY(robot_nombre="STOCK", log_func=log_func) as wd:
            for i, fila in ctx.iterar(df):
                wd.latido()   # en cada iteración del bucle principal
                ...

    Internamente corre un thread de fondo que verifica cada INTERVALO_CHECK_SEG.
    El método latido() también chequea el estado y pausa si hay un problema activo.
    """

    def __init__(
        self,
        robot_nombre: str,
        log_func: Callable = print,
        timeout_congela: int = TIMEOUT_CONGELA_SEG,
        intervalo_check: int = INTERVALO_CHECK_SEG,
        titulos_validos: list = None,
        dry_run: bool = False,
        habilitado: bool = True,
    ):
        self.robot_nombre    = robot_nombre
        self.log_func        = log_func
        self.timeout_congela = timeout_congela
        self.intervalo_check = intervalo_check
        self.titulos_validos = titulos_validos or TITULOS_PUTTY_VALIDOS
        self.dry_run         = dry_run
        self.habilitado      = habilitado  # False = watchdog completamente pasivo

        # Estado interno
        self._activo         = False
        self._detenido       = False       # señal de parada al robot
        self._alerta_activa  = False       # bloquea el robot mientras el usuario decide
        self._ignoradas      = 0           # contador de alertas ignoradas
        self._ultimo_cambio  = time.time() # para detectar congelamiento
        self._ultimo_hash    = None        # hash de la última captura de pantalla

        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # ── Context Manager ──────────────────────────────────────

    def __enter__(self):
        if not self.habilitado:
            self.log_func(f"🐕 Watchdog DESACTIVADO para robot {self.robot_nombre}")
            return self
        if not self.dry_run:
            self._activo = True
            self._ultimo_cambio = time.time()
            self._ultimo_hash   = self._capturar_hash()
            self._thread = threading.Thread(
                target=self._loop_vigilancia,
                daemon=True,
                name=f"WD-{self.robot_nombre}"
            )
            self._thread.start()
            self.log_func(f"🐕 Watchdog activo para robot {self.robot_nombre}")
        else:
            self.log_func(f"🐕 Watchdog en modo DRY-RUN (solo logging, sin alertas)")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._activo = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        if not self.dry_run:
            self.log_func(f"🐕 Watchdog desactivado para robot {self.robot_nombre}")
        return False  # no suprime excepciones

    # ── API pública ───────────────────────────────────────────

    def latido(self):
        """
        Llamar en cada iteración del bucle principal del robot.
        - Actualiza el timestamp de "último cambio" (señal de vida)
        - Si hay una alerta activa, bloquea hasta que el usuario decida
        - Si el usuario eligió DETENER, lanza RobotDetenidoError
        """
        if self.dry_run or not self.habilitado:
            return

        # Actualizar señal de vida
        with self._lock:
            self._ultimo_cambio = time.time()

        # Esperar si hay alerta activa (el thread la resolvió o está esperando al usuario)
        espera = 0
        while self._alerta_activa and espera < 120:
            time.sleep(0.5)
            espera += 0.5

        # Verificar si el usuario pidió detener
        if self._detenido:
            raise RobotDetenidoError(
                f"Robot {self.robot_nombre} detenido por el operador vía Watchdog."
            )

    def detener(self):
        """Detiene el watchdog desde fuera (ej: al finalizar el robot)."""
        self._activo = False

    @property
    def robot_detenido(self) -> bool:
        """True si el operador eligió detener el robot."""
        return self._detenido

    # ── Loop de vigilancia (thread de fondo) ─────────────────

    def _loop_vigilancia(self):
        """Corre en segundo plano mientras el robot trabaja."""
        while self._activo:
            try:
                self._verificar_ventanas_prohibidas()
                if self._activo:
                    self._verificar_foco_putty()
                if self._activo:
                    self._verificar_congelamiento()
            except RobotDetenidoError:
                self._detenido = True
                self._activo   = False
                break
            except Exception as e:
                # El watchdog nunca debe crashear el robot
                self.log_func(f"🐕 Watchdog error interno: {e}")

            time.sleep(self.intervalo_check)

    # ── Verificaciones ────────────────────────────────────────

    def _verificar_ventanas_prohibidas(self):
        """
        Busca ventanas abiertas cuyos títulos coincidan con VENTANAS_PROHIBIDAS.
        """
        if not WIN32_OK:
            return

        ventanas_encontradas = []

        def _enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                titulo = win32gui.GetWindowText(hwnd).lower()
                # Saltar ventanas explícitamente permitidas
                if any(p.lower() in titulo for p in VENTANAS_PERMITIDAS):
                    return
                for prohibida in VENTANAS_PROHIBIDAS:
                    if prohibida.lower() in titulo and titulo.strip():
                        ventanas_encontradas.append(win32gui.GetWindowText(hwnd))

        try:
            win32gui.EnumWindows(_enum_cb, None)
        except Exception:
            return

        if ventanas_encontradas:
            detalle = (
                f"Se detectaron estas ventanas inesperadas:\n"
                + "\n".join(f"  • {v}" for v in ventanas_encontradas[:5])
                + "\n\nPueden indicar un error del sistema o una interrupción en PuTTY.\n"
                  "Revisá la pantalla antes de continuar."
            )
            self._disparar_alerta("Ventana inesperada detectada", detalle)

    def _verificar_foco_putty(self):
        """
        Verifica que la ventana activa sea PuTTY.
        Si el foco está en otro programa, el robot está escribiendo en el lugar equivocado.
        """
        if not WIN32_OK:
            return

        try:
            hwnd_activo = win32gui.GetForegroundWindow()
            titulo_activo = win32gui.GetWindowText(hwnd_activo).lower()

            # Si el título está vacío o es la propia GUI, ignorar
            if not titulo_activo.strip():
                return

            # Verificar si es una ventana válida de PuTTY
            es_putty = any(v.lower() in titulo_activo for v in self.titulos_validos)

            # Verificar si es la GUI del robot (también es válido)
            es_gui_robot = any(x in titulo_activo for x in [
                "rpa suite", "tkinter", "python", "gestión", "robot"
            ])

            if not es_putty and not es_gui_robot:
                detalle = (
                    f"La ventana activa no es PuTTY:\n\n"
                    f"  Ventana activa: \"{win32gui.GetWindowText(hwnd_activo)}\"\n\n"
                    f"El robot está escribiendo en el lugar EQUIVOCADO.\n"
                    f"Hacé clic en la ventana de PuTTY y luego presioná Reintentar."
                )
                self._disparar_alerta("⚠️ Robot fuera de PuTTY", detalle)
        except Exception:
            pass

    def _verificar_congelamiento(self):
        """
        Compara el screenshot actual con el anterior.
        Si no hubo ningún cambio visual en TIMEOUT_CONGELA_SEG, alerta congelamiento.
        """
        if not PILLOW_OK or not PYAUTOGUI_OK:
            # Fallback sin Pillow: usar timestamp del último latido
            with self._lock:
                segundos_sin_latido = time.time() - self._ultimo_cambio
            if segundos_sin_latido > self.timeout_congela:
                detalle = (
                    f"El robot no procesó ninguna fila en los últimos "
                    f"{segundos_sin_latido:.0f} segundos.\n\n"
                    f"Puede indicar que PuTTY se congeló o que el sistema no responde.\n"
                    f"Revisá la pantalla de PuTTY."
                )
                self._disparar_alerta("Posible congelamiento detectado", detalle)
            return

        hash_actual = self._capturar_hash()
        if hash_actual is None:
            return

        with self._lock:
            hash_anterior = self._ultimo_hash
            segundos_sin_cambio = time.time() - self._ultimo_cambio

        if hash_actual == hash_anterior and segundos_sin_cambio > self.timeout_congela:
            detalle = (
                f"La pantalla no cambió en los últimos {segundos_sin_cambio:.0f} segundos.\n\n"
                f"Puede indicar:\n"
                f"  • PuTTY congelado o sin respuesta del servidor\n"
                f"  • La conexión SSH se cortó\n"
                f"  • El sistema ERP está procesando algo muy lento\n\n"
                f"Revisá la ventana de PuTTY antes de continuar."
            )
            self._disparar_alerta("Pantalla congelada", detalle)
        elif hash_actual != hash_anterior:
            with self._lock:
                self._ultimo_hash   = hash_actual
                self._ultimo_cambio = time.time()

    def _capturar_hash(self) -> Optional[int]:
        """Captura un screenshot y retorna un hash simple para comparar."""
        if not PYAUTOGUI_OK or not PILLOW_OK:
            return None
        try:
            img = pyautogui.screenshot()
            # Reducir a 50x50 para comparación rápida
            img_small = img.resize((50, 50))
            return hash(img_small.tobytes())
        except Exception:
            return None

    # ── Disparador de alertas ─────────────────────────────────

    def _disparar_alerta(self, tipo: str, detalle: str):
        """
        Pausa el robot, muestra el messagebox y actúa según la respuesta.
        Thread-safe: solo una alerta a la vez.
        """
        with self._lock:
            if self._alerta_activa:
                return  # ya hay una alerta pendiente
            self._alerta_activa = True

        try:
            respuesta = alerta_desvio(
                robot_nombre=self.robot_nombre,
                tipo=tipo,
                detalle=detalle,
                log_func=self.log_func,
            )

            if respuesta == 'detener':
                self._detenido = True
                self._activo   = False
                raise RobotDetenidoError(f"Robot detenido por el operador. Motivo: {tipo}")

            elif respuesta == 'reintentar':
                self.log_func(f"🔄 Watchdog: esperando 5 segundos para reintentar...")
                time.sleep(5)
                # Resetear el timer de congelamiento para no re-disparar de inmediato
                with self._lock:
                    self._ultimo_cambio = time.time()
                    self._ultimo_hash   = self._capturar_hash()

            elif respuesta == 'ignorar':
                self._ignoradas += 1
                if self._ignoradas >= MAX_IGNORADAS:
                    self.log_func(
                        f"⚠️ Watchdog: {self._ignoradas} alertas ignoradas. "
                        f"Revisá el proceso manualmente."
                    )
        finally:
            with self._lock:
                self._alerta_activa = False


# ============================================================
# EXCEPCIÓN PERSONALIZADA
# ============================================================

class RobotDetenidoError(Exception):
    """
    Lanzada cuando el operador decide detener el robot desde el watchdog.
    Los robots deben capturarla en su bucle principal para cerrar limpiamente.
    """
    pass


# ============================================================
# DECORADOR — para funciones críticas individuales
# ============================================================

def vigilar_paso(robot_nombre: str, descripcion: str, log_func: Callable = print,
                 reintentos: int = 2):
    """
    Decorador para envolver pasos críticos individuales con manejo de error.

    Uso:
        @vigilar_paso("STOCK", "Navegación al módulo 3-6-1", log_func)
        def navegar():
            ...

    Si falla, muestra alerta y ofrece reintentar hasta `reintentos` veces.
    """
    def decorador(func):
        def wrapper(*args, **kwargs):
            for intento in range(reintentos + 1):
                try:
                    return func(*args, **kwargs)
                except RobotDetenidoError:
                    raise
                except Exception as e:
                    log_func(f"❌ Error en paso '{descripcion}': {e}")
                    if intento < reintentos:
                        detalle = (
                            f"Falló el paso: {descripcion}\n\n"
                            f"Error: {e}\n\n"
                            f"Intento {intento+1} de {reintentos+1}.\n"
                            f"Revisá la pantalla y presioná Reintentar para volver a intentarlo."
                        )
                        respuesta = alerta_desvio(robot_nombre, f"Error en paso", detalle, log_func)
                        if respuesta == 'detener':
                            raise RobotDetenidoError(f"Detenido en paso: {descripcion}")
                        elif respuesta == 'ignorar':
                            return None
                        # 'reintentar' → sigue el loop
                    else:
                        raise
        return wrapper
    return decorador


# ============================================================
# FUNCIÓN DE CONVENIENCIA — alerta manual desde cualquier robot
# ============================================================

def alertar(robot_nombre: str, mensaje: str, log_func: Callable = print,
            critico: bool = False) -> str:
    """
    Función simple para disparar una alerta manual desde cualquier punto del robot.

    Ejemplo de uso en un robot:
        from watchdog import alertar, RobotDetenidoError

        resultado = alertar("STOCK", "El SKU 12345 no fue aceptado por el sistema.")
        if resultado == 'detener':
            raise RobotDetenidoError("Detenido por el operador.")

    Returns: 'reintentar' | 'ignorar' | 'detener'
    """
    tipo = "⛔ Error crítico" if critico else "⚠️ Atención requerida"
    return alerta_desvio(robot_nombre, tipo, mensaje, log_func)