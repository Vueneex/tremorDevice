# DOSYA ADI: database.py

import sqlite3
from datetime import datetime

class TestDatabase:
    def __init__(self, db_path="test_history.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        
        # YENİ KLİNİK TABLO: Boy/Kilo yerine Protocol No, Baskın Taraf, Başlangıç Yılı eklendi
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            protocol_no TEXT PRIMARY KEY,
            name TEXT UNIQUE,
            age INTEGER,
            gender TEXT,
            dominant_side TEXT,
            onset_year INTEGER,
            diagnosis TEXT,
            doctor_name TEXT,
            contact_phone TEXT
        )
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT,
            test_type TEXT,
            file_path TEXT,
            score REAL,
            extra REAL,
            notes TEXT,
            test_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_name) REFERENCES patients (name) ON DELETE CASCADE
        )
        """)
        self.conn.commit()

    def get_all_patients(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM patients ORDER BY name")
        return [row[0] for row in cursor.fetchall()]

    def get_patient_details(self, name):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT protocol_no, age, gender, dominant_side, onset_year, diagnosis, doctor_name, contact_phone 
            FROM patients WHERE name=?
        """, (name,))
        row = cursor.fetchone()
        
        if row:
            return {
                "protocol_no": row[0],
                "age": row[1],
                "gender": row[2],
                "dominant_side": row[3],
                "onset_year": row[4],
                "diagnosis": row[5],
                "doctor_name": row[6],
                "contact_phone": row[7],
            }
        return None

    def add_patient_with_details(self, protocol_no, name, age, gender, dominant_side, onset_year, diagnosis, doctor, phone):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
            INSERT INTO patients (protocol_no, name, age, gender, dominant_side, onset_year, diagnosis, doctor_name, contact_phone) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (protocol_no, name, age, gender, dominant_side, onset_year, diagnosis, doctor, phone))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Protokol numarası veya isim zaten varsa hata fırlatmadan False döner
            return False
        except Exception as e:
            print(f"DB Kayıt Hatası: {e}")
            return False

    def update_patient_details(self, name, age, dominant_side, doctor, phone):
        """Arayüzde sağ tıklayıp bilgileri güncellediğimizde çalışır"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE patients 
                SET age = ?, dominant_side = ?, doctor_name = ?, contact_phone = ?
                WHERE name = ?
            """, (age, dominant_side, doctor, phone, name))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"DB Güncelleme Hatası: {e}")
            return False

    def delete_patient(self, name):
        """Hastayı ve testlerini siler"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM patients WHERE name = ?", (name,))
            cursor.execute("DELETE FROM tests WHERE patient_name = ?", (name,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"DB Silme Hatası: {e}")
            return False

    def add_test(self, patient_name, test_type, file_path, score, extra, notes):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
            INSERT INTO tests (patient_name, test_type, file_path, score, extra, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (patient_name, test_type, file_path, score, extra, notes))
            self.conn.commit()
        except Exception as e:
            print(f"Test Kayıt Hatası: {e}")

    def __del__(self):
        """Program kapanırken bağlantıyı güvenli şekilde kapatır"""
        try:
            self.conn.close()
        except:
            pass