"""
robots/robot_descarga_clientes.py — RPA Suite v5.9
===================================================
Descarga archivos de CLIENTES desde el servidor MCANET via SFTP.
Archivos objetivo: padrón de clientes, cuentas corrientes, etc.
Origen:  35.198.62.182:9229  /home/asp/mbf/Intercambio/Public/
Destino: C:/Clientes/mbf/Intercambio/Clientes/
"""
import os
from pathlib import Path
from datetime import datetime
from robots.robot_descarga_ssh import (
    _creds, _conectar_sftp,
    descargar_archivos_ssh,
)

RUTA_CLIENTES      = "/home/asp/mbf/Intercambio/Public"
EXTENSION_CLIENTES = ".csv"
DESTINO_CLIENTES   = os.path.join("C:\\", "Clientes", "mbf", "Intercambio", "Clientes")

# Palabras clave que identifican archivos de clientes
# Ajustar según los nombres reales del servidor
KEYWORDS_CLIENTES  = ["cliente", "cxc", "cuenta", "padron", "deuda",
                       "cobro", "saldo", "haber"]


def listar_clientes_remotos(ruta=RUTA_CLIENTES, extension=EXTENSION_CLIENTES,
                              filtro_keywords=None,
                              host=None, port=None, user=None, password=None,
                              log_func=None):
    """
    Lista archivos de clientes en el servidor.
    Si filtro_keywords está vacío lista todos los CSV.
    Si se pasa lista de keywords filtra solo los que coincidan.
    """
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
    keywords = filtro_keywords or []

    try:
        ssh, sftp = _conectar_sftp(host, port, user, password, log_func)
        _log(f"  Listando archivos de clientes en: {ruta}")
        for item in sftp.listdir_attr(ruta):
            nombre_lower = item.filename.lower()
            if not nombre_lower.endswith(extension.lstrip("*")):
                continue
            # Si hay keywords, filtrar; si no hay, tomar todos
            if keywords:
                if not any(kw in nombre_lower for kw in keywords):
                    continue
            archivos.append({
                "nombre":    item.filename,
                "ruta":      f"{ruta.rstrip('/')}/{item.filename}",
                "tamano_kb": round((item.st_size or 0) / 1024, 1),
                "fecha":     datetime.fromtimestamp(item.st_mtime
                                ).strftime("%d/%m/%Y %H:%M"),
            })
        archivos.sort(key=lambda x: x["nombre"])
        _log(f"  {len(archivos)} archivo(s) de clientes encontrado(s)")
    except Exception as e:
        _log(f"  Error listando clientes: {e}")
        raise
    finally:
        try:
            if sftp: sftp.close()
            if ssh:  ssh.close()
        except Exception:
            pass
    return archivos


def descargar_clientes(destino_local=DESTINO_CLIENTES, solo_nuevos=True,
                        filtro_keywords=None,
                        host=None, port=None, user=None, password=None,
                        log_func=None):
    """
    Descarga todos los archivos CSV de clientes del servidor.
    Crea la carpeta destino si no existe.
    """
    def _log(m):
        if log_func: log_func(m)

    _log("═" * 50)
    _log("MCANET — Descarga de Clientes")
    _log(f"  Origen:  {RUTA_CLIENTES}")
    _log(f"  Destino: {destino_local}")
    _log("─" * 50)

    # Crear carpeta destino si no existe
    Path(destino_local).mkdir(parents=True, exist_ok=True)

    archivos = listar_clientes_remotos(
        filtro_keywords=filtro_keywords,
        host=host, port=port, user=user, password=password,
        log_func=log_func,
    )
    if not archivos:
        _log("  No hay archivos de clientes para descargar.")
        return []

    descargados = descargar_archivos_ssh(
        archivos=archivos,
        destino_local=destino_local,
        solo_nuevos=solo_nuevos,
        host=host, port=port, user=user, password=password,
        log_func=log_func,
    )
    _log("─" * 50)
    _log(f"  ✅ Clientes descargados: {len(descargados)} archivo(s)")
    return descargados
