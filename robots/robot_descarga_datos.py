"""
robot_descarga_datos.py — RPA Suite v5
========================================
Robot de descarga automática de datos para dashboards.
Maneja la secuencia completa dentro de PuTTY:
  - Ventas (4 semanas) → menú 9-1
  - Clientes (1 archivo, opcional) → menú 9-5
  - Stock StkFisico → menú 8-a (envío por mail)

Precondición: PuTTY abierto en menú principal.
"""
import pyautogui
import pygetwindow as gw
import pyperclip
import time
import os
from datetime import date, timedelta
from pathlib import Path
from config import get_ssh_config

pyautogui.FAILSAFE = True

_ROOT = Path(__file__).parent.parent
LOG_PATH = _ROOT / "logs" / "debug_descarga_datos.txt"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════
# HELPERS BASE
# ══════════════════════════════════════════════════════════════

def log_debug(msg: str, modo: str = "a"):
    try:
        with open(LOG_PATH, modo, encoding='utf-8') as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _foco_putty(log_func) -> bool:
    for titulo in ['PuTTY', 'putty', 'SSH']:
        wins = gw.getWindowsWithTitle(titulo)
        if wins:
            try:
                wins[0].activate()
                time.sleep(0.5)
                log_func(f"   → Foco: {wins[0].title}")
                return True
            except Exception as e:
                log_func(f"   ⚠ {e}")
    log_func("❌ PuTTY no encontrado.")
    return False


def _t(char: str, pausa: float = 0.3):
    """Escribe un carácter."""
    pyautogui.write(char, interval=0.03)
    time.sleep(pausa)


def _paste(texto: str, pausa: float = 0.25):
    """Pega via clipboard con click derecho (método nativo PuTTY)."""
    pyperclip.copy(texto)
    time.sleep(0.1)
    pyautogui.click(button='right')
    time.sleep(pausa)


def _enter(n: int = 1, pausa: float = 0.25):
    for _ in range(n):
        pyautogui.press('enter')
        time.sleep(pausa)


def _caps_off():
    """Asegura que Bloq Mayús esté apagado."""
    import ctypes
    if ctypes.WinDLL("User32.dll").GetKeyState(0x14) & 1:
        pyautogui.press('capslock')
        time.sleep(0.1)


def _E_mayuscula():
    """Escribe E siempre en mayúscula, sin importar Bloq Mayús."""
    _caps_off()
    pyautogui.keyDown('shift')
    pyautogui.press('e')
    pyautogui.keyUp('shift')
    time.sleep(0.2)


def _fecha_str(d: date) -> str:
    """Convierte date a DDMMYYYY."""
    return d.strftime('%d%m%Y')


# ══════════════════════════════════════════════════════════════
# CÁLCULO DE SEMANAS
# ══════════════════════════════════════════════════════════════

def calcular_semanas(mes: int, anio: int) -> list[tuple[date, date]]:
    """
    Divide el mes en 4 semanas de lunes a sábado.
    Semana 1: días 1-7 (o hasta fin de mes)
    Semana 2: días 8-14
    Semana 3: días 15-21
    Semana 4: días 22-fin de mes
    """
    import calendar
    ultimo_dia = calendar.monthrange(anio, mes)[1]

    cortes = [1, 8, 15, 22]
    semanas = []
    for i, inicio in enumerate(cortes):
        if i + 1 < len(cortes):
            fin = cortes[i + 1] - 1
        else:
            fin = ultimo_dia
        d_ini = date(anio, mes, inicio)
        d_fin = date(anio, mes, min(fin, ultimo_dia))
        semanas.append((d_ini, d_fin))
    return semanas


def nombre_archivo(suc: str, d_ini: date, d_fin: date) -> str:
    """
    Genera el nombre del archivo.
    Formato: SU_DINI_DFIN_MESAÑO
    Ej: 01_01_07_0126  /  09_22_31_0126  /  cli_01_31_0126
    """
    mes_anio = d_ini.strftime('%m%y')
    return f"{suc}_{d_ini.day:02d}_{d_fin.day:02d}_{mes_anio}"


MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


# ══════════════════════════════════════════════════════════════
# SECUENCIAS DE DESCARGA
# ══════════════════════════════════════════════════════════════

def _descarga_ventas_semana(
    d_ini: date, d_fin: date,
    suc_codigo: str,       # "01", "09" o "" (sin filtro)
    nombre: str,
    primer_vez: bool,      # True = viene del menú principal (9→1), False = solo 1
    ultima_iteracion: bool, # True = 2×END al menú principal, False = 1×END al submenú
    log_func,
):
    """
    Descarga un archivo de ventas para el rango dado.
    Si primer_vez=True navega 9→1, sino solo pulsa 1.
    """
    fi = _fecha_str(d_ini)
    ff = _fecha_str(d_fin)
    log_func(f"   📅 Ventas {d_ini.strftime('%d/%m')}→{d_fin.strftime('%d/%m')} | suc={suc_codigo or 'todas'} | archivo={nombre}")

    if primer_vez:
        # Primera semana: navegar desde menú principal 9 → 1
        _t('9', pausa=0.8)
        _t('1', pausa=1.5)
    else:
        # Semanas 2-4: ya estamos en el submenú de reportes, solo 1
        _t('1', pausa=1.5)

    # Rango de fechas
    _paste(fi);  _enter(1, pausa=0.3)
    _paste(ff);  _enter(3, pausa=0.3)   # 3 ENTERs después de fecha fin

    # SU + sucursal (después de los 3 ENTERs)
    if suc_codigo:
        _caps_off()
        pyautogui.write('SU', interval=0.05)
        time.sleep(0.2)
        _enter(1, pausa=0.4)
        _paste(suc_codigo, pausa=0.4)
        _enter(2, pausa=0.3)   # 2 ENTERs después del código de sucursal
    else:
        _enter(2, pausa=0.3)   # sin sucursal: 2 ENTERs igual

    # Ex (mayúscula E + x)
    _caps_off()
    pyautogui.keyDown('shift'); pyautogui.press('e'); pyautogui.keyUp('shift')
    time.sleep(0.1)
    pyautogui.write('x', interval=0.03)
    time.sleep(0.2)

    # F5
    pyautogui.press('f5')
    time.sleep(2.5)   # espera pantalla intermedia de procesamiento

    # Nombre del archivo (aparece después de la pantalla intermedia)
    _paste(nombre, pausa=0.3)
    _enter(1, pausa=0.2)
    time.sleep(1.0)
    _enter(1, pausa=0.3)

    # Navegación post-descarga
    if ultima_iteracion:
        # Última semana: 2×END para volver al menú principal
        pyautogui.press('end'); time.sleep(0.4)
        pyautogui.press('end'); time.sleep(0.5)
    else:
        # Semanas intermedias: 1×END, queda en submenú listo para escribir 1
        pyautogui.press('end')
        time.sleep(0.5)


def _descarga_clientes(
    d_ini: date, d_fin: date,
    suc_codigo: str,
    nombre: str,
    log_func,
):
    """
    Descarga 1 archivo de clientes desde el menú principal → 9→5.
    Misma secuencia que ventas pero rango completo del mes.
    """
    fi = _fecha_str(d_ini)
    ff = _fecha_str(d_fin)
    log_func(f"   👥 Clientes {d_ini.strftime('%d/%m')}→{d_fin.strftime('%d/%m')} | archivo={nombre}")

    _t('9', pausa=0.8)
    _t('5', pausa=1.5)

    _paste(fi);  _enter(1, pausa=0.3)
    _paste(ff);  _enter(3, pausa=0.3)   # 3 ENTERs después de fecha fin

    if suc_codigo:
        _caps_off()
        pyautogui.write('SU', interval=0.05)
        time.sleep(0.2)
        _enter(1, pausa=0.4)
        _paste(suc_codigo, pausa=0.4)
        _enter(2, pausa=0.3)
    else:
        _enter(2, pausa=0.3)

    _caps_off()
    pyautogui.keyDown('shift'); pyautogui.press('e'); pyautogui.keyUp('shift')
    time.sleep(0.1)
    pyautogui.write('x', interval=0.03)
    time.sleep(0.2)

    pyautogui.press('f5')
    time.sleep(2.5)   # espera pantalla intermedia

    _paste(nombre, pausa=0.3)
    _enter(1, pausa=0.2)
    time.sleep(1.0)
    _enter(1, pausa=0.3)

    pyautogui.press('end')
    time.sleep(0.5)


def _descarga_stock(email: str, log_func):
    """
    Descarga stock StkFisico → menú 8→a.
    Desde menú principal.
    """
    log_func("   📦 Descargando stock StkFisico...")

    _t('8', pausa=0.8)
    _t('a', pausa=1.5)

    _enter(1, pausa=0.5)

    # Escribir "STOCK StkFisico"
    _caps_off()
    pyautogui.write('STOCK StkFisico', interval=0.04)
    time.sleep(0.3)

    _enter(5, pausa=0.3)   # 5 enters sobre campos

    # S para confirmar "Sí"
    pyautogui.write('S', interval=0.03)
    time.sleep(0.2)

    _enter(2, pausa=0.4)

    # E mayúscula
    _E_mayuscula()
    _enter(1, pausa=0.5)

    # Mail
    _paste(email, pausa=0.4)

    # F5
    pyautogui.press('f5')
    time.sleep(2.0)

    log_func("   ✅ Stock enviado al mail.")


def _volver_menu_principal(log_func):
    """Sube al menú principal con ENDs hasta que aparezca el raíz."""
    log_func("   ↩ Volviendo al menú principal...")
    for _ in range(4):
        pyautogui.press('end')
        time.sleep(0.4)


# ══════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════

def _semanas_ya_descargadas(mes: int, anio: int, sucursales: list, log_func) -> set:
    """
    Detecta qué semanas ya fueron descargadas revisando los archivos en /procesados/VENTAS/.
    Retorna set de strings "SUC_SEMANA" que ya existen, ej: {"01_S1", "01_S2", "09_S1"}.
    """
    from pathlib import Path
    import re

    _ROOT = Path(__file__).parent.parent
    _DIR  = _ROOT / "procesados" / "VENTAS"
    if not _DIR.exists():
        return set()

    ya_descargadas = set()
    # Buscar archivos que coincidan con el mes/año
    prefix = f"{mes:02d}{anio}"
    for f in _DIR.iterdir():
        if f.suffix.lower() == ".xlsx" and prefix in f.name and f.name.startswith("ventas_suc"):
            # extraer sucursal del nombre: ventas_suc01_...
            partes = f.name.split("_")
            if len(partes) >= 2:
                suc = partes[1].replace("suc", "")
                ya_descargadas.add(suc)
    return ya_descargadas


def _semana_ya_existe(suc: str, d_ini, d_fin, log_func) -> bool:
    """Verifica si ya existe el archivo de una semana específica."""
    from pathlib import Path
    _ROOT = Path(__file__).parent.parent
    _DIR  = _ROOT / "procesados" / "VENTAS"
    if not _DIR.exists():
        return False
    nombre = nombre_archivo(suc, d_ini, d_fin)
    return (_DIR / nombre).exists()


def ejecutar_descarga_dashboard(
    mes: int,
    anio: int,
    sucursales: list,       # ["01"], ["09"] o ["01", "09"]
    email_stock: str,
    incluir_clientes: bool = False,
    solo_semanas_nuevas: bool = True,   # NEW: skip semanas ya descargadas
    log_func=None,
) -> bool:
    """
    Ejecuta la secuencia completa de descarga para el dashboard de ventas.

    Args:
        mes:              Mes a trabajar (1-12)
        anio:             Año (ej: 2026)
        sucursales:       Lista de sucursales a descargar
        email_stock:      Email para envío del stock
        incluir_clientes: Si True, descarga también el archivo de clientes
        log_func:         Función de logging
    """
    if log_func is None:
        log_func = lambda m: log_debug(m)

    log_debug(f"--- INICIO DESCARGA DASHBOARD mes={mes}/{anio} ---", modo="w")
    log_func(f"🚀 Descarga automática — {mes:02d}/{anio}")
    log_func(f"   Sucursales: {sucursales} | Clientes: {incluir_clientes}")

    if not _foco_putty(log_func):
        return False

    semanas = calcular_semanas(mes, anio)
    log_func(f"   Semanas calculadas:")
    for i, (ini, fin) in enumerate(semanas, 1):
        log_func(f"     S{i}: {ini.strftime('%d/%m')} → {fin.strftime('%d/%m')}")

    try:
        total_semanas = len(semanas) * len(sucursales)
        semanas_ok    = 0
        semanas_error = []

        for suc in sucursales:
            log_func(f"\n   ── Sucursal {suc} ──────────────────")

            ultima_suc = (suc == sucursales[-1])
            for i, (d_ini, d_fin) in enumerate(semanas):
                primer_vez    = (i == 0)
                ultima_semana = (i == len(semanas) - 1)
                ultima_iter   = ultima_semana and ultima_suc and not incluir_clientes
                nombre        = nombre_archivo(suc, d_ini, d_fin)

                # ── Descarga incremental: saltar si ya existe ─────
                if solo_semanas_nuevas and _semana_ya_existe(suc, d_ini, d_fin, log_func):
                    log_func(f"   ⏭  S{i+1} Suc {suc} ya descargada — salteada")
                    semanas_ok += 1
                    continue

                # ── Progreso visual ──────────────────────────────
                progreso_actual = semanas_ok + 1
                barra = "█" * progreso_actual + "░" * (total_semanas - progreso_actual)
                log_func(f"   [{barra}] {progreso_actual}/{total_semanas} — Suc {suc} S{i+1}: {d_ini.strftime('%d/%m')}→{d_fin.strftime('%d/%m')}")

                # ── Retry automático hasta 3 intentos ────────────
                MAX_INTENTOS = 3
                ok = False
                for intento in range(1, MAX_INTENTOS + 1):
                    try:
                        _descarga_ventas_semana(
                            d_ini=d_ini, d_fin=d_fin,
                            suc_codigo=suc,
                            nombre=nombre,
                            primer_vez=primer_vez and intento == 1,
                            ultima_iteracion=ultima_iter,
                            log_func=log_func,
                        )
                        log_func(f"   ✅ S{i+1} OK → {nombre}")
                        ok = True
                        break
                    except pyautogui.FailSafeException:
                        raise   # failsafe siempre propaga
                    except Exception as e_retry:
                        if intento < MAX_INTENTOS:
                            log_func(f"   ⚠  S{i+1} intento {intento} fallido: {e_retry} — reintentando en 3s...")
                            time.sleep(3)
                            try:
                                _volver_menu_principal(log_func)
                            except Exception:
                                pass
                        else:
                            log_func(f"   ❌ S{i+1} falló luego de {MAX_INTENTOS} intentos: {e_retry}")
                            semanas_error.append(f"Suc {suc} S{i+1} ({d_ini.strftime('%d/%m')}→{d_fin.strftime('%d/%m')})")

                if ok:
                    semanas_ok += 1
                time.sleep(0.3)

            # Si no es la última sucursal, volver al menú principal para la siguiente
            if not ultima_suc:
                _volver_menu_principal(log_func)

        # ── Resumen de semanas con error ─────────────────────
        if semanas_error:
            log_func(f"\n   ⚠  {len(semanas_error)} semana(s) con error:")
            for s in semanas_error:
                log_func(f"      • {s}")
        log_func(f"   📊 Resultado: {semanas_ok}/{total_semanas} semanas descargadas OK")

        # ── Clientes (opcional) ───────────────────────────────
        if incluir_clientes:
            import calendar
            ultimo = calendar.monthrange(anio, mes)[1]
            d_ini_mes = date(anio, mes, 1)
            d_fin_mes = date(anio, mes, ultimo)
            for suc in sucursales:
                nombre_cli = nombre_archivo(f"cli{'_'+suc if len(sucursales)>1 else ''}", d_ini_mes, d_fin_mes)
                _descarga_clientes(
                    d_ini=d_ini_mes, d_fin=d_fin_mes,
                    suc_codigo=suc,
                    nombre=nombre_cli,
                    log_func=log_func,
                )
                log_func(f"   ✅ Clientes → {nombre_cli}")
                _volver_menu_principal(log_func)

        # ── Stock ─────────────────────────────────────────────
        _descarga_stock(email=email_stock, log_func=log_func)
        _volver_menu_principal(log_func)

        log_func("\n✅ Descarga completa. Revisá el servidor.")
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
