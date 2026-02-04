import sys
import os
import time
import csv
import serial
import serial.tools.list_ports
import numpy as np
from datetime import datetime

# Arayüz Kütüphaneleri
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QComboBox, 
                             QMessageBox, QFrame, QSizePolicy)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QColor, QIcon

# Grafik Kütüphanesi
import pyqtgraph as pg

# Analiz modüllerini çağırıyoruz
try:
    import analyze_tremor
    import analyze_bradykinesia
except ImportError:
    print("Uyarı: Analiz modülleri bulunamadı, sadece canlı izleme çalışacak.")

# ----------------------------------------
# 1. ARKA PLAN İŞÇİSİ (Aynı kaldı)
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
                            # Dönüşümler (Önceki kodun aynısı)
                            ax = raw_data[0] / 16384.0
                            ay = raw_data[1] / 16384.0
                            az = raw_data[2] / 16384.0
                            gx = raw_data[3] / 131.0
                            gy = raw_data[4] / 131.0
                            gz = raw_data[5] / 131.0
                            self.data_received.emit([ax, ay, az, gx, gy, gz])
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
# 2. ANA PENCERE (Tasarım Burada Değişti)
# ----------------------------------------
class ParkinsonGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Parkinson Analiz v3.0") # İsim havalı olsun :)
        self.resize(1280, 850)
        
        # --- MODERN STİL DOSYASI (QSS) ---
        # Burası arayüzün CSS makyajıdır.
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e; /* Çok koyu lacivert/gri */
            }
            QLabel {
                color: #cdd6f4;
                font-size: 14px;
                font-family: 'Segoe UI', sans-serif;
            }
            QComboBox {
                background-color: #313244;
                color: white;
                border: 1px solid #45475a;
                border-radius: 5px;
                padding: 5px;
            }
            QComboBox::drop-down {
                border: 0px;
            }
            /* KART TASARIMI */
            QFrame#ControlPanel {
                background-color: #181825;
                border-radius: 15px;
                border: 1px solid #313244;
            }
            /* HEADER TASARIMI */
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
        """)

        # Değişkenler
        self.worker = None
        self.recording_data = [] 
        self.is_recording = False
        self.current_filename = ""
        self.data_buffer = {
            'ax': [], 'ay': [], 'az': [],
            'gx': [], 'gy': [], 'gz': []
        }
        self.buffer_size = 300 

        self.init_ui()

    def init_ui(self):
        # Ana Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0) # Kenar boşluklarını sıfırla
        main_layout.setSpacing(0)

        # --- 1. HEADER (ÜST ÇUBUK) ---
        header_frame = QFrame()
        header_frame.setObjectName("Header") # CSS'de yakalamak için ID verdik
        header_frame.setFixedHeight(60)
        header_layout = QHBoxLayout(header_frame)
        
        title_label = QLabel("🧬 NeuroMotion | Parkinson Analiz Sistemi")
        title_label.setObjectName("HeaderTitle")
        
        self.lbl_status = QLabel("Durum: Bekleniyor...")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_status)
        
        main_layout.addWidget(header_frame)

        # --- 2. İÇERİK ALANI (ORTA) ---
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(20, 20, 20, 20) # İçeriğe boşluk ver
        content_layout.setSpacing(20)

        # --- SOL PANEL (KONTROLLER) ---
        control_frame = QFrame()
        control_frame.setObjectName("ControlPanel")
        control_frame.setFixedWidth(300)
        # Gölge Efekti (Shadow)
        # Not: PyQt'de gölge biraz karmaşıktır, şimdilik renklerle derinlik verdik.
        
        left_layout = QVBoxLayout(control_frame)
        left_layout.setSpacing(15)
        left_layout.setContentsMargins(20, 30, 20, 30)

        # Başlık
        lbl_settings = QLabel("CİHAZ AYARLARI")
        lbl_settings.setStyleSheet("color: #6c7086; font-weight: bold; letter-spacing: 1px;")
        left_layout.addWidget(lbl_settings)

        # Port Seçimi
        self.combo_ports = QComboBox()
        self.refresh_ports()
        left_layout.addWidget(self.combo_ports)

        btn_refresh = self.create_button("Portları Yenile", "#45475a", "#585b70")
        btn_refresh.clicked.connect(self.refresh_ports)
        left_layout.addWidget(btn_refresh)

        # Bağlan Butonu
        self.btn_connect = self.create_button("CİHAZA BAĞLAN", "#a6e3a1", "#94e2d5", text_color="#1e1e2e")
        self.btn_connect.clicked.connect(self.toggle_connection)
        left_layout.addWidget(self.btn_connect)

        left_layout.addSpacing(20)
        
        # Analiz Bölümü Çizgisi
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #45475a;")
        left_layout.addWidget(line)

        lbl_analysis = QLabel("TEST VE ANALİZ")
        lbl_analysis.setStyleSheet("color: #6c7086; font-weight: bold; letter-spacing: 1px;")
        left_layout.addWidget(lbl_analysis)

        # Mod Seçimi
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["1. Tremor (Titreme)", "2. Bradikinezi (Yavaşlık)"])
        left_layout.addWidget(self.combo_mode)

        # Kayıt Butonu
        self.btn_record = self.create_button("KAYDI BAŞLAT", "#e32f2f", "#eba0ac", text_color="#1e1e2e")
        self.btn_record.setEnabled(False)
        self.btn_record.setMinimumHeight(50) # Büyük buton
        self.btn_record.clicked.connect(self.toggle_recording)
        left_layout.addWidget(self.btn_record)

        left_layout.addStretch()
        
        # Logo veya Versiyon
        lbl_ver = QLabel("v3.0.1 Stable")
        lbl_ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ver.setStyleSheet("color: #45475a; font-size: 10px;")
        left_layout.addWidget(lbl_ver)

        # --- SAĞ PANEL (GRAFİKLER) ---
        graph_layout = QVBoxLayout()
        
        # Grafik Stili (PyQtGraph)
        pg.setConfigOption('background', '#181825') # Grafik arka planı
        pg.setConfigOption('foreground', '#cdd6f4') # Yazı rengi
        
        # Grafik 1
        self.plot_acc = pg.PlotWidget(title="İvme (G-Force)")
        self.plot_acc.showGrid(x=True, y=True, alpha=0.3)
        self.customize_plot(self.plot_acc)
        self.curve_ax = self.plot_acc.plot(pen=pg.mkPen('#f38ba8', width=2), name="X") # Kırmızımsı
        self.curve_ay = self.plot_acc.plot(pen=pg.mkPen('#a6e3a1', width=2), name="Y") # Yeşilimsi
        self.curve_az = self.plot_acc.plot(pen=pg.mkPen('#89b4fa', width=2), name="Z") # Mavimsi
        graph_layout.addWidget(self.plot_acc)

        # Grafik 2
        self.plot_gyro = pg.PlotWidget(title="Jiroskop (Açısal Hız)")
        self.plot_gyro.showGrid(x=True, y=True, alpha=0.3)
        self.customize_plot(self.plot_gyro)
        self.curve_gx = self.plot_gyro.plot(pen=pg.mkPen('#fab387', width=2), name="X") # Turuncu
        self.curve_gy = self.plot_gyro.plot(pen=pg.mkPen('#f9e2af', width=2), name="Y") # Sarı
        self.curve_gz = self.plot_gyro.plot(pen=pg.mkPen('#cba6f7', width=2), name="Z") # Mor
        graph_layout.addWidget(self.plot_gyro)

        # Layoutları Birleştir
        content_layout.addWidget(control_frame)
        content_layout.addLayout(graph_layout)
        
        main_layout.addLayout(content_layout)

    # --- YARDIMCI TASARIM FONKSİYONLARI ---
    def create_button(self, text, bg_color, hover_color, text_color="white"):
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Buton Stili (QSS)
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
                padding-top: 12px; /* Basma efekti */
            }}
            QPushButton:disabled {{
                background-color: #313244;
                color: #585b70;
            }}
        """)
        return btn

    def customize_plot(self, plot_widget):
        plot_widget.getAxis('left').setPen('#6c7086')
        plot_widget.getAxis('bottom').setPen('#6c7086')
        plot_widget.addLegend(offset=(10, 10))
        plot_widget.setStyleSheet("border: 1px solid #313244; border-radius: 10px;")

    # ----------------------------------------
    # MANTIK FONKSİYONLARI (ESKİSİ İLE AYNI)
    # ----------------------------------------
    def refresh_ports(self):
        self.combo_ports.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.combo_ports.addItem(port.device)

    def toggle_connection(self):
        if self.worker is None:
            port = self.combo_ports.currentText()
            if not port: return
            self.worker = SerialWorker(port)
            self.worker.data_received.connect(self.update_plot)
            self.worker.start()
            
            # Tasarım Güncellemesi
            self.btn_connect.setText("BAĞLANTIYI KES")
            self.btn_connect.setStyleSheet(self.btn_connect.styleSheet().replace("#a6e3a1", "#fab387")) # Turuncuya dön
            self.btn_record.setEnabled(True)
            self.lbl_status.setText(f"BAĞLANDI: {port}")
            self.lbl_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        else:
            self.worker.stop()
            self.worker = None
            self.btn_connect.setText("CİHAZA BAĞLAN")
            self.btn_connect.setStyleSheet(self.btn_connect.styleSheet().replace("#fab387", "#a6e3a1")) # Yeşile dön
            self.btn_record.setEnabled(False)
            self.lbl_status.setText("BAĞLANTI KESİLDİ")
            self.lbl_status.setStyleSheet("color: #f38ba8; font-weight: bold;")

    def toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            self.recording_data = []
            
            self.btn_record.setText("KAYDI BİTİR VE ANALİZ ET")
            self.btn_record.setStyleSheet(self.btn_record.styleSheet().replace("#f38ba8", "#eba0ac")) # Rengi aç
            
            target_folder = r"D:\cihaz\VeriSeti_Genel"
            if self.combo_mode.currentIndex() == 0:
                target_folder = r"D:\cihaz\VeriSeti_Tremor"
            elif self.combo_mode.currentIndex() == 1:
                target_folder = r"D:\cihaz\VeriSeti_Bradikinezi"

            if not os.path.exists(target_folder):
                os.makedirs(target_folder)
            
            mode_text = "tremor" if self.combo_mode.currentIndex() == 0 else "bradi"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{mode_text}_{timestamp}.csv"
            self.current_filename = os.path.join(target_folder, filename)
            
            self.lbl_status.setText(f"KAYIT YAPILIYOR... {filename}")
            self.lbl_status.setStyleSheet("color: #f38ba8; font-weight: bold; blink;") # Kırmızı
            
        else:
            self.is_recording = False
            self.save_data_to_csv()
            self.btn_record.setText("KAYDI BAŞLAT")
            self.btn_record.setStyleSheet(self.btn_record.styleSheet().replace("#eba0ac", "#f38ba8"))
            self.run_analysis()

    def update_plot(self, data):
        # Buffer işlemleri
        self.data_buffer['ax'].append(data[0])
        self.data_buffer['ay'].append(data[1])
        self.data_buffer['az'].append(data[2])
        self.data_buffer['gx'].append(data[3])
        self.data_buffer['gy'].append(data[4])
        self.data_buffer['gz'].append(data[5])

        for key in self.data_buffer:
            if len(self.data_buffer[key]) > self.buffer_size:
                self.data_buffer[key].pop(0)

        # Çizim
        self.curve_ax.setData(self.data_buffer['ax'])
        self.curve_ay.setData(self.data_buffer['ay'])
        self.curve_az.setData(self.data_buffer['az'])
        self.curve_gx.setData(self.data_buffer['gx'])
        self.curve_gy.setData(self.data_buffer['gy'])
        self.curve_gz.setData(self.data_buffer['gz'])

        if self.is_recording:
            self.recording_data.append(data)

    def save_data_to_csv(self):
        if not self.recording_data: return
        with open(self.current_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ"])
            writer.writerows(self.recording_data)
        self.lbl_status.setText("DOSYA KAYDEDİLDİ.")

    def run_analysis(self):
        self.lbl_status.setText("ANALİZ YAPILIYOR...")
        QApplication.processEvents()
        try:
            if self.combo_mode.currentIndex() == 0:
                analyze_tremor.run_analysis(self.current_filename)
                msg = "Tremor Analizi Tamamlandı!"
            else:
                analyze_bradykinesia.run_analysis(self.current_filename)
                msg = "Bradikinezi Analizi Tamamlandı!"
            
            QMessageBox.information(self, "İşlem Başarılı", f"{msg}\nRapor klasöre kaydedildi.")
            self.lbl_status.setText("HAZIR")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Analiz hatası: {str(e)}")
            self.lbl_status.setText("HATA OLUŞTU")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ParkinsonGUI()
    window.show()
    sys.exit(app.exec())