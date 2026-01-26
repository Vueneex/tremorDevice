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
                             QMessageBox, QGroupBox)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QColor

# Grafik Kütüphanesi
import pyqtgraph as pg

# Senin Mevcut Analiz Modüllerin (Dosyalar aynı klasörde olmalı)
try:
    import analyze_tremor
    import analyze_bradykinesia
except ImportError:
    print("Uyarı: Analiz modülleri bulunamadı, sadece canlı izleme çalışacak.")

# ----------------------------------------
# 1. ARKA PLAN İŞÇİSİ (THREAD)
# Arayüz donmasın diye USB okuma işini bu arkadaş yapar.
# ----------------------------------------
class SerialWorker(QThread):
    data_received = pyqtSignal(list) # Veriyi ana ekrana fırlatan sinyal

    def __init__(self, port_name, baud_rate=115200):
        super().__init__()
        self.port_name = port_name
        self.baud_rate = baud_rate
        self.is_running = True
        self.serial_conn = None

    def run(self):
        try:
            self.serial_conn = serial.Serial(self.port_name, self.baud_rate, timeout=1)
            print(f"Bağlandı: {self.port_name}")
            
            while self.is_running:
                if self.serial_conn.in_waiting:
                    try:
                        line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                        parts = line.split(',')
                        
                        if len(parts) == 6:
                            # Önce ham veriyi alıyoruz
                            raw_data = [float(x) for x in parts]
                            
                            # --- DÖNÜŞÜM (RAW -> REAL) ---
                            # MPU9250 Standart Ayarlarına Göre:
                            # İvme (Acc): 1g = 16384 birim
                            # Gyro: 1 derece/sn = 131 birim
                            
                            ax = raw_data[0] / 16384.0
                            ay = raw_data[1] / 16384.0
                            az = raw_data[2] / 16384.0
                            
                            gx = raw_data[3] / 131.0
                            gy = raw_data[4] / 131.0
                            gz = raw_data[5] / 131.0
                            
                            # Dönüştürülmüş veriyi gönder
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
# 2. ANA PENCERE (GUI)
# ----------------------------------------
class ParkinsonGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Parkinson Hareket Analiz Sistemi v3.0")
        self.resize(1200, 800)
        self.setStyleSheet("background-color: #2b2b2b; color: white;")

        # Değişkenler
        self.worker = None
        self.recording_data = [] # Verileri burada biriktireceğiz
        self.is_recording = False
        self.current_filename = ""

        # Arayüzü Kur
        self.init_ui()

    def init_ui(self):
        # Ana Düzen
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # --- SOL PANEL (KONTROLLER) ---
        control_panel = QGroupBox("Kontrol Paneli")
        control_panel.setFixedWidth(250)
        control_panel.setStyleSheet("QGroupBox { border: 1px solid gray; border-radius: 5px; margin-top: 10px; font-weight: bold; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }")
        left_layout = QVBoxLayout(control_panel)

        # Port Seçimi
        left_layout.addWidget(QLabel("Port Seçimi:"))
        self.combo_ports = QComboBox()
        self.refresh_ports()
        left_layout.addWidget(self.combo_ports)

        btn_refresh = QPushButton("Portları Yenile")
        btn_refresh.clicked.connect(self.refresh_ports)
        left_layout.addWidget(btn_refresh)

        # Bağlan / Kes Butonları
        self.btn_connect = QPushButton("BAĞLAN")
        self.btn_connect.setStyleSheet("background-color: #27ae60; font-weight: bold; padding: 10px;")
        self.btn_connect.clicked.connect(self.toggle_connection)
        left_layout.addWidget(self.btn_connect)

        left_layout.addSpacing(20)

        # Kayıt ve Analiz
        left_layout.addWidget(QLabel("Analiz Modu:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["1 - Tremor (Titreme)", "2 - Bradikinezi (Yavaşlık)"])
        left_layout.addWidget(self.combo_mode)

        self.btn_record = QPushButton("KAYIT BAŞLAT")
        self.btn_record.setStyleSheet("background-color: #c0392b; font-weight: bold; padding: 10px;")
        self.btn_record.setEnabled(False) # Bağlanmadan kayıt yapılamaz
        self.btn_record.clicked.connect(self.toggle_recording)
        left_layout.addWidget(self.btn_record)

        self.lbl_status = QLabel("Durum: Bekleniyor...")
        self.lbl_status.setStyleSheet("color: #f1c40f; font-size: 12px;")
        left_layout.addWidget(self.lbl_status)

        left_layout.addStretch() # Boşluğu alta it
        
        # --- SAĞ PANEL (GRAFİKLER) ---
        graph_layout = QVBoxLayout()
        
        # Grafik 1: İvme (Acc)
        self.plot_acc = pg.PlotWidget(title="İvme (Accelerometer - G)")
        self.plot_acc.showGrid(x=True, y=True)
        self.plot_acc.setLabel('left', 'Acc (g)')
        self.plot_acc.addLegend()
        self.curve_ax = self.plot_acc.plot(pen=pg.mkPen('r', width=2), name="X")
        self.curve_ay = self.plot_acc.plot(pen=pg.mkPen('g', width=2), name="Y")
        self.curve_az = self.plot_acc.plot(pen=pg.mkPen('b', width=2), name="Z")
        graph_layout.addWidget(self.plot_acc)

        # Grafik 2: Jiroskop (Gyro)
        self.plot_gyro = pg.PlotWidget(title="Dönme (Gyroscope - °/s)")
        self.plot_gyro.showGrid(x=True, y=True)
        self.plot_gyro.setLabel('left', 'Gyro (°/s)')
        self.plot_gyro.addLegend()
        self.curve_gx = self.plot_gyro.plot(pen=pg.mkPen('c', width=2), name="X")
        self.curve_gy = self.plot_gyro.plot(pen=pg.mkPen('m', width=2), name="Y")
        self.curve_gz = self.plot_gyro.plot(pen=pg.mkPen('y', width=2), name="Z")
        graph_layout.addWidget(self.plot_gyro)

        # Layoutları yerleştir
        main_layout.addWidget(control_panel)
        main_layout.addLayout(graph_layout)

        # Veri Saklama (Buffer) - Son 200 veriyi grafikte göstermek için
        self.data_buffer = {
            'ax': [], 'ay': [], 'az': [],
            'gx': [], 'gy': [], 'gz': []
        }
        self.buffer_size = 300 # Ekranda kaç nokta görünecek

    def refresh_ports(self):
        self.combo_ports.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.combo_ports.addItem(port.device)

    def toggle_connection(self):
        if self.worker is None:
            # BAĞLAN
            port = self.combo_ports.currentText()
            if not port:
                return
            
            self.worker = SerialWorker(port)
            self.worker.data_received.connect(self.update_plot)
            self.worker.start()
            
            self.btn_connect.setText("KES")
            self.btn_connect.setStyleSheet("background-color: #7f8c8d; font-weight: bold; padding: 10px;")
            self.btn_record.setEnabled(True)
            self.lbl_status.setText(f"Durum: {port} Bağlandı")
        else:
            # BAĞLANTIYI KES
            self.worker.stop()
            self.worker = None
            self.btn_connect.setText("BAĞLAN")
            self.btn_connect.setStyleSheet("background-color: #27ae60; font-weight: bold; padding: 10px;")
            self.btn_record.setEnabled(False)
            self.lbl_status.setText("Durum: Bağlantı Kesildi")

    def toggle_recording(self):
        if not self.is_recording:
            # --- KAYDI BAŞLAT ---
            self.is_recording = True
            self.recording_data = [] # Listeyi temizle
            
            self.btn_record.setText("KAYDI BİTİR VE ANALİZ ET")
            self.btn_record.setStyleSheet("background-color: #e67e22; font-weight: bold; padding: 10px;")
            
            # --- YENİ EKLENEN KISIM: HEDEF KLASÖR ---
            # Kullanıcının istediği özel konum:
            target_folder = r"D:\cihaz\VeriSeti_Tremor"

            # Eğer Bradikinezi seçiliyse karışmaması için ayrı klasör yapalım mı? 
            # (İstersen burayı silebilirsin, hepsini aynı yere atar)
            if self.combo_mode.currentIndex() == 1:
                target_folder = r"D:\cihaz\VeriSeti_Bradikinezi"

            # Klasör yoksa otomatik oluştur
            if not os.path.exists(target_folder):
                os.makedirs(target_folder)
            
            # Dosya adını ve tam yolu oluştur
            mode_text = "tremor" if self.combo_mode.currentIndex() == 0 else "bradi"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{mode_text}_{timestamp}.csv"
            
            # Tam dosya yolu (D:\cihaz\VeriSeti_Tremor\tremor_2025...csv)
            self.current_filename = os.path.join(target_folder, filename)
            # ----------------------------------------

            self.lbl_status.setText(f"Durum: Kaydediliyor... ({filename})")
            
        else:
            # --- KAYDI BİTİR ---
            self.is_recording = False
            self.save_data_to_csv() # Artık D: sürücüsüne kaydedecek
            
            self.btn_record.setText("KAYIT BAŞLAT")
            self.btn_record.setStyleSheet("background-color: #c0392b; font-weight: bold; padding: 10px;")
            
            # Analizi Tetikle
            self.run_analysis()

    def update_plot(self, data):
        # Data: [ax, ay, az, gx, gy, gz]
        
        # 1. Grafikler için Buffer'a ekle
        self.data_buffer['ax'].append(data[0])
        self.data_buffer['ay'].append(data[1])
        self.data_buffer['az'].append(data[2])
        self.data_buffer['gx'].append(data[3])
        self.data_buffer['gy'].append(data[4])
        self.data_buffer['gz'].append(data[5])

        # Buffer taşarsa eskileri sil
        for key in self.data_buffer:
            if len(self.data_buffer[key]) > self.buffer_size:
                self.data_buffer[key].pop(0)

        # 2. Grafikleri Güncelle
        self.curve_ax.setData(self.data_buffer['ax'])
        self.curve_ay.setData(self.data_buffer['ay'])
        self.curve_az.setData(self.data_buffer['az'])
        
        self.curve_gx.setData(self.data_buffer['gx'])
        self.curve_gy.setData(self.data_buffer['gy'])
        self.curve_gz.setData(self.data_buffer['gz'])

        # 3. Eğer Kayıt Modundaysak, veriyi listeye at
        if self.is_recording:
            self.recording_data.append(data)

    def save_data_to_csv(self):
        if not self.recording_data:
            return
        
        # Dosyayı kaydet
        with open(self.current_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ"])
            writer.writerows(self.recording_data)
        
        self.lbl_status.setText(f"Durum: {self.current_filename} kaydedildi.")

    def run_analysis(self):
        self.lbl_status.setText("Durum: Analiz Yapılıyor...")
        QApplication.processEvents() # Arayüzün güncellenmesini sağla

        try:
            if self.combo_mode.currentIndex() == 0:
                # TREMOR ANALİZİ
                analyze_tremor.analyze_final_report(self.current_filename)
                msg = "Tremor Analizi Tamamlandı! Rapor PDF olarak oluşturuldu."
            else:
                # BRADİKİNEZİ ANALİZİ
                analyze_bradykinesia.analyze_bradykinesia_report(self.current_filename)
                msg = "Bradikinezi Analizi Tamamlandı! Rapor PDF olarak oluşturuldu."
            
            QMessageBox.information(self, "Analiz Bitti", msg)
            self.lbl_status.setText("Durum: Hazır")

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Analiz sırasında hata oluştu:\n{str(e)}")

# ----------------------------------------
# 3. UYGULAMAYI BAŞLAT
# ----------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ParkinsonGUI()
    window.show()
    sys.exit(app.exec())