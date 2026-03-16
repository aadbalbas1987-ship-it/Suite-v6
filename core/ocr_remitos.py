"""
core/ocr_remitos.py — RPA Suite v6
====================================
Módulo de extracción de datos de facturas y remitos mediante OCR con Gemini 1.5 Flash.
"""

import os
import json
import pandas as pd
from pathlib import Path
from PIL import Image
import google.generativeai as genai
import sys

# Asegurar que la raíz del proyecto esté en el path
_RAIZ = Path(__file__).parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from config import get_gemini_key

def inicializar_gemini(log_func=print):
    """Configura la API de Gemini y autodetecta el mejor modelo disponible."""
    api_key = get_gemini_key()
    if not api_key:
        raise ValueError("No se encontró GEMINI_API_KEY en el archivo .env")
    genai.configure(api_key=api_key)
    
    try:
        # Pedimos a Google la lista de modelos habilitados para esta API Key
        modelos = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        modelo_elegido = None
        # Prioridad: 2.0 > 1.5 flash > 1.5 pro > fallback
        for candidato in ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']:
            if candidato in modelos:
                modelo_elegido = candidato
                break
        return genai.GenerativeModel(modelo_elegido or 'gemini-1.5-flash')
    except Exception:
        return genai.GenerativeModel('gemini-1.5-flash')

def extraer_datos_remito(ruta_imagen: str, log_func=print) -> pd.DataFrame:
    """
    Toma la ruta de una imagen (JPG, PNG) de un remito/factura, 
    la procesa con Gemini Vision y devuelve un DataFrame estructurado.
    """
    if not Path(ruta_imagen).exists():
        log_func(f"❌ El archivo no existe: {ruta_imagen}")
        return pd.DataFrame()

    try:
        model = inicializar_gemini(log_func)
        log_func("📸 Cargando imagen del remito...")
        imagen = Image.open(ruta_imagen)
        
        # Prompt estricto pidiendo JSON
        prompt = """
        Sos un experto en extracción de datos contables y logística.
        Revisá esta imagen de un remito/factura de proveedor y extraé la tabla de productos.
        
        Reglas:
        1. Extraé solo los productos facturados (ignorá totales, impuestos, etc.).
        2. Formateá los números usando punto para decimales (ej: 1500.50).
        3. Si no encontrás un código de proveedor, dejá un string vacío "".
        
        Devolvé ÚNICAMENTE un JSON válido con esta estructura exacta (una lista de objetos):
        [
          {
            "codigo_proveedor": "12345",
            "descripcion": "Nombre del producto",
            "cantidad": 10,
            "precio_unitario": 150.75,
            "precio_total": 1507.50
          }
        ]
        """
        
        log_func("🧠 Analizando la imagen con Gemini Vision (esto puede demorar unos segundos)...")
        
        # Llamada a la API forzando salida en JSON
        response = model.generate_content(
            [prompt, imagen],
            generation_config={
                "temperature": 0.0,  # Queremos precisión absoluta, sin creatividad
                "response_mime_type": "application/json" # Fuerzo JSON nativo
            }
        )
        
        texto_json = response.text.strip()
        datos = json.loads(texto_json)
        
        if not datos:
            log_func("⚠️ La IA no detectó ningún artículo en el remito.")
            return pd.DataFrame()
            
        df = pd.DataFrame(datos)
        log_func(f"✅ ¡Éxito! Se extrajeron {len(df)} líneas del remito.")
        
        return df
        
    except Exception as e:
        log_func(f"❌ Error durante el OCR con Gemini: {e}")
        return pd.DataFrame()

# ── PRUEBA RÁPIDA ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Para probarlo:
    # 1. Sacale una foto a un remito con tu celular
    # 2. Guardala en la carpeta input/ como "remito_prueba.jpg"
    # 3. Ejecutá: python core/ocr_remitos.py
    
    print("="*50)
    print("🤖 TEST OCR DE REMITOS CON GEMINI VISION")
    print("="*50)
    
    ruta_prueba = str(_RAIZ / "input" / "remito_prueba.jpg")
    
    if not Path(ruta_prueba).exists():
        print(f"\n⚠️  Para probar, colocá una foto de un remito en:\n   {ruta_prueba}\n")
    else:
        df_resultado = extraer_datos_remito(ruta_prueba)
        if not df_resultado.empty:
            print("\n📊 RESULTADO EXTRAÍDO:\n")
            print(df_resultado.to_string())