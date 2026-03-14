
import sqlite3
from sqlite3 import Error
import os
import logging

# --- Configuración ---
# Nombre del archivo de la base de datos.
# Se guardará en el directorio raíz del proyecto.
DB_NAME = "rpa_suite.db"
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), DB_NAME)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_db_connection():
    """Crea y devuelve una conexión a la base de datos SQLite."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        logging.info(f"Conexión a SQLite DB en '{DB_PATH}' exitosa.")
    except Error as e:
        logging.error(f"Error al conectar con la base de datos: {e}")
    return conn

def execute_query(query, params=(), is_commit=False):
    """
    Ejecuta una consulta SQL genérica.

    :param query: La consulta SQL a ejecutar.
    :param params: Tupla con los parámetros para la consulta.
    :param is_commit: True si la consulta es de modificación (INSERT, UPDATE, DELETE).
    :return: Filas resultantes si es una consulta de selección, o None.
    """
    conn = get_db_connection()
    if conn is None:
        return None
        
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        if is_commit:
            conn.commit()
            logging.info("Query ejecutada y commiteada con éxito.")
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
    
    sql_create_cargas_stock_table = """
    CREATE TABLE IF NOT EXISTS cargas_stock (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        sku TEXT NOT NULL,
        cantidad_cargada REAL NOT NULL,
        robot_origen TEXT NOT NULL
    );
    """

    sql_create_ventas_historicas_table = """
    CREATE TABLE IF NOT EXISTS ventas_historicas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME NOT NULL,
        sku TEXT NOT NULL,
        cantidad_vendida REAL NOT NULL,
        precio_unitario REAL,
        id_cliente TEXT
    );
    """
    
    sql_create_precios_competencia_table = """
    CREATE TABLE IF NOT EXISTS precios_competencia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        sku TEXT NOT NULL,
        competidor TEXT NOT NULL,
        precio REAL NOT NULL
    );
    """

    sql_create_historial_precios_propios_table = """
    CREATE TABLE IF NOT EXISTS historial_precios_propios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        sku TEXT NOT NULL,
        costo REAL,
        precio_salon REAL,
        precio_mayorista REAL,
        precio_galpon REAL,
        robot_origen TEXT
    );
    """

    logging.info("Intentando crear las tablas si no existen...")
    execute_query(sql_create_cargas_stock_table, is_commit=True)
    execute_query(sql_create_ventas_historicas_table, is_commit=True)
    execute_query(sql_create_precios_competencia_table, is_commit=True)
    execute_query(sql_create_historial_precios_propios_table, is_commit=True)
    logging.info("Proceso de creación de tablas finalizado.")

if __name__ == '__main__':
    """
    Si se ejecuta este script directamente, se asegura de que la
    base de datos y las tablas estén creadas.
    """
    logging.info("Ejecutando inicializador de la base de datos...")
    create_tables()
    # Ejemplo de inserción
    logging.info("Insertando un dato de ejemplo en 'cargas_stock'...")
    sql_ejemplo = "INSERT INTO cargas_stock (sku, cantidad_cargada, robot_origen) VALUES (?, ?, ?)"
    execute_query(sql_ejemplo, params=("PROD-001", 50, "ejemplo_directo"), is_commit=True)
    
    # Ejemplo de lectura
    logging.info("Leyendo datos de ejemplo de 'cargas_stock'...")
    rows = execute_query("SELECT * FROM cargas_stock")
    if rows:
        for row in rows:
            logging.info(f"Dato leído: {row}")

