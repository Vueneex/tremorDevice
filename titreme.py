# DOSYA ADI: tremor.py
# (Bunu çalıştıracaksınız)

import serial
import time
import csv
import os
import datetime
import sys
# Yanındaki 'analiz_modulu.py' dosyasını buraya çağırıyoruz
import analyze_tremor

# --- AYARLAR ---
SERIAL_PORT = 'COM7'  # ARDUINO PORTU
BAUD_RATE = 115200
DATA_FOLDER = "VeriSeti"

if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)

def kayit_ve_analiz_yap():
    print(f"{'='*50}")
    print(f"📡 BAĞLANTI KURULUYOR: {SERIAL_PORT}")
    print(f"{'='*50}")

    ser = None
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2) 
        
        # Dosya adı
        zaman_damgasi = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dosya_adi = f"kayit_{zaman_damgasi}.csv"
        tam_yol = os.path.join(DATA_FOLDER, dosya_adi)

        print("\n🚀 KAYIT BAŞLADI! (Durdurmak için klavyeden 'Ctrl + C' basın)")
        print(f"📂 Veriler şuraya yazılıyor: {dosya_adi}\n")

        with open(tam_yol, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ"])
            
            veri_sayisi = 0
            start_time = time.time()
            
            while True: # Sonsuz döngü (Ctrl+C gelene kadar)
                if ser.in_waiting > 0:
                    try:
                        line = ser.readline().decode('utf-8', errors='ignore').strip()
                        if line:
                            parts = line.split(',')
                            if len(parts) == 6:
                                writer.writerow(parts)
                                veri_sayisi += 1
                                if veri_sayisi % 100 == 0:
                                    print(".", end="", flush=True)
                    except:
                        pass

    except KeyboardInterrupt:
        # Ctrl+C basılınca buraya düşer
        gecen_sure = time.time() - start_time
        print(f"\n\n🛑 KAYIT DURDURULDU (Kullanıcı İsteği).")
        print(f"⏱️ Süre: {gecen_sure:.1f} saniye")
        print(f"📊 Toplam Veri: {veri_sayisi} satır")
        
        if ser and ser.is_open:
            ser.close()
            
        # --- OTOMATİK ANALİZ BAŞLIYOR ---
        if veri_sayisi > 100:
            print("\n⚙️ OTOMATİK ANALİZ BAŞLATILIYOR...")
            # Burada 'analiz_modulu' dosyasındaki fonksiyonu çalıştırıyoruz
            analyze_tremor.analyze_final_report(tam_yol)
        else:
            print("❌ Analiz için yeterli veri yok.")

    except serial.SerialException:
        print(f"\n❌ HATA: {SERIAL_PORT} portu bulunamadı.")
    except Exception as e:
        print(f"\n❌ BEKLENMEYEN HATA: {e}")

if __name__ == "__main__":
    kayit_ve_analiz_yap()