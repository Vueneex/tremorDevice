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

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QComboBox, 
                             QMessageBox, QFrame, QCheckBox, QLineEdit, QListWidget,
                             QFileDialog, QTabWidget, QSpinBox, QDateEdit, QTimeEdit,
                             QTableWidget, QTableWidgetItem, QDateTimeEdit, QListWidgetItem,
                             QScrollArea, QFormLayout, QDoubleSpinBox, QProgressBar,
                             QTextEdit, QTextBrowser, QGroupBox, QGridLayout, QDialog, QMenu, QStackedWidget,
                             QSlider) 
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt, QSettings, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor, QAction

import pyqtgraph as pg

# DALGALARI PURUZSUZ CIZMEK ICIN
pg.setConfigOptions(antialias=True) 
try:
    pg.setConfigOptions(useOpenGL=True) 
except:
    pass
pg.setConfigOption('background', '#FFFFFF')
pg.setConfigOption('foreground', '#2C3E50')

# ----------------------------------------
# 1. ARKA PLAN ISCISI (SERIAL WORKER) - COKLU SENSOR
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
                            
                            base_sensor = [raw_data[0], raw_data[1], raw_data[2], raw_data[3], raw_data[4], raw_data[5]]
                            multi_sensor_data = []
                            for i in range(12):
                                if i == 0:
                                    multi_sensor_data.extend(base_sensor)
                                else:
                                    noise_acc = np.random.normal(0, 500, 3).tolist()
                                    noise_gyro = np.random.normal(0, 10, 3).tolist()
                                    multi_sensor_data.extend([
                                        base_sensor[0] + noise_acc[0], base_sensor[1] + noise_acc[1], base_sensor[2] + noise_acc[2],
                                        base_sensor[3] + noise_gyro[0], base_sensor[4] + noise_gyro[1], base_sensor[5] + noise_gyro[2]
                                    ])
                            
                            multi_sensor_data.append(battery_val)
                            self.data_received.emit(multi_sensor_data)
                            
                    except (ValueError, IndexError):
                        pass
                else:
                    time.sleep(0.001)
        except Exception as e:
            print(f"Baglanti Hatasi: {e}")
        finally:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()

    def stop(self):
        self.is_running = False
        self.quit()
        self.wait(500)


# ----------------------------------------
# HASTA GUNCELLEME PENCERESI (DIALOG)
# ----------------------------------------
class UpdatePatientDialog(QDialog):
    def __init__(self, patient_name, details, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Klinik Kayit Guncelle: {patient_name}")
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
        self.combo_side.addItems(["Sag", "Sol", "Cift Taraf"])
        self.combo_side.setCurrentText(str(details.get('dominant_side', 'Sag')))

        self.txt_doctor = QLineEdit(str(details.get('doctor_name', '')))
        self.txt_phone = QLineEdit(str(details.get('contact_phone', '')))
        
        self.txt_history = QTextEdit()
        self.txt_history.setMaximumHeight(80)

        form_layout.addRow("Yas:", self.spin_age)
        form_layout.addRow("Baskin Taraf:", self.combo_side)
        form_layout.addRow("Doktor:", self.txt_doctor)
        form_layout.addRow("Telefon:", self.txt_phone)
        form_layout.addRow("Klinik Oyku:", self.txt_history)

        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Kaydet")
        self.btn_save.setStyleSheet("background-color: #2ECC71;")
        self.btn_save.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Iptal")
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

        self.setWindowTitle("NeuroMotion Analiz - Klinik Prototip v5.8")
        self.resize(1500, 950)
        
        self.plot_counter = 0 
        
        self.setStyleSheet("""
            QMainWindow { background-color: #F4F6F9; }
            QLabel { color: #2C3E50; font-size: 14px; font-family: 'Segoe UI', sans-serif; }
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit {
                background-color: #FFFFFF; color: #2C3E50;
                border: 1px solid #BDC3C7; border-radius: 5px; padding: 5px; font-size: 13px;
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
            
            QPushButton.imu_card {
                background-color: #FFFFFF;
                border: 2px solid #BDC3C7;
                border-radius: 10px;
                color: #2C3E50;
                font-weight: bold;
                font-size: 16px;
                text-align: left;
                padding-left: 15px;
            }
            QPushButton.imu_card:hover {
                border: 2px solid #3498DB;
                background-color: #EBF5FB;
            }
        """)

        self.worker = None
        self.recording_data = [] 
        self.is_recording = False
        self.current_filename = ""
        self.current_mode = "" 
        self.current_patient = None
        
        # OSILOSKOP DEGISKENLERI (CIFT KANAL + SAYAC)
        self.is_stimulating_1 = False
        self.stim_countdown_timer_1 = QTimer()
        self.stim_countdown_timer_1.timeout.connect(self.update_stim_countdown_1)
        self.stim_remaining_1 = 0
        
        self.is_stimulating_2 = False
        self.stim_countdown_timer_2 = QTimer()
        self.stim_countdown_timer_2.timeout.connect(self.update_stim_countdown_2)
        self.stim_remaining_2 = 0
        
        self.workspace_root = os.path.dirname(os.path.abspath(__file__))
        
        db_path = os.path.join(self.workspace_root, "test_history.db")
        self.db = TestDatabase(db_path)
        
        self.buffer_size = 300
        self.multi_data_buffer = [
            {'ax': [], 'ay': [], 'az': [], 'gx': [], 'gy': [], 'gz': []} for _ in range(12)
        ]
        self.active_detailed_imu = 0 

        self.init_ui()
        self.refresh_patient_list()
        
        self.update_preview_1()
        self.update_preview_2()
    
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        header_frame = QFrame()
        header_frame.setObjectName("Header")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 5, 10, 5)
        
        self.btn_toggle_panel = QPushButton("=")
        self.btn_toggle_panel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_panel.setStyleSheet("""
            QPushButton { background-color: transparent; color: white; font-size: 26px; border: none; padding: 5px; }
            QPushButton:hover { color: #F1C40F; }
        """)
        self.btn_toggle_panel.clicked.connect(self.toggle_left_panel)
        header_layout.addWidget(self.btn_toggle_panel)

        header_title = QLabel("Klinik Hasta Yonetimi")
        header_title.setObjectName("HeaderTitle")
        header_layout.addWidget(header_title)
        header_layout.addStretch()
        
        main_layout.addWidget(header_frame)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 10, 10)
        content_layout.setSpacing(10)
        
        self.left_panel = self._create_left_panel()
        content_layout.addWidget(self.left_panel)

        main_tabs = QTabWidget()
        main_tabs.addTab(self._create_recording_tab(), "Kayit & Simulasyon")
        main_tabs.addTab(self._create_patient_management_tab(), "Rapor Yonetimi")
        main_tabs.addTab(self._create_patient_database_tab(), "Hasta Bilgi Bankasi")
        main_tabs.addTab(self._create_add_patient_tab(), "Yeni Hasta Kaydi")
        
        content_layout.addWidget(main_tabs, 1)
        main_layout.addLayout(content_layout)

    def _create_left_panel(self):
        control_frame = QFrame()
        control_frame.setObjectName("ControlPanel")
        control_frame.setMinimumWidth(320)
        control_frame.setMaximumWidth(320)
        
        left_layout = QVBoxLayout(control_frame)
        left_layout.setContentsMargins(10, 10, 10, 10)

        lbl_patient = QLabel("HASTA SECIMI")
        lbl_patient.setStyleSheet("color: #2980B9; font-weight: bold; margin-bottom: 5px;")
        left_layout.addWidget(lbl_patient)

        search_row = QHBoxLayout()
        self.txt_search_patient = QLineEdit()
        self.txt_search_patient.setPlaceholderText("Ara...")
        self.txt_search_patient.textChanged.connect(self.search_patients)
        search_row.addWidget(self.txt_search_patient)
        
        btn_refresh_patients = self.create_button("Yenile", "#ECF0F1", "#D5D8DC", text_color="#2C3E50")
        btn_refresh_patients.setMaximumWidth(60)
        btn_refresh_patients.clicked.connect(self.refresh_patient_list)
        search_row.addWidget(btn_refresh_patients)
        left_layout.addLayout(search_row)

        self.list_patients = QListWidget()
        self.list_patients.setFixedHeight(120)
        self.list_patients.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_patients.customContextMenuRequested.connect(self.show_patient_context_menu)
        self.list_patients.itemClicked.connect(self.select_patient)
        left_layout.addWidget(self.list_patients)

        self.lbl_current_patient = QLabel("Hicbiri secilmedi")
        self.lbl_current_patient.setStyleSheet("color: #27AE60; font-weight: bold; font-size: 15px; margin-top: 5px;")
        left_layout.addWidget(self.lbl_current_patient)

        self.text_patient_details = QLineEdit()
        self.text_patient_details.setReadOnly(True)
        self.text_patient_details.setStyleSheet("background-color: #F4F6F9; color: #34495E; font-size: 11px;")
        left_layout.addWidget(self.text_patient_details)

        lbl_history = QLabel("Klinik Oyku:")
        lbl_history.setStyleSheet("font-size: 12px; color: #7F8C8D; margin-top: 5px; font-weight: bold;")
        left_layout.addWidget(lbl_history)

        self.txt_patient_history = QTextEdit()
        self.txt_patient_history.setReadOnly(True)
        self.txt_patient_history.setMaximumHeight(80)
        self.txt_patient_history.setStyleSheet("background-color: #F8F9F9; color: #2C3E50; font-size: 12px;")
        left_layout.addWidget(self.txt_patient_history)

        self.btn_delete_patient = self.create_button("Hastayi Sil", "#E74C3C", "#C0392B")
        self.btn_delete_patient.setEnabled(False)
        self.btn_delete_patient.clicked.connect(self.delete_patient_action)
        left_layout.addWidget(self.btn_delete_patient)

        left_layout.addSpacing(5)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #E0E6ED;")
        left_layout.addWidget(line)

        lbl_device = QLabel("CIHAZ BAGLANTISI")
        lbl_device.setStyleSheet("color: #2980B9; font-weight: bold; margin-left: 1px;")
        left_layout.addWidget(lbl_device)

        port_row = QHBoxLayout()
        self.combo_ports = QComboBox()
        port_row.addWidget(self.combo_ports)
        btn_refresh = self.create_button("Yenile", "#ECF0F1", "#D5D8DC", text_color="#2980B9")
        btn_refresh.setMaximumWidth(65) 
        btn_refresh.clicked.connect(self.refresh_ports)
        port_row.addWidget(btn_refresh)
        left_layout.addLayout(port_row)

        self.btn_connect = self.create_button("CIHAZA BAGLAN", "#3498DB", "#2980B9")
        self.btn_connect.clicked.connect(self.toggle_connection)
        left_layout.addWidget(self.btn_connect)

        lbl_battery = QLabel("Batarya Durumu")
        lbl_battery.setStyleSheet("color: #2980B9; font-size: 13px; font-weight: bold; margin-top: 10px; margin-left: 1px;")
        left_layout.addWidget(lbl_battery)
        self.prog_battery = QProgressBar()
        self.prog_battery.setRange(0, 100)
        self.prog_battery.setValue(0)
        left_layout.addWidget(self.prog_battery)

        lbl_mode = QLabel("PROTOKOL SECIMI")
        lbl_mode.setStyleSheet("color: #E67E22; font-weight: bold; margin-top: 15px; margin-left: -6px;")
        left_layout.addWidget(lbl_mode)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Tremor Analizi", "Bradikinezi Analizi"])
        self.combo_mode.setStyleSheet("border: 2px solid #E67E22; font-weight: bold; color: #D35400;")
        left_layout.addWidget(self.combo_mode)

        left_layout.addSpacing(10)

        self.btn_record = self.create_button("KAYDI BASLAT", "#E74C3C", "#C0392B")
        self.btn_record.setEnabled(False)
        self.btn_record.setMinimumHeight(45)
        self.btn_record.clicked.connect(self.toggle_recording)
        left_layout.addWidget(self.btn_record)

        left_layout.addStretch()
        return control_frame

    def _create_slider_widget(self, title, min_val, max_val, default_val, suffix, color, callback):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(2)
        
        top_layout = QHBoxLayout()
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 12px; color: #7F8C8D; font-weight: bold;")
        
        spin_val = QSpinBox()
        spin_val.setRange(min_val, max_val)
        spin_val.setValue(default_val)
        spin_val.setSuffix(f" {suffix}")
        spin_val.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        spin_val.setAlignment(Qt.AlignmentFlag.AlignRight)
        spin_val.setFixedWidth(80)
        spin_val.setStyleSheet(f"""
            QSpinBox {{
                font-size: 13px; 
                color: {color}; 
                font-weight: bold;
                background-color: transparent;
                border: 1px solid transparent;
                padding: 1px;
            }}
            QSpinBox:focus {{
                border: 1px solid {color};
                border-radius: 4px;
                background-color: #FFFFFF;
            }}
        """)
        
        top_layout.addWidget(lbl_title)
        top_layout.addWidget(spin_val, alignment=Qt.AlignmentFlag.AlignRight)
        
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default_val)
        slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                border-radius: 4px;
                height: 6px;
                background: #ECF0F1;
            }}
            QSlider::sub-page:horizontal {{
                background: {color};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: #FFFFFF;
                border: 2px solid {color};
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {color};
            }}
        """)
        
        def on_slider_changed(val):
            spin_val.setValue(val)
            if callback:
                callback()
                
        def on_spinbox_changed(val):
            slider.setValue(val)
                
        slider.valueChanged.connect(on_slider_changed)
        spin_val.valueChanged.connect(on_spinbox_changed)
        
        layout.addLayout(top_layout)
        layout.addWidget(slider)
        return container, slider

    def _create_recording_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_bar = QHBoxLayout()
        
        self.btn_back_to_grid = self.create_button("< Tum Sensorlere Don", "#7F8C8D", "#95A5A6")
        self.btn_back_to_grid.setVisible(False) 
        self.btn_back_to_grid.clicked.connect(lambda: self.switch_sensor_view(-1))
        top_bar.addWidget(self.btn_back_to_grid)
        
        top_bar.addStretch() 
        
        lbl_view_title = QLabel("Aktif Gorunum:")
        lbl_view_title.setStyleSheet("font-weight: bold; color: #7F8C8D; margin-right: 10px;")
        top_bar.addWidget(lbl_view_title)
        
        self.btn_view1 = self.create_button("1 (Sensorler)", "#3498DB", "#2980B9", text_color="#FFFFFF")
        self.btn_view2 = self.create_button("2 (Osiloskop)", "#ECF0F1", "#BDC3C7", text_color="#2C3E50")
        
        self.btn_view1.clicked.connect(lambda: self.switch_graph_view(0))
        self.btn_view2.clicked.connect(lambda: self.switch_graph_view(1))
        
        top_bar.addWidget(self.btn_view1)
        top_bar.addWidget(self.btn_view2)
        layout.addLayout(top_bar)

        self.main_stack = QStackedWidget()
        
        page_sensors = QWidget()
        page_sensors_layout = QVBoxLayout(page_sensors)
        page_sensors_layout.setContentsMargins(0,0,0,0)
        
        self.sensor_stack = QStackedWidget()
        
        self.grid_widget = QWidget()
        grid_layout = QGridLayout(self.grid_widget)
        grid_layout.setSpacing(15)
        
        self.imu_buttons = []
        for i in range(12):
            btn = QPushButton(f"IMU {i+1}\n\nDurum: Bekliyor...")
            btn.setProperty("class", "imu_card")
            btn.setSizePolicy(btn.sizePolicy().Policy.Expanding, btn.sizePolicy().Policy.Expanding)
            btn.clicked.connect(lambda checked, idx=i: self.switch_sensor_view(idx))
            self.imu_buttons.append(btn)
            row = i // 4
            col = i % 4
            grid_layout.addWidget(btn, row, col)
            
        self.sensor_stack.addWidget(self.grid_widget) 
        
        self.detail_widget = QWidget()
        detail_layout = QVBoxLayout(self.detail_widget)
        
        self.lbl_active_imu = QLabel("IMU 1 Detay Gorunumu")
        self.lbl_active_imu.setStyleSheet("font-size: 18px; font-weight: bold; color: #2980B9;")
        detail_layout.addWidget(self.lbl_active_imu)
        
        self.plot_acc = pg.PlotWidget(title="Ivme (G-Force) - Kinematik Veri")
        self.plot_acc.showGrid(x=True, y=True, alpha=0.5)
        self.plot_acc.setYRange(-3, 3) 
        self.customize_plot(self.plot_acc)
        self.curve_ax = self.plot_acc.plot(pen=pg.mkPen('#E74C3C', width=2), name="X Ekseni")
        self.curve_ay = self.plot_acc.plot(pen=pg.mkPen('#27AE60', width=2), name="Y Ekseni")
        self.curve_az = self.plot_acc.plot(pen=pg.mkPen('#2980B9', width=2), name="Z Ekseni")
        detail_layout.addWidget(self.plot_acc, stretch=1) 

        self.plot_gyro = pg.PlotWidget(title="Jiroskop (Acisal Hiz) - Kinematik Veri")
        self.plot_gyro.showGrid(x=True, y=True, alpha=0.5)
        self.plot_gyro.setYRange(-300, 300) 
        self.customize_plot(self.plot_gyro)
        self.curve_gx = self.plot_gyro.plot(pen=pg.mkPen('#E67E22', width=2), name="X Ekseni")
        self.curve_gy = self.plot_gyro.plot(pen=pg.mkPen('#8E44AD', width=2), name="Y Ekseni")
        self.curve_gz = self.plot_gyro.plot(pen=pg.mkPen('#16A085', width=2), name="Z Ekseni")
        detail_layout.addWidget(self.plot_gyro, stretch=1)
        
        self.sensor_stack.addWidget(self.detail_widget)
        page_sensors_layout.addWidget(self.sensor_stack)
        self.main_stack.addWidget(page_sensors)

        page_stim = QWidget()
        page_stim_layout = QVBoxLayout(page_stim)
        page_stim_layout.setContentsMargins(0, 0, 0, 0)
        
        self.plot_stim_1 = pg.PlotWidget(title="Kanal 1 - Sinyal Onizlemesi")
        self.plot_stim_1.showGrid(x=True, y=True, alpha=0.5)
        self.plot_stim_1.setBackground('#111111') 
        self.plot_stim_1.getAxis('left').setPen('#2ECC71')
        self.plot_stim_1.getAxis('bottom').setPen('#2ECC71')
        self.plot_stim_1.setLabel('bottom', 'Zaman', units='ms')
        self.plot_stim_1.setLabel('left', 'Akim', units='uA')
        self.curve_stim_1 = self.plot_stim_1.plot(pen=pg.mkPen('#2ECC71', width=2))
        page_stim_layout.addWidget(self.plot_stim_1)
        
        self.plot_stim_2 = pg.PlotWidget(title="Kanal 2 - Sinyal Onizlemesi")
        self.plot_stim_2.showGrid(x=True, y=True, alpha=0.5)
        self.plot_stim_2.setBackground('#111111') 
        self.plot_stim_2.getAxis('left').setPen('#3498DB')
        self.plot_stim_2.getAxis('bottom').setPen('#3498DB')
        self.plot_stim_2.setLabel('bottom', 'Zaman', units='ms')
        self.plot_stim_2.setLabel('left', 'Akim', units='uA')
        self.curve_stim_2 = self.plot_stim_2.plot(pen=pg.mkPen('#3498DB', width=2))
        page_stim_layout.addWidget(self.plot_stim_2)

        self.main_stack.addWidget(page_stim)
        layout.addWidget(self.main_stack, stretch=1)

        group_stim = QGroupBox("Terapotik Simulasyon Yonetimi")
        group_stim.setMaximumHeight(220) 
        stim_main_layout = QVBoxLayout(group_stim)
        
        stim_layout_1 = QHBoxLayout()
        lbl_ch1 = QLabel("KANAL 1:")
        lbl_ch1.setStyleSheet("font-weight: bold; color: #2ECC71;")
        stim_layout_1.addWidget(lbl_ch1)
        
        w_hz_1, self.slider_hz_1 = self._create_slider_widget("Frekans", 1, 150, 50, "Hz", "#2ECC71", self.update_preview_1)
        w_pulse_1, self.slider_pulse_1 = self._create_slider_widget("Genislik", 50, 1000, 200, "us", "#2ECC71", self.update_preview_1)
        w_amp_1, self.slider_amp_1 = self._create_slider_widget("Siddet", 0, 10000, 1500, "uA", "#2ECC71", self.update_preview_1)
        w_dur_1, self.slider_dur_1 = self._create_slider_widget("Sure", 1, 120, 20, "Dk", "#2ECC71", None)

        stim_layout_1.addWidget(w_hz_1)
        stim_layout_1.addWidget(w_pulse_1)
        stim_layout_1.addWidget(w_amp_1)
        stim_layout_1.addWidget(w_dur_1)
        
        self.btn_apply_stim_1 = self.create_button("SINYALI BASLAT (K1)", "#2ECC71", "#27AE60")
        self.btn_apply_stim_1.clicked.connect(self.toggle_stimulation_1) 
        stim_layout_1.addWidget(self.btn_apply_stim_1)
        stim_main_layout.addLayout(stim_layout_1)
        
        stim_layout_2 = QHBoxLayout()
        lbl_ch2 = QLabel("KANAL 2:")
        lbl_ch2.setStyleSheet("font-weight: bold; color: #3498DB;")
        stim_layout_2.addWidget(lbl_ch2)
        
        w_hz_2, self.slider_hz_2 = self._create_slider_widget("Frekans", 1, 150, 50, "Hz", "#3498DB", self.update_preview_2)
        w_pulse_2, self.slider_pulse_2 = self._create_slider_widget("Genislik", 50, 1000, 200, "us", "#3498DB", self.update_preview_2)
        w_amp_2, self.slider_amp_2 = self._create_slider_widget("Siddet", 0, 10000, 1500, "uA", "#3498DB", self.update_preview_2)
        w_dur_2, self.slider_dur_2 = self._create_slider_widget("Sure", 1, 120, 20, "Dk", "#3498DB", None)

        stim_layout_2.addWidget(w_hz_2)
        stim_layout_2.addWidget(w_pulse_2)
        stim_layout_2.addWidget(w_amp_2)
        stim_layout_2.addWidget(w_dur_2)
        
        self.btn_apply_stim_2 = self.create_button("SINYALI BASLAT (K2)", "#3498DB", "#2980B9")
        self.btn_apply_stim_2.clicked.connect(self.toggle_stimulation_2) 
        stim_layout_2.addWidget(self.btn_apply_stim_2)
        stim_main_layout.addLayout(stim_layout_2)

        layout.addWidget(group_stim, stretch=0) 
        return tab

    def _create_patient_management_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        lbl_title = QLabel("Klinik Rapor Arsivi"); lbl_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(lbl_title)

        self.list_tremor = QListWidget(); self.list_tremor.setFixedHeight(150)
        self.list_tremor.itemDoubleClicked.connect(self.open_pdf_tremor)
        layout.addWidget(QLabel("Tremor Raporlari")); layout.addWidget(self.list_tremor)

        self.list_bradi = QListWidget(); self.list_bradi.setFixedHeight(150)
        self.list_bradi.itemDoubleClicked.connect(self.open_pdf_bradi)
        layout.addWidget(QLabel("Bradikinezi Raporlari")); layout.addWidget(self.list_bradi)
        
        layout.addStretch()
        return tab

    def _create_patient_database_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        search_side = QVBoxLayout()
        lbl_list_title = QLabel("KAYITLI HASTALAR")
        lbl_list_title.setStyleSheet("font-weight: bold; color: #2980B9;")
        search_side.addWidget(lbl_list_title)

        self.db_search_input = QLineEdit()
        self.db_search_input.setPlaceholderText("Isim veya protokol ile hizli ara...")
        self.db_search_input.textChanged.connect(self.search_in_database_tab)
        search_side.addWidget(self.db_search_input)

        self.db_patient_list = QListWidget()
        self.db_patient_list.setStyleSheet("QListWidget { border: 1px solid #D5D8DC; border-radius: 8px; }")
        self.db_patient_list.itemClicked.connect(self.display_full_patient_info)
        search_side.addWidget(self.db_patient_list)
        
        layout.addLayout(search_side, 1)

        self.detail_card = QGroupBox("HASTA AYRINTILI DOSYASI")
        self.detail_card.setStyleSheet("QGroupBox { font-size: 15px; background-color: #FFFFFF; }")
        card_layout = QVBoxLayout(self.detail_card)

        self.txt_full_details = QTextBrowser()
        self.txt_full_details.setOpenExternalLinks(False)
        self.txt_full_details.anchorClicked.connect(self.open_report_from_link)
        self.txt_full_details.setReadOnly(True)
        self.txt_full_details.setStyleSheet("""
            QTextEdit { 
                background-color: #FDFEFE; 
                border: none; 
                font-family: 'Consolas', 'Monospace'; 
                font-size: 14px; 
                line-height: 150%;
                color: #2C3E50;
            }
        """)
        card_layout.addWidget(self.txt_full_details)
        
        layout.addWidget(self.detail_card, 2)
        QTimer.singleShot(100, self.refresh_db_tab_list)
        return tab

    def _create_add_patient_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll_widget = QWidget(); scroll_widget.setStyleSheet("background-color: #FFFFFF;")
        form_layout = QFormLayout(scroll_widget)

        self.txt_protocol = QLineEdit(); self.txt_new_patient_name = QLineEdit()
        self.spin_age = QSpinBox(); self.spin_age.setRange(0, 150)
        self.combo_gender = QComboBox(); self.combo_gender.addItems(["Erkek", "Kadin", "Diger"])
        self.combo_dominant_side = QComboBox(); self.combo_dominant_side.addItems(["Sag", "Sol", "Cift Taraf"])
        self.spin_onset_year = QSpinBox(); self.spin_onset_year.setRange(1950, datetime.now().year); self.spin_onset_year.setValue(datetime.now().year)
        self.combo_diagnosis = QComboBox(); self.combo_diagnosis.addItems(["Parkinson", "Essential Tremor", "Diger"])
        self.txt_doctor_name = QLineEdit(); self.txt_phone = QLineEdit()
        self.txt_new_history = QTextEdit(); self.txt_new_history.setMaximumHeight(100)

        form_layout.addRow("Protokol No:", self.txt_protocol)
        form_layout.addRow("Hasta Adi:", self.txt_new_patient_name)
        form_layout.addRow("Yas:", self.spin_age)
        form_layout.addRow("Cinsiyet:", self.combo_gender)
        form_layout.addRow("Baskin Taraf:", self.combo_dominant_side)
        form_layout.addRow("Baslangic Yili:", self.spin_onset_year)
        form_layout.addRow("Tani:", self.combo_diagnosis)
        form_layout.addRow("Doktor:", self.txt_doctor_name)
        form_layout.addRow("Telefon:", self.txt_phone)
        form_layout.addRow("Klinik Oyku:", self.txt_new_history)

        layout.addWidget(scroll_widget)
        btn_layout = QHBoxLayout()
        btn_save = self.create_button("Kaydi Tamamla", "#2ECC71", "#27AE60"); btn_save.clicked.connect(self.add_new_patient)
        btn_cancel = self.create_button("Temizle", "#95A5A6", "#7F8C8D"); btn_cancel.clicked.connect(self.clear_patient_form)
        btn_layout.addWidget(btn_save); btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
        return tab

    # ---------------- FONKSİYONLAR ----------------
    
    def toggle_left_panel(self):
        width = self.left_panel.width()
        
        target_width = 0 if width > 0 else 320
        
        self.panel_anim = QPropertyAnimation(self.left_panel, b"maximumWidth")
        self.panel_anim.setDuration(300) 
        self.panel_anim.setStartValue(width)
        self.panel_anim.setEndValue(target_width)
        self.panel_anim.setEasingCurve(QEasingCurve.Type.InOutQuart)
        
        self.panel_anim_min = QPropertyAnimation(self.left_panel, b"minimumWidth")
        self.panel_anim_min.setDuration(300)
        self.panel_anim_min.setStartValue(width)
        self.panel_anim_min.setEndValue(target_width)
        self.panel_anim_min.setEasingCurve(QEasingCurve.Type.InOutQuart)
        
        self.panel_anim.start()
        self.panel_anim_min.start()

    def switch_graph_view(self, index):
        self.main_stack.setCurrentIndex(index)
        default_style = "QPushButton { background-color: #ECF0F1; color: #2C3E50; border-radius: 6px; font-weight: bold; font-size: 14px; border: 1px solid #BDC3C7; }"
        active_style = "QPushButton { background-color: #3498DB; color: #FFFFFF; border-radius: 6px; font-weight: bold; font-size: 14px; border: none; }"
        
        self.btn_view1.setStyleSheet(active_style if index == 0 else default_style)
        self.btn_view2.setStyleSheet(active_style if index == 1 else default_style)

    def switch_sensor_view(self, imu_index):
        if imu_index == -1:
            self.sensor_stack.setCurrentIndex(0)
            self.btn_back_to_grid.setVisible(False)
        else:
            self.active_detailed_imu = imu_index
            self.lbl_active_imu.setText(f"IMU {imu_index+1} Detay Gorunumu")
            self.sensor_stack.setCurrentIndex(1)
            self.btn_back_to_grid.setVisible(True)

    def refresh_db_tab_list(self):
        self.db_patient_list.clear()
        for patient in self.db.get_all_patients():
            self.db_patient_list.addItem(patient)

    def search_in_database_tab(self):
        txt = self.db_search_input.text().lower()
        self.db_patient_list.clear()
        for p in self.db.get_all_patients():
            if txt in p.lower():
                self.db_patient_list.addItem(p)

    def display_full_patient_info(self, item):
        patient_name = item.text()
        details = self.db.get_patient_details(patient_name)
        
        if details:
            history_content = "<i>Kayitli oyku bulunamadi.</i>"
            history_file = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", patient_name, "oyku.txt")
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    history_content = f.read().replace('\n', '<br>')

            p_folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", patient_name)
            t_folder = os.path.join(p_folder, "VeriSeti_Tremor")
            b_folder = os.path.join(p_folder, "VeriSeti_Bradikinezi")
            
            reports = []
            if os.path.exists(t_folder):
                for f in os.listdir(t_folder):
                    if f.endswith(('.pdf', '.csv')):
                        reports.append({'file': f, 'type': 'Tremor Analizi', 'time': os.path.getmtime(os.path.join(t_folder, f))})
            if os.path.exists(b_folder):
                for f in os.listdir(b_folder):
                    if f.endswith(('.pdf', '.csv')):
                        reports.append({'file': f, 'type': 'Bradikinezi Analizi', 'time': os.path.getmtime(os.path.join(b_folder, f))})
                        
            reports.sort(key=lambda x: x['time'], reverse=True)
            
            report_rows_html = ""
            if reports:
                for r in reports:
                    date_str = datetime.fromtimestamp(r['time']).strftime('%d.%m.%Y - %H:%M')
                    file_url = f"file:///{p_folder}/{'VeriSeti_Tremor' if r['type'] == 'Tremor Analizi' else 'VeriSeti_Bradikinezi'}/{r['file']}".replace("\\", "/")
                    
                    report_rows_html += f"""
                        <tr>
                            <td style="padding: 6px; border-bottom: 1px solid #ECF0F1; color: #34495E;">{date_str}</td>
                            <td style="padding: 6px; border-bottom: 1px solid #ECF0F1; font-weight: bold; color: #2980B9;">{r['type']}</td>
                            <td style="padding: 6px; border-bottom: 1px solid #ECF0F1;">
                                <a href="{file_url}" style="color: #E67E22; text-decoration: none; font-weight: bold;">Dosya: {r['file']}</a>
                            </td>
                        </tr>
                    """

            info_html = f"""
            <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #2C3E50;">
                <h3 style="color: #2980B9; border-bottom: 2px solid #BDC3C7; padding-bottom: 5px; margin-bottom: 10px;">GENEL KIMLIK BILGILERI</h3>
                <table style="width: 100%; font-size: 14px; margin-bottom: 20px;">
                    <tr><td style="width: 120px; font-weight: bold; color: #7F8C8D;">Protokol No:</td><td>{details.get('protocol_no', '-')}</td></tr>
                    <tr><td style="font-weight: bold; color: #7F8C8D;">Hasta Adi:</td><td style="font-weight: bold; color: #27AE60;">{patient_name}</td></tr>
                    <tr><td style="font-weight: bold; color: #7F8C8D;">Yas / Cinsiyet:</td><td>{details.get('age', '-')} / {details.get('gender', '-')}</td></tr>
                    <tr><td style="font-weight: bold; color: #7F8C8D;">Iletisim:</td><td>{details.get('contact_phone', '-')}</td></tr>
                </table>
                <h3 style="color: #E67E22; border-bottom: 2px solid #BDC3C7; padding-bottom: 5px; margin-bottom: 10px;">KLINIK DURUM VE TANI</h3>
                <table style="width: 100%; font-size: 14px; margin-bottom: 20px;">
                    <tr><td style="width: 120px; font-weight: bold; color: #7F8C8D;">Tani Grubu:</td><td><b>{details.get('diagnosis', '-')}</b></td></tr>
                    <tr><td style="font-weight: bold; color: #7F8C8D;">Baskin Taraf:</td><td>{details.get('dominant_side', '-')}</td></tr>
                </table>
                <h3 style="color: #8E44AD; border-bottom: 2px solid #BDC3C7; padding-bottom: 5px; margin-bottom: 10px;">KLINIK OYKU VE NOTLAR</h3>
                <div style="background-color: #F4F6F9; padding: 10px; border-radius: 5px; border-left: 4px solid #8E44AD; font-size: 13px; line-height: 1.5; margin-bottom: 20px;">{history_content}</div>
                <h3 style="color: #16A085; border-bottom: 2px solid #BDC3C7; padding-bottom: 5px; margin-bottom: 10px;">GECMIS KLINIK RAPORLAR VE TESTLER</h3>
                <table style="width: 100%; font-size: 13px; text-align: left; border-collapse: collapse;">
                    <tr style="background-color: #ECF0F1; color: #2C3E50;">
                        <th style="padding: 6px; border-bottom: 2px solid #BDC3C7; width: 130px;">Kayit Tarihi</th>
                        <th style="padding: 6px; border-bottom: 2px solid #BDC3C7; width: 130px;">Analiz Turu</th>
                        <th style="padding: 6px; border-bottom: 2px solid #BDC3C7;">Dosya Adi</th>
                    </tr>
                    {report_rows_html}
                </table>
            </div>
            """
            self.txt_full_details.setHtml(info_html)
            
    def open_report_from_link(self, url):
        file_path = url.toLocalFile()
        if os.path.exists(file_path):
            try: os.startfile(file_path)
            except Exception as e: print(f"Dosya acma hatasi: {e}")
        else: QMessageBox.warning(self, "Hata", "Dosya fiziksel olarak bulunamadi!")

    def update_preview_1(self):
        hz = self.slider_hz_1.value()
        pulse_us = self.slider_pulse_1.value()
        amp = self.slider_amp_1.value()

        T_ms = 1000.0 / hz if hz > 0 else 20.0
        PW_ms = pulse_us / 1000.0

        t = np.linspace(0, 50, 2000)
        t_mod = t % T_ms

        wave = np.zeros_like(t)
        wave[t_mod < PW_ms] = amp
        wave[(t_mod >= PW_ms) & (t_mod < 2 * PW_ms)] = -amp

        self.curve_stim_1.setData(t, wave)
        
        padding = 1000 if amp < 9000 else 0
        self.plot_stim_1.setYRange(-(amp + padding), (amp + padding))
        self.plot_stim_1.setXRange(0, 50)

    def update_preview_2(self):
        hz = self.slider_hz_2.value()
        pulse_us = self.slider_pulse_2.value()
        amp = self.slider_amp_2.value()

        T_ms = 1000.0 / hz if hz > 0 else 20.0
        PW_ms = pulse_us / 1000.0

        t = np.linspace(0, 50, 2000)
        t_mod = t % T_ms

        wave = np.zeros_like(t)
        wave[t_mod < PW_ms] = amp
        wave[(t_mod >= PW_ms) & (t_mod < 2 * PW_ms)] = -amp

        self.curve_stim_2.setData(t, wave)
        
        padding = 1000 if amp < 9000 else 0
        self.plot_stim_2.setYRange(-(amp + padding), (amp + padding))
        self.plot_stim_2.setXRange(0, 50)

    def toggle_stimulation_1(self):
        if not self.current_patient:
            QMessageBox.warning(self, "Uyari", "Lutfen once bir hasta secin!")
            return
            
        if not self.is_stimulating_1:
            self.is_stimulating_1 = True
            
            self.stim_remaining_1 = self.slider_dur_1.value() * 60 
            self.stim_countdown_timer_1.start(1000) 
            self.update_stim_countdown_1() 
            
            self.curve_stim_1.setPen(pg.mkPen('#E74C3C', width=3)) 
            self.btn_apply_stim_1.setStyleSheet("QPushButton { background-color: #E74C3C; color: #FFFFFF; border-radius: 6px; padding: 10px; font-weight: bold; }")
            self.switch_graph_view(1)
        else:
            self.is_stimulating_1 = False
            self.stim_countdown_timer_1.stop()
            self.curve_stim_1.setPen(pg.mkPen('#2ECC71', width=2))
            self.btn_apply_stim_1.setText("SINYALI BASLAT (K1)")
            self.btn_apply_stim_1.setStyleSheet("QPushButton { background-color: #2ECC71; color: #FFFFFF; border-radius: 6px; padding: 10px; font-weight: bold; }")

    def update_stim_countdown_1(self):
        if self.stim_remaining_1 <= 0:
            self.toggle_stimulation_1() 
            return
        mins, secs = divmod(self.stim_remaining_1, 60)
        self.btn_apply_stim_1.setText(f"DURDUR K1 ({mins:02d}:{secs:02d})")
        self.stim_remaining_1 -= 1

    def toggle_stimulation_2(self):
        if not self.current_patient:
            QMessageBox.warning(self, "Uyari", "Lutfen once bir hasta secin!")
            return
            
        if not self.is_stimulating_2:
            self.is_stimulating_2 = True
            
            self.stim_remaining_2 = self.slider_dur_2.value() * 60
            self.stim_countdown_timer_2.start(1000)
            self.update_stim_countdown_2()
            
            self.curve_stim_2.setPen(pg.mkPen('#E74C3C', width=3))
            self.btn_apply_stim_2.setStyleSheet("QPushButton { background-color: #E74C3C; color: #FFFFFF; border-radius: 6px; padding: 10px; font-weight: bold; }")
            self.switch_graph_view(1)
        else:
            self.is_stimulating_2 = False
            self.stim_countdown_timer_2.stop()
            self.curve_stim_2.setPen(pg.mkPen('#3498DB', width=2))
            self.btn_apply_stim_2.setText("SINYALI BASLAT (K2)")
            self.btn_apply_stim_2.setStyleSheet("QPushButton { background-color: #3498DB; color: #FFFFFF; border-radius: 6px; padding: 10px; font-weight: bold; }")

    def update_stim_countdown_2(self):
        if self.stim_remaining_2 <= 0:
            self.toggle_stimulation_2() 
            return
        mins, secs = divmod(self.stim_remaining_2, 60)
        self.btn_apply_stim_2.setText(f"DURDUR K2 ({mins:02d}:{secs:02d})")
        self.stim_remaining_2 -= 1

    def show_patient_context_menu(self, pos):
        item = self.list_patients.itemAt(pos)
        if item is None: return
        menu = QMenu(self)
        update_action = QAction("Bilgileri Guncelle", self)
        update_action.triggered.connect(lambda: self.open_update_dialog(item.text()))
        menu.addAction(update_action)
        menu.exec(self.list_patients.viewport().mapToGlobal(pos))

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
                    self.db.update_patient_details(patient_name, new_data['age'], new_data['dominant_side'], new_data['doctor'], new_data['phone'])
            except: pass
            with open(history_file, 'w', encoding='utf-8') as f: f.write(new_data['history'])
            self.refresh_patient_list(); self.refresh_db_tab_list()

    def refresh_patient_list(self):
        self.list_patients.clear()
        for patient in self.db.get_all_patients(): self.list_patients.addItem(patient)

    def search_patients(self):
        txt = self.txt_search_patient.text().lower()
        self.list_patients.clear()
        for p in self.db.get_all_patients():
            if txt in p.lower(): self.list_patients.addItem(p)

    def select_patient(self, item):
        self.current_patient = item.text()
        self.lbl_current_patient.setText(f"Hasta: {self.current_patient}")
        details = self.db.get_patient_details(self.current_patient)
        if details:
            self.text_patient_details.setText(f"Protokol: {details.get('protocol_no','-')} | Yas: {details.get('age','-')}")
        history_file = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", self.current_patient, "oyku.txt")
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f: self.txt_patient_history.setText(f.read())
        else: self.txt_patient_history.setText("Kayitli bir oyku bulunmuyor.")
        self.btn_delete_patient.setEnabled(True); self.update_patient_records()

    def add_new_patient(self):
        name = self.txt_new_patient_name.text().strip()
        protocol = self.txt_protocol.text().strip()
        if not name or not protocol: QMessageBox.warning(self, "Uyari", "Gerekli alanlari doldurun!"); return
        if self.db.add_patient_with_details(protocol, name, self.spin_age.value(), self.combo_gender.currentText(), self.combo_dominant_side.currentText(), self.spin_onset_year.value(), self.combo_diagnosis.currentText(), self.txt_doctor_name.text().strip(), self.txt_phone.text().strip()):
            p_folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", name)
            os.makedirs(os.path.join(p_folder, "VeriSeti_Tremor"), exist_ok=True)
            os.makedirs(os.path.join(p_folder, "VeriSeti_Bradikinezi"), exist_ok=True)
            with open(os.path.join(p_folder, "oyku.txt"), 'w', encoding='utf-8') as f: f.write(self.txt_new_history.toPlainText())
            self.clear_patient_form(); self.refresh_patient_list(); self.refresh_db_tab_list()
        else: QMessageBox.warning(self, "Hata", "Kayit mevcut!")

    def delete_patient_action(self):
        if not self.current_patient: return
        if QMessageBox.question(self, 'Onay', "Hastayi silmek istediginize emin misiniz?") == QMessageBox.StandardButton.Yes:
            try:
                self.db.delete_patient(self.current_patient)
                shutil.rmtree(os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", self.current_patient), ignore_errors=True)
                self.current_patient = None
                self.refresh_patient_list(); self.refresh_db_tab_list()
            except: pass

    def clear_patient_form(self):
        self.txt_protocol.clear(); self.txt_new_patient_name.clear()
        self.txt_new_history.clear(); self.txt_doctor_name.clear(); self.txt_phone.clear()

    def update_patient_records(self):
        if not self.current_patient: return
        p_folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", self.current_patient)
        self.list_tremor.clear(); self.list_bradi.clear()
        if os.path.exists(os.path.join(p_folder, "VeriSeti_Tremor")): self.list_tremor.addItems([f for f in os.listdir(os.path.join(p_folder, "VeriSeti_Tremor")) if f.endswith(('.pdf', '.csv'))])
        if os.path.exists(os.path.join(p_folder, "VeriSeti_Bradikinezi")): self.list_bradi.addItems([f for f in os.listdir(os.path.join(p_folder, "VeriSeti_Bradikinezi")) if f.endswith(('.pdf', '.csv'))])

    def toggle_recording(self):
        if not self.current_patient: 
            QMessageBox.warning(self, "Uyari", "Hasta secin!")
            return
        
        if not self.is_recording:
            self.is_recording = True
            self.recording_data = []
            self.btn_record.setText("KAYDI BITIR VE ANALIZ ET")
            
            self.current_mode = "Tremor" if "Tremor" in self.combo_mode.currentText() else "Bradikinezi"
            folder = os.path.join(self.workspace_root, "VeriSeti_Genel", "Hastalar", self.current_patient, f"VeriSeti_{self.current_mode}")
            os.makedirs(folder, exist_ok=True)
            self.current_filename = os.path.join(folder, f"{self.current_patient}_{self.current_mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        else:
            self.is_recording = False
            self.btn_record.setText("KAYDI BASLAT")
            self.save_data_to_csv()
            self.run_analysis()
            self.update_patient_records()

    def save_data_to_csv(self):
        if not self.recording_data: return
        with open(self.current_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            headers = []
            for i in range(12): headers.extend([f"IMU{i+1}_AccX", f"IMU{i+1}_AccY", f"IMU{i+1}_AccZ", f"IMU{i+1}_GyroX", f"IMU{i+1}_GyroY", f"IMU{i+1}_GyroZ"])
            writer.writerow(headers)
            writer.writerows(self.recording_data)
        try: self.db.add_test(self.current_patient, self.current_mode, self.current_filename, 0.0, 0.0, "")
        except: pass

    def update_plot(self, data):
        if len(data) >= 73:
            battery_pct = int(data[72])
            self.prog_battery.setValue(battery_pct)

            if self.is_recording:
                self.recording_data.append(data[:72])

            for i in range(12):
                base_idx = i * 6
                self.multi_data_buffer[i]['ax'].append(data[base_idx+0] / 16384.0)
                self.multi_data_buffer[i]['ay'].append(data[base_idx+1] / 16384.0)
                self.multi_data_buffer[i]['az'].append(data[base_idx+2] / 16384.0)
                self.multi_data_buffer[i]['gx'].append(data[base_idx+3] / 131.0)
                self.multi_data_buffer[i]['gy'].append(data[base_idx+4] / 131.0)
                self.multi_data_buffer[i]['gz'].append(data[base_idx+5] / 131.0)

                for key in ['ax', 'ay', 'az', 'gx', 'gy', 'gz']:
                    if len(self.multi_data_buffer[i][key]) > self.buffer_size:
                        self.multi_data_buffer[i][key].pop(0)
                        
            if self.sensor_stack.currentIndex() == 0:
                self.plot_counter += 1
                if self.plot_counter % 20 == 0: 
                    for i in range(12):
                        if len(self.multi_data_buffer[i]['ax']) > 0:
                            current_x = self.multi_data_buffer[i]['ax'][-1]
                            self.imu_buttons[i].setText(f"IMU {i+1}\n\nAktif: {current_x:.2f} G")

            elif self.sensor_stack.currentIndex() == 1:
                self.plot_counter += 1
                if self.plot_counter % 5 == 0:
                    idx = self.active_detailed_imu
                    self.curve_ax.setData(self.multi_data_buffer[idx]['ax'])
                    self.curve_ay.setData(self.multi_data_buffer[idx]['ay'])
                    self.curve_az.setData(self.multi_data_buffer[idx]['az'])
                    self.curve_gx.setData(self.multi_data_buffer[idx]['gx'])
                    self.curve_gy.setData(self.multi_data_buffer[idx]['gy'])
                    self.curve_gz.setData(self.multi_data_buffer[idx]['gz'])

    def toggle_connection(self):
        if self.worker is None:
            port = self.combo_ports.currentText()
            if not port: return
            self.worker = SerialWorker(port); self.worker.data_received.connect(self.update_plot); self.worker.start()
            self.btn_connect.setText("BAGLANTIYI KES"); self.btn_record.setEnabled(True)
        else:
            self.worker.stop(); self.worker = None
            self.btn_connect.setText("CIHAZA BAGLAN"); self.btn_record.setEnabled(False)
            for btn in self.imu_buttons: btn.setText(btn.text().split("\n")[0] + "\n\nDurum: Bekliyor...")

    def refresh_ports(self):
        self.combo_ports.clear()
        for p in serial.tools.list_ports.comports(): self.combo_ports.addItem(p.device)

    def run_analysis(self):
        if not getattr(self, 'current_filename', '') or not os.path.exists(self.current_filename): return
        try:
            QApplication.processEvents() 
            if self.current_mode == "Tremor":
                import analyze_tremor
                analyze_tremor.run_analysis(self.current_filename)
            else:
                import analyze_bradykinesia
                analyze_bradykinesia.run_analysis(self.current_filename)
            QApplication.processEvents()
            QMessageBox.information(self, "Basarili", "Analiz tamamlandi.")
        except Exception as e: QMessageBox.critical(self, "Hata", f"Hata: {e}")

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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ParkinsonGUI()
    window.show()
    sys.exit(app.exec())