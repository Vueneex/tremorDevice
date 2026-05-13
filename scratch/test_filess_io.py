import mysql.connector
from db_config import DB_CONFIG

# Portu tam sayıya çevirelim (bazı connectorler hata verebilir)
if 'port' in DB_CONFIG:
    DB_CONFIG['port'] = int(DB_CONFIG['port'])

print(f"Bağlantı deneniyor: {DB_CONFIG['host']}...")

try:
    conn = mysql.connector.connect(**DB_CONFIG)
    print("Bağlantı BAŞARILI!")
    
    # Tabloları oluşturmak için database.py'yi tetikleyelim
    from database import TestDatabase
    db = TestDatabase()
    print("Tablolar kontrol edildi ve gerekirse oluşturuldu.")
    
    # Admin kontrolü
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT name, email FROM doctors WHERE is_admin = 1")
    admins = cursor.fetchall()
    print(f"Sistemdeki Adminler: {admins}")
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f"BAĞLANTI HATASI: {e}")
