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

# Arayüz Kütüphaneleri (QStackedWidget eklendi)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QComboBox, 
                             QMessageBox, QFrame, QCheckBox, QLineEdit, QListWidget,
                             QFileDialog, QTabWidget, QSpinBox, QDateEdit, QTimeEdit,
                             QTableWidget, QTableWidgetItem, QDateTimeEdit, QListWidgetItem,
                             QScrollArea, QFormLayout, QDoubleSpinBox, QProgressBar,
                             QTextEdit, QGroupBox, QGridLayout, QDialog, QMenu, QStackedWidget) 
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt, QSettings
from PyQt6.QtGui import QFont, QColor, QAction

# Grafik Kütüphanesi
import pyqtgraph as pg

# DALGALARI PÜRÜZSÜZ (YUMUŞAK) ÇİZMEK İÇİN ANTIALIASING AÇILDI
pg.setConfigOptions(antialias=True) 
try:
    pg.setConfigOptions(useOpenGL=True) 
except:
    pass
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
            self.serial_conn = serial.Serial(self.port_name, self.baud_rate, timeout=0.1)
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
                    except (ValueError, IndexError):
                        pass
                else:
                    time.sleep(0.001)
        except Exception as e:
            print(f"Bağlantı Hatası: {e}")
        finally:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()

    def stop(self):
        self.is_running = False
        self.quit()
        self.wait(500)

# ----------------------------------------
# HASTA GÜNCELLEME PENCERESİ (DIALOG)
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

        self.spin_age = QSpinBox()
        self.spin_age.setRange(0, 150)
        self.spin_age.setValue(int(details.get('age', 0)) if str(details.get('age')) not in ['-', 'None', ''] else 0)
        
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
a
        self.setWindowTitle("NeuroMotion Analiz - Medikal Prototip v4.7")
        self.resize(1450, 950)
        
        self.plot_counter = 0 
        
        self.setStyleSheet("""""
            QMainWindow { background-color: #F4F6F9; }
            QLabel { color: #2C3E50; font-size: 14px; font-family: 'Segoe UI', sans-serif; }
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit {
                background-color: #FFFFFF; color: #2C3E50;
                border: 1px solid #BDC3C7; border-radius: 5px; padding: 5px; font-size: 13px;
            }
            QComboBox::drop-down { border: 0px; }
            QFrame#ControlPanel { background-color: #FFFFFF; border-radius: 10px; border: 1px solid #E0E6ED; }
            QFrame#Header { background-color: #2980B9; border-bottom: 3px solid #1ABC9C; }
            QLabel#HeaderTitle { font-size: 22px; font-weight: bold; color: #FFFFFF; }
            QLabel#StatusLabel { font-weight: bold; color: #F1C40F; }
            QTabWidget::pane { border: 1px solid #E0E6ED; background: #FFFFFF; border-radius: 5px; }
            QTabBar::tab { background-color: #ECF0F1; color: #7F8C8D; padding: 10px 20px; border: 1px solid #E0E6ED; font-weight: bold; }
            QTabBar::tab:selected { background-color: #FFFFFF; color: #2980B9; border-bottom: 3px solid #2980B9; }
            QListWidget { background-color: #FFFFFF; border: 1px solid #BDC3C7; border-radius: 5px; font-size: 13px; color: #2C3E50;}
            QListWidget::item:selected { background-color: #D6EAF8; color: #2980B9; font-weight: bold; }
            QGroupBox { color: #2980; } )