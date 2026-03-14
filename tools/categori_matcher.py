"""
tools/categori_matcher.py — RPA Suite v5.9
==========================================
Motor de asignacion automatica de categorias para articulos nuevos.

Flujo:
  1. Carga Categori.txt (TAB separado, sin encabezados)
     FAMILIA  DPTO  SECCION  GRUPO  DESCRIPCION
  2. Recibe descripcion del articulo nuevo
  3. Usa Groq para comparar semanticamente con las descripciones del txt
  4. Retorna los 4 codigos: familia, dpto, seccion, grupo

Estrategia de matching:
  - Primero busca coincidencias por palabras clave (rapido, sin API)
  - Si hay ambiguedad o baja confianza, usa Groq para decision final
  - Si Groq no esta disponible, usa el mejor match local
"""

import re
import os
from pathlib import Path
from typing import Optional

# Ruta por defecto del archivo
_DEFAULT_CATEGORI = Path(__file__).parent.parent / "Categori.txt"


def cargar_categori(ruta=None) -> list[dict]:
    """
    Carga y parsea el archivo Categori.txt.
    Retorna lista de dicts con keys: familia, dpto, seccion, grupo, descripcion
    """
    ruta = Path(ruta) if ruta else _DEFAULT_CATEGORI
    if not ruta.exists():
        raise FileNotFoundError(f"Categori.txt no encontrado en: {ruta}")

    items = []
    for linea in ruta.read_bytes().decode("latin-1").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        partes = linea.split("\t")
        if len(partes) < 5:
            continue
        items.append({
            "familia":     partes[0].strip(),
            "dpto":        partes[1].strip(),
            "seccion":     partes[2].strip(),
            "grupo":       partes[3].strip(),
            "descripcion": partes[4].strip(),
        })
    return items


def _normalizar(texto: str) -> str:
    """Normaliza texto para comparacion: minusculas, sin acentos, sin puntuacion."""
    texto = texto.lower().strip()
    reemplazos = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ä": "a", "ë": "e", "ï": "i", "ö": "o", "ü": "u",
        "ñ": "n",
    }
    for orig, repl in reemplazos.items():
        texto = texto.replace(orig, repl)
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _score_local(descripcion_nueva: str, items: list[dict]) -> list[tuple]:
    """
    Scoring rapido por palabras en comun (sin API).
    Retorna lista de (score, item) ordenada de mayor a menor.
    """
    palabras_nuevas = set(_normalizar(descripcion_nueva).split())
    # Ignorar palabras muy cortas o genéricas
    stop = {"x", "de", "la", "el", "los", "las", "con", "sin",
            "y", "e", "o", "a", "en", "gr", "ml", "kg", "lt",
            "grs", "kgs", "mls", "lts", "un", "und"}
    palabras_nuevas -= stop

    resultados = []
    for item in items:
        palabras_cat = set(_normalizar(item["descripcion"]).split()) - stop
        if not palabras_cat:
            continue
        interseccion = palabras_nuevas & palabras_cat
        # Score: palabras en comun / max(len) — premia coincidencias exactas
        score = len(interseccion) / max(len(palabras_nuevas), len(palabras_cat), 1)
        if interseccion:
            resultados.append((score, item))

    resultados.sort(key=lambda x: x[0], reverse=True)
    return resultados


def _candidatos_unicos(resultados: list[tuple], top_n=20) -> list[dict]:
    """Deduplicar por combo familia/dpto/seccion/grupo, quedarse con los top N."""
    vistos = set()
    unicos = []
    for score, item in resultados:
        key = (item["familia"], item["dpto"], item["seccion"], item["grupo"])
        if key not in vistos:
            vistos.add(key)
            unicos.append({"score": round(score, 3), **item})
        if len(unicos) >= top_n:
            break
    return unicos


def _decidir_con_groq(descripcion_nueva: str,
                       candidatos: list[dict],
                       log_func=None) -> Optional[dict]:
    """
    Usa Groq para elegir el mejor match entre los candidatos.
    Retorna el item elegido o None si falla.
    """
    def _log(m):
        if log_func: log_func(m)

    try:
        from config import GROQ_API_KEY
    except Exception:
        GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

    if not GROQ_API_KEY:
        return None

    try:
        import requests, json

        # Armar lista de candidatos para el prompt
        lista = "\n".join(
            f"{i+1}. [{c['familia']}-{c['dpto']}-{c['seccion']}-{c['grupo']}] "
            f"{c['descripcion']}"
            for i, c in enumerate(candidatos[:15])
        )

        prompt = (
            f"Tengo un articulo nuevo con descripcion: \"{descripcion_nueva}\"\n\n"
            f"Debo asignarle una categoria de esta lista:\n{lista}\n\n"
            f"Analiza semanticamente y elige el numero del item mas apropiado. "
            f"Considera tipo de producto, marca si aplica, y categoria general. "
            f"Responde SOLO con el numero del item elegido (1, 2, 3...) "
            f"y nada mas. Si ninguno es apropiado responde 0."
        )

        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 10,
                "temperature": 0.0,
            },
            timeout=10,
        )
        resp.raise_for_status()
        respuesta = resp.json()["choices"][0]["message"]["content"].strip()
        # Extraer numero
        m = re.search(r"\d+", respuesta)
        if not m:
            return None
        idx = int(m.group()) - 1
        if 0 <= idx < len(candidatos):
            return candidatos[idx]
        return None

    except Exception as e:
        _log(f"  Groq categori: {str(e)[:60]}")
        return None


def asignar_categori(descripcion: str,
                      ruta_categori=None,
                      items_precargados=None,
                      log_func=None,
                      umbral_confianza=0.3) -> dict:
    """
    Funcion principal: dado un articulo nuevo, retorna su categori.

    Args:
        descripcion:        Descripcion del articulo nuevo
        ruta_categori:      Ruta al Categori.txt (opcional, usa default)
        items_precargados:  Lista ya cargada (para no releer el archivo en cada llamada)
        log_func:           Funcion de log
        umbral_confianza:   Score minimo para confiar en match local sin Groq

    Returns:
        dict con keys: familia, dpto, seccion, grupo, descripcion_match,
                       score, metodo, confianza_alta
    """
    def _log(m):
        if log_func: log_func(m)

    items = items_precargados or cargar_categori(ruta_categori)
    _log(f"  Buscando categoria para: {descripcion}")

    # Paso 1: scoring local
    resultados = _score_local(descripcion, items)

    if not resultados:
        _log("  Sin coincidencias locales — usando Groq con muestra general")
        # Mandar los primeros 20 items como muestra al groq
        candidatos = [{"score": 0, **i} for i in items[:20]]
    else:
        candidatos = _candidatos_unicos(resultados, top_n=15)
        top_score = candidatos[0]["score"] if candidatos else 0
        _log(f"  Mejor match local: [{candidatos[0]['familia']}-{candidatos[0]['dpto']}-"
             f"{candidatos[0]['seccion']}-{candidatos[0]['grupo']}] "
             f"{candidatos[0]['descripcion']} (score={top_score:.2f})")

    # Paso 2: si el score local es alto y hay 1 candidato claro → usar directo
    top_score = candidatos[0]["score"] if candidatos else 0
    if top_score >= umbral_confianza and len(candidatos) >= 1:
        # Verificar que el segundo no sea igual de bueno (ambiguedad)
        segundo_score = candidatos[1]["score"] if len(candidatos) > 1 else 0
        diferencia = top_score - segundo_score
        if diferencia >= 0.15 or top_score >= 0.6:
            # Match claro — usar sin Groq
            elegido = candidatos[0]
            _log(f"  Match directo (score={top_score:.2f}): "
                 f"FAM={elegido['familia']} DPT={elegido['dpto']} "
                 f"SEC={elegido['seccion']} GRP={elegido['grupo']}")
            return {
                "familia":           elegido["familia"],
                "dpto":              elegido["dpto"],
                "seccion":           elegido["seccion"],
                "grupo":             elegido["grupo"],
                "descripcion_match": elegido["descripcion"],
                "score":             top_score,
                "metodo":            "local",
                "confianza_alta":    True,
            }

    # Paso 3: ambiguedad o score bajo → Groq decide
    _log(f"  Ambiguedad (top={top_score:.2f}) — consultando Groq...")
    elegido_groq = _decidir_con_groq(descripcion, candidatos, log_func)

    if elegido_groq:
        _log(f"  Groq eligio: FAM={elegido_groq['familia']} DPT={elegido_groq['dpto']} "
             f"SEC={elegido_groq['seccion']} GRP={elegido_groq['grupo']} "
             f"— {elegido_groq['descripcion']}")
        return {
            "familia":           elegido_groq["familia"],
            "dpto":              elegido_groq["dpto"],
            "seccion":           elegido_groq["seccion"],
            "grupo":             elegido_groq["grupo"],
            "descripcion_match": elegido_groq["descripcion"],
            "score":             elegido_groq.get("score", 0),
            "metodo":            "groq",
            "confianza_alta":    True,
        }

    # Paso 4: fallback — usar el mejor match local
    if candidatos:
        elegido = candidatos[0]
        confianza = top_score >= 0.40
        _log(f"  Fallback local ({'OK' if confianza else 'baja confianza'}): "
             f"FAM={elegido['familia']} DPT={elegido['dpto']} "
             f"SEC={elegido['seccion']} GRP={elegido['grupo']}")
        return {
            "familia":           elegido["familia"],
            "dpto":              elegido["dpto"],
            "seccion":           elegido["seccion"],
            "grupo":             elegido["grupo"],
            "descripcion_match": elegido["descripcion"],
            "score":             top_score,
            "metodo":            "fallback_local",
            "confianza_alta":    confianza,
        }

    # Sin ningun match
    _log("  Sin categoria asignada — revisar manualmente")
    return {
        "familia": "", "dpto": "", "seccion": "", "grupo": "",
        "descripcion_match": "", "score": 0,
        "metodo": "sin_match", "confianza_alta": False,
    }


def asignar_categori_lote(descripciones: list[str],
                           ruta_categori=None,
                           log_func=None) -> list[dict]:
    """
    Procesa una lista de descripciones en lote.
    Carga el archivo una sola vez para eficiencia.
    """
    def _log(m):
        if log_func: log_func(m)

    items = cargar_categori(ruta_categori)
    _log(f"  Categori.txt cargado: {len(items)} productos, "
         f"{len(set((i['familia'],i['dpto'],i['seccion'],i['grupo']) for i in items))} "
         f"combinaciones unicas")

    resultados = []
    for i, desc in enumerate(descripciones, 1):
        _log(f"\n  [{i}/{len(descripciones)}] {desc}")
        res = asignar_categori(desc, items_precargados=items, log_func=log_func)
        res["descripcion_input"] = desc
        resultados.append(res)

    ok = sum(1 for r in resultados if r["confianza_alta"])
    _log(f"\n  Resultado: {ok}/{len(resultados)} con alta confianza")
    return resultados


# ============================================================
# UTILIDAD: pre-categorizar todo el Excel antes del robot
# ============================================================

def precategorizar_excel(df, col_descripcion="DESCRIPCION_IA",
                          ruta_categori=None,
                          log_func=None) -> list[dict]:
    """
    Recibe un DataFrame con artículos a cargar y devuelve
    lista de resultados de categorización en el mismo orden.
    Procesa todos de una vez antes de arrancar el robot.
    """
    def _log(m):
        if log_func: log_func(m)

    items = cargar_categori(ruta_categori)
    _log(f"  Categori.txt: {len(items)} registros listos para pre-categorización")

    resultados = []
    total = len(df)
    for i, row in df.iterrows():
        desc = str(row.get(col_descripcion) or row.get("DESCRIPCION") or "")
        if not desc or desc == "nan":
            _log(f"  [{i+1}/{total}] Sin descripcion — categori no asignado")
            resultados.append(None)
            continue
        res = asignar_categori(desc, items_precargados=items, log_func=log_func)
        resultados.append(res)

    ok = sum(1 for r in resultados if r and r.get("familia"))
    _log(f"  Categorizados con éxito: {ok}/{total}")
    return resultados
