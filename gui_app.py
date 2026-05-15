# DOSYA ADI: gui_app_new.py
# VERSIYON: v7.1 (Final - Backend, PDF Ready & Bug Fixes)

import sys
import os
import shutil
import time
import csv
import serial
import serial.tools.list_ports
import numpy as np
from datetime import datetime
import importlib
from database import TestDatabase

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QComboBox, 
                             QMessageBox, QFrame, QLineEdit, QListWidget,
                             QTabWidget, QSpinBox, QTextEdit, QTextBrowser, 
                             QGroupBox, QGridLayout, QDialog, QMenu, QStackedWidget,
                             QSlider, QFormLayout, QProgressBar, QScrollArea,
                             QTableWidget, QTableWidgetItem, QHeaderView) 
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QAction

import pyqtgraph as pg

# DALGALARI PÜRÜZSÜZ ÇİZMEK İÇİN
pg.setConfigOptions(antialias=True) 
try: pg.setConfigOptions(useOpenGL=True) 
except: pass
pg.setConfigOption('background', '#FFFFFF')
pg.setConfigOption('foreground', '#2C3E50')

# ----------------------------------------
# 1. ARKA PLAN İŞÇİSİ (SERIAL WORKER)
# ----------------------------------------
class SerialWorker(QThread):
    data_received = pyqtSignal(list)

    def __init__(self, port_name, baud_rate=115200):
        super().__init__()
        self.port_name = port_name
        self.baud_rate = baud_rate
        self.is_running = True
        self.serial_conn = None

    def run(self):
        try:
            self.serial_conn = serial.Serial(self.port_name, self.baud_rate, timeout=0.1)
            while self.is_running:
                if self.serial_conn.in_waiting:
                    try:
                        line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                        parts = line.split(',')
                        
                        if len(parts) >= 6: 
                            raw_data = [float(x) for x in parts]
                            battery_val = raw_data[6] if len(parts) >= 7 else 0.0 
                            
                            # GÖMÜLÜ EKİP BURAYI GERÇEK VERİ PAKETİNE GÖRE DÜZENLEYECEK
                            base_sensor = [raw_data[0], raw_data[1], raw_data[2], raw_data[3], raw_data[4], raw_data[5]]
                            multi_sensor_data = []
                            for i in range(12):
                                if i == 0:
                                    multi_sensor_data.extend(base_sensor)
                                else:
                                    noise_acc = np.random.normal(0, 100, 3).tolist()
                                    noise_gyro = np.random.normal(0, 10, 3).tolist()
                                    multi_sensor_data.extend([
                                        base_sensor[0] + noise_acc[0], base_sensor[1] + noise_acc[1], base_sensor[2] + noise_acc[2],
                                        base_sensor[3] + noise_gyro[0], base_sensor[4] + noise_gyro[1], base_sensor[5] + noise_gyro[2]
                                    ])
                            
                            multi_sensor_data.append(battery_val)
                            self.data_received.emit(multi_sensor_data)
                            
                    except (ValueError, IndexError): pass
                else:
                    time.sleep(0.001)
        except Exception as e: print(f"Bağlantı Hatası: {e}")
        finally:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()

    def send_command(self, command_string):
        """STM32'ye komut gönderme fonksiyonu (Backend Ekibi için TX)"""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                cmd = f"{command_string}\r\n".encode('utf-8')
                self.serial_conn.write(cmd)
                print(f"-> Giden Komut: {command_string}")
            except Exception as e: print(f"Komut gönderme hatası: {e}")

    def stop(self):
        self.is_running = False
        self.quit()
        self.wait(500)


# ----------------------------------------
# DOKTOR GİRİŞ EKRANI
# ----------------------------------------
class LoginDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("NeuroMotion - Giriş Ekranı")
        self.setFixedSize(400, 550)
        self.setStyleSheet("""
            QDialog { background-color: #2C3E50; }
            QLabel { color: #ECF0F1; font-size: 14px; font-weight: bold; }
            QLineEdit { background-color: #34495E; color: white; border: 1px solid #7F8C8D; border-radius: 5px; padding: 10px; font-size: 14px; }
            QPushButton#Login { background-color: #3498DB; color: white; border-radius: 5px; padding: 12px; font-weight: bold; font-size: 15px; }
            QPushButton#Login:hover { background-color: #2980B9; }
            QPushButton#Register { background-color: transparent; color: #3498DB; border: 1px solid #3498DB; border-radius: 5px; padding: 10px; font-weight: bold; font-size: 13px; }
            QPushButton#Register:hover { background-color: rgba(52, 152, 219, 0.1); }
            QLabel#Title { font-size: 24px; color: #3498DB; margin-bottom: 20px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(15)

        title = QLabel("NeuroMotion")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addWidget(QLabel("E-posta veya Ad Soyad:"))
        self.txt_username = QLineEdit()
        self.txt_username.setPlaceholderText("Giriş kimliği...")
        layout.addWidget(self.txt_username)

        layout.addWidget(QLabel("Şifre:"))
        self.txt_password = QLineEdit()
        self.txt_password.setPlaceholderText("Şifre...")
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.txt_password)

        layout.addSpacing(10)
        self.btn_login = QPushButton("SİSTEME GİRİŞ YAP")
        self.btn_login.setObjectName("Login")
        self.btn_login.clicked.connect(self.attempt_login)
        layout.addWidget(self.btn_login)

        self.btn_register = QPushButton("YENİ DOKTOR KAYDI")
        self.btn_register.setObjectName("Register")
        self.btn_register.clicked.connect(self.open_register)
        layout.addWidget(self.btn_register)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #E74C3C; font-size: 12px;")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)

        self.doctor_info = None

    def attempt_login(self):
        user = self.txt_username.text().strip()
        pw = self.txt_password.text().strip()
        
        if not user or not pw:
            self.lbl_status.setText("Lütfen tüm alanları doldurun!")
            return

        result = self.db.authenticate_doctor(user, pw)
        if result == "PENDING":
            QMessageBox.information(self, "Kayıt Beklemede", "Kaydınız henüz yönetici tarafından onaylanmamış. Lütfen bekleyiniz.")
        elif result:
            self.doctor_info = result
            self.db.log_event("INFO", f"Başarılı giriş yapıldı: {user}", user)
            self.accept()
        else:
            self.db.log_event("WARNING", f"Hatalı giriş denemesi: {user}")
            self.lbl_status.setText("Hatalı bilgiler veya şifre!")

    def open_register(self):
        reg = RegisterDialog(self.db, self)
        reg.exec()

# ----------------------------------------
# YENİ DOKTOR KAYIT EKRANI
# ----------------------------------------
class RegisterDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("NeuroMotion - Yeni Kayıt")
        self.setFixedSize(400, 500)
        self.setStyleSheet("""
            QDialog { background-color: #2C3E50; }
            QLabel { color: #ECF0F1; font-size: 13px; font-weight: bold; }
            QLineEdit { background-color: #34495E; color: white; border: 1px solid #7F8C8D; border-radius: 5px; padding: 8px; }
            QPushButton { background-color: #2ECC71; color: white; border-radius: 5px; padding: 12px; font-weight: bold; }
            QPushButton:hover { background-color: #27AE60; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(10)

        title = QLabel("Yeni Doktor Kaydı")
        title.setStyleSheet("font-size: 20px; color: #2ECC71; margin-bottom: 10px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addWidget(QLabel("Ad Soyad:"))
        self.txt_name = QLineEdit()
        layout.addWidget(self.txt_name)

        layout.addWidget(QLabel("E-posta:"))
        self.txt_email = QLineEdit()
        layout.addWidget(self.txt_email)

        layout.addWidget(QLabel("Şifre:"))
        self.txt_pw = QLineEdit(); self.txt_pw.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.txt_pw)

        layout.addWidget(QLabel("Uzmanlık Alanı:"))
        self.txt_specialty = QLineEdit()
        layout.addWidget(self.txt_specialty)

        layout.addSpacing(15)
        btn_submit = QPushButton("KAYIT TALEBİ GÖNDER")
        btn_submit.clicked.connect(self.submit_registration)
        layout.addWidget(btn_submit)

    def submit_registration(self):
        name = self.txt_name.text().strip()
        email = self.txt_email.text().strip()
        pw = self.txt_pw.text().strip()
        spec = self.txt_specialty.text().strip()

        if not all([name, email, pw, spec]):
            QMessageBox.warning(self, "Hata", "Lütfen tüm alanları doldurun!")
            return

        if self.db.register_doctor(name, email, pw, spec):
            QMessageBox.information(self, "Başarılı", "Kayıt talebiniz iletildi. Yönetici onayından sonra giriş yapabilirsiniz.")
            self.accept()
        else:
            QMessageBox.critical(self, "Hata", "Kayıt oluşturulurken bir hata oluştu (E-posta zaten kayıtlı olabilir).")

# ----------------------------------------
# ADMİN PANELİ (GELİŞMİŞ YÖNETİM)
# ----------------------------------------
class AdminPanelDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("NeuroMotion - Sistem Yönetim Merkezi")
        self.resize(1000, 700)
        self.setStyleSheet("""
            QDialog { background-color: #F0F3F4; }
            QTabWidget::pane { border: 1px solid #D5DBDB; background: white; border-radius: 5px; }
            QTabBar::tab { background: #E5E8E8; padding: 12px 25px; margin-right: 2px; border-top-left-radius: 5px; border-top-right-radius: 5px; font-weight: bold; color: #7F8C8D; }
            QTabBar::tab:selected { background: white; color: #2980B9; border-bottom: 2px solid #2980B9; }
            QLabel#StatVal { font-size: 32px; font-weight: bold; color: #2C3E50; }
            QLabel#StatLbl { font-size: 14px; color: #7F8C8D; }
            QGroupBox#StatCard { background-color: white; border: 1px solid #D5DBDB; border-radius: 10px; }
            QPushButton#ActionBtn { border-radius: 5px; padding: 8px 15px; font-weight: bold; color: white; }
        """)

        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_dashboard_tab(), "📊 Dashboard")
        self.tabs.addTab(self._create_users_tab(), "👥 Doktor Yönetimi")
        self.tabs.addTab(self._create_patients_tab(), "📂 Hasta Havuzu")
        self.tabs.addTab(self._create_logs_tab(), "📜 Sistem Logları")
        
        layout.addWidget(self.tabs)
        
        # Alt Bilgi
        footer = QLabel(f"Yönetici Oturumu Aktif | {datetime.now().strftime('%d.%m.%Y')}")
        footer.setStyleSheet("color: #95A5A6; font-size: 11px;")
        layout.addWidget(footer, alignment=Qt.AlignmentFlag.AlignRight)

        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.update_stats)
        self.refresh_timer.start(5000)
        self.update_stats()

    def _create_dashboard_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        
        grid = QGridLayout()
        self.card_doctors = self._create_stat_card("Aktif Doktor", "0", "#3498DB")
        self.card_pending = self._create_stat_card("Bekleyen Onay", "0", "#E67E22")
        self.card_patients = self._create_stat_card("Toplam Hasta", "0", "#2ECC71")
        self.card_tests = self._create_stat_card("Yapılan Test", "0", "#9B59B6")
        
        grid.addWidget(self.card_doctors, 0, 0); grid.addWidget(self.card_pending, 0, 1)
        grid.addWidget(self.card_patients, 1, 0); grid.addWidget(self.card_tests, 1, 1)
        
        layout.addLayout(grid)
        layout.addStretch()
        return tab

    def _create_stat_card(self, label, value, color):
        card = QGroupBox(); card.setObjectName("StatCard")
        card.setMinimumHeight(150)
        lay = QVBoxLayout(card)
        
        val_lbl = QLabel(value); val_lbl.setObjectName("StatVal"); val_lbl.setStyleSheet(f"color: {color};")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        txt_lbl = QLabel(label); txt_lbl.setObjectName("StatLbl")
        txt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lay.addStretch(); lay.addWidget(val_lbl); lay.addWidget(txt_lbl); lay.addStretch()
        
        # Kartın değerini güncelleyebilmek için etiketi sakla
        if not hasattr(self, 'stat_labels'): self.stat_labels = {}
        self.stat_labels[label] = val_lbl
        return card

    def _create_users_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        
        # Üst Kısım: Onay Bekleyenler
        layout.addWidget(QLabel("⏳ ONAY BEKLEYEN KAYITLAR"))
        self.list_pending = QListWidget()
        self.list_pending.setMaximumHeight(200)
        layout.addWidget(self.list_pending)
        
        pend_btns = QHBoxLayout()
        btn_appr = QPushButton("SEÇİLENİ ONAYLA"); btn_appr.setObjectName("ActionBtn"); btn_appr.setStyleSheet("background-color: #2ECC71;")
        btn_appr.clicked.connect(self.approve_doctor)
        btn_rejt = QPushButton("SİL / REDDET"); btn_rejt.setObjectName("ActionBtn"); btn_rejt.setStyleSheet("background-color: #E74C3C;")
        btn_rejt.clicked.connect(self.reject_doctor)
        pend_btns.addWidget(btn_appr); pend_btns.addWidget(btn_rejt)
        layout.addLayout(pend_btns)
        
        layout.addSpacing(20)
        
        # Alt Kısım: Kayıtlı Doktorlar
        layout.addWidget(QLabel("✅ SİSTEME KAYITLI DOKTORLAR"))
        self.table_doctors = QTableWidget(0, 4)
        self.table_doctors.setHorizontalHeaderLabels(["ID", "Ad Soyad", "E-posta", "Uzmanlık"])
        self.table_doctors.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table_doctors)
        
        doc_btns = QHBoxLayout()
        btn_add_doc = QPushButton("+ YENİ DOKTOR EKLE"); btn_add_doc.setObjectName("ActionBtn"); btn_add_doc.setStyleSheet("background-color: #3498DB;")
        btn_add_doc.clicked.connect(self.add_doctor_direct)
        btn_del_doc = QPushButton("DOKTORU SİL"); btn_del_doc.setObjectName("ActionBtn"); btn_del_doc.setStyleSheet("background-color: #C0392B;")
        btn_del_doc.clicked.connect(self.delete_doctor)
        doc_btns.addWidget(btn_add_doc); doc_btns.addStretch(); doc_btns.addWidget(btn_del_doc)
        layout.addLayout(doc_btns)
        
        self.refresh_users()
        return tab

    def _create_patients_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("🔍 TÜM SİSTEMDEKİ HASTALAR"))
        
        search_box = QLineEdit(); search_box.setPlaceholderText("Hasta adı veya protokol no ile ara...")
        layout.addWidget(search_box)
        
        self.table_patients = QTableWidget(0, 5)
        self.table_patients.setHorizontalHeaderLabels(["Protokol", "Ad Soyad", "Yaş", "Tanı", "Doktor"])
        self.table_patients.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table_patients)
        
        btn_add_patient = QPushButton("+ YENİ HASTA EKLE"); btn_add_patient.setObjectName("ActionBtn"); btn_add_patient.setStyleSheet("background-color: #27AE60;")
        btn_add_patient.clicked.connect(self.add_patient_direct)
        layout.addWidget(btn_add_patient, alignment=Qt.AlignmentFlag.AlignRight)
        
        search_box.textChanged.connect(self.filter_patients)
        self.refresh_patients()
        return tab

    def _create_logs_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("📋 SİSTEM ETKİNLİK GÜNLÜĞÜ (AUDIT LOGS)"))
        
        self.table_logs = QTableWidget(0, 4)
        self.table_logs.setHorizontalHeaderLabels(["Tarih", "Seviye", "Mesaj", "İşlem Yapan"])
        self.table_logs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table_logs.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table_logs)
        
        btn_refresh_logs = QPushButton("LOGLARI YENİLE"); btn_refresh_logs.setObjectName("ActionBtn"); btn_refresh_logs.setStyleSheet("background-color: #34495E;")
        btn_refresh_logs.clicked.connect(self.refresh_logs)
        layout.addWidget(btn_refresh_logs, alignment=Qt.AlignmentFlag.AlignRight)
        
        self.refresh_logs()
        return tab

    # --- MANTIK FONKSİYONLARI ---
    def update_stats(self):
        stats = self.db.get_system_stats()
        if stats:
            self.stat_labels["Aktif Doktor"].setText(str(stats.get('doctors', 0)))
            self.stat_labels["Bekleyen Onay"].setText(str(stats.get('pending', 0)))
            self.stat_labels["Toplam Hasta"].setText(str(stats.get('patients', 0)))
            self.stat_labels["Yapılan Test"].setText(str(stats.get('tests', 0)))

    def refresh_users(self):
        # Onay Bekleyenler
        self.list_pending.clear()
        self.pending_data = self.db.get_pending_doctors()
        for doc in self.pending_data:
            self.list_pending.addItem(f"{doc['name']} - {doc['email']} ({doc['specialty']})")
        
        # Aktif Doktorlar
        docs = self.db.get_doctors() # Zaten database.py'de var
        self.table_doctors.setRowCount(0)
        self.active_docs_data = []
        for d in docs:
            if d['is_approved']:
                row = self.table_doctors.rowCount()
                self.table_doctors.insertRow(row)
                self.table_doctors.setItem(row, 0, QTableWidgetItem(str(d['id'])))
                self.table_doctors.setItem(row, 1, QTableWidgetItem(d['name']))
                self.table_doctors.setItem(row, 2, QTableWidgetItem(d['email']))
                self.table_doctors.setItem(row, 3, QTableWidgetItem(d['specialty']))
                self.active_docs_data.append(d)

    def refresh_patients(self):
        patient_names = self.db.get_all_patients()
        self.table_patients.setRowCount(0)
        self.all_patients_data = []
        for name in patient_names:
            details = self.db.get_patient_details(name)
            if details:
                row = self.table_patients.rowCount()
                self.table_patients.insertRow(row)
                self.table_patients.setItem(row, 0, QTableWidgetItem(details.get('protocol_no', '-')))
                self.table_patients.setItem(row, 1, QTableWidgetItem(name))
                self.table_patients.setItem(row, 2, QTableWidgetItem(str(details.get('age', '-'))))
                self.table_patients.setItem(row, 3, QTableWidgetItem(details.get('diagnosis', '-')))
                self.table_patients.setItem(row, 4, QTableWidgetItem(details.get('doctor_name', '-')))
                self.all_patients_data.append(details)

    def filter_patients(self, text):
        text = text.lower()
        for row in range(self.table_patients.rowCount()):
            match = False
            for col in range(self.table_patients.columnCount()):
                item = self.table_patients.item(row, col)
                if item and text in item.text().lower():
                    match = True
                    break
            self.table_patients.setRowHidden(row, not match)

    def refresh_logs(self):
        logs = self.db.get_all_logs(200)
        self.table_logs.setRowCount(0)
        for l in logs:
            row = self.table_logs.rowCount()
            self.table_logs.insertRow(row)
            date_str = l['log_date'].strftime('%d.%m %H:%M') if hasattr(l['log_date'], 'strftime') else str(l['log_date'])
            self.table_logs.setItem(row, 0, QTableWidgetItem(date_str))
            
            lvl_item = QTableWidgetItem(l['level'])
            if l['level'] == 'ERROR': lvl_item.setForeground(Qt.GlobalColor.red)
            elif l['level'] == 'WARNING': lvl_item.setForeground(Qt.GlobalColor.darkYellow)
            
            self.table_logs.setItem(row, 1, lvl_item)
            self.table_logs.setItem(row, 2, QTableWidgetItem(l['message']))
            self.table_logs.setItem(row, 3, QTableWidgetItem(l['doctor_name']))

    def approve_doctor(self):
        idx = self.list_pending.currentRow()
        if idx < 0: return
        doc_id = self.pending_data[idx]['id']
        if self.db.approve_doctor(doc_id):
            QMessageBox.information(self, "Başarılı", "Doktor kaydı onaylandı.")
            self.refresh_users(); self.update_stats()

    def reject_doctor(self):
        idx = self.list_pending.currentRow()
        if idx < 0: return
        doc_id = self.pending_data[idx]['id']
        if QMessageBox.question(self, "Onay", "İsteği reddetmek istiyor musunuz?", QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            if self.db.reject_doctor(doc_id): self.refresh_users(); self.update_stats()

    def delete_doctor(self):
        idx = self.table_doctors.currentRow()
        if idx < 0: return
        doc = self.active_docs_data[idx]
        if doc['name'] == 'Admin':
            QMessageBox.warning(self, "Hata", "Ana yönetici hesabı silinemez!")
            return
        if QMessageBox.question(self, "Kritik Uyarı", f"{doc['name']} isimli doktoru TAMAMEN silmek istediğinize emin misiniz?", QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            if self.db.delete_doctor(doc['id']): self.refresh_users(); self.update_stats()

    def add_doctor_direct(self):
        reg = RegisterDialog(self.db, self)
        reg.setWindowTitle("Admin - Yeni Doktor Ekle")
        # override submit logic for admin
        def admin_submit():
            name = reg.txt_name.text().strip(); email = reg.txt_email.text().strip()
            pw = reg.txt_pw.text().strip(); spec = reg.txt_specialty.text().strip()
            if not all([name, email, pw, spec]):
                QMessageBox.warning(reg, "Hata", "Tüm alanları doldurun!"); return
            if self.db.register_doctor(name, email, pw, spec, is_approved=True):
                QMessageBox.information(reg, "Başarılı", "Doktor hesabı oluşturuldu ve onaylandı.")
                reg.accept(); self.refresh_users(); self.update_stats()
            else:
                QMessageBox.critical(reg, "Hata", "Kayıt hatası (E-posta zaten var olabilir).")
        
        reg.findChild(QPushButton).clicked.disconnect()
        reg.findChild(QPushButton).clicked.connect(admin_submit)
        reg.exec()

    def add_patient_direct(self):
        # Create a simple dialog for patient entry
        dialog = QDialog(self)
        dialog.setWindowTitle("Admin - Yeni Hasta Kaydı")
        dialog.setFixedWidth(400)
        lay = QVBoxLayout(dialog)
        form = QFormLayout()
        
        txt_proto = QLineEdit(); txt_name = QLineEdit()
        spin_age = QSpinBox(); spin_age.setRange(0, 150)
        combo_gen = QComboBox(); combo_gen.addItems(["Erkek", "Kadın", "Diğer"])
        combo_side = QComboBox(); combo_side.addItems(["Sağ", "Sol", "Çift Taraf"])
        combo_diag = QComboBox(); combo_diag.addItems(["Parkinson", "Essential Tremor", "Diğer"])
        txt_doc = QLineEdit("Sistem Yöneticisi")
        txt_phone = QLineEdit()
        
        form.addRow("Protokol No:", txt_proto); form.addRow("Hasta Adı:", txt_name)
        form.addRow("Yaş:", spin_age); form.addRow("Cinsiyet:", combo_gen)
        form.addRow("Baskın Taraf:", combo_side); form.addRow("Tanı:", combo_diag)
        form.addRow("Doktor:", txt_doc); form.addRow("Telefon:", txt_phone)
        lay.addLayout(form)
        
        btn_save = QPushButton("HASTAYI KAYDET"); btn_save.setStyleSheet("background-color: #2ECC71; color: white; padding: 10px; font-weight: bold;")
        lay.addWidget(btn_save)
        
        def save():
            if not txt_proto.text() or not txt_name.text():
                QMessageBox.warning(dialog, "Hata", "Protokol ve Ad alanları zorunludur!"); return
            if self.db.add_patient_with_details(txt_proto.text(), txt_name.text(), spin_age.value(), combo_gen.currentText(), combo_side.currentText(), datetime.now().year, combo_diag.currentText(), txt_doc.text(), txt_phone.text()):
                QMessageBox.information(dialog, "Başarılı", "Hasta sisteme eklendi.")
                dialog.accept(); self.refresh_patients(); self.update_stats()
            else:
                QMessageBox.critical(dialog, "Hata", "Kayıt hatası (Protokol no veya isim çakışması).")
        
        btn_save.clicked.connect(save)
        dialog.exec()

# ----------------------------------------
# HASTA GÜNCELLEME PENCERESİ
# ----------------------------------------
class UpdatePatientDialog(QDialog):
    def __init__(self, patient_name, details, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Klinik Kayıt Güncelle: {patient_name}")
        self.setMinimumWidth(400)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; }
            QLabel { color: #2C3E50; font-weight: bold; font-size: 13px; }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #F8F9F9; color: #2C3E50; border: 1px solid #BDC3C7; border-radius: 5px; padding: 5px;
            }
            QPushButton { background-color: #3498DB; color: white; border-radius: 5px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: #2980B9; }
        """)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.spin_age = QSpinBox(); self.spin_age.setRange(0, 150)
        self.spin_age.setValue(int(details.get('age', 0)) if str(details.get('age')) not in ['-', 'None', ''] else 0)
        self.combo_side = QComboBox(); self.combo_side.addItems(["Sağ", "Sol", "Çift Taraf"])
        self.combo_side.setCurrentText(str(details.get('dominant_side', 'Sağ')))
        self.txt_doctor = QLineEdit(str(details.get('doctor_name', '')))
        self.txt_phone = QLineEdit(str(details.get('contact_phone', '')))
        self.txt_history = QTextEdit(); self.txt_history.setMaximumHeight(80)

        form_layout.addRow("Yaş:", self.spin_age); form_layout.addRow("Baskın Taraf:", self.combo_side)
        form_layout.addRow("Doktor:", self.txt_doctor); form_layout.addRow("Telefon:", self.txt_phone)
        form_layout.addRow("Klinik Öykü:", self.txt_history)

        layout.addLayout(form_layout)
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Kaydet"); self.btn_save.setStyleSheet("background-color: #2ECC71;"); self.btn_save.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("İptal"); self.btn_cancel.setStyleSheet("background-color: #95A5A6;"); self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_save); btn_layout.addWidget(self.btn_cancel); layout.addLayout(btn_layout)

    def get_updated_data(self):
        return {
            "age": self.spin_age.value(), "dominant_side": self.combo_side.currentText(),
            "doctor": self.txt_doctor.text().strip(), "phone": self.txt_phone.text().strip(),
            "history": self.txt_history.toPlainText().strip()
        }

# ----------------------------------------
# ŞİFRE DEĞİŞTİRME PENCERESİ
# ----------------------------------------
class ChangePasswordDialog(QDialog):
    def __init__(self, db, doctor_name, parent=None):
        super().__init__(parent)
        self.db = db
        self.doctor_name = doctor_name
        self.setWindowTitle("Şifre Değiştir")
        self.setFixedWidth(350)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; }
            QLabel { color: #2C3E50; font-weight: bold; }
            QLineEdit { background-color: #F8F9F9; color: #2C3E50; border: 1px solid #BDC3C7; border-radius: 5px; padding: 8px; }
            QPushButton { border-radius: 5px; padding: 10px; font-weight: bold; }
        """)

        layout = QVBoxLayout(self)
        self.txt_old_pw = QLineEdit(); self.txt_old_pw.setPlaceholderText("Eski Şifre"); self.txt_old_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_new_pw = QLineEdit(); self.txt_new_pw.setPlaceholderText("Yeni Şifre"); self.txt_new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_new_pw_confirm = QLineEdit(); self.txt_new_pw_confirm.setPlaceholderText("Yeni Şifre (Tekrar)"); self.txt_new_pw_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        
        layout.addWidget(QLabel("Eski Şifre:")); layout.addWidget(self.txt_old_pw)
        layout.addWidget(QLabel("Yeni Şifre:")); layout.addWidget(self.txt_new_pw)
        layout.addWidget(QLabel("Yeni Şifre Tekrar:")); layout.addWidget(self.txt_new_pw_confirm)

        self.btn_save = QPushButton("Şifreyi Güncelle"); self.btn_save.setStyleSheet("background-color: #2ECC71; color: white;"); self.btn_save.clicked.connect(self.save_password)
        layout.addWidget(self.btn_save)

    def save_password(self):
        old = self.txt_old_pw.text().strip()
        new = self.txt_new_pw.text().strip()
        confirm = self.txt_new_pw_confirm.text().strip()

        if not old or not new or not confirm:
            QMessageBox.warning(self, "Hata", "Tüm alanları doldurun!")
            return
        if new != confirm:
            QMessageBox.warning(self, "Hata", "Yeni şifreler uyuşmuyor!")
            return
        
        if self.db.update_doctor_password(self.doctor_name, old, new):
            QMessageBox.information(self, "Başarılı", "Şifreniz başarıyla değiştirildi.")
            self.accept()
        else:
            QMessageBox.critical(self, "Hata", "Eski şifre hatalı!")

# ----------------------------------------
# ANA PENCERE (GUI)
# ----------------------------------------
class ParkinsonGUI(QMainWindow):
    def __init__(self, doctor_info):
        super().__init__()
        self.current_doctor = doctor_info
        self.setWindowTitle(f"NeuroMotion Analiz - Klinik Komuta Merkezi v7.1 | Doktor: {self.current_doctor['name']}")
        self.resize(1500, 950)
        self.plot_counter = 0 
        
        self.setStyleSheet("""
            QMainWindow { background-color: #F4F6F9; }
            QLabel { color: #2C3E50; font-size: 14px; font-family: 'Segoe UI', sans-serif; }
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit {
                background-color: #FFFFFF; color: #2C3E50; border: 1px solid #BDC3C7; border-radius: 5px; padding: 5px; font-size: 13px;
            }
            QComboBox::drop-down { border: 0px; }
            QFrame#ControlPanel { background-color: #FFFFFF; border-right: 1px solid #E0E6ED; }
            QFrame#Header { background-color: #2980B9; border-bottom: 3px solid #1ABC9C; }
            QLabel#HeaderTitle { font-size: 22px; font-weight: bold; color: #FFFFFF; margin-left: 10px; }
            QTabWidget::pane { border: 1px solid #E0E6ED; background: #FFFFFF; border-radius: 5px; }
            QTabBar::tab { background-color: #ECF0F1; color: #7F8C8D; padding: 10px 20px; border: 1px solid #E0E6ED; font-weight: bold; }
            QTabBar::tab:selected { background-color: #FFFFFF; color: #2980B9; border-bottom: 3px solid #2980B9; }
            QListWidget { background-color: #FFFFFF; border: 1px solid #BDC3C7; border-radius: 5px; font-size: 13px; color: #2C3E50;}
            QListWidget::item:selected { background-color: #D6EAF8; color: #2980B9; font-weight: bold; }
            QGroupBox { color: #2980B9; font-weight: bold; border: 1px solid #BDC3C7; border-radius: 8px; margin-top: 10px; padding-top: 15px; background-color: #F8F9F9;}
            QProgressBar { border: 1px solid #BDC3C7; border-radius: 5px; text-align: center; color: #2C3E50; font-weight: bold; background-color: #ECF0F1; height: 18px; margin-top: 5px;}
            QProgressBar::chunk { background-color: #2ECC71; border-radius: 4px; }
            QPushButton.imu_card { background-color: #FFFFFF; border: 2px solid #BDC3C7; border-radius: 10px; color: #2C3E50; font-weight: bold; font-size: 16px; text-align: left; padding-left: 15px; }
            QPushButton.imu_card:hover { border: 2px solid #3498DB; background-color: #EBF5FB; }
        """)

        self.worker = None
        self.recording_data = [] 
        self.is_recording = False
        self.current_filename = ""
        self.current_mode = "" 
        self.current_patient = None
        
        # OSİLOSKOP DEĞİŞKENLERİ VE ZAMANLAYICILARI
        self.is_stimulating_1 = False
        self.stim_countdown_timer_1 = QTimer(); self.stim_countdown_timer_1.timeout.connect(self.update_stim_countdown_1)
        self.stim_remaining_1 = 0
        
        self.is_stimulating_2 = False
        self.stim_countdown_timer_2 = QTimer(); self.stim_countdown_timer_2.timeout.connect(self.update_stim_countdown_2)
        self.stim_remaining_2 = 0
        
        self.workspace_root = os.path.dirname(os.path.abspath(__file__))
        self.db = TestDatabase()
        self.db.log_event("INFO", f"Uygulama oturumu başladı.", self.current_doctor['name'])
        self.buffer_size = 300
        self.multi_data_buffer = [{'ax': [], 'ay': [], 'az': [], 'gx': [], 'gy': [], 'gz': []} for _ in range(12)]
        self.active_detailed_imu = 0 

        self.init_ui()
        self.refresh_patient_list()
        
        self.update_preview_1()
        self.update_preview_2()
    
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget); main_layout.setContentsMargins(0, 0, 0, 0)

        header_frame = QFrame(); header_frame.setObjectName("Header")
        header_layout = QHBoxLayout(header_frame); header_layout.setContentsMargins(10, 5, 10, 5)
        
        self.btn_toggle_panel = QPushButton("☰")
        self.btn_toggle_panel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_panel.setStyleSheet("QPushButton { background-color: transparent; color: white; font-size: 26px; border: none; padding: 5px; } QPushButton:hover { color: #F1C40F; }")
        self.btn_toggle_panel.clicked.connect(self.toggle_left_panel)
        header_layout.addWidget(self.btn_toggle_panel)

        header_title = QLabel("Klinik Hasta Yönetimi")
        header_title.setObjectName("HeaderTitle")
        header_layout.addWidget(header_title); header_layout.addStretch()

        # DOKTOR MENÜSÜ (SAĞ ÜST)
        self.btn_user_menu = QPushButton(f"👤 {self.current_doctor['name']}")
        self.btn_user_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_user_menu.setStyleSheet("""
            QPushButton { 
                background-color: rgba(255,255,255,0.2); color: white; border: 1px solid white; 
                border-radius: 5px; padding: 5px 15px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.3); }
        """)
        self.btn_user_menu.clicked.connect(self.show_user_menu)
        header_layout.addWidget(self.btn_user_menu)

        main_layout.addWidget(header_frame)

        content_layout = QHBoxLayout(); content_layout.setContentsMargins(0, 0, 10, 10); content_layout.setSpacing(10)
        self.left_panel = self._create_left_panel()
        content_layout.addWidget(self.left_panel)

        main_tabs = QTabWidget()
        main_tabs.addTab(self._create_recording_tab(), "Kayıt & Stimülasyon")
        main_tabs.addTab(self._create_patient_management_tab(), "Rapor Yönetimi")
        main_tabs.addTab(self._create_patient_database_tab(), "Hasta Bilgi Bankası")
        main_tabs.addTab(self._create_add_patient_tab(), "Yeni Hasta Kaydı")
        
        content_layout.addWidget(main_tabs, 1)
        main_layout.addLayout(content_layout)

    def _create_left_panel(self):
        control_frame = QFrame(); control_frame.setObjectName("ControlPanel")
        control_frame.setMinimumWidth(320); control_frame.setMaximumWidth(320)
        left_layout = QVBoxLayout(control_frame); left_layout.setContentsMargins(10, 10, 10, 10)

        lbl_patient = QLabel("HASTA SEÇİMİ")
        lbl_patient.setStyleSheet("color: #2980B9; font-weight: bold; margin-bottom: 5px;")
        left_layout.addWidget(lbl_patient)

        search_row = QHBoxLayout()
        self.txt_search_patient = QLineEdit(); self.txt_search_patient.setPlaceholderText("Ara...")
        self.txt_search_patient.textChanged.connect(self.search_patients)
        search_row.addWidget(self.txt_search_patient)
        
        btn_refresh_patients = self.create_button("Yenile", "#ECF0F1", "#D5D8DC", text_color="#2C3E50")
        btn_refresh_patients.setMaximumWidth(60); btn_refresh_patients.clicked.connect(self.refresh_patient_list)
        search_row.addWidget(btn_refresh_patients); left_layout.addLayout(search_row)

        self.list_patients = QListWidget(); self.list_patients.setFixedHeight(120)
        self.list_patients.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_patients.customContextMenuRequested.connect(self.show_patient_context_menu)
        self.list_patients.itemClicked.connect(self.select_patient)
        left_layout.addWidget(self.list_patients)

        self.lbl_current_patient = QLabel("Hiçbiri seçilmedi")
        self.lbl_current_patient.setStyleSheet("color: #27AE60; font-weight: bold; font-size: 15px; margin-top: 5px;")
        left_layout.addWidget(self.lbl_current_patient)

        self.text_patient_details = QLineEdit(); self.text_patient_details.setReadOnly(True)
        self.text_patient_details.setStyleSheet("background-color: #F4F6F9; color: #34495E; font-size: 11px;")
        left_layout.addWidget(self.text_patient_details)

        lbl_history = QLabel("Klinik Öykü:"); lbl_history.setStyleSheet("font-size: 12px; color: #7F8C8D; margin-top: 5px; font-weight: bold;")
        left_layout.addWidget(lbl_history)
        self.txt_patient_history = QTextEdit(); self.txt_patient_history.setReadOnly(True); self.txt_patient_history.setMaximumHeight(80)
        self.txt_patient_history.setStyleSheet("background-color: #F8F9F9; color: #2C3E50; font-size: 12px;")
        left_layout.addWidget(self.txt_patient_history)

        left_layout.addSpacing(5); line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #E0E6ED;"); left_layout.addWidget(line)

        lbl_device = QLabel("CİHAZ BAĞLANTISI"); lbl_device.setStyleSheet("color: #2980B9; font-weight: bold; margin-left: 1px;")
        left_layout.addWidget(lbl_device)

        port_row = QHBoxLayout()
        self.combo_ports = QComboBox(); port_row.addWidget(self.combo_ports)
        btn_refresh = self.create_button("Yenile", "#ECF0F1", "#D5D8DC", text_color="#2980B9")
        btn_refresh.setMaximumWidth(65); btn_refresh.clicked.connect(self.refresh_ports)
        port_row.addWidget(btn_refresh); left_layout.addLayout(port_row)

        self.btn_connect = self.create_button("CİHAZA BAĞLAN", "#3498DB", "#2980B9")
        self.btn_connect.clicked.connect(self.toggle_connection); left_layout.addWidget(self.btn_connect)

        lbl_battery = QLabel("Batarya Durumu"); lbl_battery.setStyleSheet("color: #2980B9; font-size: 13px; font-weight: bold; margin-top: 10px; margin-left: 1px;")
        left_layout.addWidget(lbl_battery)
        self.prog_battery = QProgressBar(); self.prog_battery.setRange(0, 100); self.prog_battery.setValue(0)
        left_layout.addWidget(self.prog_battery)

        lbl_mode = QLabel("PROTOKOL SEÇİMİ"); lbl_mode.setStyleSheet("color: #E67E22; font-weight: bold; margin-top: 15px; margin-left: -6px;")
        left_layout.addWidget(lbl_mode)

        self.combo_mode = QComboBox(); self.combo_mode.addItems(["Tremor Analizi", "Bradikinezi Analizi"])
        self.combo_mode.setStyleSheet("border: 2px solid #E67E22; font-weight: bold; color: #D35400;")
        left_layout.addWidget(self.combo_mode)

        left_layout.addSpacing(10)
        self.btn_record = self.create_button("KAYDI BAŞLAT", "#E74C3C", "#C0392B"); self.btn_record.setEnabled(False)
        self.btn_record.setMinimumHeight(45); self.btn_record.clicked.connect(self.toggle_recording)
        left_layout.addWidget(self.btn_record); left_layout.addStretch()
        from PyQt6.QtGui import QPixmap # Görüntü işleme modülü
        
        self.lbl_logo = QLabel()
        self.lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        logo_path = os.path.join(self.workspace_root, "logo.png")
        
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            # Logoyu sol panele sığacak şekilde (örn: 250x100) orantılı olarak küçültür
            scaled_pixmap = pixmap.scaled(250, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.lbl_logo.setPixmap(scaled_pixmap)
        else:
            # Eğer logo.png bulunamazsa yer tutucu bir yazı gösterir
            self.lbl_logo.setText("[ LOGO BULUNAMADI ]")
            self.lbl_logo.setStyleSheet("color: #BDC3C7; font-weight: bold; padding: 20px;")

        left_layout.addWidget(self.lbl_logo)
        return control_frame

    def _create_slider_widget(self, title, min_val, max_val, default_val, suffix, color, callback):
        container = QWidget(); layout = QVBoxLayout(container); layout.setContentsMargins(5, 0, 5, 0); layout.setSpacing(2)
        top_layout = QHBoxLayout(); lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 12px; color: #7F8C8D; font-weight: bold;")
        
        spin_val = QSpinBox(); spin_val.setRange(min_val, max_val); spin_val.setValue(default_val); spin_val.setSuffix(f" {suffix}")
        spin_val.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons); spin_val.setAlignment(Qt.AlignmentFlag.AlignRight)
        spin_val.setFixedWidth(80)
        spin_val.setStyleSheet(f"QSpinBox {{ font-size: 13px; color: {color}; font-weight: bold; background-color: transparent; border: 1px solid transparent; padding: 1px; }} QSpinBox:focus {{ border: 1px solid {color}; border-radius: 4px; background-color: #FFFFFF; }}")
        
        top_layout.addWidget(lbl_title); top_layout.addWidget(spin_val, alignment=Qt.AlignmentFlag.AlignRight)
        
        slider = QSlider(Qt.Orientation.Horizontal); slider.setRange(min_val, max_val); slider.setValue(default_val)
        slider.setStyleSheet(f"QSlider::groove:horizontal {{ border-radius: 4px; height: 6px; background: #ECF0F1; }} QSlider::sub-page:horizontal {{ background: {color}; border-radius: 4px; }} QSlider::handle:horizontal {{ background: #FFFFFF; border: 2px solid {color}; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }}")
        
        def on_slider_changed(val): spin_val.setValue(val); (callback() if callback else None)
        def on_spinbox_changed(val): slider.setValue(val)
                
        slider.valueChanged.connect(on_slider_changed); spin_val.valueChanged.connect(on_spinbox_changed)
        layout.addLayout(top_layout); layout.addWidget(slider)
        return container, slider

    def _create_recording_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)

        top_bar = QHBoxLayout()
        self.btn_back_to_grid = self.create_button("< Tüm Sensörlere Dön", "#7F8C8D", "#95A5A6")
        self.btn_back_to_grid.setVisible(False); self.btn_back_to_grid.clicked.connect(lambda: self.switch_sensor_view(-1))
        top_bar.addWidget(self.btn_back_to_grid); top_bar.addStretch() 
        
        lbl_view_title = QLabel("Aktif Görünüm:")
        lbl_view_title.setStyleSheet("font-weight: bold; color: #7F8C8D; margin-right: 10px;")
        top_bar.addWidget(lbl_view_title)
        
        self.btn_view1 = self.create_button("1 (Karma Ekran)", "#9B59B6", "#8E44AD", text_color="#FFFFFF")
        self.btn_view2 = self.create_button("2 (Sensörler)", "#ECF0F1", "#BDC3C7", text_color="#2C3E50")
        self.btn_view3 = self.create_button("3 (Osiloskop)", "#ECF0F1", "#BDC3C7", text_color="#2C3E50")
        
        self.btn_view1.clicked.connect(lambda: self.switch_graph_view(0))
        self.btn_view2.clicked.connect(lambda: self.switch_graph_view(1))
        self.btn_view3.clicked.connect(lambda: self.switch_graph_view(2))
        
        top_bar.addWidget(self.btn_view1); top_bar.addWidget(self.btn_view2); top_bar.addWidget(self.btn_view3)
        layout.addLayout(top_bar)

        self.main_stack = QStackedWidget()
        
        # KATMAN 1 (Index 0): KARMA GÖRÜNÜM
        # KATMAN 1 (Index 0): KARMA GÖRÜNÜM
        page_mixed = QWidget(); page_mixed_layout = QVBoxLayout(page_mixed); page_mixed_layout.setContentsMargins(0, 0, 0, 0); page_mixed_layout.setSpacing(10)
        
        # 1. Kısım: IMU Butonları (Sol El ve Sağ El Ayrımı - 6x2 Genel Düzen)
        top_imu_layout = QHBoxLayout()
        top_imu_layout.setSpacing(15) # Gruplar ve çizgi arasına nefes alma payı
        
        # SOL EL GRUBU (IMU 1-6)
        left_grid_widget = QWidget(); left_grid_layout = QGridLayout(left_grid_widget)
        left_grid_layout.setSpacing(10); left_grid_layout.setContentsMargins(0, 0, 0, 0)
        
        # AYIRICI İNCE ÇİZGİ
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet("border: 2px solid #34495E; max-width: 2px; border-radius: 1px;")
        
        # SAĞ EL GRUBU (IMU 7-12)
        right_grid_widget = QWidget(); right_grid_layout = QGridLayout(right_grid_widget)
        right_grid_layout.setSpacing(10); right_grid_layout.setContentsMargins(0, 0, 0, 0)
        
        self.imu_buttons_mixed = []
        for i in range(12):
            btn = QPushButton(f"IMU {i+1}\n\nDurum: Bekliyor...")
            btn.setProperty("class", "imu_card")
            btn.setSizePolicy(btn.sizePolicy().Policy.Expanding, btn.sizePolicy().Policy.Expanding)
            btn.clicked.connect(lambda checked, idx=i: self.switch_sensor_view(idx))
            
            # MATEMATİK: İlk 6 sensörü SOLA, son 6 sensörü SAĞA dağıtıyoruz
            if i < 6:
                # 3 sütun, 2 satır şeklinde sola dizer
                left_grid_layout.addWidget(btn, i // 3, i % 3)
            else:
                # 3 sütun, 2 satır şeklinde sağa dizer
                right_grid_layout.addWidget(btn, (i - 6) // 3, (i - 6) % 3)
                
            self.imu_buttons_mixed.append(btn)
            
        top_imu_layout.addWidget(left_grid_widget, stretch=5)
        top_imu_layout.addWidget(divider, stretch=0)
        top_imu_layout.addWidget(right_grid_widget, stretch=5)
        
        
        page_mixed_layout.addLayout(top_imu_layout, stretch=2)

        # 2. Kısım: Yatay Grafik Alanı (Sensörler ile Alt Parametrelerin Arasında)
        mixed_stim_widget = QWidget(); mixed_stim_layout = QHBoxLayout(mixed_stim_widget); mixed_stim_layout.setSpacing(10); mixed_stim_layout.setContentsMargins(0, 0, 0, 0)
        mixed_stim_widget.setMaximumHeight(160) # <-- Grafiklerin dikey boyutunu küçülttük
        
        self.plot_stim_1_mixed = pg.PlotWidget(title="Kanal 1 Önizleme"); self.plot_stim_1_mixed.showGrid(x=True, y=True, alpha=0.5); self.plot_stim_1_mixed.setBackground('#111111')
        self.plot_stim_1_mixed.getAxis('left').setPen('#2ECC71'); self.plot_stim_1_mixed.getAxis('bottom').setPen('#2ECC71')
        self.plot_stim_1_mixed.getAxis('left').setWidth(45) 
        self.plot_stim_1_mixed.setLabel('bottom', 'Zaman', units='ms'); self.plot_stim_1_mixed.setLabel('left', 'Akım', units='mA')
        self.curve_stim_1_mixed = self.plot_stim_1_mixed.plot(pen=pg.mkPen('#2ECC71', width=2))
        
        self.plot_stim_2_mixed = pg.PlotWidget(title="Kanal 2 Önizleme"); self.plot_stim_2_mixed.showGrid(x=True, y=True, alpha=0.5); self.plot_stim_2_mixed.setBackground('#111111')
        self.plot_stim_2_mixed.getAxis('left').setPen('#3498DB'); self.plot_stim_2_mixed.getAxis('bottom').setPen('#3498DB')
        self.plot_stim_2_mixed.getAxis('left').setWidth(45) 
        self.plot_stim_2_mixed.setLabel('bottom', 'Zaman', units='ms'); self.plot_stim_2_mixed.setLabel('left', 'Akım', units='µA')
        self.curve_stim_2_mixed = self.plot_stim_2_mixed.plot(pen=pg.mkPen('#3498DB', width=2))
        
        mixed_stim_layout.addWidget(self.plot_stim_1_mixed); mixed_stim_layout.addWidget(self.plot_stim_2_mixed)
        page_mixed_layout.addWidget(mixed_stim_widget, stretch=0); self.main_stack.addWidget(page_mixed)

        # KATMAN 2 (Index 1): SADECE SENSÖR GÖRÜNÜMÜ
        page_sensors = QWidget(); page_sensors_layout = QVBoxLayout(page_sensors); page_sensors_layout.setContentsMargins(0,0,0,0)
        self.sensor_stack = QStackedWidget(); self.grid_widget = QWidget(); grid_layout = QGridLayout(self.grid_widget); grid_layout.setSpacing(15)
        
        self.imu_buttons = []
        for i in range(12):
            btn = QPushButton(f"IMU {i+1}\n\nDurum: Bekliyor...")
            btn.setProperty("class", "imu_card"); btn.setSizePolicy(btn.sizePolicy().Policy.Expanding, btn.sizePolicy().Policy.Expanding)
            btn.clicked.connect(lambda checked, idx=i: self.switch_sensor_view(idx))
            self.imu_buttons.append(btn); grid_layout.addWidget(btn, row := i // 4, col := i % 4)
            
        self.sensor_stack.addWidget(self.grid_widget) 
        self.detail_widget = QWidget(); detail_layout = QVBoxLayout(self.detail_widget)
        self.lbl_active_imu = QLabel("IMU 1 Detay Görünümü"); self.lbl_active_imu.setStyleSheet("font-size: 18px; font-weight: bold; color: #2980B9;")
        detail_layout.addWidget(self.lbl_active_imu)
        
        # --- KAYDIRILABİLİR ALAN (SCROLL AREA) EKLENİYOR ---
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_scroll.setStyleSheet("QScrollArea { background-color: transparent; }")
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(20)

        # 1. GRAFİK: TOTAL GÜÇ (MAGNITUDE / BİLEŞKE VEKTÖR)
        self.plot_mag = pg.PlotWidget(title="Toplam Vektörel Güç (Magnitude - G)"); self.plot_mag.setMinimumHeight(200)
        self.plot_mag.showGrid(x=True, y=True, alpha=0.5); self.customize_plot(self.plot_mag)
        self.curve_mag = self.plot_mag.plot(pen=pg.mkPen('#8E44AD', width=2)) # Mor Renk
        scroll_layout.addWidget(self.plot_mag)
        
        scroll_layout.addStretch() # Elemanları yukarı iter ki grafikler çok esnemesin
        self.detail_scroll.setWidget(scroll_content)
        detail_layout.addWidget(self.detail_scroll, stretch=1)

        # 2. GRAFİK: KARMA EKSENLER 
        self.plot_combined = pg.PlotWidget(title="2. Karma Eksen Görünümü (X, Y, Z)")
        self.plot_combined.setMinimumHeight(250); self.plot_combined.showGrid(x=True, y=True, alpha=0.5)
        self.customize_plot(self.plot_combined)
        # Karma grafik için 3 ayrı eğri tanımlıyoruz
        self.curve_comb_x = self.plot_combined.plot(pen=pg.mkPen('#E74C3C', width=1.5), name="X")
        self.curve_comb_y = self.plot_combined.plot(pen=pg.mkPen('#27AE60', width=1.5), name="Y")
        self.curve_comb_z = self.plot_combined.plot(pen=pg.mkPen('#2980B9', width=1.5), name="Z")
        scroll_layout.addWidget(self.plot_combined)
        
        # 3. GRAFİK: SADECE X EKSENİ
        self.plot_ax_only = pg.PlotWidget(title="İvme - X Ekseni (İleri/Geri)"); self.plot_ax_only.setMinimumHeight(200)
        self.plot_ax_only.showGrid(x=True, y=True, alpha=0.5); self.customize_plot(self.plot_ax_only)
        self.curve_ax = self.plot_ax_only.plot(pen=pg.mkPen('#E74C3C', width=2))
        scroll_layout.addWidget(self.plot_ax_only)
        
        # 4. GRAFİK: SADECE Y EKSENİ
        self.plot_ay_only = pg.PlotWidget(title="İvme - Y Ekseni (Sağ/Sol)"); self.plot_ay_only.setMinimumHeight(200)
        self.plot_ay_only.showGrid(x=True, y=True, alpha=0.5); self.customize_plot(self.plot_ay_only)
        self.curve_ay = self.plot_ay_only.plot(pen=pg.mkPen('#27AE60', width=2))
        scroll_layout.addWidget(self.plot_ay_only)
        
        # 5. GRAFİK: SADECE Z EKSENİ
        self.plot_az_only = pg.PlotWidget(title="İvme - Z Ekseni (Yukarı/Aşağı)"); self.plot_az_only.setMinimumHeight(200)
        self.plot_az_only.showGrid(x=True, y=True, alpha=0.5); self.customize_plot(self.plot_az_only)
        self.curve_az = self.plot_az_only.plot(pen=pg.mkPen('#2980B9', width=2))
        scroll_layout.addWidget(self.plot_az_only)
        
        
        
        self.sensor_stack.addWidget(self.detail_widget); page_sensors_layout.addWidget(self.sensor_stack); self.main_stack.addWidget(page_sensors)

        # KATMAN 3 (Index 2): SADECE OSİLOSKOP GÖRÜNÜMÜ
        page_stim = QWidget(); page_stim_layout = QVBoxLayout(page_stim); page_stim_layout.setContentsMargins(0, 0, 0, 0)
        
        self.plot_stim_1 = pg.PlotWidget(title="Kanal 1 - Sinyal Önizlemesi"); self.plot_stim_1.showGrid(x=True, y=True, alpha=0.5); self.plot_stim_1.setBackground('#111111') 
        self.plot_stim_1.getAxis('left').setPen('#2ECC71'); self.plot_stim_1.getAxis('bottom').setPen('#2ECC71')
        self.plot_stim_1.setLabel('bottom', 'Zaman', units='ms'); self.plot_stim_1.setLabel('left', 'Akım', units='µA')
        self.curve_stim_1 = self.plot_stim_1.plot(pen=pg.mkPen('#2ECC71', width=2)); page_stim_layout.addWidget(self.plot_stim_1)
        
        self.plot_stim_2 = pg.PlotWidget(title="Kanal 2 - Sinyal Önizlemesi"); self.plot_stim_2.showGrid(x=True, y=True, alpha=0.5); self.plot_stim_2.setBackground('#111111') 
        self.plot_stim_2.getAxis('left').setPen('#3498DB'); self.plot_stim_2.getAxis('bottom').setPen('#3498DB')
        self.plot_stim_2.setLabel('bottom', 'Zaman', units='ms'); self.plot_stim_2.setLabel('left', 'Akım', units='mA')
        self.curve_stim_2 = self.plot_stim_2.plot(pen=pg.mkPen('#3498DB', width=2)); page_stim_layout.addWidget(self.plot_stim_2)

        self.main_stack.addWidget(page_stim); layout.addWidget(self.main_stack, stretch=1)

        # --- ELEKTRİK YÖNETİMİ PANELİ ---
        group_stim = QGroupBox("Terapötik Stimülasyon Yönetimi"); group_stim.setMaximumHeight(220); stim_main_layout = QVBoxLayout(group_stim)
        
        stim_layout_1 = QHBoxLayout(); lbl_ch1 = QLabel("KANAL 1:"); lbl_ch1.setStyleSheet("font-weight: bold; color: #2ECC71;"); stim_layout_1.addWidget(lbl_ch1)
        w_hz_1, self.slider_hz_1 = self._create_slider_widget("Frekans", 1, 200, 50, "Hz", "#2ECC71", self.update_preview_1)
        w_pulse_1, self.slider_pulse_1 = self._create_slider_widget("Genişlik", 50, 1000, 200, "us", "#2ECC71", self.update_preview_1)
        w_amp_1, self.slider_amp_1 = self._create_slider_widget("Şiddet", 0, 100, 2, "mA", "#2ECC71", self.update_preview_1)
        w_dur_1, self.slider_dur_1 = self._create_slider_widget("Süre", 1, 120, 20, "Dk", "#2ECC71", None)
        stim_layout_1.addWidget(w_hz_1); stim_layout_1.addWidget(w_pulse_1); stim_layout_1.addWidget(w_amp_1); stim_layout_1.addWidget(w_dur_1)
        self.btn_apply_stim_1 = self.create_button("SİNYALİ BAŞLAT (K1)", "#2ECC71", "#27AE60"); self.btn_apply_stim_1.clicked.connect(self.toggle_stimulation_1) 
        stim_layout_1.addWidget(self.btn_apply_stim_1); stim_main_layout.addLayout(stim_layout_1)
        
        stim_layout_2 = QHBoxLayout(); lbl_ch2 = QLabel("KANAL 2:"); lbl_ch2.setStyleSheet("font-weight: bold; color: #3498DB;"); stim_layout_2.addWidget(lbl_ch2)
        w_hz_2, self.slider_hz_2 = self._create_slider_widget("Frekans", 1, 200, 50, "Hz", "#3498DB", self.update_preview_2)
        w_pulse_2, self.slider_pulse_2 = self._create_slider_widget("Genişlik", 50, 1000, 200, "us", "#3498DB", self.update_preview_2)
        w_amp_2, self.slider_amp_2 = self._create_slider_widget("Şiddet", 0, 100, 2, "mA", "#3498DB", self.update_preview_2)
        w_dur_2, self.slider_dur_2 = self._create_slider_widget("Süre", 1, 120, 20, "Dk", "#3498DB", None)
        stim_layout_2.addWidget(w_hz_2); stim_layout_2.addWidget(w_pulse_2); stim_layout_2.addWidget(w_amp_2); stim_layout_2.addWidget(w_dur_2)
        self.btn_apply_stim_2 = self.create_button("SİNYALİ BAŞLAT (K2)", "#3498DB", "#2980B9"); self.btn_apply_stim_2.clicked.connect(self.toggle_stimulation_2) 
        stim_layout_2.addWidget(self.btn_apply_stim_2); stim_main_layout.addLayout(stim_layout_2)

        layout.addWidget(group_stim, stretch=0); self.switch_graph_view(0)
        return tab

    def _create_patient_management_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        lbl_title = QLabel("Klinik Rapor Arşivi"); lbl_title.setStyleSheet("font-size: 18px; font-weight: bold;"); layout.addWidget(lbl_title)
        self.list_tremor = QListWidget(); self.list_tremor.setFixedHeight(150); self.list_tremor.itemDoubleClicked.connect(self.open_pdf_tremor)
        layout.addWidget(QLabel("Tremor Raporları")); layout.addWidget(self.list_tremor)
        self.list_bradi = QListWidget(); self.list_bradi.setFixedHeight(150); self.list_bradi.itemDoubleClicked.connect(self.open_pdf_bradi)
        layout.addWidget(QLabel("Bradikinezi Raporları")); layout.addWidget(self.list_bradi); layout.addStretch()
        return tab

    def _create_patient_database_tab(self):
        tab = QWidget(); layout = QHBoxLayout(tab)
        search_side = QVBoxLayout(); lbl_list_title = QLabel("KAYITLI HASTALAR"); lbl_list_title.setStyleSheet("font-weight: bold; color: #2980B9;")
        search_side.addWidget(lbl_list_title)
        self.db_search_input = QLineEdit(); self.db_search_input.setPlaceholderText("İsim veya protokol ile hızlı ara..."); self.db_search_input.textChanged.connect(self.search_in_database_tab)
        search_side.addWidget(self.db_search_input)
        self.db_patient_list = QListWidget(); self.db_patient_list.setStyleSheet("QListWidget { border: 1px solid #D5D8DC; border-radius: 8px; }")
        self.db_patient_list.itemClicked.connect(self.display_full_patient_info); search_side.addWidget(self.db_patient_list); layout.addLayout(search_side, 1)

        self.detail_card = QGroupBox("HASTA AYRINTILI DOSYASI"); self.detail_card.setStyleSheet("QGroupBox { font-size: 15px; background-color: #FFFFFF; }")
        card_layout = QVBoxLayout(self.detail_card)
        self.txt_full_details = QTextBrowser(); self.txt_full_details.setOpenExternalLinks(False); self.txt_full_details.anchorClicked.connect(self.open_report_from_link)
        self.txt_full_details.setReadOnly(True); card_layout.addWidget(self.txt_full_details); layout.addWidget(self.detail_card, 2)
        QTimer.singleShot(100, self.refresh_db_tab_list)
        return tab

    def _create_add_patient_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll_widget = QWidget(); scroll_widget.setStyleSheet("background-color: #FFFFFF;")
        form_layout = QFormLayout(scroll_widget)
        self.txt_protocol = QLineEdit(); self.txt_new_patient_name = QLineEdit()
        self.spin_age = QSpinBox(); self.spin_age.setRange(0, 150)
        self.combo_gender = QComboBox(); self.combo_gender.addItems(["Erkek", "Kadın", "Diğer"])
        self.combo_dominant_side = QComboBox(); self.combo_dominant_side.addItems(["Sağ", "Sol", "Çift Taraf"])
        self.spin_onset_year = QSpinBox(); self.spin_onset_year.setRange(1950, datetime.now().year); self.spin_onset_year.setValue(datetime.now().year)
        self.combo_diagnosis = QComboBox(); self.combo_diagnosis.addItems(["Parkinson", "Essential Tremor", "Diğer"])
        self.txt_doctor_name = QLineEdit(); self.txt_phone = QLineEdit()
        self.txt_new_history = QTextEdit(); self.txt_new_history.setMaximumHeight(100)
        form_layout.addRow("Protokol No:", self.txt_protocol); form_layout.addRow("Hasta Adı:", self.txt_new_patient_name)
        form_layout.addRow("Yaş:", self.spin_age); form_layout.addRow("Cinsiyet:", self.combo_gender)
        form_layout.addRow("Baskın Taraf:", self.combo_dominant_side); form_layout.addRow("Başlangıç Yılı:", self.spin_onset_year)
        form_layout.addRow("Tanı:", self.combo_diagnosis); form_layout.addRow("Doktor:", self.txt_doctor_name)
        form_layout.addRow("Telefon:", self.txt_phone); form_layout.addRow("Klinik Öykü:", self.txt_new_history)
        layout.addWidget(scroll_widget)
        btn_layout = QHBoxLayout()
        btn_save = self.create_button("Kaydı Tamamla", "#2ECC71", "#27AE60"); btn_save.clicked.connect(self.add_new_patient)
        btn_cancel = self.create_button("Temizle", "#95A5A6", "#7F8C8D"); btn_cancel.clicked.connect(self.clear_patient_form)
        btn_layout.addWidget(btn_save); btn_layout.addWidget(btn_cancel); layout.addLayout(btn_layout)
        return tab

    # ---------------- FONKSİYONLAR ----------------
    def refresh_ports(self):
        """Eksik olan port yenileme fonksiyonu"""
        self.combo_ports.clear()
        for p in serial.tools.list_ports.comports():
            self.combo_ports.addItem(p.device)
            
    def toggle_left_panel(self):
        width = self.left_panel.width()
        target_width = 0 if width > 0 else 320
        self.panel_anim = QPropertyAnimation(self.left_panel, b"maximumWidth"); self.panel_anim.setDuration(300); self.panel_anim.setStartValue(width); self.panel_anim.setEndValue(target_width)
        self.panel_anim.setEasingCurve(QEasingCurve.Type.InOutQuart)
        self.panel_anim_min = QPropertyAnimation(self.left_panel, b"minimumWidth"); self.panel_anim_min.setDuration(300); self.panel_anim_min.setStartValue(width); self.panel_anim_min.setEndValue(target_width)
        self.panel_anim_min.setEasingCurve(QEasingCurve.Type.InOutQuart)
        self.panel_anim.start(); self.panel_anim_min.start()

    def switch_graph_view(self, index):
        self.main_stack.setCurrentIndex(index)
        default_style = "QPushButton { background-color: #ECF0F1; color: #2C3E50; border-radius: 6px; font-weight: bold; font-size: 14px; border: 1px solid #BDC3C7; }"
        self.btn_view1.setStyleSheet("QPushButton { background-color: #9B59B6; color: #FFFFFF; border-radius: 6px; font-weight: bold; font-size: 14px; border: none; }" if index == 0 else default_style)
        self.btn_view2.setStyleSheet("QPushButton { background-color: #3498DB; color: #FFFFFF; border-radius: 6px; font-weight: bold; font-size: 14px; border: none; }" if index == 1 else default_style)
        self.btn_view3.setStyleSheet("QPushButton { background-color: #E74C3C; color: #FFFFFF; border-radius: 6px; font-weight: bold; font-size: 14px; border: none; }" if index == 2 else default_style)
        if index != 1: self.btn_back_to_grid.setVisible(False)
        else:
            if self.sensor_stack.currentIndex() == 1: self.btn_back_to_grid.setVisible(True)

    def switch_sensor_view(self, imu_index):
        if imu_index == -1:
            self.sensor_stack.setCurrentIndex(0); self.btn_back_to_grid.setVisible(False)
        else:
            self.active_detailed_imu = imu_index; self.lbl_active_imu.setText(f"IMU {imu_index+1} Detay Görünümü")
            self.sensor_stack.setCurrentIndex(1); self.btn_back_to_grid.setVisible(True); self.switch_graph_view(1) 

    def refresh_db_tab_list(self):
        self.db_patient_list.clear()
        for patient in self.db.get_all_patients(): self.db_patient_list.addItem(patient)

    def search_in_database_tab(self):
        txt = self.db_search_input.text().lower(); self.db_patient_list.clear()
        for p in self.db.get_all_patients():
            if txt in p.lower(): self.db_patient_list.addItem(p)

    def display_full_patient_info(self, item):
        patient_name = item.text(); details = self.db.get_patient_details(patient_name)
        if details:
            history_content = details.get('clinical_history')
            if not history_content:
                history_content = "<i>Kayıtlı öykü bulunamadı.</i>"
            else:
                history_content = history_content.replace('\n', '<br>')

            p_folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", patient_name)
            t_folder = os.path.join(p_folder, "VeriSeti_Tremor"); b_folder = os.path.join(p_folder, "VeriSeti_Bradikinezi")
            
            reports = []
            if os.path.exists(t_folder):
                for f in os.listdir(t_folder):
                    if f.endswith(('.pdf', '.csv')): reports.append({'file': f, 'type': 'Tremor Analizi', 'time': os.path.getmtime(os.path.join(t_folder, f))})
            if os.path.exists(b_folder):
                for f in os.listdir(b_folder):
                    if f.endswith(('.pdf', '.csv')): reports.append({'file': f, 'type': 'Bradikinezi Analizi', 'time': os.path.getmtime(os.path.join(b_folder, f))})
                        
            reports.sort(key=lambda x: x['time'], reverse=True)
            report_rows_html = ""
            if reports:
                for r in reports:
                    date_str = datetime.fromtimestamp(r['time']).strftime('%d.%m.%Y - %H:%M')
                    file_url = f"file:///{p_folder}/{'VeriSeti_Tremor' if r['type'] == 'Tremor Analizi' else 'VeriSeti_Bradikinezi'}/{r['file']}".replace("\\", "/")
                    report_rows_html += f"<tr><td style='padding: 6px; border-bottom: 1px solid #ECF0F1;'>{date_str}</td><td style='padding: 6px; border-bottom: 1px solid #ECF0F1; font-weight: bold;'>{r['type']}</td><td style='padding: 6px; border-bottom: 1px solid #ECF0F1;'><a href='{file_url}' style='color: #E67E22; text-decoration: none; font-weight: bold;'>Dosya: {r['file']}</a></td></tr>"

            info_html = f"""
            <div style="font-family: Arial; color: #2C3E50;">
                <h3 style="color: #2980B9;">GENEL KİMLİK BİLGİLERİ</h3>
                <p><b>Protokol No:</b> {details.get('protocol_no', '-')} | <b>Hasta Adı:</b> {patient_name}</p>
                <p><b>Yaş / Cinsiyet:</b> {details.get('age', '-')} / {details.get('gender', '-')} | <b>İletişim:</b> {details.get('contact_phone', '-')}</p>
                <h3 style="color: #E67E22;">KLİNİK DURUM VE TANI</h3>
                <p><b>Tanı Grubu:</b> {details.get('diagnosis', '-')} | <b>Baskın Taraf:</b> {details.get('dominant_side', '-')}</p>
                <h3 style="color: #8E44AD;">KLİNİK ÖYKÜ</h3>
                <div style="background-color: #F4F6F9; padding: 10px; border-radius: 5px;">{history_content}</div>
                <h3 style="color: #16A085;">GEÇMİŞ RAPORLAR VE TESTLER</h3>
                <table style="width: 100%; font-size: 13px; text-align: left; border-collapse: collapse;">
                    <tr style="background-color: #ECF0F1;"><th>Kayıt Tarihi</th><th>Analiz Türü</th><th>Dosya</th></tr>{report_rows_html}
                </table>
            </div>"""
            self.txt_full_details.setHtml(info_html)
            
    def open_report_from_link(self, url):
        file_path = url.toLocalFile()
        if os.path.exists(file_path):
            try: os.startfile(file_path)
            except Exception as e: print(f"Dosya açma hatası: {e}")
        else: QMessageBox.warning(self, "Hata", "Dosya fiziksel olarak bulunamadı!")

    # ==========================================
    # ÇİFT KANAL ÖNİZLEME VE ZAMANLAYICI FONKSİYONLARI
    # ==========================================
    def update_preview_1(self):
        hz = self.slider_hz_1.value(); pulse_us = self.slider_pulse_1.value(); amp = self.slider_amp_1.value()
        T_ms = 1000.0 / hz if hz > 0 else 20.0; PW_ms = pulse_us / 1000.0
        t = np.linspace(0, 50, 2000); t_mod = t % T_ms
        wave = np.zeros_like(t); wave[t_mod < PW_ms] = amp; wave[(t_mod >= PW_ms) & (t_mod < 2 * PW_ms)] = -amp

        self.curve_stim_1.setData(t, wave)
        padding = 10 if amp < 90 else 0
        self.plot_stim_1.setYRange(-(amp + padding), (amp + padding)); self.plot_stim_1.setXRange(0, 50)
        
        # --- YATAY ÇİZİM İÇİN GÜNCELLENEN KISIM ---
        self.curve_stim_1_mixed.setData(t, wave)
        self.plot_stim_1_mixed.setYRange(-(amp + padding), (amp + padding)); self.plot_stim_1_mixed.setXRange(0, 50)
        
        # Cihaz çalışırken değer değişirse güncellemeyi gönder (Backend TX)
        if self.is_stimulating_1 and self.worker:
            self.worker.send_command(f"STIM_UPDATE:1:{hz}:{pulse_us}:{amp}")

    def update_preview_2(self):
        hz = self.slider_hz_2.value(); pulse_us = self.slider_pulse_2.value(); amp = self.slider_amp_2.value()
        T_ms = 1000.0 / hz if hz > 0 else 20.0; PW_ms = pulse_us / 1000.0
        t = np.linspace(0, 50, 2000); t_mod = t % T_ms
        wave = np.zeros_like(t); wave[t_mod < PW_ms] = amp; wave[(t_mod >= PW_ms) & (t_mod < 2 * PW_ms)] = -amp

        self.curve_stim_2.setData(t, wave)
        padding = 10 if amp < 90 else 0
        self.plot_stim_2.setYRange(-(amp + padding), (amp + padding)); self.plot_stim_2.setXRange(0, 50)
        
        # --- YATAY ÇİZİM İÇİN GÜNCELLENEN KISIM ---
        self.curve_stim_2_mixed.setData(t, wave)
        self.plot_stim_2_mixed.setYRange(-(amp + padding), (amp + padding)); self.plot_stim_2_mixed.setXRange(0, 50)
        
        # Cihaz çalışırken değer değişirse güncellemeyi gönder (Backend TX)
        if self.is_stimulating_2 and self.worker:
            self.worker.send_command(f"STIM_UPDATE:2:{hz}:{pulse_us}:{amp}")

    def toggle_stimulation_1(self):
        if not self.current_patient: QMessageBox.warning(self, "Uyarı", "Lütfen önce bir hasta seçin!"); return
        if not self.is_stimulating_1:
            self.is_stimulating_1 = True
            
            # Backend Başlatma Komutu (TX)
            hz = self.slider_hz_1.value(); pulse = self.slider_pulse_1.value(); amp = self.slider_amp_1.value()
            if self.worker: self.worker.send_command(f"STIM_START:1:{hz}:{pulse}:{amp}")
            
            self.stim_remaining_1 = self.slider_dur_1.value() * 60; self.stim_countdown_timer_1.start(1000); self.update_stim_countdown_1() 
            self.curve_stim_1.setPen(pg.mkPen('#E74C3C', width=3)); self.curve_stim_1_mixed.setPen(pg.mkPen('#E74C3C', width=3))
            self.btn_apply_stim_1.setStyleSheet("QPushButton { background-color: #E74C3C; color: #FFFFFF; border-radius: 6px; padding: 10px; font-weight: bold; }")
            if self.main_stack.currentIndex() not in [0, 2]: self.switch_graph_view(2)
        else:
            self.is_stimulating_1 = False; self.stim_countdown_timer_1.stop()
            
            # Backend Durdurma Komutu (TX)
            if self.worker: self.worker.send_command("STIM_STOP:1")
            
            self.curve_stim_1.setPen(pg.mkPen('#2ECC71', width=2)); self.curve_stim_1_mixed.setPen(pg.mkPen('#2ECC71', width=2))
            self.btn_apply_stim_1.setText("SİNYALİ BAŞLAT (K1)")
            self.btn_apply_stim_1.setStyleSheet("QPushButton { background-color: #2ECC71; color: #FFFFFF; border-radius: 6px; padding: 10px; font-weight: bold; }")

    def update_stim_countdown_1(self):
        if self.stim_remaining_1 <= 0: self.toggle_stimulation_1(); return
        mins, secs = divmod(self.stim_remaining_1, 60); self.btn_apply_stim_1.setText(f"DURDUR K1 ({mins:02d}:{secs:02d})"); self.stim_remaining_1 -= 1

    def toggle_stimulation_2(self):
        if not self.current_patient: QMessageBox.warning(self, "Uyarı", "Lütfen önce bir hasta seçin!"); return
        if not self.is_stimulating_2:
            self.is_stimulating_2 = True
            
            # Backend Başlatma Komutu (TX)
            hz = self.slider_hz_2.value(); pulse = self.slider_pulse_2.value(); amp = self.slider_amp_2.value()
            if self.worker: self.worker.send_command(f"STIM_START:2:{hz}:{pulse}:{amp}")
            
            self.stim_remaining_2 = self.slider_dur_2.value() * 60; self.stim_countdown_timer_2.start(1000); self.update_stim_countdown_2()
            self.curve_stim_2.setPen(pg.mkPen('#E74C3C', width=3)); self.curve_stim_2_mixed.setPen(pg.mkPen('#E74C3C', width=3))
            self.btn_apply_stim_2.setStyleSheet("QPushButton { background-color: #E74C3C; color: #FFFFFF; border-radius: 6px; padding: 10px; font-weight: bold; }")
            if self.main_stack.currentIndex() not in [0, 2]: self.switch_graph_view(2)
        else:
            self.is_stimulating_2 = False; self.stim_countdown_timer_2.stop()
            
            # Backend Durdurma Komutu (TX)
            if self.worker: self.worker.send_command("STIM_STOP:2")
            
            self.curve_stim_2.setPen(pg.mkPen('#3498DB', width=2)); self.curve_stim_2_mixed.setPen(pg.mkPen('#3498DB', width=2))
            self.btn_apply_stim_2.setText("SİNYALİ BAŞLAT (K2)")
            self.btn_apply_stim_2.setStyleSheet("QPushButton { background-color: #3498DB; color: #FFFFFF; border-radius: 6px; padding: 10px; font-weight: bold; }")

    def update_stim_countdown_2(self):
        if self.stim_remaining_2 <= 0: self.toggle_stimulation_2(); return
        mins, secs = divmod(self.stim_remaining_2, 60); self.btn_apply_stim_2.setText(f"DURDUR K2 ({mins:02d}:{secs:02d})"); self.stim_remaining_2 -= 1

    def show_patient_context_menu(self, pos):
        item = self.list_patients.itemAt(pos)
        if item is None: return
        menu = QMenu(self)
        update_action = QAction("Bilgileri Güncelle", self); update_action.triggered.connect(lambda: self.open_update_dialog(item.text()))
        delete_action = QAction("Hastayı Sil", self); delete_action.triggered.connect(lambda: self.delete_patient_action(item.text()))
        menu.addAction(update_action); menu.addAction(delete_action); menu.exec(self.list_patients.viewport().mapToGlobal(pos))

    def open_update_dialog(self, patient_name):
        details = self.db.get_patient_details(patient_name)
        if not details: return
        dialog = UpdatePatientDialog(patient_name, details, self)
        history_file = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", patient_name, "oyku.txt")
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f: dialog.txt_history.setText(f.read())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_updated_data()
            try:
                if hasattr(self.db, 'update_patient_details'): 
                    self.db.update_patient_details(patient_name, new_data['age'], new_data['dominant_side'], new_data['doctor'], new_data['phone'], new_data['history'])
            except Exception as e: 
                print(f"Güncelleme Hatası: {e}")
            self.refresh_patient_list(); self.refresh_db_tab_list()

    def refresh_patient_list(self):
        self.list_patients.clear()
        for patient in self.db.get_all_patients(): self.list_patients.addItem(patient)

    def search_patients(self):
        txt = self.txt_search_patient.text().lower(); self.list_patients.clear()
        for p in self.db.get_all_patients():
            if txt in p.lower(): self.list_patients.addItem(p)

    def select_patient(self, item):
        self.current_patient = item.text(); self.lbl_current_patient.setText(f"Hasta: {self.current_patient}")
        details = self.db.get_patient_details(self.current_patient)
        if details: 
            self.text_patient_details.setText(f"Protokol: {details.get('protocol_no','-')} | Yaş: {details.get('age','-')}")
            history = details.get('clinical_history', '')
            if history:
                self.txt_patient_history.setText(history)
            else:
                self.txt_patient_history.setText("Kayıtlı bir öykü bulunmuyor.")
        self.update_patient_records()

    def add_new_patient(self):
        name = self.txt_new_patient_name.text().strip(); protocol = self.txt_protocol.text().strip()
        if not name or not protocol: QMessageBox.warning(self, "Uyarı", "Gerekli alanları doldurun!"); return
        if self.db.add_patient_with_details(protocol, name, self.spin_age.value(), self.combo_gender.currentText(), self.combo_dominant_side.currentText(), self.spin_onset_year.value(), self.combo_diagnosis.currentText(), self.txt_doctor_name.text().strip(), self.txt_phone.text().strip(), self.txt_new_history.toPlainText()):
            p_folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", name)
            os.makedirs(os.path.join(p_folder, "VeriSeti_Tremor"), exist_ok=True); os.makedirs(os.path.join(p_folder, "VeriSeti_Bradikinezi"), exist_ok=True)
            self.db.log_event("INFO", f"Yeni hasta kaydı oluşturuldu: {name}", self.current_doctor['name'])
            self.clear_patient_form(); self.refresh_patient_list(); self.refresh_db_tab_list()
        else: QMessageBox.warning(self, "Hata", "Kayıt mevcut!")

    def delete_patient_action(self, patient_name=None):
        if not patient_name: patient_name = self.current_patient
        if not patient_name: return
        if QMessageBox.question(self, 'Onay', f"{patient_name} kaydını tamamen silmek istediğinize emin misiniz?") == QMessageBox.StandardButton.Yes:
            try:
                self.db.delete_patient(patient_name, self.current_doctor['name'])
                shutil.rmtree(os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", patient_name), ignore_errors=True)
                if self.current_patient == patient_name: self.current_patient = None
                self.refresh_patient_list(); self.refresh_db_tab_list()
            except: pass

    def clear_patient_form(self):
        self.txt_protocol.clear(); self.txt_new_patient_name.clear(); self.txt_new_history.clear(); self.txt_doctor_name.clear(); self.txt_phone.clear()

    def update_patient_records(self):
        if not self.current_patient: return
        p_folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", self.current_patient)
        self.list_tremor.clear(); self.list_bradi.clear()
        if os.path.exists(os.path.join(p_folder, "VeriSeti_Tremor")): self.list_tremor.addItems([f for f in os.listdir(os.path.join(p_folder, "VeriSeti_Tremor")) if f.endswith(('.pdf', '.csv'))])
        if os.path.exists(os.path.join(p_folder, "VeriSeti_Bradikinezi")): self.list_bradi.addItems([f for f in os.listdir(os.path.join(p_folder, "VeriSeti_Bradikinezi")) if f.endswith(('.pdf', '.csv'))])

    # ==========================================
    # KAYIT VE ANALIZ (HATA AYIKLAYICILI POP-UP SİSTEMİ)
    # ==========================================
    def toggle_recording(self):
        if not self.current_patient: 
            QMessageBox.warning(self, "Uyarı", "Lütfen önce bir hasta seçin!")
            return
        
        if not self.is_recording:
            self.is_recording = True
            self.recording_data = []
            self.btn_record.setText("KAYDI BİTİR VE ANALİZ ET")
            
            self.current_mode = "Tremor" if "Tremor" in self.combo_mode.currentText() else "Bradikinezi"
            folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", self.current_patient, f"VeriSeti_{self.current_mode}")
            os.makedirs(folder, exist_ok=True)
            self.current_filename = os.path.join(folder, f"{self.current_patient}_{self.current_mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        else:
            self.is_recording = False
            self.btn_record.setText("KAYDI BAŞLAT")
            
            # Veri Kaydedildiyse Analize Gönder
            if self.save_data_to_csv():
                self.run_analysis()
                self.update_patient_records()

    def save_data_to_csv(self):
        if not self.recording_data: 
            QMessageBox.critical(self, "Veri Yok", "Kayıt süresince cihazdan hiç veri alınamadı!\n\nLütfen donanım bağlantısını ve STM32 veri paket formatını kontrol edin.")
            return False
            
        with open(self.current_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            headers = []
            for i in range(12): headers.extend([f"IMU{i+1}_AccX", f"IMU{i+1}_AccY", f"IMU{i+1}_AccZ", f"IMU{i+1}_GyroX", f"IMU{i+1}_GyroY", f"IMU{i+1}_GyroZ"])
            writer.writerow(headers)
            writer.writerows(self.recording_data)
        try: self.db.add_test(self.current_patient, self.current_mode, self.current_filename, 0.0, 0.0, "", self.current_doctor['name'])
        except: pass
        return True

    def run_analysis(self):
        if not getattr(self, 'current_filename', '') or not os.path.exists(self.current_filename): return
        
        # Stimülasyon parametrelerini topla
        stim_data = {
            "ch1": {"hz": self.slider_hz_1.value(), "pw": self.slider_pulse_1.value(), "amp": self.slider_amp_1.value()},
            "ch2": {"hz": self.slider_hz_2.value(), "pw": self.slider_pulse_2.value(), "amp": self.slider_amp_2.value()}
        }

        try:
            QApplication.processEvents() 
            if self.current_mode == "Tremor":
                import analyze_tremor
                importlib.reload(analyze_tremor)
                # Parametreleri gönderiyoruz
                analyze_tremor.run_analysis(self.current_filename, stim_data)
                pdf_path = self.current_filename.replace(".csv", "_TREMOR_KLINIK_RAPOR.pdf")
            else:
                import analyze_bradykinesia
                importlib.reload(analyze_bradykinesia)
                # Parametreleri gönderiyoruz
                analyze_bradykinesia.run_analysis(self.current_filename, stim_data)
                pdf_path = self.current_filename.replace(".csv", "_FINAL_RAPOR.pdf")
            # ... geri kalan hata kontrolleri aynı kalabilir ...
                
            QApplication.processEvents()
            
            # PDF OLUŞTU MU KONTROLÜ (Sessiz Hataları Yakalar)
            if os.path.exists(pdf_path):
                QMessageBox.information(self, "Başarılı", "Kayıt ve analiz tamamlandı.\nRapor başarıyla PDF olarak oluşturuldu.")
            else:
                QMessageBox.warning(self, "PDF Oluşturulamadı", "CSV verisi başarıyla kaydedildi ancak analiz dosyası PDF'i oluşturmadı!\n\nMuhtemel Sebepler:\n1) Kayıt 2 saniyeden kısa sürmüş olabilir.\n2) Analiz dosyalarında kütüphane eksikliği veya çökme olabilir.\n\nLütfen terminal (konsol) ekranındaki kırmızı hatalara bakın.")
                
        except Exception as e: 
            QMessageBox.critical(self, "Analiz Çöktü", f"Analiz dosyası çalıştırılamadı.\n\nHata: {e}")

    def update_plot(self, data):
        if len(data) >= 73:
            battery_pct = int(data[72]); self.prog_battery.setValue(battery_pct)
            if self.is_recording: self.recording_data.append(data[:72])

            for i in range(12):
                base_idx = i * 6
                self.multi_data_buffer[i]['ax'].append(data[base_idx+0] / 16384.0)
                self.multi_data_buffer[i]['ay'].append(data[base_idx+1] / 16384.0)
                self.multi_data_buffer[i]['az'].append(data[base_idx+2] / 16384.0)
                self.multi_data_buffer[i]['gx'].append(data[base_idx+3] / 131.0)
                self.multi_data_buffer[i]['gy'].append(data[base_idx+4] / 131.0)
                self.multi_data_buffer[i]['gz'].append(data[base_idx+5] / 131.0)

                for key in ['ax', 'ay', 'az', 'gx', 'gy', 'gz']:
                    if len(self.multi_data_buffer[i][key]) > self.buffer_size: self.multi_data_buffer[i][key].pop(0)
                        
            is_grid_visible = (self.main_stack.currentIndex() == 0) or (self.main_stack.currentIndex() == 1 and self.sensor_stack.currentIndex() == 0)
            if is_grid_visible:
                self.plot_counter += 1
                if self.plot_counter % 20 == 0: 
                    for i in range(12):
                        if len(self.multi_data_buffer[i]['ax']) > 0:
                            current_x = self.multi_data_buffer[i]['ax'][-1]
                            txt = f"IMU {i+1}\n\nAktif: {current_x:.2f} G"
                            self.imu_buttons[i].setText(txt); self.imu_buttons_mixed[i].setText(txt)

            is_detail_visible = (self.main_stack.currentIndex() == 1 and self.sensor_stack.currentIndex() == 1)
            if is_detail_visible:
                self.plot_counter += 1
                if self.plot_counter % 5 == 0:
                    idx = self.active_detailed_imu
                    
                    ax_data = np.array(self.multi_data_buffer[idx]['ax'])
                    ay_data = np.array(self.multi_data_buffer[idx]['ay'])
                    az_data = np.array(self.multi_data_buffer[idx]['az'])
                    
                    # 1. Toplam Güç Hesapla ve Çiz
                    if len(ax_data) > 0:
                        mag_data = np.sqrt(ax_data**2 + ay_data**2 + az_data**2)
                        self.curve_mag.setData(mag_data)
                        
                        # 2. Karma Grafiği Güncelle
                        self.curve_comb_x.setData(ax_data)
                        self.curve_comb_y.setData(ay_data)
                        self.curve_comb_z.setData(az_data)
                        
                        # 3. Bireysel Grafikleri Güncelle
                        self.curve_ax.setData(ax_data)
                        self.curve_ay.setData(ay_data)
                        self.curve_az.setData(az_data)
                        
    def toggle_connection(self):
        if self.worker is None:
            port = self.combo_ports.currentText()
            if not port: return
            self.worker = SerialWorker(port); self.worker.data_received.connect(self.update_plot); self.worker.start()
            self.btn_connect.setText("BAĞLANTIYI KES"); self.btn_record.setEnabled(True)
        else:
            self.worker.stop(); self.worker = None
            self.btn_connect.setText("CİHAZA BAĞLAN"); self.btn_record.setEnabled(False)
            for i in range(12): 
                txt = f"IMU {i+1}\n\nDurum: Bekliyor..."; self.imu_buttons[i].setText(txt); self.imu_buttons_mixed[i].setText(txt)

    def open_pdf_tremor(self, item):
        if not self.current_patient: return
        filepath = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", self.current_patient, "VeriSeti_Tremor", item.text())
        if os.path.exists(filepath):
            try: os.startfile(filepath)
            except: pass

    def open_pdf_bradi(self, item):
        if not self.current_patient: return
        filepath = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", self.current_patient, "VeriSeti_Bradikinezi", item.text())
        if os.path.exists(filepath):
            try: os.startfile(filepath)
            except: pass

    def create_button(self, text, bg_color, hover_color=None, text_color="#FFFFFF"):
        if hover_color is None: hover_color = bg_color 
        btn = QPushButton(text); btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"QPushButton {{ background-color: {bg_color}; color: {text_color}; border-radius: 6px; padding: 10px; font-weight: bold; }} QPushButton:hover {{ background-color: {hover_color}; }}")
        return btn

    def customize_plot(self, plot_widget):
        plot_widget.getAxis('left').setPen('#7F8C8D'); plot_widget.getAxis('bottom').setPen('#7F8C8D')
        plot_widget.addLegend(offset=(10, 10))

    def show_user_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: white; border: 1px solid #BDC3C7; }
            QMenu::item { padding: 8px 25px; color: #2C3E50; }
            QMenu::item:selected { background-color: #3498DB; color: white; }
        """)
        
        action_change_pw = QAction("🔑 Şifre Değiştir", self)
        action_change_pw.triggered.connect(self.show_change_password)
        
        action_logout = QAction("🚪 Güvenli Çıkış", self)
        action_logout.triggered.connect(self.logout)
        
        menu.addAction(action_change_pw)
        menu.addSeparator()
        menu.addAction(action_logout)
        
        # Butonun hemen altına açılması için konum hesapla
        button_pos = self.btn_user_menu.mapToGlobal(self.btn_user_menu.rect().bottomLeft())
        menu.exec(button_pos)

    def show_change_password(self):
        dialog = ChangePasswordDialog(self.db, self.current_doctor['name'], self)
        dialog.exec()

    def logout(self):
        if QMessageBox.question(self, "Çıkış", "Oturumu kapatmak istediğinize emin misiniz?", 
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.db.log_event("INFO", "Oturum kapatıldı.", self.current_doctor['name'])
            self.close()
            QApplication.exit(1000)

if __name__ == "__main__":
    while True:
        app = QApplication(sys.argv)
        
        db = TestDatabase()
        login = LoginDialog(db)
        
        if login.exec() == QDialog.DialogCode.Accepted:
            if login.doctor_info.get('is_admin'):
                admin = AdminPanelDialog(db)
                admin.exec()
                # Admin panelinden çıkınca tekrar login ekranına dön
                continue
            else:
                window = ParkinsonGUI(login.doctor_info)
                window.show()
                exit_code = app.exec()
                
                if exit_code == 1000: # Logout kodu
                    continue # Döngü sayesinde tekrar login açılır
                else:
                    sys.exit(exit_code)
        else:
            sys.exit(0)