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


def _limpiar_ansi(texto: str) -> str:
    """Elimina secuencias de control ANSI para leer texto limpio."""
    return re.sub(r'\x1b\[[0-9;?]*[a-zA-Z]', '', texto)


class SSHSessionManager:
    """Gestiona la sesión SSH interactiva con Paramiko."""

    def __init__(self, host: str, port: int, user: str, password: str, trazador: Trazador):
        self.config = {'host': host, 'port': port, 'user': user, 'password': password}
        self.trazador = trazador
        self.client: Optional[paramiko.SSHClient] = None
        self.channel: Optional[paramiko.Channel] = None

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
        self.channel = self.client.invoke_shell(term='vt100', width=120, height=40)
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
                screen += self.channel.recv(4096).decode('latin-1', errors='ignore')
                screen_limpia = _limpiar_ansi(screen)
                for prompt in expected_prompts:
                    if prompt.lower() in screen_limpia.lower():
                        self.trazador.registrar_posicion(f"Prompt encontrado: '{prompt}'")
                        return screen_limpia
            time.sleep(0.1)
        raise TimeoutError(f"Timeout esperando por prompts: {expected_prompts}. Última pantalla:\n{_limpiar_ansi(screen)[-500:]}")

    def send(self, command: str):
        """Envía un comando al canal."""
        self.trazador.registrar_posicion(f"Enviando comando: {repr(command)}")
        self.channel.send(command)

    def send_enter(self):
        self.send('\n')

    def send_f_key(self, key_num: int):
        f_keys = {1: '\x1bOP', 5: '\x1b[15~', 8: '\x1b[19~'} # F1, F5, F8
        self.send(f_keys.get(key_num, ''))

    def send_esc(self):
        self.send('\x1b')


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
            ssh.connect()
            ssh.read_until(["login as:", "password:"])

        # 2. Skip impresoras
        with trazador.etapa("SKIP_IMPRESORAS", "Saltando popups de impresoras con 4 ENTERs"):
            for i in range(4):
                ssh.send_enter()
                time.sleep(0.4)
            ssh.read_until(["M E N U   P R I N C I P A L", "Menú Principal"])

        # 3. Navegación al módulo
        with trazador.etapa("NAVEGACION", "Navegando al módulo de precios (3 -> 4 -> 2)"):
            ssh.send('3'); ssh.read_until(["SISTEMA DE STOCK", "Stock"])
            ssh.send('4'); ssh.read_until(["PRECIOS", "Precios"])
            ssh.send('2'); ssh.read_until(["Artículo:", "Articulo:", "Código:"])

        # 4. Bucle de carga de datos
        total_filas = len(df)
        for i, row in df.iterrows():
            sku = _limpiar_sku(row.iloc[0])
            costo = _to_float(row.iloc[1])
            p_salon = _to_float(row.iloc[2])
            p_may = _to_float(row.iloc[3]) if len(row) > 3 else 0.0
            p_galpon = _to_float(row.iloc[4]) if len(row) > 4 else 0.0

            if not sku or p_salon is None:
                log_func(f"⚠️ Fila {i+1} saltada: SKU o Precio Salón inválido.")
                continue

            with trazador.etapa("CARGA_ITEM", f"SKU {sku}", fila=i + 1, sku=sku):
                # Ingresar SKU
                ssh.send(str(sku))
                ssh.send_enter()
                ssh.read_until(["Costo:", "COSTO"])

                # Ingresar Costo
                if costo is not None:
                    ssh.send(str(costo).replace('.', ','))
                ssh.send_enter()
                ssh.read_until(["Salón:", "SALON"])

                # Ingresar Precio Salón
                ssh.send(str(p_salon).replace('.', ','))
                ssh.send_enter()
                ssh.read_until(["Mayor:", "MAYOR"])

                # Ingresar Precio Mayorista
                if p_may is not None and p_may > 0:
                    ssh.send(str(p_may).replace('.', ','))
                ssh.send_enter()
                ssh.read_until(["Galpón:", "GALPON"])

                # Ingresar Precio Galpón
                if p_galpon is not None and p_galpon > 0:
                    ssh.send(str(p_galpon).replace('.', ','))
                ssh.send_enter()
                
                # El sistema puede requerir un ENTER extra para procesar el último campo
                time.sleep(0.2)
                ssh.send_enter()

                # Guardar
                trazador.registrar_posicion("Enviando F1 para guardar el artículo")
                ssh.send_f_key(1)
                ssh.read_until(["Confirma", "confirma", "seguro"])

                # Confirmar
                trazador.registrar_posicion("Confirmando guardado con 'S'")
                ssh.send('S')
                ssh.read_until(["Artículo:", "Articulo:", "Código:"]) # Esperar al siguiente

                if progress_func:
                    progress_func((i + 1) / total_filas)

        # 5. Salir del módulo
        with trazador.etapa("SALIDA", "Saliendo del módulo de precios con ESC"):
            ssh.send_esc()
            time.sleep(0.5)
            ssh.send_esc()
            ssh.read_until(["M E N U   P R I N C I P A L", "Menú Principal"])

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