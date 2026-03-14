"""
╔══════════════════════════════════════════════════════════════╗
║          ROBOT PUTTY UXB — Cargador Automático              ║
║  Lee el archivo exportado por Robot UXB y carga en Putty    ║
║                                                              ║
║  PRE-REQUISITO: Putty ya abierto y en menú 3-3-2            ║
║  ARCHIVO: El .txt exportado por la app web (Parte 1)        ║
╚══════════════════════════════════════════════════════════════╝

FLUJO POR PRODUCTO:
  1. Pegar código de artículo → Enter x2
  2. Pegar UXB nuevo → F5
  3. Escribir "arreglo de UXB" → F5
  4. Siguiente producto (mismo menú 3-3-2)

AL FINALIZAR:
  End + Enter + End x2 (volver menú principal)

INSTALACIÓN (ejecutar 1 sola vez):
  pip install pyautogui pyperclip

USO:
  python uxb_putty_robot.py --file uxb_aprobados_XXXXX.txt
  python uxb_putty_robot.py --file uxb_aprobados_XXXXX.txt --delay 0.8
  python uxb_putty_robot.py --file uxb_aprobados_XXXXX.txt --dry-run
"""

import sys
import time
import argparse
import pyautogui
import pyperclip
from datetime import datetime

# ─── CONFIGURACIÓN ───────────────────────────────────────────
DELAY_BETWEEN_ACTIONS = 0.5   # segundos entre acciones (ajustable)
DELAY_BETWEEN_PRODUCTS = 1.0  # segundos entre productos
MOTIVO = "arreglo de UXB"     # texto del motivo de novedad
COUNTDOWN_SECONDS = 5         # cuenta regresiva antes de arrancar

# ─── COLORES PARA CONSOLA ────────────────────────────────────
GREEN  = '\033[92m'
YELLOW = '\033[93m'
RED    = '\033[91m'
CYAN   = '\033[96m'
RESET  = '\033[0m'
BOLD   = '\033[1m'

def log(msg, color=RESET):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"{color}[{ts}] {msg}{RESET}")

def banner():
    print(f"""{CYAN}{BOLD}
╔══════════════════════════════════════════════════════════╗
║         ROBOT PUTTY UXB — Cargador Automático           ║
╚══════════════════════════════════════════════════════════╝{RESET}""")

# ─── LEER ARCHIVO EXPORTADO ──────────────────────────────────
def load_products(filepath):
    products = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                code = parts[0].strip()
                try:
                    uxb  = int(parts[1].strip())
                    if code and uxb > 0:
                        products.append({'code': code, 'uxb': uxb})
                except ValueError:
                    log(f"Línea ignorada (UXB no numérico): {line}", YELLOW)
    return products

# ─── ACCIÓN PUTTY: PEGAR TEXTO ───────────────────────────────
def paste_text(text, delay):
    """Copia al portapapeles y pega con Ctrl+V en Putty."""
    pyperclip.copy(str(text))
    time.sleep(delay * 0.5)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(delay)

def press_key(key, delay):
    pyautogui.press(key)
    time.sleep(delay)

def press_keys(*keys, delay):
    """Presiona múltiples teclas en secuencia."""
    for key in keys:
        pyautogui.press(key)
        time.sleep(delay * 0.4)

# ─── CARGAR UN PRODUCTO EN PUTTY ─────────────────────────────
def load_product(code, uxb, delay, dry_run=False):
    """
    Secuencia:
      [pegar código] → Enter → Enter → [pegar UXB] → F5 → [pegar motivo] → F5
    """
    if dry_run:
        log(f"  [DRY-RUN] Código: {code} → UXB: {uxb}", CYAN)
        return

    # 1. Pegar código de artículo
    paste_text(code, delay)

    # 2. Enter x2 (confirmar código, pasar al campo UXB)
    press_key('enter', delay)
    press_key('enter', delay)

    # 3. Pegar UXB nuevo
    paste_text(uxb, delay)

    # 4. F5 (confirmar UXB / pasar a motivo)
    press_key('f5', delay)

    # 5. Escribir motivo de novedad
    paste_text(MOTIVO, delay)

    # 6. F5 (confirmar y guardar)
    press_key('f5', delay)

# ─── SALIR AL MENÚ PRINCIPAL ─────────────────────────────────
def exit_to_main_menu(delay, dry_run=False):
    """
    End + Enter + End x2
    """
    if dry_run:
        log("[DRY-RUN] Saliendo al menú principal: End → Enter → End → End", CYAN)
        return

    log("Saliendo al menú principal...", YELLOW)
    press_key('end', delay)
    press_key('enter', delay)
    press_key('end', delay)
    time.sleep(delay * 0.5)
    press_key('end', delay)

# ─── CUENTA REGRESIVA ────────────────────────────────────────
def countdown(seconds):
    print()
    for i in range(seconds, 0, -1):
        print(f"\r{YELLOW}{BOLD}  Arrancando en {i}...  (Ctrl+C para cancelar){RESET}", end='', flush=True)
        time.sleep(1)
    print(f"\r{GREEN}{BOLD}  ¡Arrancando ahora!                           {RESET}")
    print()

# ─── MAIN ────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='Robot Putty UXB - Carga automática de UXB en sistema'
    )
    parser.add_argument('--file',    required=True,  help='Archivo exportado por Robot UXB (.txt)')
    parser.add_argument('--delay',   type=float, default=DELAY_BETWEEN_ACTIONS, help='Delay entre acciones en segundos (default: 0.5)')
    parser.add_argument('--delay-product', type=float, default=DELAY_BETWEEN_PRODUCTS, help='Delay entre productos (default: 1.0)')
    parser.add_argument('--dry-run', action='store_true', help='Simular sin tocar Putty')
    parser.add_argument('--start',   type=int, default=1, help='Nro de producto donde arrancar (default: 1)')
    parser.add_argument('--limit',   type=int, default=None, help='Máximo de productos a cargar')
    args = parser.parse_args()

    banner()

    # Cargar archivo
    log(f"Cargando archivo: {args.file}", CYAN)
    try:
        products = load_products(args.file)
    except FileNotFoundError:
        log(f"ERROR: No se encontró el archivo '{args.file}'", RED)
        sys.exit(1)

    if not products:
        log("ERROR: El archivo no tiene productos válidos.", RED)
        sys.exit(1)

    # Aplicar --start y --limit
    start_idx = max(0, args.start - 1)
    products = products[start_idx:]
    if args.limit:
        products = products[:args.limit]

    total = len(products)
    log(f"Productos a cargar: {total}", GREEN)
    log(f"Delay por acción: {args.delay}s | Delay entre productos: {args.delay_product}s", CYAN)

    if args.dry_run:
        log("MODO DRY-RUN activo — no se tocará Putty", YELLOW)
    else:
        print(f"""
{YELLOW}{BOLD}  IMPORTANTE ANTES DE CONTINUAR:
  ─────────────────────────────────────────
  1. Putty debe estar ABIERTO y ENFOCADO
  2. Debés estar en el menú 3-3-2
  3. NO muevas el mouse ni teclado mientras corre
  4. Para pausar/detener: presioná Ctrl+C
  ─────────────────────────────────────────{RESET}""")
        input(f"\n{GREEN}  Presioná ENTER cuando Putty esté listo...{RESET}")
        countdown(COUNTDOWN_SECONDS)

    # ─── LOOP DE CARGA ───
    ok = 0
    errors = 0
    log(f"Iniciando carga de {total} productos...\n", GREEN)

    for i, prod in enumerate(products, 1):
        code = prod['code']
        uxb  = prod['uxb']

        log(f"[{i:4d}/{total}] Código: {code:>8} → UXB: {uxb}")

        try:
            load_product(code, uxb, args.delay, args.dry_run)
            ok += 1
            time.sleep(args.delay_product)

        except pyautogui.FailSafeException:
            log(f"\n{RED}¡DETENIDO! Esquina de pantalla activada (failsafe).{RESET}", RED)
            log(f"Progreso: {ok} cargados, {errors} errores, {total-i} restantes", YELLOW)
            break

        except KeyboardInterrupt:
            log(f"\n¡DETENIDO por el usuario!", YELLOW)
            log(f"Progreso: {ok} cargados, {errors} errores, {total-i} restantes", YELLOW)
            break

        except Exception as e:
            errors += 1
            log(f"  ERROR en {code}: {e}", RED)
            time.sleep(args.delay_product)

    # ─── SALIR AL MENÚ PRINCIPAL ───
    if not args.dry_run and ok > 0:
        time.sleep(0.5)
        exit_to_main_menu(args.delay, args.dry_run)

    # ─── RESUMEN ───
    print()
    log("══════════════════════════════════", CYAN)
    log(f"  Cargados correctamente: {GREEN}{BOLD}{ok}{RESET}", '')
    log(f"  Errores:                {RED}{errors}{RESET}", '')
    log(f"  Total procesados:       {ok + errors}/{total}", CYAN)
    log("══════════════════════════════════", CYAN)
    log("Listo. Putty retornó al menú principal.", GREEN)

if __name__ == '__main__':
    main()
