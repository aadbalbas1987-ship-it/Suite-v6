"""
robots/robot_descarga_ssh.py - RPA Suite v5.9
Reemplaza el .bat de MCANET via SFTP/Paramiko.
Origen:  35.198.62.182:9229 /home/asp/mbf/Intercambio/Public/*.csv
Destino: C:/Clientes/mbf/Intercambio/Estadistica
"""
import os
import time
from pathlib import Path
from datetime import datetime

try:
    import paramiko
    _PARAMIKO = True
except ImportError:
    _PARAMIKO = False

RUTA_REMOTA_DEFAULT = "/home/asp/mbf/Intercambio/Public"
EXTENSION_DEFAULT   = ".csv"
DESTINO_WIN         = os.path.join("C:\\", "Clientes", "mbf", "Intercambio", "Estadistica")


def _conectar_sftp(host, port, user, password, log_func=None):
    def _log(m):
        if log_func: log_func(m)
    if not _PARAMIKO:
        raise RuntimeError("paramiko no instalado: pip install paramiko")
    _log(f"  Conectando {host}:{port} como {user}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=host, port=int(port), username=user, password=password,
                timeout=15, banner_timeout=15, allow_agent=False, look_for_keys=False)
    sftp = ssh.open_sftp()
    _log(f"  Conectado a {host}")
    return ssh, sftp


def _creds(host, port, user, password):
    if host:
        return host, port, user, password
    from config import get_ssh_config
    c = get_ssh_config()
    return c.host, c.port, c.user, c.password


def listar_archivos_remotos(ruta_remota=RUTA_REMOTA_DEFAULT,
                             extension=EXTENSION_DEFAULT,
                             host=None, port=None, user=None, password=None,
                             log_func=None):
    def _log(m):
        if log_func: log_func(m)
    host, port, user, password = _creds(host, port, user, password)
    archivos = []
    ssh = sftp = None
    try:
        ssh, sftp = _conectar_sftp(host, port, user, password, log_func)
        _log(f"  Listando: {ruta_remota}  ({extension})")
        ext = extension.lower().lstrip("*")
        for item in sftp.listdir_attr(ruta_remota):
            if item.filename.lower().endswith(ext):
                archivos.append({
                    "nombre":    item.filename,
                    "ruta":      f"{ruta_remota.rstrip('/')}/{item.filename}",
                    "tamano_kb": round((item.st_size or 0) / 1024, 1),
                    "fecha":     datetime.fromtimestamp(item.st_mtime).strftime("%d/%m/%Y %H:%M"),
                })
        archivos.sort(key=lambda x: x["nombre"])
        _log(f"  {len(archivos)} archivo(s) encontrado(s)")
    except paramiko.AuthenticationException:
        _log("  Contrasena incorrecta")
        raise
    except FileNotFoundError:
        _log(f"  Ruta no encontrada: {ruta_remota}")
    except Exception as e:
        _log(f"  Error listando: {e}")
        raise
    finally:
        try:
            if sftp: sftp.close()
            if ssh: ssh.close()
        except Exception:
            pass
    return archivos


def descargar_archivos_ssh(archivos, destino_local=DESTINO_WIN,
                            solo_nuevos=True,
                            host=None, port=None, user=None, password=None,
                            log_func=None, progress_func=None):
    def _log(m):
        if log_func: log_func(m)
    if not archivos:
        _log("  Sin archivos para descargar.")
        return []
    host, port, user, password = _creds(host, port, user, password)
    dest = Path(destino_local)
    dest.mkdir(parents=True, exist_ok=True)
    descargados = []
    salteados   = []
    errores     = []
    ssh = sftp  = None
    try:
        ssh, sftp = _conectar_sftp(host, port, user, password, log_func)
        total = len(archivos)
        _log(f"  Descargando {total} archivo(s) -> {dest}")
        _log("  " + "-"*50)
        for i, arch in enumerate(archivos, 1):
            nombre     = arch["nombre"]
            ruta_local = dest / nombre
            if solo_nuevos and ruta_local.exists():
                salteados.append(nombre)
                _log(f"  [{i}/{total}] {nombre} - ya existe, salteado")
                if progress_func: progress_func(i/total)
                continue
            try:
                _log(f"  [{i}/{total}] {nombre}  ({arch.get('tamano_kb',0)} KB)")
                sftp.get(arch["ruta"], str(ruta_local))
                descargados.append(str(ruta_local))
                _log(f"  OK: {nombre}")
            except Exception as e:
                errores.append(nombre)
                _log(f"  ERROR: {nombre} - {e}")
            if progress_func: progress_func(i/total)
            time.sleep(0.1)
    except paramiko.AuthenticationException:
        _log("  Contrasena incorrecta - verifica la clave ingresada")
        return descargados
    except Exception as e:
        _log(f"  Error de conexion: {e}")
        return descargados
    finally:
        try:
            if sftp: sftp.close()
            if ssh: ssh.close()
        except Exception:
            pass
    _log("  " + "-"*50)
    _log(f"  Descargados: {len(descargados)}  Salteados: {len(salteados)}  Errores: {len(errores)}")
    _log(f"  Destino: {dest}")
    return descargados


def sincronizar_procesados(ruta_remota=RUTA_REMOTA_DEFAULT,
                            extension=EXTENSION_DEFAULT,
                            destino_local=DESTINO_WIN,
                            solo_nuevos=True,
                            host=None, port=None, user=None, password=None,
                            log_func=None):
    def _log(m):
        if log_func: log_func(m)
    _log("MCANET - Descarga desde servidor")
    _log(f"  Origen:  {ruta_remota}")
    _log(f"  Destino: {destino_local}")
    archivos = listar_archivos_remotos(ruta_remota, extension, host, port, user, password, log_func)
    if not archivos:
        _log("  No hay archivos para descargar.")
        return []
    return descargar_archivos_ssh(archivos, destino_local, solo_nuevos, host, port, user, password, log_func)
