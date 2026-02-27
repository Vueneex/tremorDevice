import sqlite3

class TestDatabase:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            name TEXT PRIMARY KEY,
            age INTEGER,
            gender TEXT,
            height REAL,
            weight REAL,
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
            notes TEXT
        )
        """)
        self.conn.commit()

    def get_all_patients(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM patients")
        return [row[0] for row in cursor.fetchall()]

    def get_patient_details(self, name):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM patients WHERE name=?", (name,))
        row = cursor.fetchone()
        if row:
            return {
                "age": row[1],
                "gender": row[2],
                "height": row[3],
                "weight": row[4],
                "diagnosis": row[5],
                "doctor_name": row[6],
                "contact_phone": row[7],
            }
        return None

    def add_patient_with_details(self, name, age, gender, height, weight, diagnosis, doctor, phone):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
            INSERT INTO patients VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, age, gender, height, weight, diagnosis, doctor, phone))
            self.conn.commit()
            return True
        except:
            return False

    def add_test(self, patient_name, test_type, file_path, score, extra, notes):
        cursor = self.conn.cursor()
        cursor.execute("""
        INSERT INTO tests (patient_name, test_type, file_path, score, extra, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (patient_name, test_type, file_path, score, extra, notes))
        self.conn.commit()