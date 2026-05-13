# DOSYA ADI: database.py

import mysql.connector
from mysql.connector import errorcode
from datetime import datetime
from db_config import DB_CONFIG

class TestDatabase:
    def __init__(self):
        try:
            self.conn = mysql.connector.connect(**DB_CONFIG)
            self.ensure_columns_exist()
            self.create_tables()
        except mysql.connector.Error as err:
            print(f"Bağlantı Hatası: {err}")
            self.conn = None

    def ensure_columns_exist(self):
        if not self.conn: return
        cursor = self.conn.cursor()
        
        # Check and add columns to doctors table
        try:
            cursor.execute("SHOW COLUMNS FROM doctors")
            columns = [row[0] for row in cursor.fetchall()]
            
            if 'email' not in columns:
                # Add as NULLable first to avoid unique constraint issues with empty strings
                cursor.execute("ALTER TABLE doctors ADD COLUMN email VARCHAR(100) NULL AFTER name")
                self.conn.commit()
                
                # Update existing rows with default emails
                cursor.execute("SELECT id, name FROM doctors")
                docs = cursor.fetchall()
                for doc_id, name in docs:
                    email = name.lower().replace(" ", ".").replace("dr.", "dr") + "@neuromotion.com"
                    cursor.execute("UPDATE doctors SET email = %s WHERE id = %s", (email, doc_id))
                
                # Now make it UNIQUE and NOT NULL
                cursor.execute("ALTER TABLE doctors MODIFY COLUMN email VARCHAR(100) UNIQUE NOT NULL")
                print("Added and initialized 'email' column.")
            
            if 'is_approved' not in columns:
                cursor.execute("ALTER TABLE doctors ADD COLUMN is_approved TINYINT(1) DEFAULT 0")
                # Set existing doctors to approved
                cursor.execute("UPDATE doctors SET is_approved = 1")
                print("Added 'is_approved' column and approved existing doctors.")
                
            if 'is_admin' not in columns:
                cursor.execute("ALTER TABLE doctors ADD COLUMN is_admin TINYINT(1) DEFAULT 0")
                # Set 'Admin' user to admin
                cursor.execute("UPDATE doctors SET is_admin = 1 WHERE name LIKE '%Admin%'")
                print("Added 'is_admin' column.")
                
            self.conn.commit()
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_NO_SUCH_TABLE:
                pass # Table will be created in create_tables
            else:
                print(f"Sütun Kontrol Hatası: {err}")
        finally:
            cursor.close()

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

        # 4. Doctors Table (Updated)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) DEFAULT '1234',
            specialty VARCHAR(100),
            is_approved TINYINT(1) DEFAULT 0,
            is_admin TINYINT(1) DEFAULT 0
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
        
        # Initial Data (Admin & Default Doctor)
        cursor.execute("INSERT IGNORE INTO doctors (name, email, password, specialty, is_approved, is_admin) VALUES ('Admin', 'admin@neuromotion.com', 'admin123', 'System Administrator', 1, 1)")
        cursor.execute("INSERT IGNORE INTO doctors (name, email, password, specialty, is_approved) VALUES ('Dr. Aytaç Durmaz', 'aytac@neuromotion.com', '1234', 'Neurology', 1)")
        
        self.conn.commit()
        cursor.close()

    # --- Auth Methods ---
    def authenticate_doctor(self, identifier, password):
        """Identifier can be email or name"""
        if not self.conn: return None
        cursor = self.conn.cursor(dictionary=True)
        query = "SELECT * FROM doctors WHERE (email=%s OR name=%s) AND password=%s"
        cursor.execute(query, (identifier, identifier, password))
        doctor = cursor.fetchone()
        cursor.close()
        
        if doctor and not doctor['is_approved']:
            return "PENDING"
        return doctor

    def register_doctor(self, name, email, password, specialty, is_approved=0):
        if not self.conn: return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
            INSERT INTO doctors (name, email, password, specialty, is_approved, is_admin)
            VALUES (%s, %s, %s, %s, %s, 0)
            """, (name, email, password, specialty, 1 if is_approved else 0))
            self.conn.commit()
            cursor.close()
            msg = f"Yeni doktor eklendi (Admin): {name}" if is_approved else f"Yeni doktor kayıt isteği: {name} ({email})"
            self.log_event("INFO", msg)
            return True
        except Exception as e:
            print(f"Kayıt Hatası: {e}")
            return False

    def get_pending_doctors(self):
        if not self.conn: return []
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, email, specialty FROM doctors WHERE is_approved = 0")
        result = cursor.fetchall()
        cursor.close()
        return result

    def approve_doctor(self, doctor_id):
        if not self.conn: return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE doctors SET is_approved = 1 WHERE id = %s", (doctor_id,))
            self.conn.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"Onay Hatası: {e}")
            return False

    def reject_doctor(self, doctor_id):
        if not self.conn: return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM doctors WHERE id = %s AND is_approved = 0", (doctor_id,))
            self.conn.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"Reddetme Hatası: {e}")
            return False

    def delete_doctor(self, doctor_id):
        if not self.conn: return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM doctors WHERE id = %s", (doctor_id,))
            self.conn.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"Doktor Silme Hatası: {e}")
            return False

    def update_doctor_admin_status(self, doctor_id, is_admin):
        if not self.conn: return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE doctors SET is_admin = %s WHERE id = %s", (1 if is_admin else 0, doctor_id))
            self.conn.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"Yetki Güncelleme Hatası: {e}")
            return False

    def get_system_stats(self):
        if not self.conn: return {}
        stats = {}
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM doctors WHERE is_approved = 1")
        stats['doctors'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM doctors WHERE is_approved = 0")
        stats['pending'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM patients")
        stats['patients'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM tests")
        stats['tests'] = cursor.fetchone()[0]
        
        cursor.close()
        return stats

    def get_all_logs(self, limit=200):
        if not self.conn: return []
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM system_logs ORDER BY log_date DESC LIMIT %s", (limit,))
        result = cursor.fetchall()
        cursor.close()
        return result

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