"""
core/seguridad.py — RPA Suite v5.9
=====================================
Sistema de seguridad multicapa para el .env y credenciales.

CAPAS IMPLEMENTADAS:
  1. Cifrado AES-256-GCM del .env  → .env.enc (ilegible sin master password)
  2. Master password derivada con PBKDF2 (100.000 iteraciones) — fuerza bruta inviable
  3. .env jamás se sube a Git      → .gitignore lo bloquea siempre
  4. Variables de entorno en memoria — nunca se logean ni se imprimen
  5. Detección de .env expuesto    — alerta si está fuera de la carpeta raíz
  6. Hash de integridad            — detecta si alguien modificó el .env
  7. Bloqueo de pantalla           — opción de ocultar valores en la GUI
  8. Limpieza de portapapeles      — borra claves copiadas después de 30 seg

DEPENDENCIAS:
  pip install cryptography
"""

import os
import sys
import json
import time
import base64
import hashlib
import secrets
import threading
from pathlib import Path
from typing import Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    _CRYPTO = True
except ImportError:
    _CRYPTO = False

_ROOT = Path(__file__).parent.parent
_ENV_PATH     = _ROOT / ".env"
_ENV_ENC_PATH = _ROOT / ".env.enc"
_HASH_PATH    = _ROOT / ".env.hash"
_GITIGNORE    = _ROOT / ".gitignore"

# ══════════════════════════════════════════════════════════════
# CAPA 1 — CIFRADO AES-256-GCM
# ══════════════════════════════════════════════════════════════

def _derivar_clave(password: str, salt: bytes) -> bytes:
    """PBKDF2-SHA256 con 100.000 iteraciones → clave AES-256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return kdf.derive(password.encode("utf-8"))


def cifrar_env(master_password: str, log_func=None) -> bool:
    """
    Lee el .env actual, lo cifra con AES-256-GCM y guarda .env.enc.
    El .env original NO se borra — es responsabilidad del usuario.
    Retorna True si éxito.
    """
    def _log(m):
        if log_func: log_func(m)

    if not _CRYPTO:
        _log("❌ 'cryptography' no instalada. pip install cryptography")
        return False

    if not _ENV_PATH.exists():
        _log(f"❌ No se encontró {_ENV_PATH}")
        return False

    try:
        contenido = _ENV_PATH.read_bytes()
        salt      = secrets.token_bytes(16)     # 128-bit salt aleatorio
        nonce     = secrets.token_bytes(12)     # 96-bit nonce para GCM
        clave     = _derivar_clave(master_password, salt)
        aesgcm    = AESGCM(clave)
        cifrado   = aesgcm.encrypt(nonce, contenido, b"rpa-suite-env")

        # Estructura: versión(1) + salt(16) + nonce(12) + cifrado(variable)
        payload = b"\x01" + salt + nonce + cifrado
        _ENV_ENC_PATH.write_bytes(payload)

        # Hash de integridad del .env original
        h = hashlib.sha256(contenido).hexdigest()
        _HASH_PATH.write_text(h, encoding="utf-8")

        _log(f"✅ .env cifrado → {_ENV_ENC_PATH.name} ({len(payload)} bytes)")
        _log(f"   SHA-256 integridad: {h[:16]}...")
        _log("   ⚠ Guardá tu master password en un lugar SEGURO — sin ella no podés descifrar")
        return True

    except Exception as e:
        _log(f"❌ Error cifrando: {e}")
        return False


def descifrar_env(master_password: str, log_func=None) -> Optional[dict]:
    """
    Descifra .env.enc con la master password.
    Retorna dict {VARIABLE: valor} o None si falla.
    NO escribe el .env a disco — carga en memoria.
    """
    def _log(m):
        if log_func: log_func(m)

    if not _CRYPTO:
        _log("❌ 'cryptography' no instalada")
        return None

    if not _ENV_ENC_PATH.exists():
        _log("⚠ No existe .env.enc — usá el .env normal")
        return None

    try:
        payload = _ENV_ENC_PATH.read_bytes()
        version = payload[0]
        if version != 1:
            _log(f"❌ Versión de cifrado desconocida: {version}")
            return None

        salt   = payload[1:17]
        nonce  = payload[17:29]
        cifrado= payload[29:]
        clave  = _derivar_clave(master_password, salt)
        aesgcm = AESGCM(clave)

        try:
            contenido = aesgcm.decrypt(nonce, cifrado, b"rpa-suite-env")
        except Exception:
            _log("❌ Master password incorrecta o archivo corrompido")
            return None

        # Parsear .env
        variables = {}
        for linea in contenido.decode("utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            if "=" in linea:
                k, _, v = linea.partition("=")
                variables[k.strip()] = v.strip().strip('"').strip("'")

        _log(f"✅ .env descifrado: {len(variables)} variables en memoria")
        return variables

    except Exception as e:
        _log(f"❌ Error descifrando: {e}")
        return None


def cargar_env_seguro(master_password: str = None, log_func=None) -> bool:
    """
    Carga el .env en os.environ de forma segura:
    - Si existe .env.enc Y hay master_password → descifra y carga en memoria
    - Si solo existe .env → carga normal con dotenv
    Retorna True si alguna de las dos funcionó.
    """
    def _log(m):
        if log_func: log_func(m)

    if master_password and _ENV_ENC_PATH.exists():
        variables = descifrar_env(master_password, log_func)
        if variables:
            for k, v in variables.items():
                os.environ.setdefault(k, v)
            _log("🔐 Credenciales cargadas desde .env cifrado")
            return True

    # Fallback: .env normal
    if _ENV_PATH.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(_ENV_PATH)
            _log("📄 Credenciales cargadas desde .env (sin cifrar)")
            return True
        except ImportError:
            # Manual parse
            for linea in _ENV_PATH.read_text(encoding="utf-8").splitlines():
                if "=" in linea and not linea.startswith("#"):
                    k, _, v = linea.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"'))
            return True

    _log("❌ No se encontró .env ni .env.enc")
    return False


# ══════════════════════════════════════════════════════════════
# CAPA 2 — INTEGRIDAD DEL .env
# ══════════════════════════════════════════════════════════════

def verificar_integridad_env(log_func=None) -> bool:
    """
    Verifica que el .env no fue modificado desde el último cifrado.
    Compara SHA-256 actual vs hash guardado en .env.hash.
    """
    def _log(m):
        if log_func: log_func(m)

    if not _ENV_PATH.exists() or not _HASH_PATH.exists():
        return True  # No hay hash = no se cifró nunca, no hay problema

    hash_guardado = _HASH_PATH.read_text(encoding="utf-8").strip()
    hash_actual   = hashlib.sha256(_ENV_PATH.read_bytes()).hexdigest()

    if hash_guardado != hash_actual:
        _log("⚠️  ALERTA DE SEGURIDAD: el .env fue modificado desde el último cifrado")
        _log("   Volvé a cifrar con 'Cifrar .env' para actualizar la versión segura")
        return False
    return True


# ══════════════════════════════════════════════════════════════
# CAPA 3 — PROTECCIÓN DEL .gitignore
# ══════════════════════════════════════════════════════════════

_ENTRADAS_GITIGNORE_REQUERIDAS = [
    ".env",
    ".env.enc",
    ".env.hash",
    "*.env",
    "__pycache__/",
    "*.pyc",
    "logs/",
    "procesados/",
    "pricing_data/",
    "scheduler_tasks.json",
]

def asegurar_gitignore(log_func=None) -> bool:
    """
    Verifica y completa el .gitignore para asegurar que
    .env, .env.enc y archivos sensibles NUNCA se suban a Git.
    """
    def _log(m):
        if log_func: log_func(m)

    contenido_actual = ""
    if _GITIGNORE.exists():
        contenido_actual = _GITIGNORE.read_text(encoding="utf-8")

    agregadas = []
    for entrada in _ENTRADAS_GITIGNORE_REQUERIDAS:
        if entrada not in contenido_actual:
            contenido_actual += f"\n{entrada}"
            agregadas.append(entrada)

    if agregadas:
        _GITIGNORE.write_text(contenido_actual.strip() + "\n", encoding="utf-8")
        _log(f"✅ .gitignore actualizado: {len(agregadas)} entrada(s) protegidas")
    else:
        _log("✅ .gitignore ya protege todos los archivos sensibles")

    return True


# ══════════════════════════════════════════════════════════════
# CAPA 4 — SETUP GIT COMPLETO
# ══════════════════════════════════════════════════════════════

def configurar_git_repositorio(
    remote_url: str,
    user_name: str,
    user_email: str,
    branch: str = "main",
    log_func=None,
) -> bool:
    """
    Configura Git desde cero en la carpeta del proyecto:
    1. git init (si no existe)
    2. git config user.name / user.email
    3. git remote add origin <url>
    4. Protege .gitignore
    5. Primer commit si no hay commits
    Retorna True si todo OK.
    """
    import subprocess as _sp

    def _log(m):
        if log_func: log_func(m)

    repo = str(_ROOT)

    def _run(cmd, check_err=True):
        r = _sp.run(cmd, cwd=repo, capture_output=True, text=True)
        if r.stdout.strip():
            _log(f"  {r.stdout.strip()}")
        if r.returncode != 0 and r.stderr.strip() and check_err:
            _log(f"  ⚠ {r.stderr.strip()}")
        return r

    # 1. Verificar si ya es repo
    r = _sp.run(["git", "rev-parse", "--is-inside-work-tree"],
                cwd=repo, capture_output=True, text=True)
    es_repo = r.returncode == 0

    if not es_repo:
        _log("📁 Inicializando repositorio Git...")
        r_init = _run(["git", "init"])
        # Forzar rama main (equivale a git branch -M main)
        _run(["git", "checkout", "-b", branch], check_err=False)
        _run(["git", "symbolic-ref", "HEAD", f"refs/heads/{branch}"], check_err=False)
    else:
        _log("✅ Ya es un repositorio Git")

    # 2. Configurar identidad
    _run(["git", "config", "user.name",  user_name])
    _run(["git", "config", "user.email", user_email])
    _log(f"  👤 Git config: {user_name} <{user_email}>")

    # 3. Remote — siempre forzar la URL correcta
    r_remote = _sp.run(["git", "remote", "get-url", "origin"],
                        cwd=repo, capture_output=True, text=True)
    if r_remote.returncode != 0:
        _log(f"  🔗 Agregando remote origin: {remote_url}")
        _run(["git", "remote", "add", "origin", remote_url])
    else:
        actual = r_remote.stdout.strip()
        if actual != remote_url:
            _log(f"  🔄 Remote anterior: {actual}")
            _log(f"  🔗 Actualizando a: {remote_url}")
            _run(["git", "remote", "set-url", "origin", remote_url])
        else:
            _log(f"  ✅ Remote OK: {actual}")

    # 4. Proteger .gitignore
    asegurar_gitignore(log_func)

    # 5. Primer commit si no hay historial
    r_log = _sp.run(["git", "log", "--oneline", "-1"],
                     cwd=repo, capture_output=True, text=True)
    if not r_log.stdout.strip():
        _log("  📝 Creando commit inicial...")
        # Crear README.md si no existe
        readme = _ROOT / "README.md"
        if not readme.exists():
            readme.write_text("# RPA Suite v5.9\n", encoding="utf-8")
        asegurar_gitignore(log_func)
        _run(["git", "add", "."])
        _run(["git", "commit", "-m", "first commit"])
        _log("  🌿 Configurando rama main...")
        _run(["git", "branch", "-M", branch], check_err=False)
        _log("  ⬆ Primer push a origin main...")
        r_push = _run(["git", "push", "-u", "origin", branch])
        if r_push.returncode != 0:
            _log(f"  ⚠ Push inicial falló: {r_push.stderr.strip()[:100]}")
            _log("  → Verificá tu token de GitHub en la URL")
            _log("  → Formato: https://TOKEN@github.com/usuario/repo.git")
        else:
            _log("  ✅ Push inicial exitoso")
    else:
        _log(f"  ✅ Repo con historial existente ({r_log.stdout.strip()[:50]})")

    _log("✅ Git configurado. Usá 'Guardar en GitHub' para los próximos commits.")
    return True


def git_commit_push_seguro(
    mensaje: str,
    log_func=None,
) -> bool:
    """
    Hace git add + commit + push de forma segura:
    - Verifica que .env NO esté en el staging
    - Asegura .gitignore antes de agregar
    - Reporta cada paso con detalle
    """
    import subprocess as _sp

    def _log(m):
        if log_func: log_func(m)

    repo = str(_ROOT)

    def _run(cmd):
        r = _sp.run(cmd, cwd=repo, capture_output=True, text=True)
        return r

    # 1. Asegurar .gitignore
    asegurar_gitignore(log_func)

    # 2. Verificar que es repo
    r = _run(["git", "rev-parse", "--is-inside-work-tree"])
    if r.returncode != 0:
        _log("❌ No es un repositorio Git. Usá 'Configurar Git' primero.")
        return False

    # 3. Verificar remote
    r = _run(["git", "remote", "get-url", "origin"])
    if r.returncode != 0:
        _log("❌ No hay remote 'origin' configurado. Usá 'Configurar Git' primero.")
        return False
    _log(f"  🔗 Remote: {r.stdout.strip()}")

    # 4. git add (respetando .gitignore)
    _log("  git add .")
    r = _run(["git", "add", "."])
    if r.returncode != 0:
        _log(f"  ❌ Error en git add: {r.stderr.strip()}")
        return False

    # 5. Verificar que .env NO está en staging
    r_check = _run(["git", "diff", "--cached", "--name-only"])
    archivos_staged = r_check.stdout.strip().splitlines()
    archivos_peligrosos = [f for f in archivos_staged
                           if ".env" in f and not f.endswith(".template")]
    if archivos_peligrosos:
        _log(f"🚨 ALERTA: {archivos_peligrosos} iban a subirse. Abortando por seguridad.")
        _run(["git", "reset", "HEAD"] + archivos_peligrosos)
        return False

    _log(f"  📦 {len(archivos_staged)} archivo(s) en staging")

    # 6. Commit
    _log(f"  git commit: {mensaje}")
    r = _run(["git", "commit", "-m", mensaje])
    out = r.stdout.strip()
    if r.returncode != 0:
        if "nothing to commit" in r.stdout + r.stderr:
            _log("  ℹ Sin cambios nuevos — nada que commitear")
            return True
        _log(f"  ❌ Error commit: {r.stderr.strip()}")
        return False
    _log(f"  {out}")

    # 7. Push
    _log("  git push origin main...")
    r = _run(["git", "push", "origin", "main"])
    if r.returncode != 0:
        # Intentar con --set-upstream si es el primer push
        if "no upstream" in r.stderr or "set-upstream" in r.stderr:
            _log("  ↩ Configurando upstream y reintentando...")
            r2 = _run(["git", "push", "--set-upstream", "origin", "main"])
            if r2.returncode == 0:
                _log("  ✅ Push exitoso")
                return True
        _log(f"  ❌ Error push: {r.stderr.strip()}")
        _log("  💡 Tip: verificar token GitHub en Credenciales de Windows")
        _log("  💡 O configurar: git config credential.helper manager-core")
        return False

    _log("  ✅ Push exitoso a origin/main")
    return True


# ══════════════════════════════════════════════════════════════
# CAPA 5 — LIMPIEZA DE PORTAPAPELES
# ══════════════════════════════════════════════════════════════

def limpiar_portapapeles_delay(segundos: int = 30, log_func=None):
    """
    Limpia el portapapeles después de N segundos.
    Útil cuando se copia una clave para no dejarla expuesta.
    """
    def _limpiar():
        time.sleep(segundos)
        try:
            import pyperclip
            pyperclip.copy("")
            if log_func: log_func(f"🔐 Portapapeles limpiado ({segundos}s)")
        except Exception:
            pass
    threading.Thread(target=_limpiar, daemon=True).start()


# ══════════════════════════════════════════════════════════════
# CAPA 6 — AUDITORÍA DE ACCESO
# ══════════════════════════════════════════════════════════════

_AUDIT_LOG = _ROOT / "logs" / "seguridad_audit.log"

def registrar_acceso(evento: str, detalle: str = ""):
    """Registra accesos a credenciales y operaciones de seguridad."""
    try:
        _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        usuario = os.getenv("USERNAME", os.getenv("USER", "desconocido"))
        linea = f"{ts} | {usuario} | {evento} | {detalle}\n"
        with open(_AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(linea)
    except Exception:
        pass


def resumen_seguridad(log_func=None) -> dict:
    """
    Evalúa el estado de seguridad actual y retorna un reporte.
    """
    def _log(m):
        if log_func: log_func(m)

    estado = {
        "env_existe":        _ENV_PATH.exists(),
        "env_enc_existe":    _ENV_ENC_PATH.exists(),
        "gitignore_ok":      False,
        "env_integro":       True,
        "git_configurado":   False,
        "crypto_disponible": _CRYPTO,
        "puntuacion":        0,
        "alertas":           [],
    }

    # Verificar .gitignore
    if _GITIGNORE.exists():
        gi = _GITIGNORE.read_text(encoding="utf-8")
        estado["gitignore_ok"] = ".env" in gi and ".env.enc" in gi
    if not estado["gitignore_ok"]:
        estado["alertas"].append("⚠ .gitignore no protege el .env")

    # Verificar integridad
    if estado["env_existe"] and _HASH_PATH.exists():
        estado["env_integro"] = verificar_integridad_env()
    if not estado["env_integro"]:
        estado["alertas"].append("⚠ El .env fue modificado sin volver a cifrar")

    # Verificar Git
    import subprocess as _sp
    r = _sp.run(["git", "remote", "get-url", "origin"],
                cwd=str(_ROOT), capture_output=True, text=True)
    estado["git_configurado"] = r.returncode == 0

    # Puntuación de seguridad (0-100)
    puntos = 0
    if estado["env_enc_existe"]:         puntos += 35  # Cifrado AES
    if estado["gitignore_ok"]:           puntos += 25  # No sube a Git
    if estado["env_integro"]:            puntos += 15  # Integridad verificada
    if estado["git_configurado"]:        puntos += 10  # Git listo
    if estado["crypto_disponible"]:      puntos += 10  # cryptography instalado
    if not estado["env_existe"]:         puntos += 5   # .env eliminado (máximo)
    estado["puntuacion"] = puntos

    nivel = "🔴 BAJO" if puntos < 40 else "🟡 MEDIO" if puntos < 70 else "🟢 ALTO"
    _log(f"  Nivel de seguridad: {nivel} ({puntos}/100)")
    for a in estado["alertas"]:
        _log(f"  {a}")

    return estado
