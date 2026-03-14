"""
tools/categorizador.py — RPA Suite v5.9
=========================================
Asigna automáticamente FAMILIA/DPTO/SECCION/GRUPO a un artículo nuevo
comparando su descripción contra Categori.txt usando Groq (llama-3.3-70b).

Formato Categori.txt:
  FAMILIA<TAB>DPTO<TAB>SECCION<TAB>GRUPO<TAB>DESCRIPCION
  Sin encabezados, separado por tabulación.
"""
import re
import json
from pathlib import Path
from typing import Optional

CATEGORI_PATH = Path(__file__).parent.parent / "Categori.txt"
CACHE_PATH = Path(__file__).parent.parent / "categori_cache.json"

_mem_cache = None

def _get_cache() -> dict:
    global _mem_cache
    if _mem_cache is None:
        if CACHE_PATH.exists():
            try:
                _mem_cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            except Exception:
                _mem_cache = {}
        else:
            _mem_cache = {}
    return _mem_cache

def _save_cache():
    if _mem_cache is not None:
        CACHE_PATH.write_text(json.dumps(_mem_cache, ensure_ascii=False, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════════════════════
# CARGA DEL ARCHIVO
# ══════════════════════════════════════════════════════════════

def cargar_categori(path=None) -> list[dict]:
    """
    Carga Categori.txt y retorna lista de dicts:
      [{"familia": 3, "dpto": 1, "seccion": 1, "grupo": 4,
        "descripcion": "Good Show Papas Sabor Cheddar X 63Grs"}, ...]
    """
    ruta = Path(path) if path else CATEGORI_PATH
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró {ruta}")

    registros = []
    for i, linea in enumerate(ruta.read_text(encoding="latin-1").splitlines(), 1):
        linea = linea.strip()
        if not linea:
            continue
        partes = linea.split("\t")
        if len(partes) < 5:
            continue
        try:
            registros.append({
                "familia":    int(partes[0].strip()),
                "dpto":       int(partes[1].strip()),
                "seccion":    int(partes[2].strip()),
                "grupo":      int(partes[3].strip()),
                "descripcion": partes[4].strip(),
            })
        except ValueError:
            continue  # saltar líneas malformadas

    return registros


def _crear_indice_invertido(registros: list[dict]) -> dict:
    """Crea un índice invertido: palabra -> set de índices de registros."""
    indice = {}
    for i, reg in enumerate(registros):
        palabras = _palabras_clave(reg["descripcion"])
        for p in palabras:
            if p not in indice:
                indice[p] = set()
            indice[p].add(i)
    return indice

# ══════════════════════════════════════════════════════════════
# BÚSQUEDA POR PALABRAS CLAVE (pre-filtro rápido)
# ══════════════════════════════════════════════════════════════

def _palabras_clave(descripcion: str) -> list[str]:
    """Extrae palabras significativas (len >= 3, no stopwords)."""
    stopwords = {"con", "sin", "por", "para", "del", "las", "los",
                 "una", "uno", "unos", "unas", "grs", "gms", "kgs",
                 "litros", "lts", "ml", "kg", "cm", "und", "x"}
    return [p for p in re.sub(r"[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ\s]", " ",
                               descripcion).lower().split()
            if len(p) >= 3 and p not in stopwords]


def _prefilter(descripcion: str, registros: list[dict],
               indice_invertido: Optional[dict] = None,
               max_candidatos: int = 60) -> list[dict]:
    """
    Filtra el catálogo buscando registros que compartan
    al menos 1 palabra clave con la descripción nueva.
    Usa un índice invertido si se provee para mayor velocidad.
    """
    palabras = _palabras_clave(descripcion)
    if not palabras:
        return registros[:max_candidatos]

    # --- Ruta rápida con índice invertido ---
    if indice_invertido:
        indices_coincidentes = set()
        for p in palabras:
            indices_coincidentes.update(indice_invertido.get(p, set()))
        if not indices_coincidentes:
            return registros[:max_candidatos]
        coincidentes = [registros[i] for i in sorted(list(indices_coincidentes))]
        return coincidentes[:max_candidatos]

    # --- Ruta lenta (fallback si no hay índice) ---
    coincidentes = []
    for reg in registros:
        desc_lower = reg["descripcion"].lower()
        if any(p in desc_lower for p in palabras):
            coincidentes.append(reg)

    return coincidentes[:max_candidatos] if coincidentes else registros[:max_candidatos]


# ══════════════════════════════════════════════════════════════
# CATEGORIZACIÓN CON GROQ
# ══════════════════════════════════════════════════════════════

def categorizar_con_groq(descripcion_nueva: str,
                          registros: list[dict],
                          indice_invertido: Optional[dict] = None,
                          log_func=None) -> Optional[dict]:
    """
    Usa Groq para encontrar el registro más similar y devuelve
    {"familia": X, "dpto": X, "seccion": X, "grupo": X,
     "descripcion_match": "...", "confianza": "alta/media/baja"}
    Retorna None si falla.
    """
    def _log(m):
        if log_func: log_func(m)

    try:
        from config import GROQ_API_KEY
    except Exception:
        import os
        GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

    if not GROQ_API_KEY:
        _log("  Groq: GROQ_API_KEY no configurada")
        return None
        
    cache = _get_cache()
    if descripcion_nueva in cache:
        _log("  ⚡ Recuperado de caché (sin costo API)")
        return cache[descripcion_nueva]

    # Pre-filtrar candidatos relevantes
    candidatos = _prefilter(descripcion_nueva, registros,
                            indice_invertido=indice_invertido, max_candidatos=60)

    # Construir lista compacta para el prompt
    lista = "\n".join(
        f"{i+1}. [{r['familia']}-{r['dpto']}-{r['seccion']}-{r['grupo']}] {r['descripcion']}"
        for i, r in enumerate(candidatos)
    )

    prompt = (
        f"Tengo un artículo nuevo: \"{descripcion_nueva}\"\n\n"
        f"Del siguiente catálogo, ¿cuál es el artículo más similar "
        f"en cuanto a tipo de producto, categoría y características?\n\n"
        f"{lista}\n\n"
        f"Respondé SOLO con JSON puro sin markdown:\n"
        f'{{ "numero": <número de la lista>, "confianza": "alta|media|baja" }}\n'
        f"Usá \"baja\" si ninguno se parece bien."
    )

    try:
        import requests
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.1,
            },
            timeout=15,
        )
        resp.raise_for_status()
        texto = resp.json()["choices"][0]["message"]["content"].strip()
        texto = re.sub(r"```(?:json)?", "", texto).strip()
        resultado = json.loads(texto)

        numero = int(resultado.get("numero", 0))
        if numero < 1 or numero > len(candidatos):
            _log(f"  Groq: numero {numero} fuera de rango")
            return None

        match = candidatos[numero - 1]
        confianza = resultado.get("confianza", "media")

        res_final = {
            "familia":           match["familia"],
            "dpto":              match["dpto"],
            "seccion":           match["seccion"],
            "grupo":             match["grupo"],
            "descripcion_match": match["descripcion"],
            "confianza":         confianza,
        }
        
        cache[descripcion_nueva] = res_final
        _save_cache()
        return res_final

    except Exception as e:
        _log(f"  Groq error: {str(e)[:80]}")
        return None


# ══════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════

def asignar_categori(descripcion: str,
                      categori_path=None,
                      log_func=None) -> Optional[dict]:
    """
    Función principal. Dado una descripción de artículo nuevo,
    devuelve el categori asignado:
      {
        "familia": 3, "dpto": 1, "seccion": 1, "grupo": 4,
        "descripcion_match": "Good Show Papas Sabor Cheddar X 63Grs",
        "confianza": "alta"
      }
    Retorna None si no se puede asignar.
    """
    def _log(m):
        if log_func: log_func(m)

    try:
        registros = cargar_categori(categori_path)
        _log(f"  Categori.txt cargado: {len(registros)} registros.")
        indice_invertido = _crear_indice_invertido(registros)
        _log(f"  Índice creado con {len(indice_invertido)} palabras clave.")
    except FileNotFoundError as e:
        _log(f"  {e}")
        return None

    _log(f"  Analizando: \"{descripcion}\"")
    resultado = categorizar_con_groq(descripcion, registros, indice_invertido, log_func)

    if resultado:
        c = resultado["confianza"]
        _log(
            f"  Match ({c}): [{resultado['familia']}-{resultado['dpto']}-"
            f"{resultado['seccion']}-{resultado['grupo']}] "
            f"{resultado['descripcion_match']}"
        )
    else:
        _log("  No se pudo asignar categori automáticamente")

    return resultado


# ══════════════════════════════════════════════════════════════
# UTILIDAD: pre-categorizar todo el Excel antes del robot
# ══════════════════════════════════════════════════════════════

def precategorizar_excel(df, col_descripcion="DESCRIPCION_IA",
                          categori_path=None,
                          log_func=None) -> list[dict]:
    """
    Recibe un DataFrame con artículos a cargar y devuelve
    lista de resultados de categorización en el mismo orden.
    Procesa todos de una vez antes de arrancar el robot.
    """
    def _log(m):
        if log_func: log_func(m)

    try:
        registros = cargar_categori(categori_path)
        _log(f"  Categori.txt cargado: {len(registros)} registros.")
        _log("  Creando índice invertido para búsqueda rápida...")
        indice_invertido = _crear_indice_invertido(registros)
        _log(f"  Índice creado con {len(indice_invertido)} palabras clave.")
    except FileNotFoundError as e:
        _log(f"  {e}")
        return [None] * len(df)

    resultados = []
    total = len(df)
    for i, row in df.iterrows():
        desc = str(row.get(col_descripcion) or row.get("DESCRIPCION") or "")
        if not desc or desc == "nan":
            _log(f"  [{i+1}/{total}] Sin descripcion — categori no asignado")
            resultados.append(None)
            continue
        _log(f"  [{i+1}/{total}] {desc[:50]}")
        res = categorizar_con_groq(desc, registros, indice_invertido, log_func)
        if res:
            _log(
                f"    -> [{res['familia']}-{res['dpto']}-{res['seccion']}-{res['grupo']}] "
                f"{res['descripcion_match'][:40]} ({res['confianza']})"
            )
        else:
            _log(f"    -> Sin match")
        resultados.append(res)

    ok = sum(1 for r in resultados if r)
    _log(f"  Categorizados: {ok}/{total}")
    return resultados
