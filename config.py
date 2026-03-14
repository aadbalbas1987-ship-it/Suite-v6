"""
config.py — RPA Suite v5
========================
Punto central de configuración. Lee TODAS las credenciales desde .env.
Ningún otro archivo debe hardcodear credenciales o IPs.

Uso:
    from config import SSH, GEMINI_API_KEY, APP
    client.connect(SSH.host, port=SSH.port, username=SSH.user, password=SSH.password)
"""
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Buscamos el .env en la carpeta raíz del proyecto
_BASE_DIR = Path(__file__).parent
load_dotenv(_BASE_DIR / ".env")


def _requerir(nombre: str) -> str:
    """Lee una variable de entorno. Si no existe, lanza error con instrucción clara."""
    valor = os.getenv(nombre)
    if not valor:
        raise EnvironmentError(
            f"\n❌ Variable de entorno '{nombre}' no encontrada.\n"
            f"   → Copiá '.env.example' a '.env' y completá el valor de {nombre}.\n"
            f"   → Ruta esperada: {_BASE_DIR / '.env'}"
        )
    return valor


def _opcional(nombre: str, default: str = "") -> str:
    """Lee una variable de entorno opcional con valor por defecto."""
    return os.getenv(nombre, default)


# ============================================================
# CONFIGURACIONES
# ============================================================

@dataclass(frozen=True)
class _SSHConfig:
    host: str
    port: int
    user: str
    password: str
    default_email: str


@dataclass(frozen=True)
class _AppConfig:
    nombre: str
    sucursales: list


# --- INSTANCIAS GLOBALES ---
# Se construyen lazy para no fallar al importar si no se usa SSH

def get_ssh_config() -> _SSHConfig:
    """Retorna configuración SSH. Llama esto solo cuando vayas a conectar."""
    return _SSHConfig(
        host=_requerir("SSH_HOST"),
        port=int(_opcional("SSH_PORT", "22")),
        user=_requerir("SSH_USER"),
        password=_requerir("SSH_PASSWORD"),
        default_email=_opcional("SSH_DEFAULT_EMAIL", ""),
    )


# Gemini API Key (usada en utils.py y normalizador_articulos.py)
GEMINI_API_KEY: str = _opcional("GEMINI_API_KEY", "")


def get_gemini_key() -> str:
    """
    Retorna la Gemini API Key como string.
    Lanza EnvironmentError con instrucción clara si no está configurada.
    Compatible con normalizador_articulos.py y cualquier módulo que la necesite.
    """
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "\n\u274c GEMINI_API_KEY no encontrada.\n"
            "   \u2192 Completá el valor en .env y reiniciá la aplicación.\n"
            "   \u2192 Obtené tu key en: https://aistudio.google.com/app/apikey"
        )
    return key


# App general
APP = _AppConfig(
    nombre=_opcional("APP_NOMBRE", "RPA Suite v5"),
    sucursales=_opcional("APP_SUCURSALES", "Principal").split(","),
)

# Groq API Key (usada en Robot_Putty.py y utils.py para validación IA)
GROQ_API_KEY: str = _opcional("GROQ_API_KEY", "")
ANTHROPIC_API_KEY: str = _opcional("ANTHROPIC_API_KEY", "")

def get_groq_key() -> str:
    """
    Retorna la Groq API Key.
    Lanza EnvironmentError si no está configurada.
    """
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "\n❌ GROQ_API_KEY no encontrada.\n"
            "   → Completá el valor en .env y reiniciá la aplicación.\n"
            "   → Obtené tu key gratuita en: https://console.groq.com/"
        )
    return key


# ============================================================
# VALIDADOR DE ENTORNO (llamar al iniciar la app)
# ============================================================
def validar_entorno(requerir_ssh: bool = True, requerir_gemini: bool = True) -> list[str]:
    """
    Verifica que las variables críticas estén configuradas.
    Retorna lista de advertencias (vacía = todo OK).
    """
    warnings = []

    if requerir_gemini and not GEMINI_API_KEY:
        warnings.append("⚠️  GEMINI_API_KEY no configurada → Módulos de IA desactivados.")
    if not GROQ_API_KEY:
        warnings.append("⚠️  GROQ_API_KEY no configurada → Validación IA de archivos desactivada.")

    if requerir_ssh:
        for var in ["SSH_HOST", "SSH_USER", "SSH_PASSWORD"]:
            if not os.getenv(var):
                warnings.append(f"⚠️  {var} no configurada → Robot SSH desactivado.")
                break

    return warnings
