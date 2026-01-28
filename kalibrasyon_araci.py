# DOSYA ADI: kalibrasyon_araci.py
import serial
import time
import numpy as np
import os

# --- AYARLAR ---
SERIAL_PORT = 'COM10'   # Portunu kontrol et
BAUD_RATE = 115200
ORNEK_SAYISI = 500     # Ne kadar çok o kadar hassas (500 veri yaklaşık 10 saniye sürer)

def kalibrasyon_baslat():
    print("\n" + "="*50)
    print("   SENSÖR KALİBRASYON SİSTEMİ")
    print("="*50)
    print("⚠️  ÖNEMLİ: Cihazı düz bir zemine koyun.")
    print("⚠️  Sensör çipi yukarı baksın (Z ekseni yukarı).")
    print("⚠️  İşlem boyunca masayı ASLA sallamayın.")
    print("-" * 50)
    input("Hazır olduğunda ENTER tuşuna bas...")

    print("\n📡 Bağlantı kuruluyor...")
    
    ser = None
    data_buffer = []

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2) # Arduino reset beklemesi
        
        print(f"⏳ Veri toplanıyor... Lütfen bekleyin ({ORNEK_SAYISI} örnek)")

        while len(data_buffer) < ORNEK_SAYISI:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    parts = line.split(',')
                    if len(parts) == 6:
                        # Hepsini integer'a çevir
                        vals = [int(p) for p in parts]
                        data_buffer.append(vals)
                        
                        if len(data_buffer) % 50 == 0:
                            print(f"-> %{int(len(data_buffer)/ORNEK_SAYISI*100)} tamamlandı")
                except:
                    pass
        
        # --- HESAPLAMA KISMI ---
        data = np.array(data_buffer)
        
        # Sütunlar: 0:AccX, 1:AccY, 2:AccZ, 3:GyroX, 4:GyroY, 5:GyroZ
        
        # JİROSKOP: Dururken hepsi 0 olmalı. Ortalaması hatadır.
        bias_gx = np.mean(data[:, 3])
        bias_gy = np.mean(data[:, 4])
        bias_gz = np.mean(data[:, 5])

        # İVMEÖLÇER: Düz dururken X ve Y 0, Z ise 16384 (1g) olmalı.
        bias_ax = np.mean(data[:, 0])           # Hedef 0
        bias_ay = np.mean(data[:, 1])           # Hedef 0
        bias_az = np.mean(data[:, 2]) - 16384.0 # Hedef 16384

        print("\n✅ KALİBRASYON TAMAMLANDI!")
        print(f"Jiroskop Hataları (X, Y, Z): {bias_gx:.2f}, {bias_gy:.2f}, {bias_gz:.2f}")
        print(f"İvmeölçer Hataları (X, Y, Z): {bias_ax:.2f}, {bias_ay:.2f}, {bias_az:.2f}")

        # --- DOSYAYA KAYDETME ---
        dosya_icerigi = f"""# OTOMATIK OLUSTURULAN KALIBRASYON DOSYASI
# Olusturulma Tarihi: {time.strftime("%Y-%m-%d %H:%M:%S")}

# Jiroskop Sapma Degerleri (Bias)
OFFSET_GX = {bias_gx:.4f}
OFFSET_GY = {bias_gy:.4f}
OFFSET_GZ = {bias_gz:.4f}

# Ivmeolcer Sapma Degerleri (Bias)
OFFSET_AX = {bias_ax:.4f}
OFFSET_AY = {bias_ay:.4f}
OFFSET_AZ = {bias_az:.4f}
"""
        
        with open("kalibrasyon_verisi.py", "w") as f:
            f.write(dosya_icerigi)
            
        print("\n💾 'kalibrasyon_verisi.py' dosyası kaydedildi.")
        print("Artık analiz kodları bu dosyayı otomatik okuyacak.")

    except Exception as e:
        print(f"\n❌ HATA: {e}")
    finally:
        if ser and ser.is_open: ser.close()

if __name__ == "__main__":
    kalibrasyon_baslat()