# DOSYA ADI: database.py

import mysql.connector
from mysql.connector import errorcode
from datetime import datetime
from db_config import DB_CONFIG

class TestDatabase:
    def __init__(self):
        try:
            self.conn = mysql.connector.connect(**DB_CONFIG)
            self.create_tables()
        except mysql.connector.Error as err:
            print(f"Bağlantı Hatası: {err}")
            self.conn = None

    def create_tables(self):
        if not self.conn: return
        cursor = self.conn.cursor()
        
        # 1. Patients Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            protocol_no VARCHAR(50) PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            age INT,
            gender VARCHAR(20),
            dominant_side VARCHAR(20),
            onset_year INT,
            diagnosis VARCHAR(100),
            doctor_name VARCHAR(100),
            contact_phone VARCHAR(50),
            clinical_history TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # 2. Tests Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_name VARCHAR(100),
            test_type VARCHAR(50),
            file_path TEXT,
            score DOUBLE,
            extra DOUBLE,
            notes TEXT,
            test_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            doctor_name VARCHAR(100),
            FOREIGN KEY (patient_name) REFERENCES patients(name) ON DELETE CASCADE
        )
        """)
        
        # 3. Calibration Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS device_calibration (
            id INT AUTO_INCREMENT PRIMARY KEY,
            device_id VARCHAR(50) DEFAULT 'Main_Device',
            offset_ax DOUBLE DEFAULT 0,
            offset_ay DOUBLE DEFAULT 0,
            offset_az DOUBLE DEFAULT 0,
            offset_gx DOUBLE DEFAULT 0,
            offset_gy DOUBLE DEFAULT 0,
            offset_gz DOUBLE DEFAULT 0,
            calibrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 4. Doctors Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) DEFAULT '1234',
            specialty VARCHAR(100),
            email VARCHAR(100)
        )
        """)

        # 5. Logs Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            log_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            level VARCHAR(20),
            message TEXT,
            doctor_name VARCHAR(100)
        )
        """)
        
        # Initial Data
        cursor.execute("INSERT IGNORE INTO doctors (name, password, specialty) VALUES ('Dr. Aytaç Durmaz', '1234', 'Neurology')")
        
        self.conn.commit()
        cursor.close()

    # --- Auth Methods ---
    def authenticate_doctor(self, name, password):
        if not self.conn: return None
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM doctors WHERE name=%s AND password=%s", (name, password))
        doctor = cursor.fetchone()
        cursor.close()
        return doctor

    # --- Logging Methods ---
    def log_event(self, level, message, doctor_name="System"):
        if not self.conn: return
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
            INSERT INTO system_logs (level, message, doctor_name)
            VALUES (%s, %s, %s)
            """, (level, message, doctor_name))
            self.conn.commit()
            cursor.close()
        except Exception as e:
            print(f"Log Yazma Hatası: {e}")

    # --- Patient Methods ---
    def get_all_patients(self):
        if not self.conn: return []
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM patients ORDER BY name")
        result = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return result

    def get_patient_details(self, name):
        if not self.conn: return None
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT protocol_no, age, gender, dominant_side, onset_year, diagnosis, doctor_name, contact_phone, clinical_history 
            FROM patients WHERE name=%s
        """, (name,))
        row = cursor.fetchone()
        cursor.close()
        return row

    def add_patient_with_details(self, protocol_no, name, age, gender, dominant_side, onset_year, diagnosis, doctor, phone, history=""):
        if not self.conn: return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
            INSERT INTO patients (protocol_no, name, age, gender, dominant_side, onset_year, diagnosis, doctor_name, contact_phone, clinical_history) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (protocol_no, name, age, gender, dominant_side, onset_year, diagnosis, doctor, phone, history))
            self.conn.commit()
            cursor.close()
            self.log_event("INFO", f"Yeni hasta eklendi: {name}", doctor)
            return True
        except mysql.connector.IntegrityError:
            return False
        except Exception as e:
            print(f"DB Kayıt Hatası: {e}")
            return False

    def update_patient_details(self, name, age, dominant_side, doctor, phone, history=None):
        if not self.conn: return False
        try:
            cursor = self.conn.cursor()
            if history is not None:
                cursor.execute("""
                    UPDATE patients 
                    SET age = %s, dominant_side = %s, doctor_name = %s, contact_phone = %s, clinical_history = %s
                    WHERE name = %s
                """, (age, dominant_side, doctor, phone, history, name))
            else:
                cursor.execute("""
                    UPDATE patients 
                    SET age = %s, dominant_side = %s, doctor_name = %s, contact_phone = %s
                    WHERE name = %s
                """, (age, dominant_side, doctor, phone, name))
            self.conn.commit()
            cursor.close()
            self.log_event("INFO", f"Hasta bilgileri güncellendi: {name}", doctor)
            return True
        except Exception as e:
            print(f"DB Güncelleme Hatası: {e}")
            return False

    def delete_patient(self, name, doctor="System"):
        if not self.conn: return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM patients WHERE name = %s", (name,))
            self.conn.commit()
            cursor.close()
            self.log_event("WARNING", f"Hasta silindi: {name}", doctor)
            return True
        except Exception as e:
            print(f"DB Silme Hatası: {e}")
            return False

    def add_test(self, patient_name, test_type, file_path, score, extra, notes, doctor_name="System"):
        if not self.conn: return
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
            INSERT INTO tests (patient_name, test_type, file_path, score, extra, notes, doctor_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (patient_name, test_type, file_path, score, extra, notes, doctor_name))
            self.conn.commit()
            cursor.close()
            self.log_event("INFO", f"Yeni test eklendi: {test_type} - Hasta: {patient_name}", doctor_name)
        except Exception as e:
            print(f"Test Kayıt Hatası: {e}")

    # --- Calibration Methods ---
    def save_calibration(self, ax, ay, az, gx, gy, gz, device_id='Main_Device', doctor='System'):
        if not self.conn: return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
            INSERT INTO device_calibration (device_id, offset_ax, offset_ay, offset_az, offset_gx, offset_gy, offset_gz)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (device_id, ax, ay, az, gx, gy, gz))
            self.conn.commit()
            cursor.close()
            self.log_event("INFO", f"Cihaz kalibre edildi: {device_id}", doctor)
            return True
        except Exception as e:
            print(f"Kalibrasyon Kayıt Hatası: {e}")
            return False

    def get_latest_calibration(self, device_id='Main_Device'):
        if not self.conn: return None
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT offset_ax, offset_ay, offset_az, offset_gx, offset_gy, offset_gz 
            FROM device_calibration 
            WHERE device_id=%s 
            ORDER BY calibrated_at DESC LIMIT 1
        """, (device_id,))
        row = cursor.fetchone()
        cursor.close()
        return row

    def get_doctors(self):
        if not self.conn: return []
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM doctors ORDER BY name")
        result = cursor.fetchall()
        cursor.close()
        return result

    def update_doctor_password(self, name, old_pw, new_pw):
        if not self.conn: return False
        try:
            cursor = self.conn.cursor()
            # Önce eski şifreyi doğrula
            cursor.execute("SELECT id FROM doctors WHERE name=%s AND password=%s", (name, old_pw))
            if not cursor.fetchone():
                cursor.close()
                return False
            
            # Yeni şifreyi güncelle
            cursor.execute("UPDATE doctors SET password=%s WHERE name=%s", (new_pw, name))
            self.conn.commit()
            cursor.close()
            self.log_event("INFO", "Şifre değiştirildi.", name)
            return True
        except Exception as e:
            print(f"Şifre Güncelleme Hatası: {e}")
            return False

    def __del__(self):
        try:
            if hasattr(self, 'conn') and self.conn and self.conn.is_connected():
                self.conn.close()
        except:
            pass