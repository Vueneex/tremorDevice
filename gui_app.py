# DOSYA ADI: gui_app_new.py

import sys
import os
import time
import csv
import serial
import serial.tools.list_ports
import numpy as np
from datetime import datetime, timedelta
import re
import importlib
import json
from database import TestDatabase


# Arayüz Kütüphaneleri
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QComboBox, 
                             QMessageBox, QFrame, QCheckBox, QLineEdit, QListWidget,
                             QFileDialog, QTabWidget, QSpinBox, QDateEdit, QTimeEdit,
                             QTableWidget, QTableWidgetItem, QDateTimeEdit, QListWidgetItem,
                             QScrollArea, QFormLayout, QDoubleSpinBox) 
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt, QSettings
from PyQt6.QtGui import QFont, QColor

# Grafik Kütüphanesi
import pyqtgraph as pg

# Analiz Modülleri
ANALYSIS_AVAILABLE = None
analyze_tremor = None
analyze_bradykinesia = None

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
            self.serial_conn = serial.Serial(self.port_name, self.baud_rate, timeout=1)
            while self.is_running:
                if self.serial_conn.in_waiting:
                    try:
                        line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                        parts = line.split(',')
                        if len(parts) == 6:
                            raw_data = [float(x) for x in parts]
                            self.data_received.emit([raw_data[0], raw_data[1], raw_data[2], 
                                                   raw_data[3], raw_data[4], raw_data[5]])
                    except ValueError:
                        pass
        except Exception as e:
            print(f"Bağlantı Hatası: {e}")
        finally:
            if self.serial_conn:
                self.serial_conn.close()

    def stop(self):
        self.is_running = False
        self.wait()

# ----------------------------------------
# 2. ANA PENCERE (GUI)
# ----------------------------------------
class ParkinsonGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("NeuroMotion Analiz - Hasta Yönetimi v3.3")
        self.resize(1400, 900)
        
        # --- STİL DOSYASI (QSS) ---
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e;
            }
            QLabel {
                color: #cdd6f4;
                font-size: 14px;
                font-family: 'Segoe UI', sans-serif;
            }
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
                background-color: #313244;
                color: white;
                border: 1px solid #45475a;
                border-radius: 5px;
                padding: 5px;
                font-size: 13px;
            }
            QComboBox::drop-down { border: 0px; }
            
            QFrame#ControlPanel {
                background-color: #181825;
                border-radius: 15px;
                border: 1px solid #313244;
            }
            QFrame#Header {
                background-color: #11111b;
                border-bottom: 2px solid #cba6f7;
            }
            QLabel#HeaderTitle {
                font-size: 22px;
                font-weight: bold;
                color: #cba6f7;
            }
            QLabel#StatusLabel {
                font-weight: bold;
                color: #f9e2af;
            }
            QCheckBox {
                color: #cdd6f4;
                spacing: 10px;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #6c7086;
                background-color: #313244;
            }
            QCheckBox::indicator:checked {
                background-color: #a6e3a1;
                border: 1px solid #a6e3a1;
            }
        """)

        # Değişkenler
        self.worker = None
        self.recording_data = [] 
        self.is_recording = False
        self.current_filename = ""
        self.current_patient = None  # Seçilen hasta
        
        # WORKSPACE ROOT: Script'in bulunduğu dizin (SABİT!)
        # C++'taki const char* gibi - DEĞİŞMEZ!
        self.workspace_root = os.path.dirname(os.path.abspath(__file__))
        self.save_root = self.workspace_root  # Artık her zaman aynı yer!
        
        # Veritabanı: Workspace root'ta SABİT konumda
        # Her seferinde AYNI dosyayı kullanacak
        db_path = os.path.join(self.workspace_root, "test_history.db")
        self.db = TestDatabase(db_path)
        self.data_buffer = {
            'ax': [], 'ay': [], 'az': [],
            'gx': [], 'gy': [], 'gz': []
        }
        self.buffer_size = 300 

        self.init_ui()
        self.refresh_patient_list()
    
    def init_ui(self):
        """Ana UI'yi kuruluştur"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)

        # HEADER
        header_frame = QFrame()
        header_frame.setObjectName("Header")
        header_layout = QHBoxLayout(header_frame)
        
        header_title = QLabel("🩺 NeuroMotion - Hasta Yönetimi Sistemi")
        header_title.setObjectName("HeaderTitle")
        header_layout.addWidget(header_title)

        self.lbl_status = QLabel("HAZIR")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignRight)
        header_layout.addWidget(self.lbl_status)
        main_layout.addWidget(header_frame)

        # CONTENT
        content_layout = QHBoxLayout()

        # SOL PANEL
        left_panel = self._create_left_panel()
        content_layout.addWidget(left_panel)

        # SAĞ PANEL (TAB WIDGET)
        main_tabs = QTabWidget()
        main_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #45475a; }
            QTabBar::tab { 
                background-color: #313244; 
                color: #cdd6f4; 
                padding: 8px 20px;
                border: 1px solid #45475a;
            }
            QTabBar::tab:selected { 
                background-color: #45475a;
                border-bottom: 2px solid #89b4fa;
            }
        """)
        
        # Tab 1: Kayıt ve Görüntüleme
        main_tabs.addTab(self._create_recording_tab(), "🎛️ Kayıt & İzleme")
        
        # Tab 2: Hasta Yönetimi
        main_tabs.addTab(self._create_patient_management_tab(), "👥 Hasta Yönetimi")
        
        # Tab 3: Yeni Hasta Ekleme
        main_tabs.addTab(self._create_add_patient_tab(), "➕ Yeni Hasta Ekle")
        
        content_layout.addWidget(main_tabs, 1)
        
        main_layout.addLayout(content_layout)

    def _create_left_panel(self):
        """Sol paneli oluştur"""
        control_frame = QFrame()
        control_frame.setObjectName("ControlPanel")
        control_frame.setMaximumWidth(320)
        
        left_layout = QVBoxLayout(control_frame)

        # Hasta Seçimi
        lbl_patient = QLabel("👤 HASTA SEÇİMİ")
        lbl_patient.setStyleSheet("color: #cba6f7; font-weight: bold; letter-spacing: 1px; margin-bottom: 10px;")
        left_layout.addWidget(lbl_patient)

        search_row = QHBoxLayout()
        self.txt_search_patient = QLineEdit()
        self.txt_search_patient.setPlaceholderText("Hasta adı ara...")
        self.txt_search_patient.textChanged.connect(self.search_patients)
        search_row.addWidget(self.txt_search_patient)
        
        btn_refresh_patients = self.create_button("🔄", "#45475a", "#585b70")
        btn_refresh_patients.setMaximumWidth(50)
        btn_refresh_patients.clicked.connect(self.refresh_patient_list)
        search_row.addWidget(btn_refresh_patients)
        left_layout.addLayout(search_row)

        # Hasta Listesi
        self.list_patients = QListWidget()
        self.list_patients.setFixedHeight(150)
        self.list_patients.setStyleSheet("""
            QListWidget {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 5px;
                color: #cdd6f4;
                font-size: 11px;
            }
            QListWidget::item:hover { background-color: #45475a; }
            QListWidget::item:selected { background-color: #89b4fa; }
        """)
        self.list_patients.itemClicked.connect(self.select_patient)
        left_layout.addWidget(self.list_patients)

        # Seçilen Hasta Bilgileri
        lbl_selected = QLabel("Seçilen Hasta:")
        lbl_selected.setStyleSheet("font-size: 12px; color: #a6adc8; margin-top: 15px;")
        left_layout.addWidget(lbl_selected)

        self.lbl_current_patient = QLabel("Hiçbiri seçilmedi")
        self.lbl_current_patient.setStyleSheet("color: #89b4fa; font-weight: bold; font-size: 13px;")
        left_layout.addWidget(self.lbl_current_patient)

        # Hasta Detayları
        self.text_patient_details = QLineEdit()
        self.text_patient_details.setReadOnly(True)
        self.text_patient_details.setPlaceholderText("Hasta bilgileri...")
        self.text_patient_details.setMinimumHeight(80)
        left_layout.addWidget(self.text_patient_details)

        # --- AYRAÇ ---
        left_layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #45475a; min-height: 1px;")
        left_layout.addWidget(line)

        # Cihaz Bağlantısı
        lbl_device = QLabel("📱 CİHAZ BAĞLANTISI")
        lbl_device.setStyleSheet("color: #a6e3a1; font-weight: bold; letter-spacing: 1px; margin-top: 15px;")
        left_layout.addWidget(lbl_device)

        # Port
        lbl_port = QLabel("COM Port:")
        lbl_port.setStyleSheet("font-size: 12px; color: #a6adc8;")
        left_layout.addWidget(lbl_port)

        port_row = QHBoxLayout()
        self.combo_ports = QComboBox()
        port_row.addWidget(self.combo_ports)
        
        btn_refresh = self.create_button("🔄", "#45475a", "#585b70")
        btn_refresh.setMaximumWidth(50)
        btn_refresh.clicked.connect(self.refresh_ports)
        port_row.addWidget(btn_refresh)
        left_layout.addLayout(port_row)

        # Bağlan Butonu
        self.btn_connect = self.create_button("CİHAZA BAĞLAN", "#a6e3a1", "#94e2d5")
        self.btn_connect.clicked.connect(self.toggle_connection)
        left_layout.addWidget(self.btn_connect)

        # Analiz Modu
        lbl_mode = QLabel("Analiz Modu:")
        lbl_mode.setStyleSheet("font-size: 12px; color: #a6adc8;")
        left_layout.addWidget(lbl_mode)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Tremor (Titreme)", "Bradikinezi (Yavaşlık)"])
        left_layout.addWidget(self.combo_mode)

        # Kayıt Klasörü
        lbl_save_root = QLabel("Kayıt Klasörü:")
        lbl_save_root.setStyleSheet("font-size: 12px; color: #a6adc8;")
        left_layout.addWidget(lbl_save_root)

        save_root_row = QHBoxLayout()
        self.txt_save_root = QLineEdit()
        self.txt_save_root.setReadOnly(True)
        self.txt_save_root.setText(self.get_save_root())
        save_root_row.addWidget(self.txt_save_root)

        btn_browse_root = self.create_button("Seç", "#45475a", "#585b70")
        btn_browse_root.setMaximumWidth(50)
        btn_browse_root.clicked.connect(self.browse_save_root)
        save_root_row.addWidget(btn_browse_root)
        left_layout.addLayout(save_root_row)

        # Kayıt Butonu
        self.btn_record = self.create_button("KAYDI BAŞLAT", "#f38ba8", "#eba0ac", text_color="#1e1e2e")
        self.btn_record.setEnabled(False)
        self.btn_record.setMinimumHeight(50)
        self.btn_record.clicked.connect(self.toggle_recording)
        left_layout.addWidget(self.btn_record)

        # PDF Checkbox
        self.chk_create_pdf = QCheckBox("PDF Oluştur")
        self.chk_create_pdf.setChecked(True)
        left_layout.addWidget(self.chk_create_pdf)

        left_layout.addStretch()
        
        lbl_ver = QLabel("v3.3.0 Hasta Yönetimi")
        lbl_ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ver.setStyleSheet("color: #45475a; font-size: 10px;")
        left_layout.addWidget(lbl_ver)

        return control_frame

    def _create_recording_tab(self):
        """Kayıt ve İzleme Tab'ı"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        pg.setConfigOption('background', '#181825')
        pg.setConfigOption('foreground', '#cdd6f4')
        
        # İvme Grafiği
        self.plot_acc = pg.PlotWidget(title="İvme (G-Force)")
        self.plot_acc.showGrid(x=True, y=True, alpha=0.3)
        self.customize_plot(self.plot_acc)
        self.curve_ax = self.plot_acc.plot(pen=pg.mkPen('#f38ba8', width=2), name="X")
        self.curve_ay = self.plot_acc.plot(pen=pg.mkPen('#a6e3a1', width=2), name="Y")
        self.curve_az = self.plot_acc.plot(pen=pg.mkPen('#89b4fa', width=2), name="Z")
        layout.addWidget(self.plot_acc)

        # Jiroskop Grafiği
        self.plot_gyro = pg.PlotWidget(title="Jiroskop (Açısal Hız)")
        self.plot_gyro.showGrid(x=True, y=True, alpha=0.3)
        self.customize_plot(self.plot_gyro)
        self.curve_gx = self.plot_gyro.plot(pen=pg.mkPen('#fab387', width=2), name="X")
        self.curve_gy = self.plot_gyro.plot(pen=pg.mkPen('#f9e2af', width=2), name="Y")
        self.curve_gz = self.plot_gyro.plot(pen=pg.mkPen('#cba6f7', width=2), name="Z")
        layout.addWidget(self.plot_gyro)

        return tab

    def _create_patient_management_tab(self):
        """Hasta Yönetimi Tab'ı"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        lbl_title = QLabel("Eski Kayıtları Görüntüle")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa; margin-bottom: 10px;")
        layout.addWidget(lbl_title)

        # Tremor Raporları
        lbl_tremor = QLabel("📊 Tremor Raporları")
        lbl_tremor.setStyleSheet("color: #a6e3a1; font-weight: bold; margin-top: 10px;")
        layout.addWidget(lbl_tremor)

        self.list_tremor = QListWidget()
        self.list_tremor.setFixedHeight(150)
        self.list_tremor.setStyleSheet("""
            QListWidget {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 5px;
            }
        """)
        self.list_tremor.itemDoubleClicked.connect(self.open_pdf_tremor)
        layout.addWidget(self.list_tremor)

        # Bradikinezi Raporları
        lbl_bradi = QLabel("🖱️ Bradikinezi Raporları")
        lbl_bradi.setStyleSheet("color: #fab387; font-weight: bold; margin-top: 10px;")
        layout.addWidget(lbl_bradi)

        self.list_bradi = QListWidget()
        self.list_bradi.setFixedHeight(150)
        self.list_bradi.setStyleSheet("""
            QListWidget {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 5px;
            }
        """)
        self.list_bradi.itemDoubleClicked.connect(self.open_pdf_bradi)
        layout.addWidget(self.list_bradi)

        layout.addStretch()
        return tab

    def _create_add_patient_tab(self):
        """Yeni Hasta Ekleme Tab'ı"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        form_layout = QFormLayout(scroll_widget)

        lbl_title = QLabel("Yeni Hasta Bilgileri")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #cba6f7; margin-bottom: 10px;")
        form_layout.addRow(lbl_title)

        lbl_title = QLabel("Yeni Hasta Bilgileri Ekle")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #cba6f7; margin-bottom: 15px;")
        layout.addWidget(lbl_title)

        # Form
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)

        # Form Alanları
        self.txt_new_patient_name = QLineEdit()
        self.txt_new_patient_name.setPlaceholderText("Hastanın tam adı")
        form_layout.addRow("Hasta Adı *:", self.txt_new_patient_name)

        self.spin_age = QSpinBox()
        self.spin_age.setRange(0, 150)
        form_layout.addRow("Yaş:", self.spin_age)

        self.combo_gender = QComboBox()
        self.combo_gender.addItems(["Erkek", "Kadın", "Diğer"])
        form_layout.addRow("Cinsiyet:", self.combo_gender)

        self.spin_height = QDoubleSpinBox()
        self.spin_height.setRange(0, 250)
        self.spin_height.setSuffix(" cm")
        form_layout.addRow("Boy:", self.spin_height)

        self.spin_weight = QDoubleSpinBox()
        self.spin_weight.setRange(0, 300)
        self.spin_weight.setSuffix(" kg")
        form_layout.addRow("Kilo:", self.spin_weight)

        self.combo_diagnosis = QComboBox()
        self.combo_diagnosis.addItems(["Parkinson", "Essential Tremor", "Diğer"])
        form_layout.addRow("Tanı:", self.combo_diagnosis)

        self.txt_doctor_name = QLineEdit()
        self.txt_doctor_name.setPlaceholderText("Doktor adı")
        form_layout.addRow("Doktor Adı:", self.txt_doctor_name)

        self.txt_phone = QLineEdit()
        self.txt_phone.setPlaceholderText("+90...")
        form_layout.addRow("Telefon:", self.txt_phone)

        layout.addWidget(form_widget)
        layout.addSpacing(15)

        # Butonlar
        btn_layout = QHBoxLayout()
        btn_save = self.create_button("✓ Hastayı Ekle", "#a6e3a1", "#94e2d5")
        btn_save.setMinimumHeight(45)
        btn_save.clicked.connect(self.add_new_patient)
        btn_layout.addWidget(btn_save)

        btn_cancel = self.create_button("🔄 Temizle", "#45475a", "#585b70")
        btn_cancel.setMinimumHeight(45)
        btn_cancel.clicked.connect(self.clear_patient_form)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)
        layout.addStretch()
        return tab

    def refresh_patient_list(self):
        """Hasta listesini yenile"""
        self.list_patients.clear()
        all_patients = self.db.get_all_patients()
        for patient in all_patients:
            self.list_patients.addItem(patient)

    def search_patients(self):
        """Hasta adıyla ara"""
        search_text = self.txt_search_patient.text().lower()
        all_patients = self.db.get_all_patients()
        
        self.list_patients.clear()
        for patient in all_patients:
            if search_text in patient.lower():
                self.list_patients.addItem(patient)

    def select_patient(self, item):
        """Hastayı seç"""
        self.current_patient = item.text()
        self.lbl_current_patient.setText(f"✓ {self.current_patient}")
        self.lbl_current_patient.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 13px;")

        # Hasta detaylarını göster
        details = self.db.get_patient_details(self.current_patient)
        if details:
            detail_text = f"""
Yaş: {details['age']} | Cinsiyet: {details['gender']}
Boy: {details['height']} cm | Kilo: {details['weight']} kg
Tanı: {details['diagnosis']}
Doktor: {details['doctor_name']}
Tel: {details['contact_phone']}
            """
            self.text_patient_details.setText(detail_text)
        
        # Seçilen hastanın kayıtlarını göster
        self.update_patient_records()

    def update_patient_records(self):
        """Seçilen hastanın eski kayıtlarını göster"""
        if not self.current_patient:
            return

        # Hasta klasörleri - TUTARLI YOL (her zaman aynı!)
        # WORKSPACE_ROOT/VeriSeti_Genel/Hastalar/[HASTA_ADI]/
        patient_folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", self.current_patient)
        tremor_folder = os.path.join(patient_folder, "VeriSeti_Tremor")
        bradi_folder = os.path.join(patient_folder, "VeriSeti_Bradikinezi")

        self.list_tremor.clear()
        self.list_bradi.clear()

        if os.path.exists(tremor_folder):
            files = [f for f in os.listdir(tremor_folder) if f.endswith(('.pdf', '.csv'))]
            files.sort(key=lambda x: os.path.getmtime(os.path.join(tremor_folder, x)), reverse=True)
            self.list_tremor.addItems(files)

        if os.path.exists(bradi_folder):
            files = [f for f in os.listdir(bradi_folder) if f.endswith(('.pdf', '.csv'))]
            files.sort(key=lambda x: os.path.getmtime(os.path.join(bradi_folder, x)), reverse=True)
            self.list_bradi.addItems(files)

    def add_new_patient(self):
        """Yeni hasta ekle"""
        name = self.txt_new_patient_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Uyarı", "Hasta adı gerekli!")
            return

        age = self.spin_age.value()
        gender = self.combo_gender.currentText()
        height = self.spin_height.value()
        weight = self.spin_weight.value()
        diagnosis = self.combo_diagnosis.currentText()
        doctor = self.txt_doctor_name.text().strip()
        phone = self.txt_phone.text().strip()

        # Veritabanına ekle
        if self.db.add_patient_with_details(name, age, gender, height, weight, diagnosis, doctor, phone):
            # Hasta klasörlerini oluştur - WORKSPACE_ROOT/VeriSeti_Genel/Hastalar/ altında
            # C++'ta string path = root + "/VeriSeti_Genal/Hastalar/" + name; gibi
            patient_folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", name)
            os.makedirs(os.path.join(patient_folder, "VeriSeti_Tremor"), exist_ok=True)
            os.makedirs(os.path.join(patient_folder, "VeriSeti_Bradikinezi"), exist_ok=True)

            QMessageBox.information(self, "Başarılı", f"Hasta '{name}' başarıyla eklendi!\nKlasör: {patient_folder}")
            self.clear_patient_form()
            self.refresh_patient_list()
        else:
            QMessageBox.warning(self, "Hata", f"Hasta '{name}' zaten var!")

    def clear_patient_form(self):
        """Hasta formu temizle"""
        self.txt_new_patient_name.clear()
        self.spin_age.setValue(0)
        self.combo_gender.setCurrentIndex(0)
        self.spin_height.setValue(0)
        self.spin_weight.setValue(0)
        self.combo_diagnosis.setCurrentIndex(0)
        self.txt_doctor_name.clear()
        self.txt_phone.clear()

    def toggle_recording(self):
        """Kayıt başlat/durdur"""
        if not self.current_patient:
            QMessageBox.warning(self, "Uyarı", "Lütfen hasta seçin!")
            return

        if not self.is_recording:
            # KAYIT BAŞLAT
            self.is_recording = True
            self.recording_data = []
            self.btn_record.setText("KAYDI BİTİR")
            self.lbl_status.setText(f"KAYIT: {self.current_patient}")

            # Hasta klasörüne kaydet - TUTARLI YOL!
            # WORKSPACE_ROOT/VeriSeti_Genel/Hastalar/[HASTA_ADI]/[MOD_KLASÖRÜ]/
            mode = "Tremor" if self.combo_mode.currentIndex() == 0 else "Bradikinezi"
            mode_folder = "VeriSeti_Tremor" if mode == "Tremor" else "VeriSeti_Bradikinezi"
            
            patient_folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", self.current_patient, mode_folder)
            os.makedirs(patient_folder, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.current_patient}_{mode_folder}_{timestamp}.csv"
            self.current_filename = os.path.join(patient_folder, filename)
        else:
            # KAYIT DURDUR
            self.is_recording = False
            self.btn_record.setText("KAYDI BAŞLAT")
            self.save_data_to_csv()
            self.run_analysis()
            self.update_patient_records()

    def save_data_to_csv(self):
        """Verileri CSV'ye kaydet"""
        if not self.recording_data:
            return

        with open(self.current_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ"])
            writer.writerows(self.recording_data)

        self.lbl_status.setText("DOSYA KAYDEDİLDİ")

        # Veritabanına ekle
        try:
            accel_data = np.array([[float(row[0]), float(row[1]), float(row[2])] for row in self.recording_data])
            tremor_score = np.sqrt(np.mean(accel_data**2))
            test_type = "Tremor" if self.combo_mode.currentIndex() == 0 else "Bradikinezi"
            self.db.add_test(self.current_patient, test_type, self.current_filename, tremor_score, 0.0, "")
        except:
            pass

    def update_plot(self, data):
        """Grafikleri güncelle"""
        self.data_buffer['ax'].append(data[0] / 16384.0)
        self.data_buffer['ay'].append(data[1] / 16384.0)
        self.data_buffer['az'].append(data[2] / 16384.0)
        
        self.data_buffer['gx'].append(data[3] / 131.0)
        self.data_buffer['gy'].append(data[4] / 131.0)
        self.data_buffer['gz'].append(data[5] / 131.0)

        if self.is_recording:
            self.recording_data.append([data[0], data[1], data[2], data[3], data[4], data[5]])

        for key in self.data_buffer:
            if len(self.data_buffer[key]) > self.buffer_size:
                self.data_buffer[key].pop(0)

        if len(self.data_buffer['ax']) > 0:
            self.curve_ax.setData(self.data_buffer['ax'])
            self.curve_ay.setData(self.data_buffer['ay'])
            self.curve_az.setData(self.data_buffer['az'])
            
            self.curve_gx.setData(self.data_buffer['gx'])
            self.curve_gy.setData(self.data_buffer['gy'])
            self.curve_gz.setData(self.data_buffer['gz'])

    def toggle_connection(self):
        """Cihaza bağlan/bağlantıyı kes"""
        if self.worker is None:
            port = self.combo_ports.currentText()
            if not port:
                return
            self.worker = SerialWorker(port)
            self.worker.data_received.connect(self.update_plot)
            self.worker.start()
            
            self.btn_connect.setText("BAĞLANTIYI KES")
            self.btn_record.setEnabled(True)
            self.lbl_status.setText(f"BAĞLANDI: {port}")
        else:
            self.worker.stop()
            self.worker = None
            self.btn_connect.setText("CİHAZA BAĞLAN")
            self.btn_record.setEnabled(False)
            self.lbl_status.setText("BAĞLANTI KESİLDİ")

    def refresh_ports(self):
        """COM portlarını yenile"""
        self.combo_ports.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.combo_ports.addItem(port.device)

    def run_analysis(self):
        """Analiz yap"""
        pass

    def open_pdf_tremor(self, item):
        """Tremor raporunu aç"""
        if not self.current_patient:
            return
        
        base_path = self.get_save_root()
        folder = os.path.join(base_path, "Hastalar", self.current_patient, "VeriSeti_Tremor")
        filepath = os.path.join(folder, item.text())
        
        if os.path.exists(filepath):
            try:
                os.startfile(filepath)
            except:
                pass

    def open_pdf_bradi(self, item):
        """Bradikinezi raporunu aç"""
        if not self.current_patient:
            return
        
        base_path = self.get_save_root()
        folder = os.path.join(base_path, "Hastalar", self.current_patient, "VeriSeti_Bradikinezi")
        filepath = os.path.join(folder, item.text())
        
        if os.path.exists(filepath):
            try:
                os.startfile(filepath)
            except:
                pass

    def browse_save_root(self):
        """Kayıt klasörü seç"""
        current_root = self.get_save_root()
        folder = QFileDialog.getExistingDirectory(self, "Kayıt Klasörü Seç", current_root)
        if folder:
            self.save_root = folder
            self.settings.setValue("save_root", folder)
            self.txt_save_root.setText(folder)

    def get_save_root(self):
        """Kayıt klasörünü getir - Artık her zaman workspace_root döner"""
        # C++'taki getter gibi - SABİT değer döndürür
        return self.workspace_root

    def create_button(self, text, bg_color, hover_color, text_color="white"):
        """Buton oluştur"""
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color};
                color: {text_color};
                border-radius: 8px;
                padding: 10px;
                font-weight: bold;
                font-size: 13px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {bg_color};
                padding-top: 12px;
            }}
            QPushButton:disabled {{
                background-color: #313244;
                color: #585b70;
            }}
        """)
        return btn

    def customize_plot(self, plot_widget):
        """Grafik özelleştir"""
        plot_widget.getAxis('left').setPen('#6c7086')
        plot_widget.getAxis('bottom').setPen('#6c7086')
        plot_widget.addLegend(offset=(10, 10))
        plot_widget.setStyleSheet("border: 1px solid #313244; border-radius: 10px;")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ParkinsonGUI()
    window.show()
    # Ensure the window is brought to the foreground on start.
    window.raise_()
    window.activateWindow()
    QTimer.singleShot(0, window.raise_)
    QTimer.singleShot(0, window.activateWindow)
    sys.exit(app.exec())
