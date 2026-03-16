import sqlite3
from sqlite3 import Error
import os
import logging
import time
from pathlib import Path

# Configuración
DB_NAME = "rpa_suite.db"
DB_PATH = Path(__file__).parent.parent / DB_NAME

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def retry_on_lock(func):
    """Decorador para reintentar operaciones si la base de datos está bloqueada."""
    def wrapper(*args, **kwargs):
        import random
        intentos = 10
        for i in range(intentos):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and i < intentos - 1:
                    # Espera aleatoria progresiva para evitar colisiones múltiples
                    espera = random.uniform(0.1, 0.8) * (1.5 ** i)
                    logging.warning(f"⚠️ Base de datos ocupada (locked). Reintentando {i+1}/{intentos} en {espera:.2f}s...")
                    time.sleep(espera)
                else:
                    raise e
        return func(*args, **kwargs)
    return wrapper

def get_db_connection():
    """Crea y devuelve una conexión a la base de datos SQLite con timeout de seguridad."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=20)
        conn.row_factory = sqlite3.Row
        # Habilitar WAL: Permite lectura (Dashboards) y escritura (Robots) en simultáneo sin bloquearse.
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA synchronous=NORMAL;')
    except Error as e:
        logging.error(f"Error al conectar con la base de datos: {e}")
    return conn

@retry_on_lock
def execute_query(query, params=(), is_commit=False):
    """Ejecuta una consulta SQL genérica con manejo de reintentos."""
    conn = get_db_connection()
    if conn is None:
        return None
        
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        if is_commit:
            conn.commit()
            return None
        else:
            rows = cursor.fetchall()
            return rows
    except Error as e:
        logging.error(f"Error al ejecutar la query: {e}")
        return None
    finally:
        if conn:
            conn.close()

def create_tables():
    """Crea las tablas iniciales en la base de datos si no existen."""
    sql_queries = [
        """CREATE TABLE IF NOT EXISTS cargas_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            sku TEXT NOT NULL,
            cantidad_cargada REAL NOT NULL,
            robot_origen TEXT NOT NULL
        );""",
        """CREATE TABLE IF NOT EXISTS ventas_historicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            sku TEXT NOT NULL,
            cantidad_vendida REAL NOT NULL,
            precio_unitario REAL,
            id_cliente TEXT
        );""",
        """CREATE TABLE IF NOT EXISTS precios_competencia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            sku TEXT NOT NULL,
            competidor TEXT NOT NULL,
            precio REAL NOT NULL
        );""",
        """CREATE TABLE IF NOT EXISTS historial_precios_propios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            sku TEXT NOT NULL,
            costo REAL,
            precio_salon REAL,
            precio_mayorista REAL,
            precio_galpon REAL,
            robot_origen TEXT
        );"""
    ]
    for q in sql_queries:
        execute_query(q, is_commit=True)

if __name__ == '__main__':
    create_tables()