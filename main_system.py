# DOSYA ADI: main_system.py
import serial
import time
import csv
import os
import datetime
import analyze_tremor       # Titreme modülü
import analyze_bradykinesia # Bredikinezi m1odülü

# --- AYARLAR ---
SERIAL_PORT = 'COM10'   
BAUD_RATE = 115200


TREMOR_FOLDER = r"D:\cihaz\VeriSeti_Tremor"
BRADY_FOLDER = r"D:\cihaz\VeriSeti_Bradikinezi"

# Klasörler yoksa oluştur
if not os.path.exists(TREMOR_FOLDER): os.makedirs(TREMOR_FOLDER)
if not os.path.exists(BRADY_FOLDER): os.makedirs(BRADY_FOLDER)

def baslat():
    print("\n" + "="*40)
    print("   PARKİNSON ANALİZ SİSTEMİ (V2.2 - KLASÖRLÜ)")
    print("="*40)
    print("1. TREMOR (Titreme) Testi")
    print("2. BREDIKINEZI (Yavaşlık) Testi")
    secim = input("Lütfen test türünü seçin (1 veya 2): ")
    
    # SEÇİME GÖRE KLASÖR VE TÜR BELİRLEME
    test_turu = "GENEL"
    hedef_klasor = ""
    
    if secim == "1": 
        test_turu = "TREMOR"
        hedef_klasor = TREMOR_FOLDER
    elif secim == "2": 
        test_turu = "BRADY"
        hedef_klasor = BRADY_FOLDER
    else: 
        print("❌ Geçersiz seçim! Varsayılan olarak TREMOR seçildi.")
        test_turu = "TREMOR"
        hedef_klasor = TREMOR_FOLDER

    print(f"\n📡 BAĞLANTI: {SERIAL_PORT} bekleniyor...")
    
    ser = None
    tam_yol = ""
    veri_sayisi = 0

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2) 
        
        zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dosya_adi = f"{test_turu}_{zaman}.csv"
        
        # Dosyayı ilgili klasöre yönlendiriyoruz
        tam_yol = os.path.join(hedef_klasor, dosya_adi)

        print(f"\n🚀 {test_turu} TESTİ BAŞLADI! (Sınırsız Süre)")
        print(f"📂 Kayıt Yeri: {tam_yol}")
        print("🛑 Bitirmek için klavyeden 'Ctrl + C' tuşlarına basın.")
        print("-" * 40)
        
        with open(tam_yol, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ"])
            
            # --- SONSUZ DÖNGÜ ---
            while True:
                if ser.in_waiting > 0:
                    try:
                        line = ser.readline().decode('utf-8', errors='ignore').strip()
                        parts = line.split(',')
                        if len(parts) == 6:
                            writer.writerow(parts)
                            veri_sayisi += 1
                            if veri_sayisi % 50 == 0: 
                                print(".", end="", flush=True)
                    except: 
                        pass

    except KeyboardInterrupt:
        print(f"\n\n🛑 KULLANICI DURDURDU. ({veri_sayisi} satır alındı)")

    except Exception as e:
        print(f"\n❌ BAĞLANTI HATASI: {e}")

    finally:
        if ser and ser.is_open: ser.close()
        
        # --- ANALİZİ TETİKLE ---
        if veri_sayisi > 50:
            print(f"\n⏳ {test_turu} Analizi Başlatılıyor...")
            try:
                if test_turu == "TREMOR":
                    analyze_tremor.run_analysis(tam_yol)
                elif test_turu == "BRADY":
                    analyze_bradykinesia.run_analysis(tam_yol)
            except Exception as e:
                print(f"❌ Analiz Hatası: {e}")
        else:
            print("\n❌ Yetersiz veri, analiz yapılmadı.")

if __name__ == "__main__":
    baslat()