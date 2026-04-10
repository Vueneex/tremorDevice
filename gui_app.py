# DOSYA ADI: gui_app_new.py

import sys
import os
import shutil
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
                             QScrollArea, QFormLayout, QDoubleSpinBox, QProgressBar,
                             QTextEdit, QGroupBox, QGridLayout, QDialog, QMenu) 
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt, QSettings
from PyQt6.QtGui import QFont, QColor, QAction

# Grafik Kütüphanesi
import pyqtgraph as pg

# DALGALARI PÜRÜZSÜZ (YUMUŞAK) ÇİZMEK İÇİN ANTIALIASING AÇILDI
pg.setConfigOptions(antialias=True) 

# MEDİKAL TEMA İÇİN GRAFİK RENKLERİ TERSİNE ÇEVRİLDİ
pg.setConfigOption('background', '#FFFFFF')
pg.setConfigOption('foreground', '#2C3E50')

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
                        if len(parts) >= 6: 
                            raw_data = [float(x) for x in parts]
                            battery_val = raw_data[6] if len(parts) >= 7 else 0.0 
                            
                            self.data_received.emit([raw_data[0], raw_data[1], raw_data[2], 
                                                   raw_data[3], raw_data[4], raw_data[5], battery_val])
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
# HASTA GÜNCELLEME PENCERESİ (DIALOG)
# ----------------------------------------
class UpdatePatientDialog(QDialog):
    def __init__(self, patient_name, details, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Klinik Kayıt Güncelle: {patient_name}")
        self.setMinimumWidth(400)
        
        # Medikal Tema
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; }
            QLabel { color: #2C3E50; font-weight: bold; font-size: 13px; }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #F8F9F9; color: #2C3E50; border: 1px solid #BDC3C7;
                border-radius: 5px; padding: 5px;
            }
            QPushButton {
                background-color: #3498DB; color: white; border-radius: 5px; padding: 8px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2980B9; }
        """)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # Alanlar (Mevcut verilerle dolduruluyor)
        self.spin_age = QSpinBox()
        self.spin_age.setRange(0, 150)
        self.spin_age.setValue(int(details.get('age', 0)) if details.get('age') not in ['-', None, ''] else 0)
        
        self.combo_side = QComboBox()
        self.combo_side.addItems(["Sağ", "Sol", "Çift Taraf"])
        self.combo_side.setCurrentText(str(details.get('dominant_side', 'Sağ')))

        self.txt_doctor = QLineEdit(str(details.get('doctor_name', '')))
        self.txt_phone = QLineEdit(str(details.get('contact_phone', '')))
        
        self.txt_history = QTextEdit()
        self.txt_history.setMaximumHeight(80)

        form_layout.addRow("Yaş:", self.spin_age)
        form_layout.addRow("Baskın Taraf:", self.combo_side)
        form_layout.addRow("Doktor:", self.txt_doctor)
        form_layout.addRow("Telefon:", self.txt_phone)
        form_layout.addRow("Klinik Öykü:", self.txt_history)

        layout.addLayout(form_layout)

        # Butonlar
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("✓ Kaydet")
        self.btn_save.setStyleSheet("background-color: #2ECC71;")
        self.btn_save.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("İptal")
        self.btn_cancel.setStyleSheet("background-color: #95A5A6;")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def get_updated_data(self):
        return {
            "age": self.spin_age.value(),
            "dominant_side": self.combo_side.currentText(),
            "doctor": self.txt_doctor.text().strip(),
            "phone": self.txt_phone.text().strip(),
            "history": self.txt_history.toPlainText().strip()
        }

# ----------------------------------------
# 2. ANA PENCERE (GUI)
# ----------------------------------------
class ParkinsonGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("NeuroMotion Analiz - Medikal Prototip v4.6")
        self.resize(1450, 950)
        
        # --- STİL DOSYASI (QSS) - KLİNİK BEYAZ, MAVİ, GRİ TEMA ---
        self.setStyleSheet("""
            QMainWindow { background-color: #F4F6F9; }
            QLabel { color: #2C3E50; font-size: 14px; font-family: 'Segoe UI', sans-serif; }
            
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit {
                background-color: #FFFFFF; color: #2C3E50;
                border: 1px solid #BDC3C7; border-radius: 5px; padding: 5px; font-size: 13px;
            }
            QComboBox::drop-down { border: 0px; }
            QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QTextEdit:focus {
                border: 1px solid #3498DB;
            }
            
            QFrame#ControlPanel { background-color: #FFFFFF; border-radius: 10px; border: 1px solid #E0E6ED; }
            QFrame#Header { background-color: #2980B9; border-bottom: 3px solid #1ABC9C; }
            QLabel#HeaderTitle { font-size: 22px; font-weight: bold; color: #FFFFFF; }
            QLabel#StatusLabel { font-weight: bold; color: #F1C40F; }
            
            QCheckBox { color: #2C3E50; spacing: 10px; font-size: 13px; }
            
            QTabWidget::pane { border: 1px solid #E0E6ED; background: #FFFFFF; border-radius: 5px; }
            QTabBar::tab { background-color: #ECF0F1; color: #7F8C8D; padding: 10px 20px; border: 1px solid #E0E6ED; font-weight: bold; border-top-left-radius: 4px; border-top-right-radius: 4px;}
            QTabBar::tab:selected { background-color: #FFFFFF; color: #2980B9; border-bottom: 3px solid #2980B9; }
            
            QListWidget { background-color: #FFFFFF; border: 1px solid #BDC3C7; border-radius: 5px; font-size: 13px; color: #2C3E50;}
            QListWidget::item { padding: 5px; }
            QListWidget::item:hover { background-color: #ECF0F1; }
            QListWidget::item:selected { background-color: #D6EAF8; color: #2980B9; font-weight: bold; border-left: 3px solid #2980B9;}
            
            QGroupBox { color: #2980B9; font-weight: bold; border: 1px solid #BDC3C7; border-radius: 8px; margin-top: 10px; padding-top: 15px; background-color: #F8F9F9;}
            
            QProgressBar { border: 1px solid #BDC3C7; border-radius: 5px; text-align: center; color: #2C3E50; font-weight: bold; background-color: #ECF0F1; height: 18px; margin-top: 5px;}
            QProgressBar::chunk { background-color: #2ECC71; border-radius: 4px; }
        """)

        # Değişkenler
        self.worker = None
        self.recording_data = [] 
        self.is_recording = False
        self.current_filename = ""
        self.current_mode = "" 
        self.current_patient = None
        
        self.workspace_root = os.path.dirname(os.path.abspath(__file__))
        self.save_root = self.workspace_root  
        
        db_path = os.path.join(self.workspace_root, "test_history.db")
        self.db = TestDatabase(db_path)
        self.data_buffer = { 'ax': [], 'ay': [], 'az': [], 'gx': [], 'gy': [], 'gz': [] }
        self.buffer_size = 300 

        self.init_ui()
        self.refresh_patient_list()
    
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # HEADER
        header_frame = QFrame()
        header_frame.setObjectName("Header")
        header_layout = QHBoxLayout(header_frame)
        header_title = QLabel("🩺 NeuroMotion - Klinik Hasta Yönetimi")
        header_title.setObjectName("HeaderTitle")
        header_layout.addWidget(header_title)
        self.lbl_status = QLabel("SİSTEM HAZIR")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignRight)
        header_layout.addWidget(self.lbl_status)
        main_layout.addWidget(header_frame)

        # CONTENT
        content_layout = QHBoxLayout()
        left_panel = self._create_left_panel()
        content_layout.addWidget(left_panel)

        main_tabs = QTabWidget()
        main_tabs.addTab(self._create_recording_tab(), "🎛️ Kayıt & Stimülasyon")
        main_tabs.addTab(self._create_patient_management_tab(), "👥 Rapor Yönetimi")
        main_tabs.addTab(self._create_add_patient_tab(), "➕ Yeni Hasta Kaydı")
        
        content_layout.addWidget(main_tabs, 1)
        main_layout.addLayout(content_layout)

    def _create_left_panel(self):
        control_frame = QFrame()
        control_frame.setObjectName("ControlPanel")
        control_frame.setMaximumWidth(320)
        left_layout = QVBoxLayout(control_frame)

        # Hasta Seçimi
        lbl_patient = QLabel("👤 HASTA SEÇİMİ")
        lbl_patient.setStyleSheet("color: #2980B9; font-weight: bold; letter-spacing: 1px; margin-bottom: 5px;")
        left_layout.addWidget(lbl_patient)

        search_row = QHBoxLayout()
        self.txt_search_patient = QLineEdit()
        self.txt_search_patient.setPlaceholderText("İsim veya Protokol No ara...")
        self.txt_search_patient.textChanged.connect(self.search_patients)
        search_row.addWidget(self.txt_search_patient)
        
        btn_refresh_patients = self.create_button("🔄", "#ECF0F1", "#D5D8DC", text_color="#2C3E50")
        btn_refresh_patients.setMaximumWidth(40)
        btn_refresh_patients.clicked.connect(self.refresh_patient_list)
        search_row.addWidget(btn_refresh_patients)
        left_layout.addLayout(search_row)

        self.list_patients = QListWidget()
        self.list_patients.setFixedHeight(120)
        # Sağ Tık Menüsü Ayarı
        self.list_patients.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_patients.customContextMenuRequested.connect(self.show_patient_context_menu)
        self.list_patients.itemClicked.connect(self.select_patient)
        left_layout.addWidget(self.list_patients)

        self.lbl_current_patient = QLabel("Hiçbiri seçilmedi")
        self.lbl_current_patient.setStyleSheet("color: #27AE60; font-weight: bold; font-size: 15px; margin-top: 5px;")
        left_layout.addWidget(self.lbl_current_patient)

        self.text_patient_details = QLineEdit()
        self.text_patient_details.setReadOnly(True)
        self.text_patient_details.setPlaceholderText("Klinik veriler...")
        self.text_patient_details.setStyleSheet("background-color: #F4F6F9; color: #34495E; font-size: 11px;")
        left_layout.addWidget(self.text_patient_details)

        # --- HASTA ÖYKÜSÜ PANELİ ---
        lbl_history = QLabel("Klinik Öykü:")
        lbl_history.setStyleSheet("font-size: 12px; color: #7F8C8D; margin-top: 5px; font-weight: bold;")
        left_layout.addWidget(lbl_history)

        self.txt_patient_history = QTextEdit()
        self.txt_patient_history.setReadOnly(True)
        self.txt_patient_history.setPlaceholderText("Hastanın klinik öyküsü burada görünecek...")
        self.txt_patient_history.setMaximumHeight(80)
        self.txt_patient_history.setStyleSheet("background-color: #F8F9F9; color: #2C3E50; font-size: 12px;")
        left_layout.addWidget(self.txt_patient_history)

        self.btn_delete_patient = self.create_button("🗑️ Hastayı Sil", "#E74C3C", "#C0392B")
        self.btn_delete_patient.setEnabled(False)
        self.btn_delete_patient.clicked.connect(self.delete_patient_action)
        left_layout.addWidget(self.btn_delete_patient)

        left_layout.addSpacing(5)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #E0E6ED;")
        left_layout.addWidget(line)

        # Cihaz Bağlantısı
        lbl_device = QLabel("📱 CİHAZ BAĞLANTISI")
        lbl_device.setStyleSheet("color: #2980B9; font-weight: bold; letter-spacing: 1px;")
        left_layout.addWidget(lbl_device)

        port_row = QHBoxLayout()
        self.combo_ports = QComboBox()
        port_row.addWidget(self.combo_ports)
        btn_refresh = self.create_button("🔄", "#ECF0F1", "#D5D8DC", text_color="#2C3E50")
        btn_refresh.setMaximumWidth(40)
        btn_refresh.clicked.connect(self.refresh_ports)
        port_row.addWidget(btn_refresh)
        left_layout.addLayout(port_row)

        self.btn_connect = self.create_button("CİHAZA BAĞLAN", "#3498DB", "#2980B9")
        self.btn_connect.clicked.connect(self.toggle_connection)
        left_layout.addWidget(self.btn_connect)

        # Batarya Durumu
        self.prog_battery = QProgressBar()
        self.prog_battery.setRange(0, 100)
        self.prog_battery.setValue(0)
        self.prog_battery.setFormat("Batarya Bekleniyor...")
        left_layout.addWidget(self.prog_battery)

        # --- ANALİZ MODU SEÇİMİ ---
        lbl_mode = QLabel("🎯 PROTOKOL SEÇİMİ")
        lbl_mode.setStyleSheet("color: #E67E22; font-weight: bold; letter-spacing: 1px; margin-top: 15px;")
        left_layout.addWidget(lbl_mode)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Tremor Analizi", "Bradikinezi Analizi"])
        self.combo_mode.setStyleSheet("border: 2px solid #E67E22; font-weight: bold; font-size: 13px; color: #D35400;")
        left_layout.addWidget(self.combo_mode)

        self.btn_record = self.create_button("KAYDI BAŞLAT", "#E74C3C", "#C0392B")
        self.btn_record.setEnabled(False)
        self.btn_record.setMinimumHeight(45)
        self.btn_record.clicked.connect(self.toggle_recording)
        left_layout.addWidget(self.btn_record)

        left_layout.addStretch()
        return control_frame

    def _create_recording_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Grafikler (Medikal Temaya Uygun Renkler)
        self.plot_acc = pg.PlotWidget(title="İvme (G-Force) - Kinematik Veri")
        self.plot_acc.showGrid(x=True, y=True, alpha=0.5)
        self.plot_acc.setYRange(-3, 3) 
        self.customize_plot(self.plot_acc)
        self.curve_ax = self.plot_acc.plot(pen=pg.mkPen('#E74C3C', width=2), name="X Ekseni") # Kırmızı
        self.curve_ay = self.plot_acc.plot(pen=pg.mkPen('#27AE60', width=2), name="Y Ekseni") # Yeşil
        self.curve_az = self.plot_acc.plot(pen=pg.mkPen('#2980B9', width=2), name="Z Ekseni") # Mavi
        layout.addWidget(self.plot_acc, stretch=1) 

        self.plot_gyro = pg.PlotWidget(title="Jiroskop (Açısal Hız) - Kinematik Veri")
        self.plot_gyro.showGrid(x=True, y=True, alpha=0.5)
        self.plot_gyro.setYRange(-300, 300) 
        self.customize_plot(self.plot_gyro)
        self.curve_gx = self.plot_gyro.plot(pen=pg.mkPen('#E67E22', width=2), name="X Ekseni") # Turuncu
        self.curve_gy = self.plot_gyro.plot(pen=pg.mkPen('#8E44AD', width=2), name="Y Ekseni") # Mor
        self.curve_gz = self.plot_gyro.plot(pen=pg.mkPen('#16A085', width=2), name="Z Ekseni") # Turkuaz
        layout.addWidget(self.plot_gyro, stretch=1)

        # --- ELEKTRİK YÖNETİMİ PANELİ (GRAFİKLERİN EN ALTINA SABİTLENDİ) ---
        group_stim = QGroupBox("⚡ Terapötik Stimülasyon Yönetimi - [PROTOTİP GÖRSEL MODU]")
        group_stim.setMaximumHeight(110) 
        
        stim_layout = QHBoxLayout(group_stim)

        # 1. Frekans (Hz)
        self.spin_hz = QSpinBox()
        self.spin_hz.setRange(1, 150)
        self.spin_hz.setValue(50)
        self.spin_hz.setSuffix(" Hz")
        stim_layout.addWidget(QLabel("Frekans:"))
        stim_layout.addWidget(self.spin_hz)

        # 2. Sinyal Süresi (Pulse Width)
        self.spin_pulse = QSpinBox()
        self.spin_pulse.setRange(50, 1000)
        self.spin_pulse.setValue(200)
        self.spin_pulse.setSuffix(" µs")
        stim_layout.addWidget(QLabel("Sinyal Uzunluğu:"))
        stim_layout.addWidget(self.spin_pulse)

        # 3. Akım Şiddeti (Mikroamper)
        self.spin_amp = QSpinBox()
        self.spin_amp.setRange(0, 10000)
        self.spin_amp.setValue(1500)
        self.spin_amp.setSuffix(" µA")
        stim_layout.addWidget(QLabel("Şiddet:"))
        stim_layout.addWidget(self.spin_amp)

        # 4. Toplam Süre (Dakika)
        self.spin_duration = QSpinBox()
        self.spin_duration.setRange(1, 60)
        self.spin_duration.setValue(20)
        self.spin_duration.setSuffix(" Dk")
        stim_layout.addWidget(QLabel("Süre:"))
        stim_layout.addWidget(self.spin_duration)

        # Uygula Butonu (Mock)
        self.btn_apply_stim = self.create_button("⚡ SİNYALİ GÖNDER", "#1ABC9C", "#16A085")
        self.btn_apply_stim.setMinimumWidth(150)
        self.btn_apply_stim.clicked.connect(self.send_stimulation_params_mock) 
        stim_layout.addWidget(self.btn_apply_stim)

        layout.addWidget(group_stim, stretch=0) 
        
        return tab

    def _create_patient_management_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        lbl_title = QLabel("Klinik Rapor Arşivi")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2C3E50; margin-bottom: 10px;")
        layout.addWidget(lbl_title)

        lbl_tremor = QLabel("📊 Tremor Raporları (PDF)")
        lbl_tremor.setStyleSheet("color: #2980B9; font-weight: bold; margin-top: 10px;")
        layout.addWidget(lbl_tremor)

        self.list_tremor = QListWidget()
        self.list_tremor.setFixedHeight(150)
        self.list_tremor.itemDoubleClicked.connect(self.open_pdf_tremor)
        layout.addWidget(self.list_tremor)

        lbl_bradi = QLabel("🖱️ Bradikinezi Raporları (PDF)")
        lbl_bradi.setStyleSheet("color: #E67E22; font-weight: bold; margin-top: 10px;")
        layout.addWidget(lbl_bradi)

        self.list_bradi = QListWidget()
        self.list_bradi.setFixedHeight(150)
        self.list_bradi.itemDoubleClicked.connect(self.open_pdf_bradi)
        layout.addWidget(self.list_bradi)

        layout.addStretch()
        return tab

    def _create_add_patient_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background-color: #FFFFFF;")
        form_layout = QFormLayout(scroll_widget)

        lbl_title = QLabel("Yeni Hasta Kaydı (Klinik Protokol)")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2C3E50; margin-bottom: 15px;")
        layout.addWidget(lbl_title)

        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # --- YENİ EKLENEN/DEĞİŞEN ALANLAR ---
        self.txt_protocol = QLineEdit()
        self.txt_protocol.setPlaceholderText("Örn: PRT-2026-001")
        form_layout.addRow("Protokol No *:", self.txt_protocol)

        self.txt_new_patient_name = QLineEdit()
        form_layout.addRow("Hasta Adı *:", self.txt_new_patient_name)

        self.spin_age = QSpinBox()
        self.spin_age.setRange(0, 150)
        form_layout.addRow("Yaş:", self.spin_age)

        self.combo_gender = QComboBox()
        self.combo_gender.addItems(["Erkek", "Kadın", "Diğer"])
        form_layout.addRow("Cinsiyet:", self.combo_gender)

        self.combo_dominant_side = QComboBox()
        self.combo_dominant_side.addItems(["Sağ", "Sol", "Çift Taraf"])
        form_layout.addRow("Baskın Hastalık Tarafı:", self.combo_dominant_side)

        self.spin_onset_year = QSpinBox()
        self.spin_onset_year.setRange(1950, datetime.now().year)
        self.spin_onset_year.setValue(datetime.now().year)
        form_layout.addRow("Tremor Başlangıç Yılı:", self.spin_onset_year)

        self.combo_diagnosis = QComboBox()
        self.combo_diagnosis.addItems(["Parkinson", "Essential Tremor", "Diğer"])
        form_layout.addRow("Tanı:", self.combo_diagnosis)

        self.txt_doctor_name = QLineEdit()
        form_layout.addRow("Sorumlu Hekim:", self.txt_doctor_name)

        self.txt_phone = QLineEdit()
        form_layout.addRow("İletişim / Tel:", self.txt_phone)

        self.txt_new_history = QTextEdit()
        self.txt_new_history.setPlaceholderText("Hastanın klinik öyküsünü, kullandığı ilaçları (örn: Levodopa) buraya yazın...")
        self.txt_new_history.setMaximumHeight(100)
        form_layout.addRow("Klinik Öykü:", self.txt_new_history)

        layout.addWidget(form_widget)
        layout.addSpacing(15)

        btn_layout = QHBoxLayout()
        btn_save = self.create_button("✓ Kaydı Tamamla", "#2ECC71", "#27AE60")
        btn_save.setMinimumHeight(45)
        btn_save.clicked.connect(self.add_new_patient)
        btn_layout.addWidget(btn_save)

        btn_cancel = self.create_button("🔄 Formu Temizle", "#95A5A6", "#7F8C8D")
        btn_cancel.setMinimumHeight(45)
        btn_cancel.clicked.connect(self.clear_patient_form)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)
        layout.addStretch()
        return tab

    # ---------------- FONKSİYONLAR ----------------
    
    def show_patient_context_menu(self, pos):
        """Listede sağ tıklandığında menüyü açar"""
        item = self.list_patients.itemAt(pos)
        if item is None:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #FFFFFF; border: 1px solid #BDC3C7; color: #2C3E50; font-weight: bold;}
            QMenu::item:selected { background-color: #3498DB; color: white; }
        """)
        
        update_action = QAction("📝 Bilgileri Güncelle", self)
        update_action.triggered.connect(lambda: self.open_update_dialog(item.text()))
        menu.addAction(update_action)
        
        # Menüyü farenin tam tıklandığı yerde aç
        menu.exec(self.list_patients.viewport().mapToGlobal(pos))

    def open_update_dialog(self, patient_name):
        """Güncelleme panelini açar ve yeni veriyi kaydeder"""
        details = self.db.get_patient_details(patient_name)
        if not details:
            return
            
        dialog = UpdatePatientDialog(patient_name, details, self)
        
        # Eski öyküyü okuyup pencereye yazdır
        history_file = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", patient_name, "oyku.txt")
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                dialog.txt_history.setText(f.read())

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_updated_data()
            
            # 1. Veritabanında güncelle
            try:
                if hasattr(self.db, 'update_patient_details'):
                    self.db.update_patient_details(patient_name, new_data['age'], new_data['dominant_side'], new_data['doctor'], new_data['phone'])
            except Exception as e:
                print(f"DB Güncelleme uyarısı: Lütfen database.py dosyanıza update_patient_details fonksiyonunu ekleyin.\n{e}")

            # 2. Öykü (Txt) dosyasını güncelle
            if new_data['history'] or new_data['history'] == "":
                with open(history_file, 'w', encoding='utf-8') as f:
                    f.write(new_data['history'])
            
            QMessageBox.information(self, "Başarılı", f"{patient_name} adlı hastanın bilgileri güncellendi.")
            
            # Ekranda o an seçiliyse arayüzü tazele
            if self.current_patient == patient_name:
                # Eşleşen öğeyi bulup tıkla
                items = self.list_patients.findItems(patient_name, Qt.MatchFlag.MatchExactly)
                if items:
                    self.select_patient(items[0])

    def send_stimulation_params_mock(self):
        if not self.current_patient:
            QMessageBox.warning(self, "Uyarı", "Lütfen önce bir hasta seçin!")
            return
            
        hz = self.spin_hz.value()
        pulse = self.spin_pulse.value()
        amp = self.spin_amp.value()
        duration = self.spin_duration.value()

        QMessageBox.information(self, "Klinik Simülasyon Modu", 
            f"Terapötik Elektrik parametreleri arayüzde onaylandı:\n\n"
            f"Frekans: {hz} Hz\n"
            f"Sinyal Uzunluğu: {pulse} µs\n"
            f"Şiddet: {amp} µA\n"
            f"Süre: {duration} Dakika\n\n"
            f"⚠️ NOT: Cihaz donanımı şu an pasif izleme modundadır. "
            f"Gerçek elektriksel uyarım bir sonraki revizyonda aktif edilecektir.")

    def refresh_patient_list(self):
        self.list_patients.clear()
        for patient in self.db.get_all_patients():
            self.list_patients.addItem(patient)

    def search_patients(self):
        search_text = self.txt_search_patient.text().lower()
        self.list_patients.clear()
        for patient in self.db.get_all_patients():
            if search_text in patient.lower():
                self.list_patients.addItem(patient)

    def select_patient(self, item):
        self.current_patient = item.text()
        self.lbl_current_patient.setText(f"Hasta: {self.current_patient}")

        details = self.db.get_patient_details(self.current_patient)
        if details:
            protocol = details.get('protocol_no', '-')
            side = details.get('dominant_side', '-')
            onset = details.get('onset_year', '-')
            
            detail_text = f"Protokol: {protocol} | Yaş: {details.get('age','-')} | Taraf: {side} | Başlangıç: {onset}"
            self.text_patient_details.setText(detail_text)
        
        history_file = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", self.current_patient, "oyku.txt")
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                self.txt_patient_history.setText(f.read())
        else:
            self.txt_patient_history.setText("Kayıtlı bir öykü bulunmuyor.")
            
        self.btn_delete_patient.setEnabled(True)
        self.update_patient_records()

    def add_new_patient(self):
        name = self.txt_new_patient_name.text().strip()
        protocol = self.txt_protocol.text().strip()
        
        if not name or not protocol:
            QMessageBox.warning(self, "Uyarı", "Hasta Adı ve Protokol Numarası zorunludur!")
            return

        age = self.spin_age.value()
        gender = self.combo_gender.currentText()
        dominant_side = self.combo_dominant_side.currentText()
        onset_year = self.spin_onset_year.value()
        diagnosis = self.combo_diagnosis.currentText()
        doctor = self.txt_doctor_name.text().strip()
        phone = self.txt_phone.text().strip()

        try:
            success = self.db.add_patient_with_details(protocol, name, age, gender, dominant_side, onset_year, diagnosis, doctor, phone)
        except Exception as e:
            QMessageBox.critical(self, "Veritabanı Uyarısı", f"Veritabanı alanları uyuşmuyor. Lütfen database.py dosyanızı yeni alanlara göre güncelleyin!\nHata:\n{e}")
            return

        if success:
            patient_folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", name)
            os.makedirs(os.path.join(patient_folder, "VeriSeti_Tremor"), exist_ok=True)
            os.makedirs(os.path.join(patient_folder, "VeriSeti_Bradikinezi"), exist_ok=True)

            history_text = self.txt_new_history.toPlainText().strip()
            history_file = os.path.join(patient_folder, "oyku.txt")
            with open(history_file, 'w', encoding='utf-8') as f:
                f.write(history_text if history_text else "Öykü girilmedi.")

            QMessageBox.information(self, "Başarılı", f"Klinik Kayıt Tamamlandı!\nKlasör: {patient_folder}")
            self.clear_patient_form()
            self.refresh_patient_list()
        else:
            QMessageBox.warning(self, "Hata", f"Bu hasta veya protokol numarası sistemde kayıtlı!")

    def delete_patient_action(self):
        if not self.current_patient: return
        reply = QMessageBox.question(self, 'Hasta Silme Onayı',
                                     f"'{self.current_patient}' adlı hastanın tüm klinik verilerini silmek istediğinize emin misiniz?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if hasattr(self.db, 'delete_patient'): self.db.delete_patient(self.current_patient)
                patient_folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", self.current_patient)
                if os.path.exists(patient_folder): shutil.rmtree(patient_folder, ignore_errors=True)
                
                self.current_patient = None
                self.lbl_current_patient.setText("Hiçbiri seçilmedi")
                self.text_patient_details.clear()
                self.txt_patient_history.clear()
                self.btn_delete_patient.setEnabled(False)
                self.list_tremor.clear()
                self.list_bradi.clear()
                self.refresh_patient_list()
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Silme hatası:\n{e}")

    def clear_patient_form(self):
        self.txt_protocol.clear()
        self.txt_new_patient_name.clear()
        self.spin_age.setValue(0)
        self.combo_gender.setCurrentIndex(0)
        self.combo_dominant_side.setCurrentIndex(0)
        self.spin_onset_year.setValue(datetime.now().year)
        self.combo_diagnosis.setCurrentIndex(0)
        self.txt_doctor_name.clear()
        self.txt_phone.clear()
        self.txt_new_history.clear()

    def update_patient_records(self):
        if not self.current_patient: return
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

    def toggle_recording(self):
        if not self.current_patient:
            QMessageBox.warning(self, "Uyarı", "Lütfen kayıt için bir hasta seçin!")
            return

        if not self.is_recording:
            self.is_recording = True
            self.recording_data = []
            self.btn_record.setText("KAYDI BİTİR VE ANALİZ ET")
            self.btn_record.setStyleSheet("background-color: #8E44AD; color: white;") 
            
            selected_mode = self.combo_mode.currentText()
            if "Tremor" in selected_mode:
                self.current_mode = "Tremor"
                folder_name = "VeriSeti_Tremor"
            else:
                self.current_mode = "Bradikinezi"
                folder_name = "VeriSeti_Bradikinezi"

            patient_folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", self.current_patient)
            folder_path = os.path.join(patient_folder, folder_name)
            os.makedirs(folder_path, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.current_filename = os.path.join(folder_path, f"{self.current_patient}_{self.current_mode}_{timestamp}.csv")
            
            self.lbl_status.setText(f"KAYITTA: {self.current_mode.upper()} ({self.current_patient})")
        else:
            self.is_recording = False
            self.btn_record.setText("KAYDI BAŞLAT")
            self.btn_record.setStyleSheet("background-color: #E74C3C; color: white;") 
            self.save_data_to_csv()
            self.run_analysis()
            self.update_patient_records()

    def save_data_to_csv(self):
        if not self.recording_data: return
        
        with open(self.current_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ"])
            writer.writerows(self.recording_data)

        try:
            accel_data = np.array([[float(row[0]), float(row[1]), float(row[2])] for row in self.recording_data])
            score = np.sqrt(np.mean(accel_data**2))
            self.db.add_test(self.current_patient, self.current_mode, self.current_filename, score, 0.0, "")
        except:
            pass

    def update_plot(self, data):
        if len(data) >= 7:
            battery_pct = int(data[6])
            self.prog_battery.setValue(battery_pct)
            self.prog_battery.setFormat(f"%p% - {'⚡ Şarj Oluyor' if battery_pct >= 100 else 'Batarya Durumu'}")

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
        if self.worker is None:
            port = self.combo_ports.currentText()
            if not port: return
            self.worker = SerialWorker(port)
            self.worker.data_received.connect(self.update_plot)
            self.worker.start()
            self.btn_connect.setText("BAĞLANTIYI KES")
            self.btn_connect.setStyleSheet("background-color: #E67E22; color: white;")
            self.btn_record.setEnabled(True)
            self.lbl_status.setText(f"CİHAZ BAĞLI: {port}")
        else:
            self.worker.stop()
            self.worker = None
            self.btn_connect.setText("CİHAZA BAĞLAN")
            self.btn_connect.setStyleSheet("background-color: #3498DB; color: white;")
            self.btn_record.setEnabled(False)
            self.lbl_status.setText("SİSTEM HAZIR")

    def refresh_ports(self):
        self.combo_ports.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports: self.combo_ports.addItem(port.device)

    def run_analysis(self):
        if not getattr(self, 'current_filename', '') or not os.path.exists(self.current_filename):
            QMessageBox.warning(self, "Hata", "Analiz edilecek CSV dosyası bulunamadı!")
            return
        try:
            self.lbl_status.setText(f"ANALİZ EDİLİYOR: {self.current_mode}...")
            QApplication.processEvents()
            
            if self.current_mode == "Tremor":
                import analyze_tremor
                analyze_tremor.run_analysis(self.current_filename)
            elif self.current_mode == "Bradikinezi":
                import analyze_bradykinesia
                analyze_bradykinesia.run_analysis(self.current_filename)

            self.lbl_status.setText("SİSTEM HAZIR")
            QMessageBox.information(self, "Klinik Rapor Hazır", f"{self.current_mode} analizi başarıyla tamamlandı.\nPDF raporu hasta dosyasına eklendi.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Analiz sırasında bir hata oluştu:\n{e}")

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

    def create_button(self, text, bg_color, hover_color, text_color="#FFFFFF"):
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{ background-color: {bg_color}; color: {text_color}; border-radius: 6px; padding: 10px; font-weight: bold; font-size: 13px; border: none; }}
            QPushButton:hover {{ background-color: {hover_color}; }}
            QPushButton:pressed {{ background-color: {bg_color}; padding-top: 12px; }}
            QPushButton:disabled {{ background-color: #BDC3C7; color: #7F8C8D; }}
        """)
        return btn

    def customize_plot(self, plot_widget):
        plot_widget.getAxis('left').setPen('#7F8C8D')
        plot_widget.getAxis('bottom').setPen('#7F8C8D')
        plot_widget.addLegend(offset=(10, 10))
        plot_widget.setStyleSheet("border: 1px solid #BDC3C7; border-radius: 8px; background-color: #FFFFFF;")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ParkinsonGUI()
    window.show()
    window.raise_()
    window.activateWindow()
    QTimer.singleShot(0, window.raise_)
    QTimer.singleShot(0, window.activateWindow)
    sys.exit(app.exec())