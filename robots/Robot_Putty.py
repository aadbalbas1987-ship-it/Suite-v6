"""
Robot_Putty.py — RPA Suite v5
================================
Robot de carga masiva de stock (módulo 3-6-1).
Mejoras v5:
  - Dry-Run: simulá la carga antes de ejecutarla en el sistema
  - Checkpoint: si se corta, reanudá desde donde quedó
  - Gemini valida el archivo antes de arrancar
Mejoras v5.2:
  - Watchdog: detección automática de ventanas inesperadas,
    congelamiento de PuTTY y pérdida de foco
"""
import pyautogui
import time
import json
from core.utils import forzar_caps_off, limpiar_sku, f_monto
from config import GROQ_API_KEY, get_groq_key
from core.checkpoint import ContextoEjecucion
from core.file_manager import archivar_procesado
from core.database import execute_query


# ============================================================
# VALIDADOR IA DEL ARCHIVO (pre-vuelo)
# ============================================================
def validar_archivo_con_ia(df, log_func=print) -> tuple[bool, str]:
    """Valida el archivo con Groq/Llama antes de que arranque el robot."""
    if not GROQ_API_KEY:
        return True, "Validación IA omitida (GROQ_API_KEY no configurada)"
    try:
        from groq import Groq
        muestra = df.head(5).to_dict(orient='records')
        total = len(df)
        nulos = df.iloc[:, 0].isna().sum()
        prompt = (
            f"Soy un operador de sistema ERP de retail. Voy a cargar masivamente stock.\n"
            f"El archivo tiene {total} filas, {nulos} SKUs vacíos.\n"
            f"Estructura esperada: Col A=SKU, Col B=Cantidad, Col C=ID control, Col D=gramaje (opcional).\n"
            f"Muestra: {muestra}\n\n"
            f"Analizá si hay problemas que impidan una carga exitosa. Sé conciso.\n"
            'Respondé SOLO en JSON: {"ok": true/false, "problemas": [], "advertencias": [], "resumen": "texto"}'
        )
        client = Groq(api_key=GROQ_API_KEY)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.1,
        )
        texto = resp.choices[0].message.content.strip()
        texto = texto.replace("```json", "").replace("```", "").strip()
        resultado = json.loads(texto)
        for p in resultado.get("problemas", []):
            log_func(f"  ❌ PROBLEMA: {p}")
        for a in resultado.get("advertencias", []):
            log_func(f"  ⚠️ AVISO: {a}")
        return resultado.get("ok", True), resultado.get("resumen", "")
    except Exception as e:
        log_func(f"  ⚠️ Validación IA falló ({e}). Continuando igual.")
        return True, "Validación IA no disponible"


# ============================================================
# ROBOT PRINCIPAL
# ============================================================
def ejecutar_stock(df, total_filas, log_func, progress_func, velocidad, dry_run=False, archivo_origen=None, watchdog_habilitado=True):
    log_func(f"🔍 Validando archivo con IA antes de arrancar...")
    ok, resumen = validar_archivo_con_ia(df, log_func)
    log_func(f"  → {resumen}")
    if not ok:
        log_func("❌ El archivo tiene problemas críticos. Corregilo antes de ejecutar.")
        return

    forzar_caps_off()
    pyautogui.FAILSAFE = True

    with ContextoEjecucion(
        robot_nombre="STOCK",
        archivo_origen=str(archivo_origen or df.shape),
        total_filas=total_filas,
        dry_run=dry_run,
        log_func=log_func,
        progress_func=progress_func,
    ) as ctx:
        try:
            if not dry_run:
                # NAVEGACIÓN AL MÓDULO 3-6-1
                log_func("📂 Navegando a Módulo 3-6-1...")
                for tecla in ['3', '6', '1']:
                    pyautogui.press(tecla)
                    time.sleep(0.5)
                pyautogui.press('enter')
                time.sleep(0.8)

                # CABECERA
                log_func("📝 Cargando Cabecera de Pedido...")
                id_pedido = str(int(float(df.iloc[0, 2])))
                pyautogui.write(id_pedido, interval=velocidad)
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
                pyautogui.write(id_pedido, interval=velocidad)
                pyautogui.press('enter')
                time.sleep(0.5)
            else:
                id_pedido = str(int(float(df.iloc[0, 2]))) if len(df) > 0 else "N/A"
                log_func(f"   [SIM] Cabecera: ID={id_pedido}, Obs={df.iloc[1, 2] if len(df)>1 else ''}")

            # BUCLE MAESTRO
            log_func("📦 Iniciando Bucle de Artículos...")
            for i, fila in ctx.iterar(df):
                sku = limpiar_sku(fila.iloc[0])
                try:
                    cantidad = str(int(float(fila.iloc[1])))
                except Exception:
                    ctx.registrar_error(i, f"SKU {sku}", "Cantidad no válida")
                    continue
                dato_d = str(fila.iloc[3]).strip() if len(fila) > 3 else "nan"
                es_gramaje = dato_d.lower() not in ['nan', '', 'none']
                if not sku or sku in ["None", "nan"]:
                    continue
                descripcion = (
                    f"SKU={sku} | Cant={cantidad}"
                    + (f" | Gramaje={dato_d}" if es_gramaje else " | Unidad")
                )
                def accion_stock(s=sku, c=cantidad, d=dato_d, eg=es_gramaje):
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
                ctx.simular_o_ejecutar(descripcion, accion_stock, fila_idx=i)
                if not dry_run:
                    try:
                        # Registrar en la base de datos central
                        sql = "INSERT INTO cargas_stock (sku, cantidad_cargada, robot_origen) VALUES (?, ?, ?)"
                        params = (sku, int(cantidad), "Robot_Putty")
                        execute_query(sql, params, is_commit=True)
                    except Exception as db_error:
                        log_func(f"  ⚠️ Error al registrar en BD para SKU {sku}: {db_error}")

                if (i + 1) % 10 == 0:
                    log_func(f"  ✅ {i+1}/{total_filas} procesados")

            # CIERRE
            if not dry_run:
                log_func("💾 Grabando...")
                pyautogui.press('f5')
                time.sleep(3.0)
                for tecla in ['end', 'enter', 'end', 'end']:
                    pyautogui.press(tecla)
                    time.sleep(0.4)
        except Exception as e:
            log_func(f"❌ Error: {e}")
    log_func("🏁 Robot Stock finalizado.")
    if archivo_origen:
        procesadas = sum(1 for i in range(total_filas) if limpiar_sku(df.iloc[i, 0]))
        archivar_procesado(
            ruta_archivo=archivo_origen,
            robot_nombre="STOCK",
            filas_procesadas=procesadas,
            dry_run=dry_run,
            log_func=log_func,
        )