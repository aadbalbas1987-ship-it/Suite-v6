"""
robots/Stock_Paramiko.py — RPA Suite v6.0
=========================================
Clon del robot de carga de stock (3-6-1), migrado a Paramiko.
Operación "backdoor" directa por SSH.
"""

import time
import re
from typing import Optional
from pathlib import Path

try:
    import paramiko
    _PARAMIKO_OK = True
except ImportError:
    _PARAMIKO_OK = False

from config import get_ssh_config
from core.trazabilidad import Trazador, Estado
from core.pre_validador import _limpiar_sku
from core.utils import obtener_descripcion_maestra
from core.file_manager import archivar_procesado
from robots.Robot_Putty import validar_archivo_con_ia

_ANSI_RE = re.compile(
    r'\x1b'
    r'(?:'
    r'\[[0-9;?]*[A-Za-z]'
    r'|\([A-Z]'
    r'|[ABCDHIJKLMNOPQRST=>]'
    r'|\][^\x07]*\x07'
    r')'
)

def _limpiar_ansi(texto: str) -> str:
    """Elimina secuencias de control ANSI para leer texto limpio."""
    limpio = _ANSI_RE.sub('', texto)
    return re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', limpio)

class SSHSessionManager:
    """Gestiona la sesión SSH interactiva con Paramiko."""

    def __init__(self, host: str, port: int, user: str, password: str, trazador: Trazador):
        self.config = {'host': host, 'port': port, 'user': user, 'password': password}
        self.trazador = trazador
        self.client: Optional[paramiko.SSHClient] = None
        self.channel: Optional[paramiko.Channel] = None
        
        log_dir = Path(__file__).parent.parent / "logs" / "terminal"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_file = str(log_dir / f"debug_terminal_{int(time.time())}.txt")
        
        with open(self.transcript_file, "w", encoding="utf-8") as f:
            f.write("=== LOG DE TERMINAL SSH (PANTALLA LIMPIA) ===\n")

    def _log_terminal(self, direccion: str, texto: str):
        if not texto: return
        with open(self.transcript_file, "a", encoding="utf-8") as f:
            f.write(f"\n[{direccion}] {texto}\n")

    def connect(self):
        if not _PARAMIKO_OK:
            raise ImportError("La librería 'paramiko' es necesaria. Ejecutá: pip install paramiko")

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            hostname=self.config['host'], port=self.config['port'],
            username=self.config['user'], password=self.config['password'],
            timeout=20, look_for_keys=False, allow_agent=False,
        )
        self.channel = self.client.invoke_shell(term='xterm', width=189, height=49)
        self.trazador.registrar_posicion("Canal SSH interactivo abierto.")

    def disconnect(self):
        if self.channel: self.channel.close()
        if self.client: self.client.close()
        self.trazador.registrar_posicion("Conexión SSH cerrada.")

    def resolver_bloqueo_ia(self, screen: str) -> str:
        """Self-Healing: Consulta a la IA qué hacer ante un error o bloqueo del ERP legacy."""
        try:
            from core.utils import _groq_completar
            prompt = f"El ERP legacy por consola mostró esta pantalla:\n{screen[-1000:]}\n\n¿Qué tecla debe presionar el robot para volver atrás o confirmar el error y destrabarse? Responde UNA SOLA PALABRA de estas: ESC, ENTER, END, NADA."
            respuesta = _groq_completar(prompt).strip().upper()
            self.trazador.registrar_posicion(f"🤖 IA Self-Healing evaluó la pantalla. Decisión: {respuesta}")
            return respuesta
        except Exception as e:
            self._log_terminal("SELF_HEALING_ERR", str(e))
            return "ESC"

    def read_until(self, expected_prompts: list, timeout: int = 15, auto_heal: bool = True) -> str:
        """Lee del canal hasta encontrar uno de los prompts esperados."""
        screen = ""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.channel.recv_ready():
                chunk = self.channel.recv(4096).decode('latin-1', errors='ignore')
                screen += chunk
                screen_limpia = _limpiar_ansi(screen)
                for prompt in expected_prompts:
                    if prompt.lower() in screen_limpia.lower():
                        self._log_terminal("RECIBE", screen_limpia)
                        return screen_limpia
            time.sleep(0.1)
        self._log_terminal("TIMEOUT_RECIBE", _limpiar_ansi(screen))
        if auto_heal:
            self.trazador.registrar_posicion("⏳ Timeout detectado. Iniciando rutina Self-Healing...")
            accion = self.resolver_bloqueo_ia(_limpiar_ansi(screen))
            if "ESC" in accion:
                self.send('\x1b') # ESC
            elif "ENTER" in accion:
                self.send_enter()
            time.sleep(1.5)
            # Reintentar lectura tras intentar destrabar
            return self.read_until(expected_prompts, timeout=5, auto_heal=False)
        else:
            raise TimeoutError(f"Timeout esperando por prompts: {expected_prompts}. Última pantalla:\n{_limpiar_ansi(screen)[-500:]}")

    def send(self, command: str, interval: float = 0.04):
        """Envía un comando al canal simulando tipeo humano para no atragantar el sistema legacy."""
        # Sincronización Estricta (Anti-lock): Limpieza predictiva del buffer antes de interactuar
        if self.channel and self.channel.recv_ready():
            self.channel.recv(32768)
            
        self._log_terminal("ENVIA", repr(command))
        for char in command:
            self.channel.send(char)
            time.sleep(interval)

    def send_enter(self):
        self._log_terminal("TECLA", "ENTER")
        self.channel.send('\r')

    def send_f_key(self, key_num: int):
        f_keys = {1: '\x1bOP', 5: '\x1b[15~', 8: '\x1b[19~'}
        self._log_terminal("TECLA", f"F{key_num}")
        self.channel.send(f_keys.get(key_num, ''))

    def send_end(self):
        self._log_terminal("TECLA", "END")
        self.channel.send('\x1b[4~')


def ejecutar_stock_paramiko(df, log_func, progress_func, archivo_origen):
    """Robot de carga de stock usando Paramiko."""
    log_func(f"🔍 Validando archivo con IA antes de arrancar...")
    ok, resumen = validar_archivo_con_ia(df, log_func)
    log_func(f"  → {resumen}")
    if not ok:
        log_func("❌ El archivo tiene problemas críticos. Corregilo antes de ejecutar.")
        return

    trazador = Trazador("STOCK_PARAMIKO", archivo_origen, total_filas=len(df), log_func=log_func)
    trazador.iniciar()

    ssh: Optional[SSHSessionManager] = None
    try:
        with trazador.etapa("CONEXION", "Estableciendo conexión SSH directa"):
            ssh_config = get_ssh_config()
            ssh = SSHSessionManager(ssh_config.host, ssh_config.port, ssh_config.user, ssh_config.password, trazador)
            log_func(f"🕵️‍♂️ Generando transcript en: {ssh.transcript_file}")
            ssh.connect()
            ssh.read_until(["impresora", "elija", "m e n u", "menú"])

        with trazador.etapa("SKIP_IMPRESORAS", "Saltando popups de impresoras con 4 ENTERs"):
            for i in range(4):
                ssh.send_enter(); time.sleep(0.4)
            ssh.read_until(["principal", "menu", "m e n u", "sistema"])

        with trazador.etapa("NAVEGACION", "Navegando al módulo de stock (3 -> 6 -> 1)"):
            ssh.send('3'); time.sleep(0.5)
            ssh.send('6'); time.sleep(0.5)
            ssh.send('1'); time.sleep(0.5)
            ssh.send_enter(); time.sleep(0.8)

        with trazador.etapa("CABECERA", "Cargando Cabecera de Pedido"):
            id_pedido = str(int(float(df.iloc[0, 2])))
            obs = str(df.iloc[1, 2]).upper().strip()
            tipo_ingreso = str(df.iloc[2, 2]).upper().strip()

            ssh.send(id_pedido); ssh.send_enter(); time.sleep(0.8); ssh.send_enter()
            ssh.send(obs); ssh.send_enter(); time.sleep(0.5); ssh.send_enter()
            ssh.send(tipo_ingreso); ssh.send_enter(); time.sleep(1.2)
            ssh.send(id_pedido); ssh.send_enter(); time.sleep(0.5)

        # Detectar y saltar cabecera de 3 filas
        tiene_cabecera = False
        if len(df) > 0 and not str(df.iloc[0, 0]).strip().isdigit():
            tiene_cabecera = True
            
        df_datos = df.iloc[3:] if tiene_cabecera else df
        total_filas = len(df_datos)
        for i, fila in df_datos.iterrows():
            sku = _limpiar_sku(fila.iloc[0])
            try: cantidad = str(int(float(fila.iloc[1])))
            except Exception: continue
                
            dato_d = str(fila.iloc[3]).strip() if len(fila) > 3 else "nan"
            es_gramaje = dato_d.lower() not in ['nan', '', 'none']
            if not sku or sku.lower() in ("none", "nan", ""): continue

            desc_m = obtener_descripcion_maestra(sku)
            titulo_log = f"SKU {sku} — {desc_m[:25]} (+{cantidad} un.)" if desc_m else f"SKU {sku} (+{cantidad} un.)"
            with trazador.etapa("CARGA_ITEM", titulo_log, fila=i + 1, sku=sku):
                ssh.send(str(sku))
                for _ in range(4):
                    ssh.send_enter(); time.sleep(0.1)
                if es_gramaje:
                    ssh.send('g'); ssh.send(cantidad); ssh.send_enter()
                    ssh.send(dato_d); ssh.send_enter()
                else:
                    ssh.send('u'); ssh.send(cantidad); ssh.send_enter()

                if ssh.channel.recv_ready(): ssh.channel.recv(4096)
                if progress_func: progress_func((i + 1) / total_filas)

        with trazador.etapa("SALIDA", "Guardando y saliendo del módulo"):
            log_func("💾 Guardando documento (F5)...")
            time.sleep(1.0)
            trazador.registrar_posicion("Enviando F5")
            ssh.send_f_key(5); time.sleep(1.5)
            ssh.channel.send('\x1b[M'); time.sleep(3.0) # Failsafe F5
            
            for t in ['end', 'enter', 'end', 'end']:
                if t == 'end': ssh.send_end()
                else: ssh.send_enter()
                time.sleep(0.4)
            ssh.read_until(["principal", "menu", "m e n u", "sistema"], timeout=5)

        trazador.finalizar(Estado.OK)

    except Exception as e:
        log_func(f"🔥 Error en robot Paramiko: {e}")
        trazador.finalizar(Estado.ERROR)
    finally:
        if ssh: ssh.disconnect()
        if archivo_origen:
            archivar_procesado(
                ruta_archivo=archivo_origen,
                robot_nombre="STOCK_PARAMIKO",
                filas_procesadas=len(df),
                dry_run=False,
                log_func=log_func
            )