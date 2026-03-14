"""
diagnostico_ssh.py — RPA Suite v5
===================================
Herramienta de diagnóstico para mapear la sesión SSH del robot de Precios.

Qué hace:
  - Conecta al servidor por SSH (sin tocar mouse ni teclado)
  - Navega la ruta de Precios paso a paso (3 → 4 → 2)
  - Captura TODO lo que manda el servidor después de cada acción
  - Limpia los caracteres ANSI (colores, cursores, escape codes)
  - Guarda un log estructurado en el Escritorio: diagnostico_ssh_YYYYMMDD_HHMMSS.txt
  - Genera un resumen de los textos clave encontrados en cada paso

Cómo usarlo:
  1. Corré este script directamente: python diagnostico_ssh.py
  2. Mirá el log generado en el Escritorio
  3. Pasale el log a Claude para construir el robot de Precios robusto

Modos disponibles:
  - MODO_INTERACTIVO: True  → para después de cada paso y te muestra la pantalla
  - MODO_INTERACTIVO: False → corre todo automático y guarda el log completo
"""

import paramiko
import time
import re
import os
import sys
import datetime
from pathlib import Path
from config import get_ssh_config   # ← credenciales desde .env (nunca hardcodeadas)

# ============================================================
# CONFIGURACIÓN
# ============================================================
# Las credenciales SSH vienen del .env via config.py.
# Para cambiar host/usuario/contraseña editá el .env, no este archivo.
_SSH = get_ssh_config()
HOST = _SSH.host
PORT = _SSH.port
USER = _SSH.user
PASS = _SSH.password

# Modo interactivo: pausa en cada paso esperando tu confirmación
# Poné False para que corra todo automático
MODO_INTERACTIVO = True

# Cuántos segundos esperar la respuesta del servidor en cada lectura
TIMEOUT_LECTURA = 12

# Escritorio del usuario actual
ESCRITORIO = Path(os.path.expanduser("~")) / "Desktop"
TIMESTAMP  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_PATH   = ESCRITORIO / f"diagnostico_ssh_{TIMESTAMP}.txt"


# ============================================================
# LIMPIADOR DE ANSI
# ============================================================
# El servidor manda secuencias como \x1b[1;32m (colores), \x1b[2J (limpiar pantalla),
# \x1b[H (mover cursor), etc. Las eliminamos para leer el texto limpio.
_ANSI_RE = re.compile(
    r'\x1b'
    r'(?:'
    r'\[[0-9;]*[A-Za-z]'       # CSI sequences: ESC [ ... letra
    r'|\([A-Z]'                 # G0/G1 charset: ESC ( A
    r'|[ABCDHIJKLMNOPQRST=>]'  # single char sequences
    r'|\][^\x07]*\x07'          # OSC: ESC ] ... BEL
    r')'
)

def limpiar_ansi(texto: str) -> str:
    """Elimina todos los escape codes ANSI del texto."""
    limpio = _ANSI_RE.sub('', texto)
    # Eliminar caracteres de control excepto newline y tab
    limpio = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', limpio)
    # Normalizar espacios múltiples pero preservar estructura
    lineas = limpio.split('\n')
    lineas = [l.rstrip() for l in lineas]
    # Eliminar líneas que son solo espacios o guiones repetidos (separadores)
    return '\n'.join(lineas)


def extraer_texto_util(raw: str) -> str:
    """
    Limpia ANSI y además elimina líneas completamente vacías repetidas,
    dejando el contenido legible de la pantalla.
    """
    limpio = limpiar_ansi(raw)
    lineas = limpio.split('\n')
    resultado = []
    linea_vacia_consecutiva = 0
    for l in lineas:
        if not l.strip():
            linea_vacia_consecutiva += 1
            if linea_vacia_consecutiva <= 2:
                resultado.append('')
        else:
            linea_vacia_consecutiva = 0
            resultado.append(l)
    return '\n'.join(resultado).strip()


# ============================================================
# LECTOR DE RESPUESTA DEL SERVIDOR
# ============================================================
def leer_respuesta(chan, timeout: float = TIMEOUT_LECTURA,
                   esperar_estabilidad: float = 1.5) -> tuple[str, str]:
    """
    Lee todo lo que manda el servidor hasta que deja de mandar datos.

    Estrategia:
      1. Espera hasta `timeout` segundos a que lleguen datos
      2. Una vez que empiezan a llegar, sigue leyendo mientras haya
      3. Si pasan `esperar_estabilidad` segundos sin datos nuevos → fin

    Returns:
      (raw, limpio) — el texto crudo y el texto limpio/legible
    """
    raw_total = b""
    deadline  = time.time() + timeout
    ultimo_dato = time.time()

    while time.time() < deadline:
        if chan.recv_ready():
            chunk = chan.recv(32768)
            if chunk:
                raw_total += chunk
                ultimo_dato = time.time()
                # Una vez que empezamos a recibir, reseteamos deadline más corto
                deadline = min(deadline, time.time() + timeout)
        else:
            # Si ya recibimos algo y pasó el tiempo de estabilidad → listo
            if raw_total and (time.time() - ultimo_dato) >= esperar_estabilidad:
                break
            time.sleep(0.1)

    raw_str   = raw_total.decode('latin-1', errors='replace')
    limpio    = extraer_texto_util(raw_str)
    return raw_str, limpio


# ============================================================
# LOGGER ESTRUCTURADO
# ============================================================
class Logger:
    def __init__(self, path: Path):
        self.path = path
        self.pasos = []
        path.parent.mkdir(parents=True, exist_ok=True)
        # Escribir encabezado
        self._escribir(f"""
╔══════════════════════════════════════════════════════════════════════════╗
║           DIAGNÓSTICO SSH — RPA Suite v5 · Robot de Precios              ║
╚══════════════════════════════════════════════════════════════════════════╝
Servidor  : {HOST}:{PORT}
Usuario   : {USER}
Iniciado  : {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
Log       : {path}
{'='*74}
""", modo='w')

    def _escribir(self, texto: str, modo: str = 'a'):
        with open(self.path, modo, encoding='utf-8') as f:
            f.write(texto + '\n')

    def paso(self, numero: int, accion: str, comando: str,
             respuesta_limpia: str, respuesta_raw: str,
             tiempo_seg: float, notas: str = ""):
        ts = datetime.datetime.now().strftime('%H:%M:%S')
        bloque = f"""
┌─ PASO {numero:02d} [{ts}] ─────────────────────────────────────────────────────┐
│ Acción   : {accion}
│ Comando  : {repr(comando)}
│ Tiempo   : {tiempo_seg:.2f}s
{('│ Notas    : ' + notas) if notas else ''}
├─ RESPUESTA DEL SERVIDOR (LIMPIA) ──────────────────────────────────────┤
{respuesta_limpia}
├─ RAW (primeros 500 chars) ─────────────────────────────────────────────┤
{repr(respuesta_raw[:500])}
└────────────────────────────────────────────────────────────────────────┘"""
        self._escribir(bloque)
        print(f"\n{'='*60}")
        print(f"PASO {numero:02d} | {accion}")
        print(f"{'─'*60}")
        # Mostrar solo las líneas con contenido
        lineas_utiles = [l for l in respuesta_limpia.split('\n') if l.strip()]
        for l in lineas_utiles[-20:]:  # últimas 20 líneas
            print(f"  {l}")
        self.pasos.append({
            'numero': numero, 'accion': accion,
            'comando': comando, 'tiempo': tiempo_seg,
            'respuesta': respuesta_limpia,
        })

    def resumen(self, exito: bool, notas_finales: str = ""):
        total_pasos = len(self.pasos)
        total_tiempo = sum(p['tiempo'] for p in self.pasos)

        # Buscar palabras clave en las respuestas para el resumen
        keywords_encontrados = {}
        palabras_clave = [
            'impresora', 'printer', 'fecha', 'date', 'error', 'stock',
            'precio', 'módulo', 'modulo', 'canal', 'sucursal', 'ok',
            'incorrecto', 'inválido', 'sesión', 'session', 'usuario',
            'clave', 'acceso', 'ingrese', 'seleccione', 'artículo', 'sku',
        ]
        for p in self.pasos:
            resp_lower = p['respuesta'].lower()
            encontrados = [kw for kw in palabras_clave if kw in resp_lower]
            if encontrados:
                keywords_encontrados[f"Paso {p['numero']:02d} — {p['accion']}"] = encontrados

        bloque = f"""
{'='*74}
RESUMEN DEL DIAGNÓSTICO
{'='*74}
Estado     : {'✅ COMPLETADO' if exito else '❌ FALLÓ'}
Pasos      : {total_pasos}
Tiempo total: {total_tiempo:.1f}s
{notas_finales}

PALABRAS CLAVE DETECTADAS POR PASO:
"""
        for paso_label, kws in keywords_encontrados.items():
            bloque += f"  {paso_label}: {', '.join(kws)}\n"

        bloque += f"""
PRÓXIMOS PASOS:
  1. Compartí este archivo con Claude para construir el robot robusto
  2. Prestá atención a los pasos donde aparece "impresora", "popup" o "fecha"
  3. Cualquier texto inesperado en las respuestas es un popup a manejar

Archivo: {self.path}
{'='*74}
"""
        self._escribir(bloque)
        print(bloque)


# ============================================================
# PAUSA INTERACTIVA
# ============================================================
def pausar(mensaje: str = ""):
    if not MODO_INTERACTIVO:
        return
    print(f"\n{'─'*60}")
    print(f"⏸  PAUSA INTERACTIVA{': ' + mensaje if mensaje else ''}")
    print("  Revisá la pantalla arriba y presioná ENTER para continuar")
    print("  (o escribí 'stop' y ENTER para detener el diagnóstico)")
    resp = input("  > ").strip().lower()
    if resp == 'stop':
        print("\n🛑 Diagnóstico detenido por el usuario.")
        sys.exit(0)


# ============================================================
# DIAGNÓSTICO PRINCIPAL
# ============================================================
def ejecutar_diagnostico():
    log = Logger(LOG_PATH)
    print(f"\n🔍 DIAGNÓSTICO SSH — Robot de Precios")
    print(f"   Servidor : {HOST}:{PORT}")
    print(f"   Log      : {LOG_PATH}")
    print(f"   Modo     : {'INTERACTIVO (pausa en cada paso)' if MODO_INTERACTIVO else 'AUTOMÁTICO'}")
    print(f"{'='*60}\n")

    client = None
    chan   = None
    paso   = 0

    try:
        # ── PASO 0: Conexión ──────────────────────────────────
        paso += 1
        print(f"📡 Conectando a {HOST}:{PORT}...")
        t0 = time.time()

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            HOST, port=PORT,
            username=USER, password=PASS,
            timeout=20,
            look_for_keys=False,
            allow_agent=False,
        )

        # Abrir shell interactivo con el mismo PTY que usa el robot SSH actual
        chan = client.get_transport().open_session()
        chan.get_pty(term='xterm', width=220, height=50)
        chan.invoke_shell()

        t_conn = time.time() - t0
        raw, limpio = leer_respuesta(chan, timeout=5, esperar_estabilidad=1.0)
        log.paso(paso, "CONEXIÓN SSH", f"connect({HOST}:{PORT})",
                 limpio, raw, t_conn,
                 notas="Pantalla inicial del sistema al conectar")
        pausar("¿Qué ves en la pantalla inicial?")

        # ── PASO 1: Limpieza de impresoras (4 ENTERs) ─────────
        paso += 1
        print("\n📠 Enviando 4 ENTERs para limpiar solicitud de impresoras...")
        t0 = time.time()
        for n in range(4):
            chan.send('\n')
            time.sleep(0.6)
            # Leer respuesta intermedia de cada ENTER
            if chan.recv_ready():
                parcial = chan.recv(4096).decode('latin-1', errors='replace')
                print(f"   ENTER {n+1}/4 → {repr(limpiar_ansi(parcial)[:80])}")

        raw, limpio = leer_respuesta(chan, timeout=5, esperar_estabilidad=1.5)
        log.paso(paso, "LIMPIEZA IMPRESORAS (4 ENTERs)", "\\n × 4",
                 limpio, raw, time.time() - t0,
                 notas="Después de los 4 ENTERs iniciales. ¿Llegó al menú principal?")
        pausar("¿Estamos en el menú principal?")

        # ── PASO 2: Navegar → Menú 3 ──────────────────────────
        paso += 1
        t0 = time.time()
        print("\n📂 Enviando '3' (primer nivel del menú)...")
        chan.send('3')
        raw, limpio = leer_respuesta(chan, timeout=6, esperar_estabilidad=1.5)
        log.paso(paso, "MENÚ NIVEL 1 → '3'", "3",
                 limpio, raw, time.time() - t0,
                 notas="¿Abrió el submenú de nivel 2?")
        pausar("¿Qué submenú apareció?")

        # ── PASO 3: Navegar → Submenú 4 ───────────────────────
        paso += 1
        t0 = time.time()
        print("\n📂 Enviando '4' (segundo nivel)...")
        chan.send('4')
        raw, limpio = leer_respuesta(chan, timeout=6, esperar_estabilidad=1.5)
        log.paso(paso, "MENÚ NIVEL 2 → '4'", "4",
                 limpio, raw, time.time() - t0,
                 notas="¿Abrió el submenú de precios?")
        pausar("¿Qué submenú apareció?")

        # ── PASO 4: Navegar → Módulo 2 ────────────────────────
        paso += 1
        t0 = time.time()
        print("\n📂 Enviando '2' (módulo de precios)...")
        chan.send('2')
        raw, limpio = leer_respuesta(chan, timeout=8, esperar_estabilidad=2.0)
        log.paso(paso, "MÓDULO PRECIOS → '2'", "2",
                 limpio, raw, time.time() - t0,
                 notas="Primer campo del módulo de precios. ¿Qué pide?")
        pausar("¿Qué aparece en pantalla? ¿Pide algún dato?")

        # ── PASO 5: ENTER inicial (si pide confirmación) ──────
        paso += 1
        t0 = time.time()
        print("\n↩  Enviando ENTER (posible confirmación inicial del módulo)...")
        chan.send('\n')
        raw, limpio = leer_respuesta(chan, timeout=6, esperar_estabilidad=1.5)
        log.paso(paso, "ENTER inicial módulo", "\\n",
                 limpio, raw, time.time() - t0,
                 notas="¿Cambió la pantalla? ¿Qué campo aparece ahora?")
        pausar("¿Qué cambió?")

        # ── PASO 6: Detectar popups / campos extra ─────────────
        # Mandamos un ENTER a ciegas para ver si hay algún popup
        paso += 1
        t0 = time.time()
        print("\n🔍 Enviando ENTER de exploración (detectar popups)...")
        chan.send('\n')
        raw, limpio = leer_respuesta(chan, timeout=6, esperar_estabilidad=1.5)
        log.paso(paso, "ENTER exploración popup", "\\n",
                 limpio, raw, time.time() - t0,
                 notas="¿Apareció algún popup inesperado? ¿Cambió la pantalla?")
        pausar("¿Hay algún popup o cartel visible?")

        # ── PASO 7: SKU de prueba (sin confirmar) ─────────────
        SKU_TEST = "00001"   # SKU inventado solo para ver qué pide el campo
        paso += 1
        t0 = time.time()
        print(f"\n🧪 Enviando SKU de prueba '{SKU_TEST}' para ver estructura del formulario...")
        chan.send(SKU_TEST)
        raw, limpio = leer_respuesta(chan, timeout=6, esperar_estabilidad=1.5)
        log.paso(paso, f"SKU TEST '{SKU_TEST}' (sin ENTER)", SKU_TEST,
                 limpio, raw, time.time() - t0,
                 notas="¿Qué aparece mientras escribimos el SKU? ¿Autocompletado?")
        pausar("¿Qué cambió al escribir el SKU?")

        # ── PASO 8: ENTER sobre el SKU ────────────────────────
        paso += 1
        t0 = time.time()
        print("\n↩  ENTER sobre el SKU de prueba...")
        chan.send('\n')
        raw, limpio = leer_respuesta(chan, timeout=8, esperar_estabilidad=2.0)
        log.paso(paso, "ENTER sobre SKU test", "\\n",
                 limpio, raw, time.time() - t0,
                 notas="¿Cargó el artículo? ¿Cuántos ENTERs necesita para llegar a Costo?")
        pausar("¿Qué campos aparecen ahora?")

        # ── PASO 9: Navegar campos con ENTERs ─────────────────
        print("\n🔍 Enviando 6 ENTERs para mapear los campos del formulario...")
        for n in range(6):
            paso += 1
            t0 = time.time()
            chan.send('\n')
            raw, limpio = leer_respuesta(chan, timeout=4, esperar_estabilidad=0.8)
            log.paso(paso, f"ENTER de navegación {n+1}/6", "\\n",
                     limpio, raw, time.time() - t0,
                     notas=f"Mapeo de campo {n+1}")
            if MODO_INTERACTIVO and n == 0:
                pausar(f"ENTER {n+1}/6 — ¿en qué campo estamos?")

        # ── PASO FINAL: ESC para salir sin guardar ─────────────
        paso += 1
        t0 = time.time()
        print("\n🚪 Enviando ESC + F8 para salir sin guardar (no modificamos nada)...")
        chan.send('\x1b')      # ESC
        time.sleep(0.5)
        chan.send('\x1b[19~')  # F8
        time.sleep(0.5)
        chan.send('\n')        # ENTER de confirmación si pide
        raw, limpio = leer_respuesta(chan, timeout=5, esperar_estabilidad=1.0)
        log.paso(paso, "SALIDA SEGURA (ESC + F8)", "ESC + F8",
                 limpio, raw, time.time() - t0,
                 notas="Salida sin guardar cambios. ¿Volvió al menú?")

        # ── Cerrar sesión limpiamente ──────────────────────────
        paso += 1
        t0 = time.time()
        print("\n🔌 Cerrando sesión SSH...")
        try:
            chan.send('exit\n')
            time.sleep(1)
        except Exception:
            pass
        chan.close()
        client.close()
        log.paso(paso, "CIERRE SESIÓN SSH", "exit",
                 "Sesión cerrada correctamente", "", time.time() - t0)

        log.resumen(
            exito=True,
            notas_finales=(
                "DIAGNÓSTICO COMPLETADO.\n"
                "Compartí el archivo de log con Claude para construir el robot robusto.\n"
                "Especialmente los PASOS donde aparecen palabras como:\n"
                "  'impresora', 'popup', 'fecha', 'campo', 'costo', 'precio'\n"
            )
        )

        print(f"\n✅ Diagnóstico finalizado.")
        print(f"📄 Log guardado en: {LOG_PATH}")
        print(f"\n💡 Próximo paso: abrí el archivo de log y compartilo con Claude.")

    except KeyboardInterrupt:
        print("\n\n⚠️  Diagnóstico interrumpido por el usuario.")
        log.resumen(exito=False, notas_finales="Interrumpido con Ctrl+C")
        _cerrar_seguro(chan, client)

    except paramiko.AuthenticationException:
        msg = f"❌ Error de autenticación. Verificá usuario/contraseña."
        print(f"\n{msg}")
        log._escribir(f"\n{msg}\n")

    except paramiko.SSHException as e:
        msg = f"❌ Error SSH: {e}"
        print(f"\n{msg}")
        log._escribir(f"\n{msg}\n")
        _cerrar_seguro(chan, client)

    except Exception as e:
        import traceback
        msg = f"❌ Error inesperado en paso {paso}: {e}\n{traceback.format_exc()}"
        print(f"\n{msg}")
        log._escribir(f"\n{msg}\n")
        log.resumen(exito=False, notas_finales=f"Error en paso {paso}: {e}")
        _cerrar_seguro(chan, client)


def _cerrar_seguro(chan, client):
    """Cierra la sesión SSH limpiamente aunque haya fallado."""
    try:
        if chan and not chan.closed:
            chan.send('\x1b')   # ESC
            time.sleep(0.3)
            chan.send('exit\n')
            time.sleep(0.5)
            chan.close()
    except Exception:
        pass
    try:
        if client:
            client.close()
    except Exception:
        pass
    print("🔌 Sesión SSH cerrada.")


# ============================================================
# EJECUCIÓN DIRECTA
# ============================================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  DIAGNÓSTICO SSH — RPA Suite v5")
    print("  Robot de Precios — Sesión de Mapeo")
    print("="*60)
    print(f"\n  Servidor : {HOST}:{PORT}")
    print(f"  Usuario  : {USER}")
    print(f"  Log      : {LOG_PATH}")
    print(f"  Modo     : {'INTERACTIVO' if MODO_INTERACTIVO else 'AUTOMÁTICO'}")
    print("\n  ⚠️  Este script NO modifica nada en el servidor.")
    print("  Solo observa y registra. Sale con ESC sin guardar.")
    print("\n  Para cambiar a modo automático: MODO_INTERACTIVO = False")
    print("  Para detener durante la ejecución: Ctrl+C\n")

    if MODO_INTERACTIVO:
        resp = input("  ¿Arrancamos? (ENTER para sí / 'n' para cancelar): ").strip().lower()
        if resp == 'n':
            print("  Cancelado.")
            sys.exit(0)

    ejecutar_diagnostico()