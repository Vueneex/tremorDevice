# DOSYA ADI: migrate_to_mysql.py
import sqlite3
import mysql.connector
import os
from db_config import DB_CONFIG

# SQLite Path
SQLITE_PATH = "test_history.db"
WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
PATIENTS_DIR = os.path.join(WORKSPACE_ROOT, "VeriSeti_Genel", "Hastalar")

def migrate():
    if not os.path.exists(SQLITE_PATH):
        print(f"Hata: {SQLITE_PATH} bulunamadı!")
        return

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_cursor = sqlite_conn.cursor()

    # Connect to MySQL
    try:
        mysql_conn = mysql.connector.connect(**DB_CONFIG)
        mysql_cursor = mysql_conn.cursor()
    except Exception as e:
        print(f"MySQL Bağlantı Hatası: {e}")
        return

    print("Veri aktarımı başlıyor...")

    # 1. Patients Migration
    sqlite_cursor.execute("SELECT protocol_no, name, age, gender, dominant_side, onset_year, diagnosis, doctor_name, contact_phone FROM patients")
    patients = sqlite_cursor.fetchall()

    for p in patients:
        protocol_no, name, age, gender, dominant_side, onset_year, diagnosis, doctor_name, contact_phone = p
        
        # Read clinical history from oyku.txt if exists
        history = ""
        oyku_path = os.path.join(PATIENTS_DIR, name, "oyku.txt")
        if os.path.exists(oyku_path):
            try:
                with open(oyku_path, 'r', encoding='utf-8') as f:
                    history = f.read()
            except Exception as e:
                print(f"Uyarı: {name} için öykü dosyası okunamadı: {e}")

        try:
            mysql_cursor.execute("""
            INSERT INTO patients (protocol_no, name, age, gender, dominant_side, onset_year, diagnosis, doctor_name, contact_phone, clinical_history)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE clinical_history=%s
            """, (protocol_no, name, age, gender, dominant_side, onset_year, diagnosis, doctor_name, contact_phone, history, history))
            print(f"Hasta aktarıldı: {name}")
        except Exception as e:
            print(f"Hasta aktarım hatası ({name}): {e}")

    # 2. Tests Migration
    sqlite_cursor.execute("SELECT patient_name, test_type, file_path, score, extra, notes, test_date FROM tests")
    tests = sqlite_cursor.fetchall()

    for t in tests:
        patient_name, test_type, file_path, score, extra, notes, test_date = t
        try:
            mysql_cursor.execute("""
            INSERT INTO tests (patient_name, test_type, file_path, score, extra, notes, test_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (patient_name, test_type, file_path, score, extra, notes, test_date))
        except Exception as e:
            print(f"Test aktarım hatası ({patient_name} - {test_type}): {e}")

    mysql_conn.commit()
    print("Veri aktarımı başarıyla tamamlandı!")

    sqlite_conn.close()
    mysql_conn.close()

if __name__ == "__main__":
    migrate()
