import mysql.connector
from db_config import DB_CONFIG

try:
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT VERSION()")
    version = cursor.fetchone()
    print(f"MySQL Versiyonunuz: {version[0]}")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"Hata: {e}")
