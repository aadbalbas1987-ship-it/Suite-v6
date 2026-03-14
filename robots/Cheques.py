"""
Cheques.py — RPA Suite v5.2
Mejoras v5.2: Watchdog integrado para detección de desvíos.
"""
import pandas as pd
import pyautogui
import time
from core.utils import f_monto
from core.checkpoint import ContextoEjecucion
from core.file_manager import archivar_procesado


def ejecutar_cheques(df, log_func, progress_func, dry_run=False, archivo_origen=None, watchdog_habilitado=True):
    """
    ROBOT CHEQUES: Carga masiva de cartera de cheques.

    Estructura del Excel esperada:
      Fila 0: [Entidad, Comision, ...]
      Filas 1+: [_, Ref, Serie, Nro, Fecha_Emision, Fecha_Vto, Banco, Nombre, CUIT, Monto]
    """
    try:
        log_func("🎫 Iniciando Módulo de Cheques...")

        entidad = str(df.iloc[0, 0])
        try:
            comision = float(str(df.iloc[0, 1]).replace(',','.'))
        except (ValueError, TypeError):
            comision = 0.0
            log_func('⚠️ Comisión no válida, usando 0.0')
        total_cheques = df[df.columns[9]].sum()
        ajuste_apf = total_cheques - comision

        log_func(f"  Entidad: {entidad}")
        log_func(f"  Total cheques: ${total_cheques:,.2f} | Comisión: ${comision:,.2f} | APF: ${ajuste_apf:,.2f}")

        total_filas = len(df)

        with ContextoEjecucion(
            robot_nombre="CHEQUES",
            archivo_origen=str(archivo_origen or df.shape),
            total_filas=total_filas,
            dry_run=dry_run,
            log_func=log_func,
            progress_func=progress_func,
        ) as ctx:
            try:
                if not dry_run:
                    pyautogui.press('2')
                    pyautogui.press('enter', presses=6, interval=0.1)
                    pyautogui.write(entidad)
                    pyautogui.press('enter')
                    pyautogui.write('afd')
                    pyautogui.press('enter')
                    pyautogui.write('0')
                    pyautogui.press('enter')
                else:
                    log_func(f"   [SIM] Navegación → Módulo Cheques | Entidad: {entidad}")

                for i, fila in ctx.iterar(df):
                    if pd.isna(fila.iloc[1]):
                        log_func("  ℹ️ Col B vacía → Fin de datos.")
                        break

                    ref       = str(fila.iloc[1])
                    serie     = str(fila.iloc[2])
                    nro       = str(fila.iloc[3])
                    fecha_em  = str(fila.iloc[4])
                    fecha_vto = str(fila.iloc[5])
                    banco     = str(fila.iloc[6])
                    nombre    = str(fila.iloc[7])
                    cuit      = str(fila.iloc[8])
                    monto     = f_monto(fila.iloc[9])

                    descripcion = f"Cheque #{nro} | Banco={banco} | {nombre} | ${monto}"

                    def accion_cheque(
                        r=ref, s=serie, n=nro, fe=fecha_em, fv=fecha_vto,
                        b=banco, nm=nombre, c=cuit, m=monto
                    ):
                        for valor in [r, s, n, fe, fv, b]:
                            pyautogui.write(str(valor))
                            pyautogui.press('enter')
                        pyautogui.hotkey('shift', 't')
                        pyautogui.write(nm)
                        pyautogui.press('enter')
                        pyautogui.write(c)
                        pyautogui.press('enter')
                        pyautogui.write(m)
                        pyautogui.press('enter')

                    ctx.simular_o_ejecutar(descripcion, accion_cheque, fila_idx=i)

                # BALANCEO POST-GRILLA
                if not dry_run:
                    pyautogui.press('f5')
                    pyautogui.press('enter', presses=2)
                    pyautogui.write(f_monto(total_cheques))
                    pyautogui.press('enter')
                    pyautogui.write('cof')
                    pyautogui.press('enter')
                    pyautogui.write(f_monto(comision))
                    pyautogui.press('enter')
                    pyautogui.write('apf')
                    pyautogui.press('enter')
                    pyautogui.write(f_monto(ajuste_apf))
                    pyautogui.press('enter')
                else:
                    log_func(f"   [SIM] Balanceo: Total={f_monto(total_cheques)}, COF={f_monto(comision)}, APF={f_monto(ajuste_apf)}")

            except Exception as e:
                log_func(f"❌ Error en ejecución: {e}")

        log_func("⚠️ CARGA LISTA. VERIFICACIÓN MANUAL REQUERIDA.")

        if archivo_origen:
            archivar_procesado(
                ruta_archivo=archivo_origen,
                robot_nombre="CHEQUES",
                filas_procesadas=len(df),
                dry_run=dry_run,
                log_func=log_func,
            )
    except Exception as e:
        log_func(f"❌ Error: {e}")