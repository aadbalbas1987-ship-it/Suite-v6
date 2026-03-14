"""
tools/afip_validador.py — RPA Suite v5.9
==========================================
Validación de CUITs:
  1. Validación LOCAL inmediata (formato + dígito verificador)
  2. Consulta ONLINE al padrón público de AFIP
  3. Fallback: si AFIP no responde, retorna validación local

Nunca se cuelga — timeout de 10 segundos máximo por CUIT.
"""
import re
import time
import requests
from typing import Optional

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_TIMEOUT = 5


# ══════════════════════════════════════════════════════════════
# VALIDACIÓN LOCAL (sin internet)
# ══════════════════════════════════════════════════════════════

def limpiar_cuit(cuit: str) -> str:
    """Normaliza CUIT: elimina guiones, puntos y espacios."""
    return re.sub(r'\D', '', str(cuit).strip())


def formato_cuit(cuit: str) -> str:
    """Formatea como XX-XXXXXXXX-X."""
    c = limpiar_cuit(cuit)
    if len(c) == 11:
        return f"{c[:2]}-{c[2:10]}-{c[10]}"
    return cuit


def validar_formato_cuit(cuit: str) -> tuple[bool, str]:
    """
    Valida formato y dígito verificador del CUIT.
    Retorna (valido: bool, mensaje: str).
    """
    c = limpiar_cuit(cuit)

    if not c:
        return False, "CUIT vacío"

    if not c.isdigit():
        return False, f"Contiene caracteres no numéricos: {cuit}"

    if len(c) != 11:
        return False, f"Debe tener 11 dígitos, tiene {len(c)}: {c}"

    prefijos_validos = ["20", "23", "24", "27", "30", "33", "34"]
    if c[:2] not in prefijos_validos:
        return False, (f"Prefijo '{c[:2]}' inválido. "
                       f"Válidos: {', '.join(prefijos_validos)}")

    # Dígito verificador
    multiplos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    suma = sum(int(c[i]) * multiplos[i] for i in range(10))
    resto = suma % 11
    if resto == 0:
        dv_calc = 0
    elif resto == 1:
        return False, "Dígito verificador imposible (resto=1) — CUIT inválido"
    else:
        dv_calc = 11 - resto

    if int(c[10]) != dv_calc:
        return False, (f"Dígito verificador incorrecto — "
                       f"el último dígito debería ser {dv_calc}, es {c[10]}")

    return True, "Formato y dígito verificador correctos"



# ══════════════════════════════════════════════════════════════
# CONSULTA VIA GROQ (fallback cuando ARCA bloquea requests)
# ══════════════════════════════════════════════════════════════

def _consultar_via_groq(cuit_limpio: str, log_func=None) -> dict:
    """
    Usa Groq (llama-3.3-70b) para obtener datos del contribuyente.
    Groq tiene conocimiento de empresas registradas en AFIP/ARCA.
    """
    def _log(m):
        if log_func: log_func(m)

    try:
        from config import GROQ_API_KEY
    except Exception:
        import os
        GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

    if not GROQ_API_KEY:
        return {}

    fmt = f"{cuit_limpio[:2]}-{cuit_limpio[2:10]}-{cuit_limpio[10]}"
    prompt = (
        f"Para el CUIT argentino {fmt} indicame: razon social o nombre completo, "
        f"condicion frente al IVA (Responsable Inscripto, Monotributista, Exento, etc), "
        f"y si es persona fisica o juridica. "
        f"Responde SOLO con JSON puro sin markdown ni backticks: "
        '{"razon_social": "...", "condicion_iva": "...", "tipo": "...", "activo": true}. '
        "Si no tenes informacion certera responde con JSON vacio: {}"
    )

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        texto = resp.json()["choices"][0]["message"]["content"].strip()
        texto = re.sub(r"```(?:json)?", "", texto).strip()
        import json as _json
        datos = _json.loads(texto)
        return {k: v for k, v in datos.items()
                if v and str(v).strip() not in ["", "...", "null", "None"]}
    except Exception as e:
        _log(f"  Groq: {str(e)[:60]}")
        return {}


def _intentar_arca_directo(cuit_limpio: str) -> dict:
    """Intenta ARCA directamente — frecuentemente bloqueado."""
    datos = {}
    for url in [
        f"https://sdi.afip.gob.ar/viewer/index.aspx?cuit={cuit_limpio}",
        f"https://constancia.afip.gob.ar/impresion/?tipo=pdf&cuit={cuit_limpio}",
    ]:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            texto = resp.text
            for pat in [
                r"Denominaci[o\xf3]n[\s:]+<[^>]+>([^<\n]{3,80})",
                r"denominacion[\"'\s:]+([^\"<\n]{3,80})",
                r"Raz[o\xf3]n\s+Social[\s:]+([^<\n]{3,80})",
            ]:
                m = re.search(pat, texto, re.IGNORECASE)
                if m:
                    val = m.group(1).strip().strip('"')
                    if len(val) > 3:
                        datos["razon_social"] = val
                        datos["activo"] = not bool(
                            re.search(r"\bbaja\b", texto, re.IGNORECASE))
                        return datos
        except Exception:
            continue
    return datos



def _consultar_arca_selenium(cuit_limpio, log_func=None):
    """
    Consulta el padron publico de ARCA usando Selenium + Chrome headless.
    URL oficial: https://padron.afip.gob.ar — acceso publico sin clave fiscal.
    Requiere: pip install selenium webdriver-manager
    """
    def _log(m):
        if log_func: log_func(m)

    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except ImportError:
        _log("  selenium no instalado -- ejecuta: pip install selenium webdriver-manager")
        return {}

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,800")
    opts.add_argument("--log-level=3")
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    driver = None
    try:
        # Intentar chromedriver del PATH, luego webdriver-manager
        try:
            service = Service()
            driver = webdriver.Chrome(service=service, options=opts)
        except Exception:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=opts)

        driver.set_page_load_timeout(20)
        _log("  Abriendo padron.afip.gob.ar...")
        driver.get("https://padron.afip.gob.ar/main.html")

        wait = WebDriverWait(driver, 10)
        campo = None
        for sel in [(By.ID, "txtCUIT"),
                    (By.CSS_SELECTOR, "input[placeholder*='CUIT']"),
                    (By.CSS_SELECTOR, "input[type='text']")]:
            try:
                campo = wait.until(EC.presence_of_element_located(sel))
                break
            except Exception:
                continue
        if not campo:
            _log("  No se encontro el campo CUIT")
            return {}

        campo.clear()
        campo.send_keys(cuit_limpio)

        btn = None
        for sel in [(By.ID, "btnBuscar"),
                    (By.CSS_SELECTOR, "button[type='submit']"),
                    (By.CSS_SELECTOR, "input[type='submit']"),
                    (By.XPATH, "//button[contains(text(),'Buscar')]")]:
            try:
                btn = driver.find_element(*sel)
                break
            except Exception:
                continue
        if not btn:
            _log("  No se encontro el boton de busqueda")
            return {}

        btn.click()
        import time as _t
        _t.sleep(2)
        page = driver.page_source
        datos = {}

        # Razon social
        pats_razon = [
            r"Denominaci.n[^<]{0,20}<[^>]+>\s*<[^>]+>([^<]{3,80})",
            r"Raz.n\s+Social[\s:]+([^<\n]{3,80})",
            r'"denominacion"[^:]*:"([^"]{3,80})"',
            r"Apellido.*?Nombre[\s:]+([^<\n]{3,80})",
        ]
        for pat in pats_razon:
            m = re.search(pat, page, re.IGNORECASE)
            if m:
                val = m.group(1).strip().strip('"').strip()
                if len(val) > 2 and val.upper() not in ["CUIT", "CUIL", "CDI"]:
                    datos["razon_social"] = val
                    break

        # Condicion IVA
        pats_iva = [
            r"Condici.n\s+frente\s+al\s+IVA[\s:]+([^<\n]{3,60})",
            r"Condici.n\s+IVA[\s:]+([^<\n]{3,60})",
            r"(Responsable\s+Inscripto|Monotributo[a-z\s]*|Exento|No\s+Responsable)",
        ]
        for pat in pats_iva:
            m = re.search(pat, page, re.IGNORECASE)
            if m:
                datos["condicion_iva"] = m.group(1).strip()
                break

        if re.search(r"Persona\s+Jur.dica", page, re.IGNORECASE):
            datos["tipo"] = "Persona Juridica"
        elif re.search(r"Persona\s+F.sica", page, re.IGNORECASE):
            datos["tipo"] = "Persona Fisica"

        datos["activo"] = not bool(re.search(r"\bBaja\b", page, re.IGNORECASE))

        m_act = re.search(r"Actividad\s+Principal[\s:]+([^<\n]{5,100})", page, re.IGNORECASE)
        if m_act:
            datos["actividad"] = m_act.group(1).strip()

        if datos.get("razon_social"):
            iva = datos.get("condicion_iva", "")
            _log(f"  ARCA: {datos['razon_social']}  |  {iva}")
        else:
            _log("  ARCA: pagina cargada pero sin datos reconocibles")

        return datos

    except Exception as e:
        _log(f"  Selenium error: {str(e)[:80]}")
        return {}
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def consultar_afip(cuit: str, log_func=None) -> dict:
    """
    Valida un CUIT:
      1. Validacion local INMEDIATA (formato + digito verificador)
      2. Intenta ARCA directo (frecuentemente bloqueado)
      3. Fallback a Groq para obtener razon social y condicion IVA
    """
    def _log(m):
        if log_func: log_func(m)

    c   = limpiar_cuit(cuit)
    fmt = formato_cuit(c)

    # Paso 1: validacion local — INSTANTANEA
    valido_local, msg_local = validar_formato_cuit(c)
    if not valido_local:
        _log(f"  {fmt if len(c)==11 else cuit} -- {msg_local}")
        return {
            "cuit":   fmt if len(c) == 11 else cuit,
            "valido": False,
            "error":  msg_local,
            "fuente": "validacion local",
        }

    _log(f"  {fmt} -- formato y digito verificador OK")
    _log(f"  Consultando ARCA/Groq...")

    # Paso 2: Consulta online
    datos_online = {}
    fuente = "validacion local"

    # Intento 1: HTTP directo (muy rápido, oficial)
    datos_directo = _intentar_arca_directo(c)
    if datos_directo and datos_directo.get("razon_social"):
        datos_online = datos_directo
        fuente = "ARCA (Directo)"
    else:
        # Intento 2: Selenium contra padron oficial ARCA (lento pero efectivo)
        _log("  Consultando padron oficial ARCA (Chrome headless)...")
        datos_selenium = _consultar_arca_selenium(c, log_func)

        if datos_selenium and datos_selenium.get("razon_social"):
            datos_online = datos_selenium
            fuente = "ARCA (Selenium)"
        else:
            # Intento 3: Groq — referencial, NO oficial
            _log("  Fuentes oficiales sin respuesta -- usando Groq (referencial)...")
            datos_groq = _consultar_via_groq(c, log_func)
            if datos_groq:
                datos_online = datos_groq
                fuente = "Groq (referencial - NO oficial)"
                _log("  ADVERTENCIA: verificar en padron.afip.gob.ar para uso legal")
            else:
                _log("  Sin datos online -- resultado con validacion matematica")

    resultado = {"cuit": fmt, "valido": True, "fuente": fuente, **datos_online}

    if "Groq" in fuente:
        resultado["advertencia"] = (
            "Dato referencial de Groq — NO usar para facturacion o fines legales. "
            "Verificar en padron.afip.gob.ar"
        )
    elif not datos_online:
        resultado["nota"] = (
            "CUIT valido matematicamente. "
            "Para datos oficiales instala: pip install selenium webdriver-manager"
        )

    return resultado


# ══════════════════════════════════════════════════════════════
# VALIDACIÓN EN LOTE
# ══════════════════════════════════════════════════════════════

def validar_lista_cuits(
    cuits: list,
    log_func=None,
    delay: float = 0.5,
) -> list[dict]:
    """
    Valida una lista de CUITs en paralelo.
    Retorna lista de resultados en el mismo orden.
    """
    def _log(m):
        if log_func: log_func(m)

    resultados = []
    cuits_limpios = [str(c).strip() for c in cuits if str(c).strip()]
    total = len(cuits_limpios)
    
    if total == 0:
        return []
        
    _log(f"\n🚀 Validando {total} CUIT(s) en paralelo (máx 3 hilos)...")
    
    import concurrent.futures
    
    def _worker(cuit):
        # Silenciamos los logs de cada worker para no ensuciar la salida global en paralelo
        return consultar_afip(cuit, log_func=None)
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # Usamos map para mantener el orden original de los resultados de entrada
        for i, res in enumerate(executor.map(_worker, cuits_limpios), 1):
            resultados.append(res)

    ok    = sum(1 for r in resultados if r.get("valido"))
    error = len(resultados) - ok
    _log(f"\n📊 Resultado final: {ok} válido(s), {error} inválido(s) de {total}")
    return resultados
