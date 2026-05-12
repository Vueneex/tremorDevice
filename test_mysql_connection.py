# DOSYA ADI: test_mysql_connection.py
import mysql.connector
from db_config import DB_CONFIG

def test_connection():
    try:
        print(f"Bağlanılıyor: {DB_CONFIG['host']}...")
        conn = mysql.connector.connect(**DB_CONFIG)
        if conn.is_connected():
            print("Başarılı! MySQL veritabanına bağlanıldı.")
            cursor = conn.cursor()
            cursor.execute("SELECT DATABASE();")
            db_name = cursor.fetchone()
            print(f"Aktif Veritabanı: {db_name[0]}")
            cursor.close()
            conn.close()
        else:
            print("Bağlantı kurulamadı.")
    except Exception as e:
        print(f"Hata: {e}")
        print("\nİpucu: MySQL sunucusunun çalıştığından ve db_config.py dosyasındaki bilgilerin doğru olduğundan emin olun.")

if __name__ == "__main__":
    test_connection()
