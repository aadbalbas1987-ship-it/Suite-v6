"""
robots/Precios_Paramiko.py — RPA Suite v6.0
===========================================
Clon del robot de precios, migrado a Paramiko para operación "backdoor".

Características:
  - Conexión directa por SSH, sin PyAutoGUI.
  - Login y salto de impresoras automático.
  - Navegación y carga de datos por comandos de texto.
  - Trazador de diagnóstico integrado para generar reportes detallados.
"""

import time
import re
from typing import Optional, Callable

try:
    import paramiko
    _PARAMIKO_OK = True
except ImportError:
    _PARAMIKO_OK = False

from config import get_ssh_config
from core.trazabilidad import Trazador, Estado
from core.pre_validador import _limpiar_sku, _to_float
from core.utils import f_monto
from core.file_manager import archivar_procesado


def _cargar_hijos() -> set:
    from pathlib import Path
    _robot_dir = Path(__file__).parent
    _root_dir  = _robot_dir.parent
    candidatos = [_root_dir / "hijos.txt", _robot_dir / "hijos.txt", Path("hijos.txt")]
    for ruta in candidatos:
        if ruta.exists():
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    return {line.strip() for line in f if line.strip()}
            except Exception:
                pass
    return set()

# Expresión regular avanzada para limpiar TODO el ruido de la terminal
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
        
        # -- Creador del Archivo Transcript (Caja Negra) --
        self.transcript_file = f"debug_terminal_{int(time.time())}.txt"
        with open(self.transcript_file, "w", encoding="utf-8") as f:
            f.write("=== LOG DE TERMINAL SSH (PANTALLA LIMPIA) ===\n")

    def _log_terminal(self, direccion: str, texto: str):
        if not texto: return
        with open(self.transcript_file, "a", encoding="utf-8") as f:
            f.write(f"\n[{direccion}] {texto}\n")

    def connect(self):
        """Establece la conexión y abre un shell interactivo."""
        if not _PARAMIKO_OK:
            raise ImportError("La librería 'paramiko' es necesaria. Ejecutá: pip install paramiko")

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            hostname=self.config['host'],
            port=self.config['port'],
            username=self.config['user'],
            password=self.config['password'],
            timeout=20,
            look_for_keys=False,
            allow_agent=False,
        )
        # Usamos xterm para que el servidor reconozca correctamente la tecla F5
        self.channel = self.client.invoke_shell(term='xterm', width=189, height=49)
        self.trazador.registrar_posicion("Canal SSH interactivo abierto.")

    def disconnect(self):
        """Cierra la conexión SSH."""
        if self.channel:
            self.channel.close()
        if self.client:
            self.client.close()
        self.trazador.registrar_posicion("Conexión SSH cerrada.")

    def read_until(self, expected_prompts: list, timeout: int = 15) -> str:
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
                        self.trazador.registrar_posicion(f"Prompt encontrado: '{prompt}'")
                        self._log_terminal("RECIBE", screen_limpia)
                        return screen_limpia
            time.sleep(0.1)
        self._log_terminal("TIMEOUT_RECIBE", _limpiar_ansi(screen))
        raise TimeoutError(f"Timeout esperando por prompts: {expected_prompts}. Última pantalla:\n{_limpiar_ansi(screen)[-500:]}")

    def read_all(self, timeout: float = 1.5) -> str:
        """Lee todo el contenido actual del buffer (captura de pantalla SSH)."""
        screen = ""
        start = time.time()
        while time.time() - start < timeout:
            if self.channel.recv_ready():
                chunk = self.channel.recv(32768).decode('latin-1', errors='ignore')
                screen += chunk
                start = time.time()  # extender si sigue llegando info
            time.sleep(0.1)
        if screen:
            self._log_terminal("RECIBE", _limpiar_ansi(screen))
        return screen

    def send(self, command: str, interval: float = 0.04):
        """Envía un comando al canal simulando tipeo humano para no atragantar el sistema legacy."""
        self.trazador.registrar_posicion(f"Enviando comando: {repr(command)}")
        self._log_terminal("ENVIA", repr(command))
        for char in command:
            self.channel.send(char)
            time.sleep(interval)

    def send_enter(self):
        self.trazador.registrar_posicion("Tecla: ENTER")
        self._log_terminal("TECLA", "ENTER")
        self.channel.send('\r')

    def send_f_key(self, key_num: int):
        f_keys = {1: '\x1bOP', 5: '\x1b[15~', 8: '\x1b[19~'} # F1, F5, F8
        self.trazador.registrar_posicion(f"Tecla: F{key_num}")
        self._log_terminal("TECLA", f"F{key_num}")
        self.channel.send(f_keys.get(key_num, ''))

    def send_esc(self):
        self.trazador.registrar_posicion("Tecla: ESC")
        self._log_terminal("TECLA", "ESC")
        self.channel.send('\x1b')

    def send_end(self):
        """Envía la tecla End (Fin) usando la secuencia ANSI de terminal."""
        self.trazador.registrar_posicion("Tecla: END")
        self._log_terminal("TECLA", "END")
        self.channel.send('\x1b[4~')


def ejecutar_precios_paramiko(df, log_func, progress_func, archivo_origen):
    """
    Robot de carga de precios usando Paramiko.
    """
    trazador = Trazador("PRECIOS_PARAMIKO", archivo_origen, total_filas=len(df), log_func=log_func)
    trazador.iniciar()

    ssh: Optional[SSHSessionManager] = None
    try:
        # 1. Conexión
        with trazador.etapa("CONEXION", "Estableciendo conexión SSH directa"):
            ssh_config = get_ssh_config()
            ssh = SSHSessionManager(ssh_config.host, ssh_config.port, ssh_config.user, ssh_config.password, trazador)
            log_func(f"🕵️‍♂️ Generando transcript en: {ssh.transcript_file}")
            ssh.connect()
            # Paramiko ya gestiona el login automático. Esperamos a que cargue el sistema.
            ssh.read_until(["impresora", "elija", "m e n u", "menú"])

        # 2. Skip impresoras
        with trazador.etapa("SKIP_IMPRESORAS", "Saltando popups de impresoras con 4 ENTERs"):
            for i in range(4):
                ssh.send_enter()
                time.sleep(0.4)
            pant_menu = ssh.read_until(["principal", "menu", "m e n u", "sistema"])
            trazador.registrar_posicion(f"👀 Pantalla post-impresoras: {pant_menu[-100:].replace(chr(10), ' ❯ ')}")

        # 3. Navegación al módulo
        with trazador.etapa("NAVEGACION", "Navegando al módulo de precios (3 -> 4 -> 2)"):
            ssh.send('3'); p1 = ssh.read_until(["stock", "inventario", "sistema"])
            trazador.registrar_posicion(f"👀 Menú 1: {p1[-80:].replace(chr(10), ' ❯ ')}")
            time.sleep(0.5) # Respiro al sistema
            
            ssh.send('4'); p2 = ssh.read_until(["precios", "lista", "actualizacion"])
            trazador.registrar_posicion(f"👀 Menú 2: {p2[-80:].replace(chr(10), ' ❯ ')}")
            time.sleep(0.5) # Respiro al sistema
            
            ssh.send('2'); p3 = ssh.read_until(["artículo", "articulo", "código", "codigo", "sku"])
            trazador.registrar_posicion(f"👀 Módulo Precios: {p3[-80:].replace(chr(10), ' ❯ ')}")
            time.sleep(1.5) # TIEMPO CLAVE: Esperar que el formulario pesado termine de dibujarse

        # 4. Bucle de carga de datos
        total_filas = len(df)
        listado_hijos = _cargar_hijos()

        for i, row in df.iterrows():
            sku = _limpiar_sku(row.iloc[0])
            costo = f_monto(row.iloc[1]).replace('.', ',')
            p_salon = f_monto(row.iloc[2]).replace('.', ',')
            p_may = f_monto(row.iloc[3]).replace('.', ',') if len(row) > 3 else ""
            
            p_galpon_raw = str(row.iloc[4]).strip() if len(row) > 4 else ""
            tiene_galpon = p_galpon_raw.lower() not in ('0.00', '0', '', 'nan', 'none')
            p_galpon = f_monto(row.iloc[4]).replace('.', ',') if tiene_galpon and len(row) > 4 else ""

            if not sku or not p_salon:
                log_func(f"⚠️ Fila {i+1} saltada: SKU o Precio Salón inválido.")
                continue
                
            es_hijo = sku in listado_hijos
            enters_ini = 6 if es_hijo else 5

            with trazador.etapa("CARGA_ITEM", f"SKU {sku}", fila=i + 1, sku=sku):

                # A. SKU + ENTERs de posicionamiento en Costo
                ssh.send(str(sku))
                for _ in range(enters_ini):
                    ssh.send_enter()
                    time.sleep(0.1)
                time.sleep(0.2)

                # B. Costo + 3 ENTERs
                if costo:
                    ssh.send(costo)
                for _ in range(3):
                    ssh.send_enter()
                    time.sleep(0.1)

                # C. Precio Salon
                if p_salon:
                    ssh.send(p_salon)

                # D. Lógica condicional de saltos
                if tiene_galpon:
                    for _ in range(2): 
                        ssh.send_enter()
                        time.sleep(0.1)
                    if p_galpon: ssh.send(p_galpon)
                    ssh.send_enter()
                    if p_may: ssh.send(p_may)
                    ssh.send_enter()
                    ssh.send('G')
                else:
                    for _ in range(3): 
                        ssh.send_enter()
                        time.sleep(0.1)
                    if p_may: ssh.send(p_may)
                    ssh.send_enter()
                    ssh.send('N')
                
                # E. Guardar fila
                ssh.send_enter()
                time.sleep(0.5)
                
                # Limpiar cualquier residuo de red antes de guardar
                if ssh.channel.recv_ready():
                    ssh.channel.recv(4096)
                    
                trazador.registrar_posicion("Enviando F5 para guardar el artículo")
                ssh.send_f_key(5)
                time.sleep(1.5)

                # Vaciar buffer de lectura para estar limpios en el próximo SKU
                if ssh.channel.recv_ready():
                    ssh.channel.recv(4096)

                if progress_func:
                    progress_func((i + 1) / total_filas)

        # 5. Salir del módulo
        with trazador.etapa("SALIDA", "Esperando 1s y saliendo del módulo con END"):
            log_func("⏳ Fin de lote. Esperando 1s para confirmar que no hay más datos...")
            time.sleep(1.0)
            
            # Salir con ráfaga de teclas END (como el robot original)
            for _ in range(4):
                ssh.send_end()
                time.sleep(0.4)
            ssh.read_until(["principal", "menu", "m e n u", "sistema"], timeout=5)

        trazador.finalizar(Estado.OK)

    except (ImportError, ModuleNotFoundError) as e:
        log_func(f"❌ Error de dependencia: {e}. Asegurate de tener 'paramiko' instalado.")
        trazador.finalizar(Estado.ERROR)
    except TimeoutError as e:
        log_func(f"🔥 Timeout: El sistema no respondió a tiempo. {e}")
        trazador.finalizar(Estado.ERROR)
    except Exception as e:
        log_func(f"🔥 Error crítico en robot Paramiko: {e}")
        trazador.finalizar(Estado.ERROR)
    finally:
        if ssh:
            ssh.disconnect()
            
    # Archivar Excel para que no quede en input/
    if archivo_origen:
        archivar_procesado(
            ruta_archivo=archivo_origen,
            robot_nombre="PRECIOS_PARAMIKO",
            filas_procesadas=len(df),
            dry_run=False,
            log_func=log_func
        )


if __name__ == '__main__':
    # Ejemplo de ejecución directa para testing
    import pandas as pd

    print("Ejecutando test del robot de precios con Paramiko...")

    # Crear un DataFrame de ejemplo
    data = {
        'SKU': ['1001', '1002'],
        'Costo': [150.50, 200.00],
        'P. Salon': [250.00, 320.50],
        'P. Mayorista': [230.00, 300.00],
        'P. Galpon': [220.00, 290.00]
    }
    df_test = pd.DataFrame(data)

    def log_consola(msg):
        print(msg)

    ejecutar_precios_paramiko(
        df=df_test,
        log_func=log_consola,
        progress_func=lambda p: print(f"Progreso: {p:.0%}"),
        archivo_origen="test_directo.xlsx"
    )
    print("Test finalizado.")