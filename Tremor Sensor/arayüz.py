import sys
import serial
import serial.tools.list_ports
import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QComboBox, QLabel
from PyQt6.QtCore import QThread, pyqtSignal, QTimer

class SerialWorker(QThread):
    data_received = pyqtSignal(list)
    error_received = pyqtSignal(str)

    def __init__(self, port, baud):
        super().__init__()
        self.port = port
        self.baud = baud
        self.is_running = True
        self.serial_conn = None

    def run(self):
        try:
            self.serial_conn = serial.Serial(self.port, self.baud, timeout=0.1)
            while self.is_running:
                if self.serial_conn.in_waiting:
                    line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    
                    if line.startswith("ERR"):
                        self.error_received.emit("Sensör Bağlantı Hatası!")
                        continue
                    
                    parts = line.split(',')
                    if len(parts) == 7:
                        try:
                            # 6 Eksen + 1 Batarya verisini çevir
                            values = [float(x) for x in parts]
                            self.data_received.emit(values)
                        except ValueError:
                            pass # Bozuk karakter gelirse o anki döngüyü atla
        except Exception as e:
            self.error_received.emit(f"Port Hatası: {str(e)}")

    def stop(self):
        self.is_running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Biyomedikal Sensör Arayüzü")
        self.resize(1000, 600)
        
        # Grafik veri listeleri (100 verilik kuyruk)
        self.data_length = 100
        self.accel_z_data = [0] * self.data_length
        self.worker = None

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Üst Kontrol Paneli
        top_layout = QHBoxLayout()
        self.port_combo = QComboBox()
        self.refresh_ports()
        
        self.btn_connect = QPushButton("BAĞLAN")
        self.btn_connect.clicked.connect(self.toggle_connection)
        
        self.lbl_battery = QLabel("Batarya: %-- | Durum: Bekleniyor")
        self.lbl_battery.setStyleSheet("font-weight: bold; font-size: 14px; color: blue;")

        top_layout.addWidget(self.port_combo)
        top_layout.addWidget(self.btn_connect)
        top_layout.addWidget(self.lbl_battery)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # PyQtGraph Çizim Alanı (Sadece sensör verisi için temiz grafik)
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        self.plot_widget = pg.PlotWidget(title="Gerçek Zamanlı İvme (Z Ekseni)")
        self.plot_widget.setYRange(-30000, 30000)
        self.plot_widget.showGrid(x=True, y=True)
        self.curve = self.plot_widget.plot(pen=pg.mkPen('b', width=2))
        
        main_layout.addWidget(self.plot_widget)

    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.port_combo.addItem(p.device)

    def toggle_connection(self):
        if self.btn_connect.text() == "BAĞLAN":
            port = self.port_combo.currentText()
            if port:
                self.worker = SerialWorker(port, 115200)
                self.worker.data_received.connect(self.update_data)
                self.worker.error_received.connect(self.show_error)
                self.worker.start()
                self.btn_connect.setText("BAĞLANTIYI KES")
                self.lbl_battery.setText("Durum: Bağlandı, Veri Bekleniyor...")
                self.lbl_battery.setStyleSheet("color: green;")
        else:
            if self.worker:
                self.worker.stop()
            self.btn_connect.setText("BAĞLAN")
            self.lbl_battery.setText("Durum: Bağlantı Kesildi")
            self.lbl_battery.setStyleSheet("color: black;")

    def update_data(self, data):
        # data = [Ax, Ay, Az, Gx, Gy, Gz, Battery]
        acc_z = data[2]
        battery = data[6]

        # Çift uçlu kuyruk mantığı: Yeni veriyi sona ekle, baştakini sil
        self.accel_z_data.append(acc_z)
        self.accel_z_data.pop(0)

        # Grafiği güncelle
        self.curve.setData(self.accel_z_data)

        # Batarya bilgisini güncelle
        self.lbl_battery.setText(f"Batarya: %{int(battery)} | Durum: Veri Akıyor")

    def show_error(self, err_msg):
        self.lbl_battery.setText(f"DURUM: {err_msg}")
        self.lbl_battery.setStyleSheet("color: red;")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())