# DOSYA ADI: main_system.py
import serial
import time
import csv
import os
import datetime
import sys

# --- ANALİZ MODÜLLERİNİ İÇERİ ALIYORUZ ---
# (Dosyaların aynı klasörde olduğundan emin olun)
try:
    import analyze_tremor       # Senin eski kodun
    import analyze_bradykinesia # Yeni kodumuz
except ImportError as e:
    print("❌ HATA: Analiz modülleri (analyze_tremor.py veya analyze_bradykinesia.py) bulunamadı!")
    print(f"Detay: {e}")
    sys.exit()

# --- AYARLAR ---
SERIAL_PORT = 'COM6'  # Portunu kontrol et
BAUD_RATE = 115200

def menu():
    print("\n" + "#"*50)
    print("      HAREKET ANALİZ SİSTEMİ (v2.0)")
    print("#"*50)
    print("Lütfen yapılacak testi seçin:")
    print("1️⃣  TREMOR ANALİZİ (Titreme, Parkinson, Frekans)")
    print("2️⃣  BRADİKİNEZİ ANALİZİ (Hareket Yavaşlığı, Tutukluk)")
    print("#"*50)
    
    secim = input("Seçiminiz (1 veya 2): ")
    return secim

def kayit_baslat(mod, klasor_adi):
    if not os.path.exists(klasor_adi):
        os.makedirs(klasor_adi)

    ser = None
    try:
        print(f"\n📡 {SERIAL_PORT} Portuna Bağlanılıyor...")
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        
        zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if mod == "1":
            prefix = "tremor"
            print("\n👋 TEST: TREMOR (Eller sabit veya uzatılmış bekleyin)")
        else:
            prefix = "bradi"
            print("\n🐢 TEST: BRADİKİNEZİ (Bilek çevirme veya parmak vurma yapın)")

        dosya_adi = f"{prefix}_{zaman}.csv"
        tam_yol = os.path.join(klasor_adi, dosya_adi)

        print(f"\n🚀 KAYIT BAŞLADI! (Bitirmek için 'Ctrl + C' basın)")
        print(f"📂 Kayıt Yeri: {dosya_adi}\n")

        with open(tam_yol, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ"])
            
            veri_sayisi = 0
            start_time = time.time()
            
            while True:
                if ser.in_waiting > 0:
                    try:
                        line = ser.readline().decode('utf-8', errors='ignore').strip()
                        parts = line.split(',')
                        if len(parts) == 6:
                            writer.writerow(parts)
                            veri_sayisi += 1
                            if veri_sayisi % 50 == 0:
                                print("•", end="", flush=True)
                    except:
                        pass
                        
    except KeyboardInterrupt:
        print(f"\n\n🛑 KAYIT BİTTİ.")
        if ser: ser.close()
        return tam_yol, veri_sayisi

    except Exception as e:
        print(f"\n❌ HATA: {e}")
        if ser: ser.close()
        return None, 0

if __name__ == "__main__":
    secim = menu()
    
    if secim == "1":
        klasor = "VeriSeti_Tremor"
        dosya, adet = kayit_baslat("1", klasor)
        
        if dosya and adet > 100:
            print("\n⚙️ TREMOR ANALİZİ BAŞLATILIYOR...")
            # Eski modülünü çağırıyoruz
            analyze_tremor.analyze_final_report(dosya) 
            
    elif secim == "2":
        klasor = "VeriSeti_Bradikinezi"
        dosya, adet = kayit_baslat("2", klasor)
        
        if dosya and adet > 50:
            print("\n⚙️ BRADİKİNEZİ ANALİZİ BAŞLATILIYOR...")
            # Yeni modülü çağırıyoruz
            analyze_bradykinesia.analyze_bradykinesia_report(dosya)
            
    else:
        print("❌ Geçersiz seçim! Programdan çıkılıyor.")