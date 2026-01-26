# DOSYA ADI: analyze_bradykinesia.py
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy.signal import butter, filtfilt, find_peaks
from matplotlib.backends.backend_pdf import PdfPages
import os
import datetime
import traceback

FS = 100.0

def run_analysis(file_path):
    print(f"\n{'='*60}")
    print(f"🐢 BREDIKINEZI (YAVAŞLIK) ANALİZİ BAŞLATILDI: {os.path.basename(file_path)}")
    print(f"{'='*60}")

    try:
        try: df = pd.read_csv(file_path, on_bad_lines='skip')
        except: df = pd.read_csv(file_path, error_bad_lines=False)

        cols = ["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ"]
        if len(df.columns) >= 6: df.columns = cols[:len(df.columns)]
        for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.dropna().reset_index(drop=True)

        if len(df) < 50:
            print("❌ HATA: Kayıt çok kısa.")
            return

        # Zaman
        dosya_zamani = os.path.getctime(file_path)
        baslangic_zamani = datetime.datetime.fromtimestamp(dosya_zamani)
        t_seconds = np.arange(len(df)) / FS

        # Bredikinezi için en önemli veri JİROSKOP (Dönme) verisidir.
        # Çünkü parmak vuruşu veya el çevirme hareketlerini en iyi bu görür.
        gyro_mag = np.sqrt(df['GyroX']**2 + df['GyroY']**2 + df['GyroZ']**2) / 131.0 # Derece/Saniye

        # Low Pass Filtre (Titreşimleri sil, sadece ana hareketi gör)
        b, a = butter(4, 5.0 / (0.5 * FS), btype='low')
        movement_sig = filtfilt(b, a, gyro_mag)

        # Hareketin Tepelerini Bul (Her el açıp kapama bir tepedir)
        peaks, _ = find_peaks(movement_sig, height=30, distance=20) # Min 30 derece/sn hız
        
        # Analiz Metrikleri
        hareket_sayisi = len(peaks)
        ortalama_hiz = np.mean(movement_sig[peaks]) if len(peaks) > 0 else 0
        
        # Genlik Düşüşü (Decrement) Hesabı
        decrement_text = "Stabil"
        decrement_color = "#27ae60" # Yeşil
        
        if len(peaks) > 4:
            first_half = np.mean(movement_sig[peaks[:int(len(peaks)/2)]])
            second_half = np.mean(movement_sig[peaks[int(len(peaks)/2):]])
            if second_half < first_half * 0.7:
                decrement_text = "GENLİK DÜŞÜŞÜ (Yorulma)"
                decrement_color = "#e74c3c" # Kırmızı
            elif second_half < first_half * 0.9:
                decrement_text = "HAFİF DÜŞÜŞ"
                decrement_color = "#f39c12" # Turuncu

        print(f"   -> Hareket Sayısı: {hareket_sayisi}")
        print(f"   -> Durum: {decrement_text}")

        # --- PDF RAPOR ---
        report_filename = file_path.replace(".csv", "_BRADY_RAPOR.pdf")
        with PdfPages(report_filename) as pdf:
            fig = plt.figure(figsize=(8.27, 11.69))
            
            # Başlık
            header_ax = fig.add_axes([0.1, 0.85, 0.8, 0.12]) 
            header_ax.axis('off')
            header_ax.add_patch(plt.Rectangle((0, 0), 1, 1, color="#eaeded", transform=header_ax.transAxes, zorder=-1, alpha=0.5))
            header_ax.text(0.05, 0.7, "BREDİKİNEZİ ANALİZİ", transform=header_ax.transAxes, fontsize=24, weight='bold', color="#2c3e50")
            header_ax.text(0.05, 0.4, f"Hareket Hızı ve Süreklilik Testi\nDurum: {decrement_text}", transform=header_ax.transAxes, fontsize=12, color=decrement_color)
            
            # Grafik 1: Hareket Hızı
            ax1 = fig.add_axes([0.1, 0.50, 0.8, 0.30])
            ax1.plot(t_seconds, movement_sig, color='#2980b9', linewidth=1.5, label='Hareket Hızı')
            ax1.plot(t_seconds[peaks], movement_sig[peaks], "x", color='red', label='Hareket Tepe Noktaları')
            ax1.set_ylabel("Hız (°/sn)", fontsize=10)
            ax1.set_xlabel("Süre (sn)", fontsize=10)
            ax1.set_title("TEKRARLAYAN HAREKET ANALİZİ (Jiroskop)", fontsize=12, weight='bold')
            ax1.legend()
            ax1.grid(True, alpha=0.5)

            # İstatistik Kutusu
            fig.text(0.1, 0.40, f"Toplam Hareket: {hareket_sayisi}", fontsize=12)
            fig.text(0.1, 0.37, f"Ortalama Hız: {ortalama_hiz:.1f} °/sn", fontsize=12)
            
            pdf.savefig(fig)
            plt.close()

        print(f"✅ BRADYKINESIA PDF OLUŞTU: {report_filename}")

    except Exception as e:
        print("\n❌ BRADY ANALİZ HATASI:")
        print(traceback.format_exc())