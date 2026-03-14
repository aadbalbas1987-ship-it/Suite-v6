"""
ajuste.py — RPA Suite v5.2
Mejoras v5.2: Watchdog integrado en Ajuste y Ajuste Analítico.
"""
import pyautogui
import time
from core.utils import forzar_caps_off, limpiar_sku, f_monto
from core.checkpoint import ContextoEjecucion
from core.file_manager import archivar_procesado


def _ejecutar_cabecera(df, velocidad, log_func, dry_run):
    id_control = str(int(float(df.iloc[0, 2])))
    if dry_run:
        log_func(f"   [SIM] Cabecera: ID={id_control}, Obs={df.iloc[1, 2]}, Tipo={df.iloc[2, 2]}")
        return id_control
    for tecla in ['3', '6', '2']:
        pyautogui.press(tecla)
        time.sleep(0.5)
    pyautogui.press('enter')
    time.sleep(0.8)
    pyautogui.write(id_control, interval=velocidad)
    pyautogui.press('enter')
    time.sleep(0.8)
    pyautogui.press('enter')
    obs = str(df.iloc[1, 2]).upper().strip()
    pyautogui.write(obs, interval=velocidad)
    pyautogui.press('enter')
    time.sleep(0.5)
    pyautogui.press('enter')
    tipo_ingreso = str(df.iloc[2, 2]).upper().strip()
    pyautogui.write(tipo_ingreso, interval=velocidad)
    pyautogui.press('enter')
    time.sleep(1.2)
    pyautogui.write(id_control, interval=velocidad)
    pyautogui.press('enter')
    time.sleep(0.5)
    return id_control


def ejecutar_ajuste(df, total_filas, log_func, progress_func, velocidad, dry_run=False, archivo_origen=None, watchdog_habilitado=True):
    """ROBOT AJUSTE 3-6-2 (columna B). dry_run=True simula sin tocar el sistema."""
    log_func("🚀 Inicializando Robot Ajustes (3-6-2)...")
    forzar_caps_off()
    pyautogui.FAILSAFE = True

    with ContextoEjecucion(
        robot_nombre="AJUSTE",
        archivo_origen=str(archivo_origen or df.shape),
        total_filas=total_filas,
        dry_run=dry_run,
        log_func=log_func,
        progress_func=progress_func,
    ) as ctx:
        try:
            _ejecutar_cabecera(df, velocidad, log_func, dry_run)
            log_func("📦 Iniciando Bucle de Ajustes...")

            for i, fila in ctx.iterar(df):
                sku = limpiar_sku(fila.iloc[0])
                if not sku or sku in ["None", "nan"]:
                    continue
                try:
                    cantidad = f_monto(fila.iloc[1])
                except Exception:
                    ctx.registrar_error(i, f"SKU {sku}", "Cantidad inválida")
                    continue

                dato_d = str(fila.iloc[3]).strip() if len(fila) > 3 else "nan"
                es_gramaje = dato_d.lower() not in ['nan', '', 'none']
                descripcion = (
                    f"AJUSTE SKU={sku} | Delta={cantidad}"
                    + (f" | Gramaje={dato_d}" if es_gramaje else " | Unidad")
                )

                def accion_ajuste(s=sku, c=cantidad, d=dato_d, eg=es_gramaje):
                    pyautogui.write(s, interval=velocidad)
                    for _ in range(4):
                        pyautogui.press('enter')
                        time.sleep(0.1)
                    if eg:
                        pyautogui.write('g', interval=velocidad)
                        pyautogui.write(c, interval=velocidad)
                        pyautogui.press('enter')
                        pyautogui.write(d, interval=velocidad)
                        pyautogui.press('enter')
                    else:
                        pyautogui.write('u', interval=velocidad)
                        pyautogui.write(c, interval=velocidad)
                        pyautogui.press('enter')

                ctx.simular_o_ejecutar(descripcion, accion_ajuste, fila_idx=i)
                if (i + 1) % 5 == 0:
                    log_func(f"  ✅ {i+1}/{total_filas} ajustes procesados")

            if not dry_run:
                log_func("💾 Grabando...")
                pyautogui.press('f5')
                time.sleep(3.0)
                for tecla in ['end', 'enter', 'end', 'end']:
                    pyautogui.press(tecla)
                    time.sleep(0.4)
        except Exception as e:
            log_func(f"❌ Error: {e}")
    log_func("🏁 Robot Ajustes finalizado.")
    if archivo_origen:
        archivar_procesado(
            ruta_archivo=archivo_origen,
            robot_nombre="AJUSTE",
            filas_procesadas=total_filas,
            dry_run=dry_run,
            log_func=log_func,
        )


def ejecutar_ajuste_analitico(df, total_filas, log_func, progress_func, velocidad, dry_run=False, archivo_origen=None, watchdog_habilitado=True):
    """ROBOT AJUSTE ANALÍTICO 3-6-2 (columna E). dry_run=True simula."""
    log_func("🚀 Iniciando Robot Ajustes ANALÍTICO (Col E)...")
    forzar_caps_off()
    pyautogui.FAILSAFE = True

    with ContextoEjecucion(
        robot_nombre="AJUSTE_ANALITICO",
        archivo_origen=str(archivo_origen or df.shape),
        total_filas=total_filas,
        dry_run=dry_run,
        log_func=log_func,
        progress_func=progress_func,
    ) as ctx:
        try:
            _ejecutar_cabecera(df, velocidad, log_func, dry_run)

            for i, fila in ctx.iterar(df):
                sku = limpiar_sku(fila.iloc[0])
                if not sku or sku in ["None", "nan"]:
                    continue
                try:
                    cantidad = f_monto(fila.iloc[4])
                except Exception:
                    ctx.registrar_error(i, f"SKU {sku}", "Cantidad (col E) inválida")
                    continue

                dato_d = str(fila.iloc[3]).strip() if len(fila) > 3 else "nan"
                es_gramaje = dato_d.lower() not in ['nan', '', 'none']
                descripcion = f"AJUSTE_ANALITICO SKU={sku} | Delta_ColE={cantidad}"

                def accion_analitico(s=sku, c=cantidad, d=dato_d, eg=es_gramaje):
                    pyautogui.write(s, interval=velocidad)
                    for _ in range(4):
                        pyautogui.press('enter')
                        time.sleep(0.1)
                    if eg:
                        pyautogui.write('g', interval=velocidad)
                        pyautogui.write(c, interval=velocidad)
                        pyautogui.press('enter')
                        pyautogui.write(d, interval=velocidad)
                        pyautogui.press('enter')
                    else:
                        pyautogui.write('u', interval=velocidad)
                        pyautogui.write(c, interval=velocidad)
                        pyautogui.press('enter')

                ctx.simular_o_ejecutar(descripcion, accion_analitico, fila_idx=i)

            if not dry_run:
                pyautogui.press('f5')
                time.sleep(3.0)
                for tecla in ['end', 'enter', 'end', 'end']:
                    pyautogui.press(tecla)
                    time.sleep(0.4)
        except Exception as e:
            log_func(f"❌ Error: {e}")
    log_func("✅ Ajuste Analítico finalizado.")
    if archivo_origen:
        archivar_procesado(
            ruta_archivo=archivo_origen,
            robot_nombre="AJUSTE_ANALITICO",
            filas_procesadas=total_filas,
            dry_run=dry_run,
            log_func=log_func,
        )