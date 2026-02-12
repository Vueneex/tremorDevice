# DOSYA ADI: gui_app.py

import sys
import os
import time
import csv
import serial
import serial.tools.list_ports
import numpy as np
from datetime import datetime
import re # Dosya ismindeki yasaklı karakterleri temizlemek için

# Arayüz Kütüphaneleri
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QComboBox, 
                             QMessageBox, QFrame, QCheckBox, QLineEdit, QListWidget) 
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QColor

# Grafik Kütüphanesi
import pyqtgraph as pg

# Analiz Modülleri
try:
    import analyze_tremor
    import analyze_bradykinesia
except ImportError:
    print("Uyarı: Analiz modülleri bulunamadı, sadece canlı izleme çalışacak.")

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
                            
                            ax = raw_data[0] 
                            ay = raw_data[1] 
                            az = raw_data[2] 
                            gx = raw_data[3] 
                            gy = raw_data[4] 
                            gz = raw_data[5] 
                            
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

        self.setWindowTitle("NeuroMotion Analiz v3.2")
        self.resize(1280, 850)
        
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
            /* ORTAK STİL: Hem ComboBox Hem LineEdit Aynı Görünsün */
            QComboBox, QLineEdit {
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
        self.data_buffer = {
            'ax': [], 'ay': [], 'az': [],
            'gx': [], 'gy': [], 'gz': []
        }
        self.buffer_size = 300 

        self.init_ui()
    
    def update_file_lists(self):
        """Klasördeki PDF dosyalarını bulur ve listeye ekler (En yeni en üstte)"""
        self.list_tremor.clear()
        self.list_bradi.clear()
        
        # Klasör Yolları
        folder_tremor = r"D:\cihaz\VeriSeti_Tremor"
        folder_bradi = r"D:\cihaz\VeriSeti_Bradikinezi"

        # Tremor Dosyalarını Yükle
        if os.path.exists(folder_tremor):
            files = [f for f in os.listdir(folder_tremor) if f.endswith('.pdf')]
            # Tarihe göre sırala (En yeni en başa)
            files.sort(key=lambda x: os.path.getmtime(os.path.join(folder_tremor, x)), reverse=True)
            self.list_tremor.addItems(files)

        # Bradikinezi Dosyalarını Yükle
        if os.path.exists(folder_bradi):
            files = [f for f in os.listdir(folder_bradi) if f.endswith('.pdf')]
            files.sort(key=lambda x: os.path.getmtime(os.path.join(folder_bradi, x)), reverse=True)
            self.list_bradi.addItems(files)

    def open_pdf_tremor(self, item):
        """Tremor listesinden tıklanan dosyayı açar"""
        folder = r"D:\cihaz\VeriSeti_Tremor"
        filepath = os.path.join(folder, item.text())
        try:
            os.startfile(filepath) # Windows için dosya açma komutu
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"Dosya açılamadı:\n{e}")

    def open_pdf_bradi(self, item):
        """Bradikinezi listesinden tıklanan dosyayı açar"""
        folder = r"D:\cihaz\VeriSeti_Bradikinezi"
        filepath = os.path.join(folder, item.text())
        try:
            os.startfile(filepath)
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"Dosya açılamadı:\n{e}")

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- HEADER ---
        header_frame = QFrame()
        header_frame.setObjectName("Header")
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

        # --- İÇERİK ---
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(20)

        # --- SOL PANEL ---
        control_frame = QFrame()
        control_frame.setObjectName("ControlPanel")
        control_frame.setFixedWidth(300)
        
        left_layout = QVBoxLayout(control_frame)
        left_layout.setSpacing(15)
        left_layout.setContentsMargins(20, 30, 20, 30)

        # Ayarlar
        lbl_settings = QLabel("CİHAZ AYARLARI")
        lbl_settings.setStyleSheet("color: #6c7086; font-weight: bold; letter-spacing: 1px;")
        left_layout.addWidget(lbl_settings)

        self.combo_ports = QComboBox()
        self.refresh_ports()
        left_layout.addWidget(self.combo_ports)

        btn_refresh = self.create_button("Portları Yenile", "#45475a", "#585b70")
        btn_refresh.clicked.connect(self.refresh_ports)
        left_layout.addWidget(btn_refresh)

        self.btn_connect = self.create_button("CİHAZA BAĞLAN", "#a6e3a1", "#94e2d5", text_color="#1e1e2e")
        self.btn_connect.clicked.connect(self.toggle_connection)
        left_layout.addWidget(self.btn_connect)

        left_layout.addSpacing(20)
        
        # --- ARA ÇİZGİ ---
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #45475a; min-height: 1px;")
        left_layout.addWidget(line)

        # Analiz Başlığı
        lbl_analysis = QLabel("TEST VE ANALİZ")
        lbl_analysis.setStyleSheet("color: #6c7086; font-weight: bold; letter-spacing: 1px;")
        left_layout.addWidget(lbl_analysis)

        # Mod Seçimi
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["1. Tremor (Titreme)", "2. Bradikinezi (Yavaşlık)"])
        left_layout.addWidget(self.combo_mode)

        # --- YENİ EKLENEN KISIM: DOSYA İSMİ GİRİŞİ ---
        # "Tıpkı buton gibi" görünen metin kutusu
        lbl_filename = QLabel("Hasta Adı / Dosya İsmi:")
        lbl_filename.setStyleSheet("font-size: 12px; color: #a6adc8;")
        left_layout.addWidget(lbl_filename)

        self.txt_filename = QLineEdit()
        self.txt_filename.setPlaceholderText("Hasta Adı / Dosya İsmi:") # Silik yazı
        left_layout.addWidget(self.txt_filename)
        # ----------------------------------------------

        # Kayıt Butonu
        self.btn_record = self.create_button("KAYDI BAŞLAT", "#f38ba8", "#eba0ac", text_color="#1e1e2e")
        self.btn_record.setEnabled(False)
        self.btn_record.setMinimumHeight(50)
        self.btn_record.clicked.connect(self.toggle_recording)
        left_layout.addWidget(self.btn_record)

        # PDF Checkbox
        self.chk_create_pdf = QCheckBox("PDF Oluştur")
        self.chk_create_pdf.setChecked(True)
        self.chk_create_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        left_layout.addWidget(self.chk_create_pdf)

        # --- ALT AYRAÇ ÇİZGİSİ ---
        left_layout.addSpacing(5)
        line_bottom = QFrame()
        line_bottom.setFrameShape(QFrame.Shape.HLine)
        line_bottom.setStyleSheet("color: #45475a; min-height: 1px;")
        left_layout.addWidget(line_bottom)

# --- ALT PANEL (Sıkıştırılmış Alan) ---
        # Bu özel kutu sayesinde ana layout'un 15px boşluk kuralını eziyoruz.
        bottom_container = QWidget()
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(5) 
        
        # 2. Tremor Listesi
        lbl_list_tremor = QLabel("📂 Son Tremor Raporları")
        lbl_list_tremor.setStyleSheet("color: #89b4fa; font-size: 11px; font-weight: bold;")
        bottom_layout.addWidget(lbl_list_tremor)

        self.list_tremor = QListWidget()
        self.list_tremor.setFixedHeight(80) # Yüksekliği biraz azalttım, daha kibar dursun
        self.list_tremor.setStyleSheet("""
            QListWidget {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 5px;
                color: #cdd6f4;
                font-size: 10px;
            }
            QListWidget::item:hover { background-color: #45475a; }
        """)
        self.list_tremor.itemDoubleClicked.connect(self.open_pdf_tremor)
        bottom_layout.addWidget(self.list_tremor)

        # 3. Bradikinezi Listesi
        lbl_list_bradi = QLabel("📂 Son Bradikinezi Raporları")
        lbl_list_bradi.setStyleSheet("color: #fab387; font-size: 11px; font-weight: bold; margin-top: 10px;")
        bottom_layout.addWidget(lbl_list_bradi)

        self.list_bradi = QListWidget()
        self.list_bradi.setFixedHeight(80)
        self.list_bradi.setStyleSheet(self.list_tremor.styleSheet())
        self.list_bradi.itemDoubleClicked.connect(self.open_pdf_bradi)
        bottom_layout.addWidget(self.list_bradi)
        
        # Bu özel kutuyu ana panele ekle
        left_layout.addWidget(bottom_container)

        # Program açılınca listeleri doldur
        self.update_file_lists()
        # ---------------------------------------

        left_layout.addStretch()
        
        lbl_ver = QLabel("v3.2.0 Stable")
        lbl_ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ver.setStyleSheet("color: #45475a; font-size: 10px;")
        left_layout.addWidget(lbl_ver)

        # --- SAĞ PANEL ---
        graph_layout = QVBoxLayout()
        pg.setConfigOption('background', '#181825')
        pg.setConfigOption('foreground', '#cdd6f4')
        
        self.plot_acc = pg.PlotWidget(title="İvme (G-Force)")
        self.plot_acc.showGrid(x=True, y=True, alpha=0.3)
        self.customize_plot(self.plot_acc)
        self.curve_ax = self.plot_acc.plot(pen=pg.mkPen('#f38ba8', width=2), name="X")
        self.curve_ay = self.plot_acc.plot(pen=pg.mkPen('#a6e3a1', width=2), name="Y")
        self.curve_az = self.plot_acc.plot(pen=pg.mkPen('#89b4fa', width=2), name="Z")
        graph_layout.addWidget(self.plot_acc)

        self.plot_gyro = pg.PlotWidget(title="Jiroskop (Açısal Hız)")
        self.plot_gyro.showGrid(x=True, y=True, alpha=0.3)
        self.customize_plot(self.plot_gyro)
        self.curve_gx = self.plot_gyro.plot(pen=pg.mkPen('#fab387', width=2), name="X")
        self.curve_gy = self.plot_gyro.plot(pen=pg.mkPen('#f9e2af', width=2), name="Y")
        self.curve_gz = self.plot_gyro.plot(pen=pg.mkPen('#cba6f7', width=2), name="Z")
        graph_layout.addWidget(self.plot_gyro)

        content_layout.addWidget(control_frame)
        content_layout.addLayout(graph_layout)
        
        main_layout.addLayout(content_layout)

    # --- YARDIMCI FONKSİYONLAR ---
    def create_button(self, text, bg_color, hover_color, text_color="white"):
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
        plot_widget.getAxis('left').setPen('#6c7086')
        plot_widget.getAxis('bottom').setPen('#6c7086')
        plot_widget.addLegend(offset=(10, 10))
        plot_widget.setStyleSheet("border: 1px solid #313244; border-radius: 10px;")

    # --- MANTIK ---
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
            
            self.btn_connect.setText("BAĞLANTIYI KES")
            self.btn_connect.setStyleSheet(self.btn_connect.styleSheet().replace("#a6e3a1", "#fab387"))
            self.btn_record.setEnabled(True)
            self.lbl_status.setText(f"BAĞLANDI: {port}")
            self.lbl_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        else:
            self.worker.stop()
            self.worker = None
            self.btn_connect.setText("CİHAZA BAĞLAN")
            self.btn_connect.setStyleSheet(self.btn_connect.styleSheet().replace("#fab387", "#a6e3a1"))
            self.btn_record.setEnabled(False)
            self.lbl_status.setText("BAĞLANTI KESİLDİ")
            self.lbl_status.setStyleSheet("color: #f38ba8; font-weight: bold;")

    def toggle_recording(self):
        if not self.is_recording:
            # --- KAYIT BAŞLIYOR ---
            self.is_recording = True
            self.recording_data = []
            
            self.btn_record.setText("KAYDI BİTİR VE ANALİZ ET")
            self.btn_record.setStyleSheet(self.btn_record.styleSheet().replace("#fbf6f7", "#e71414"))
            
            # Klasör Seçimi
            target_folder = r"D:\cihaz\VeriSeti_Genel"
            if self.combo_mode.currentIndex() == 0:
                target_folder = r"D:\cihaz\VeriSeti_Tremor"
            elif self.combo_mode.currentIndex() == 1:
                target_folder = r"D:\cihaz\VeriSeti_Bradikinezi"

            if not os.path.exists(target_folder):
                os.makedirs(target_folder)
            
            # --- DOSYA İSMİ OLUŞTURMA (BURASI DEĞİŞTİ) ---
            mode_text = "tremor" if self.combo_mode.currentIndex() == 0 else "bradi"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 1. Kullanıcının girdiği ismi al
            user_input = self.txt_filename.text().strip()
            
            # 2. Eğer isim girildiyse temizle (Türkçe karakter ve boşluk sorunu olmasın)
            if user_input:
                # Sadece harf, rakam ve alt çizgiye izin ver, gerisini sil
                clean_name = re.sub(r'[^\w\s-]', '', user_input).replace(" ", "_")
                # Dosya Adı: Ahmet_Yilmaz_tremor_2025...csv
                filename = f"{clean_name}_{mode_text}_{timestamp}.csv"
            else:
                # İsim girilmediyse eski usul devam et
                filename = f"{mode_text}_{timestamp}.csv"
            # -----------------------------------------------
            
            self.current_filename = os.path.join(target_folder, filename)
            
            self.lbl_status.setText(f"KAYIT: {filename}")
            self.lbl_status.setStyleSheet("color: #f38ba8; font-weight: bold; blink;")
            
        else:
            # --- KAYIT BİTİYOR ---
            self.is_recording = False
            self.save_data_to_csv()
            self.btn_record.setText("KAYDI BAŞLAT")
            self.btn_record.setStyleSheet(self.btn_record.styleSheet().replace("#eba0ac", "#f38ba8"))
            
            self.run_analysis()

    def update_plot(self, data):
        self.data_buffer['ax'].append(data[0] / 16384.0)
        self.data_buffer['ay'].append(data[1] / 16384.0)
        self.data_buffer['az'].append(data[2] / 16384.0)
        
        self.data_buffer['gx'].append(data[3] / 131.0)
        self.data_buffer['gy'].append(data[4] / 131.0)
        self.data_buffer['gz'].append(data[5] / 131.0)

        # Buffer taşarsa temizle
        for key in self.data_buffer:
            if len(self.data_buffer[key]) > self.buffer_size:
                self.data_buffer[key].pop(0)

        # Çizim (Grafikler bölünmüş veriyi gösterir)
        self.curve_ax.setData(self.data_buffer['ax'])
        self.curve_ay.setData(self.data_buffer['ay'])
        self.curve_az.setData(self.data_buffer['az'])
        self.curve_gx.setData(self.data_buffer['gx'])
        self.curve_gy.setData(self.data_buffer['gy'])
        self.curve_gz.setData(self.data_buffer['gz'])

        # --- KRİTİK KISIM BURASI ---
        # Kayıt listesine (CSV'ye gidecek olana) HAM veriyi ('data') ekliyoruz.
        # Bölünmüş halini DEĞİL.
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
            create_pdf = self.chk_create_pdf.isChecked()
            pdf_file = ""
            msg = ""

            if self.combo_mode.currentIndex() == 0:
                analyze_tremor.run_analysis(self.current_filename) 
                pdf_file = self.current_filename.replace(".csv", "_TREMOR_KLINIK_RAPOR.pdf")
                msg = "Tremor Analizi Tamamlandı!"
            else:
                analyze_bradykinesia.run_analysis(self.current_filename)
                pdf_file = self.current_filename.replace(".csv", "_FINAL_RAPOR.pdf")
                msg = "Bradikinezi Analizi Tamamlandı!"

            if not create_pdf and os.path.exists(pdf_file):
                os.remove(pdf_file)
                msg += "\n(PDF Raporu kaydedilmedi.)"
            elif create_pdf:
                msg += f"\nDosya: {os.path.basename(pdf_file)}"
            
            QMessageBox.information(self, "İşlem Başarılı", msg)
            self.lbl_status.setText("HAZIR")

            self.update_file_lists()

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Analiz hatası: {str(e)}")
            self.lbl_status.setText("HATA OLUŞTU")

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