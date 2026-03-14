"""
robots/robot_descarga_ventas.py — RPA Suite v5.9
=================================================
Descarga archivos de VENTAS desde el servidor MCANET via SFTP.
Archivos objetivo: ventas semanales (S1, S2, S3, S4) + LPCIO + Linvalor
Origen:  35.198.62.182:9229  /home/asp/mbf/Intercambio/Public/
Destino: C:/Clientes/mbf/Intercambio/Estadistica/
"""
import os
from pathlib import Path
from robots.robot_descarga_ssh import (
    _creds, _conectar_sftp, DESTINO_WIN,
    descargar_archivos_ssh,
)

RUTA_VENTAS        = "/home/asp/mbf/Intercambio/Public"
EXTENSION_VENTAS   = ".csv"
DESTINO_VENTAS     = DESTINO_WIN   # C:\Clientes\mbf\Intercambio\Estadistica

# Palabras clave que identifican archivos de ventas
# Ajustar según los nombres reales del servidor
KEYWORDS_VENTAS = ["venta", "s1", "s2", "s3", "s4", "semana",
                   "lpcio", "linvalor", "exis", "precio"]


def listar_ventas_remotas(ruta=RUTA_VENTAS, extension=EXTENSION_VENTAS,
                           host=None, port=None, user=None, password=None,
                           log_func=None):
    """Lista todos los CSV de ventas disponibles en el servidor."""
    def _log(m):
        if log_func: log_func(m)

    try:
        import paramiko
    except ImportError:
        _log("  paramiko no instalado: pip install paramiko")
        return []

    host, port, user, password = _creds(host, port, user, password)
    ssh = sftp = None
    archivos = []
    try:
        ssh, sftp = _conectar_sftp(host, port, user, password, log_func)
        _log(f"  Listando archivos de ventas en: {ruta}")
        from datetime import datetime
        for item in sftp.listdir_attr(ruta):
            if item.filename.lower().endswith(extension.lstrip("*")):
                archivos.append({
                    "nombre":    item.filename,
                    "ruta":      f"{ruta.rstrip('/')}/{item.filename}",
                    "tamano_kb": round((item.st_size or 0) / 1024, 1),
                    "fecha":     datetime.fromtimestamp(item.st_mtime
                                    ).strftime("%d/%m/%Y %H:%M"),
                })
        archivos.sort(key=lambda x: x["nombre"])
        _log(f"  {len(archivos)} archivo(s) encontrado(s)")
    except Exception as e:
        _log(f"  Error listando ventas: {e}")
        raise
    finally:
        try:
            if sftp: sftp.close()
            if ssh:  ssh.close()
        except Exception:
            pass
    return archivos


def descargar_ventas(destino_local=DESTINO_VENTAS, solo_nuevos=True,
                      host=None, port=None, user=None, password=None,
                      log_func=None):
    """
    Descarga todos los archivos CSV de ventas del servidor.
    Equivale a la primera mitad del .bat MCANET.
    """
    def _log(m):
        if log_func: log_func(m)

    _log("═" * 50)
    _log("MCANET — Descarga de Ventas")
    _log(f"  Origen:  {RUTA_VENTAS}")
    _log(f"  Destino: {destino_local}")
    _log("─" * 50)

    archivos = listar_ventas_remotas(
        host=host, port=port, user=user, password=password, log_func=log_func
    )
    if not archivos:
        _log("  No hay archivos de ventas para descargar.")
        return []

    descargados = descargar_archivos_ssh(
        archivos=archivos,
        destino_local=destino_local,
        solo_nuevos=solo_nuevos,
        host=host, port=port, user=user, password=password,
        log_func=log_func,
    )
    _log("─" * 50)
    _log(f"  ✅ Ventas descargadas: {len(descargados)} archivo(s)")

    # --- NUEVO: Fase de procesamiento ---
    if descargados:
        _log("🏭 Iniciando fase de procesamiento de archivos...")
        procesar_ventas_descargadas(descargados, log_func)

    return descargados


def procesar_ventas_descargadas(lista_archivos, log_func=print):
    """
    Lee una lista de archivos CSV de ventas, los procesa y guarda
    los datos en la base de datos SQLite.
    """
    try:
        import pandas as pd
        from core.database import execute_query
        from core.file_manager import archivar_procesado
    except ImportError as e:
        log_func(f"  ❌ Error: se necesita la librería 'pandas' para procesar. Instalá con: pip install pandas. ({e})")
        return

    log_func(f"  Procesando {len(lista_archivos)} archivo(s) para la base de datos...")
    total_registros_insertados = 0

    for archivo_info in lista_archivos:
        ruta_completa = archivo_info.get("ruta_local")
        if not ruta_completa or not os.path.exists(ruta_completa):
            log_func(f"  ⚠️ No se encontró el archivo descargado: {ruta_completa}")
            continue

        log_func(f"    - Leyendo: {os.path.basename(ruta_completa)}...")
        try:
            # Intentamos leer el CSV, probando con separadores comunes
            try:
                df = pd.read_csv(ruta_completa, delimiter=',')
            except Exception:
                df = pd.read_csv(ruta_completa, delimiter=';', encoding='latin1')

            # --- LÓGICA DE MAPEADO DE COLUMNAS (ASUNCIONES) ---
            # Es necesario adivinar los nombres de las columnas. Esto es un ejemplo.
            # Ajustar estos nombres a los nombres reales en los archivos CSV.
            mapa_columnas = {
                "sku": ["sku", "articulo", "código", "item"],
                "cantidad": ["cantidad", "unidades", "cant."],
                "precio": ["precio", "precio_unitario", "valor"],
                "fecha": ["fecha", "timestamp", "día"]
            }

            def encontrar_columna(df_cols, posibles_nombres):
                for nombre in posibles_nombres:
                    if nombre in df_cols:
                        return nombre
                return None

            df.columns = df.columns.str.lower()
            col_sku = encontrar_columna(df.columns, mapa_columnas["sku"])
            col_cantidad = encontrar_columna(df.columns, mapa_columnas["cantidad"])
            col_precio = encontrar_columna(df.columns, mapa_columnas["precio"])
            col_fecha = encontrar_columna(df.columns, mapa_columnas["fecha"])

            if not all([col_sku, col_cantidad, col_fecha]):
                log_func(f"      ⚠️ No se encontraron las columnas necesarias (SKU, Cantidad, Fecha) en '{os.path.basename(ruta_completa)}'. Omitiendo.")
                continue

            registros_archivo = 0
            for _, fila in df.iterrows():
                try:
                    sku = fila[col_sku]
                    cantidad = fila[col_cantidad]
                    fecha = fila[col_fecha]
                    precio = fila.get(col_precio) if col_precio else 0.0

                    sql = """INSERT INTO ventas_historicas 
                             (timestamp, sku, cantidad_vendida, precio_unitario) 
                             VALUES (?, ?, ?, ?)"""
                    params = (str(fecha), str(sku), float(cantidad), float(precio))
                    execute_query(sql, params, is_commit=True)
                    registros_archivo += 1
                except Exception as db_error:
                    log_func(f"      ❌ Error al insertar fila en BD: {db_error}")

            log_func(f"      ✅ Se insertaron {registros_archivo} registros de ventas en la BD.")
            total_registros_insertados += registros_archivo

            # Archivar el archivo procesado para no volver a leerlo
            archivar_procesado(
                ruta_archivo=ruta_completa,
                robot_nombre="PROCESADOR_VENTAS",
                filas_procesadas=len(df),
                dry_run=False,
                log_func=log_func,
                subdirectorio="procesados_ventas"
            )

        except Exception as e:
            log_func(f"    ❌ Error al procesar el archivo '{os.path.basename(ruta_completa)}': {e}")

    log_func(f"  ✅ Fase de procesamiento finalizada. Total de registros insertados: {total_registros_insertados}")

