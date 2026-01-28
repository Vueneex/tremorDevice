# DOSYA ADI: analyze_bradykinesia.py

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt, find_peaks
from scipy.fft import fft, fftfreq
from matplotlib.backends.backend_pdf import PdfPages
import os
import warnings

# Kalibrasyon Kontrolü
try:
    import kalibrasyon_verisi
    CALIBRATION_EXIST = True
except ImportError:
    CALIBRATION_EXIST = False

# Stil Ayarları
plt.style.use('seaborn-v0_8-whitegrid')
warnings.filterwarnings("ignore")

# --- AYARLAR ---
FS = 50.0               # Örnekleme frekansı
LOW_PASS_CUTOFF = 5.0   # Filtre
MIN_PEAK_HEIGHT = 15.0  # Hız eşiği
MIN_PEAK_DIST = 20      # Minimum pik aralığı

def butter_lowpass_filter(data, cutoff, fs, order=4):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    y = filtfilt(b, a, data)
    return y

def calculate_slope(values):
    """Hareketin zamanla küçülüp küçülmediğini hesaplar (Trend)."""
    if len(values) < 2: return 0
    x = np.arange(len(values))
    slope, _ = np.polyfit(x, values, 1)
    return slope

def calculate_cv(values):
    """
    Değişim Katsayısı (Coefficient of Variation) Hesaplar.
    Sonuç % cinsindendir. Değer ne kadar yüksekse DÜZENSİZLİK o kadar fazladır.
    """
    if len(values) < 2: return 0
    mean_val = np.mean(values)
    if mean_val == 0: return 0
    std_val = np.std(values)
    cv = (std_val / mean_val) * 100.0 
    return cv

def calculate_fft(signal, fs):
    N = len(signal)
    yf = fft(signal - np.mean(signal))
    xf = fftfreq(N, 1 / fs)
    idx = np.where((xf >= 0.1) & (xf <= 12)) 
    freqs = xf[idx]
    amps = 2.0/N * np.abs(yf[idx])
    return freqs, amps

def run_analysis(file_path): # Fonksiyon adını 'run_analysis' olarak sabitledim (main_system ile uyum için)
    print(f"\n{'='*60}")
    print(f"🐢 GELİŞMİŞ BRADİKİNEZİ ANALİZİ (Varyasyon ve Takılma)")
    print(f"{'='*60}")

    try:
        try: df = pd.read_csv(file_path, on_bad_lines='skip')
        except: df = pd.read_csv(file_path, error_bad_lines=False)

        expected_cols = ["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ"]
        if len(df.columns) >= 6: df.columns = expected_cols[:len(df.columns)]
        for c in expected_cols: df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.dropna().reset_index(drop=True)

        if len(df) < 50:
            print("❌ Yetersiz veri.")
            return

        # --- KALİBRASYON UYGULAMA (GÜNCELLEME BURADA) ---
        if CALIBRATION_EXIST:
            # Sadece Gyro verilerini düzeltmek şu an için yeterli ama hepsini yapalım
            df['AccX'] -= kalibrasyon_verisi.OFFSET_AX
            df['AccY'] -= kalibrasyon_verisi.OFFSET_AY
            df['AccZ'] -= kalibrasyon_verisi.OFFSET_AZ
            df['GyroX'] -= kalibrasyon_verisi.OFFSET_GX
            df['GyroY'] -= kalibrasyon_verisi.OFFSET_GY
            df['GyroZ'] -= kalibrasyon_verisi.OFFSET_GZ

        t_seconds = np.arange(len(df)) / FS

        # En aktif Gyro eksenini bul
        # Kalibrasyon sonrası veriler temizlendiği için bu seçim çok daha doğru çalışacak
        gyro_data = df[['GyroX', 'GyroY', 'GyroZ']].values / 131.0 
        stds = np.std(gyro_data, axis=0)
        main_axis_idx = np.argmax(stds)
        raw_signal = gyro_data[:, main_axis_idx]
        
        # Filtreleme
        smooth_signal = butter_lowpass_filter(raw_signal, LOW_PASS_CUTOFF, FS)
        abs_signal = np.abs(smooth_signal)

        # Tepe Noktaları
        peaks, _ = find_peaks(abs_signal, height=MIN_PEAK_HEIGHT, distance=MIN_PEAK_DIST)
        
        # --- GELİŞMİŞ METRİKLER ---
        freqs, amps = calculate_fft(smooth_signal, FS)
        dominant_freq = 0
        max_amp = 0
        if len(amps) > 0:
            peak_idx = np.argmax(amps)
            dominant_freq = freqs[peak_idx]
            max_amp = amps[peak_idx]

        diagnosis_title = "BELİRSİZ"
        color = "#7f8c8d"
        subtitle = "Yeterli döngü yok."
        
        # Değişkenler
        cv_rhythm = 0
        cv_amp = 0
        hesitation_count = 0
        amp_slope = 0

        if len(peaks) >= 3:
            peak_times = t_seconds[peaks]
            peak_amplitudes = abs_signal[peaks]
            
            # 1. Aralıklar (Intervals)
            intervals = np.diff(peak_times)
            mean_interval = np.mean(intervals)
            
            # 2. CV Hesapları (Düzensizlik Puanı)
            cv_rhythm = calculate_cv(intervals)   # Ritim bozukluğu
            cv_amp = calculate_cv(peak_amplitudes) # Genlik dengesizliği
            
            # 3. Trend (Eğim)
            amp_slope = calculate_slope(peak_amplitudes)
            
            # 4. Takılma (Hesitation) Dedektörü
            # Eğer bir aralık, ortalamanın 1.8 katından fazlaysa "Takılma" sayılır.
            hesitation_threshold = mean_interval * 1.8
            hesitation_count = np.sum(intervals > hesitation_threshold)

            print(f"🔹 Hareket Sayısı: {len(peaks)}")
            print(f"🔹 Ritim Düzensizliği (CV): %{cv_rhythm:.1f} (Normal < %10)")
            print(f"🔹 Takılma Sayısı: {hesitation_count}")
            print(f"🔹 Genlik Eğimi: {amp_slope:.2f}")

            # --- TANI MANTIĞI (ÖNCELİK SIRASI) ---
            
            # 1. Öncelik: HAREKET YOK veya ÇOK ZAYIF
            if max_amp < 15:
                diagnosis_title = "HAREKET YOK"
                subtitle = "Belirgin hareket algılanamadı."
                color = "#95a5a6"
            
            # 2. Öncelik: TAKILMA / DONMA (En ciddi belirti)
            elif hesitation_count > 0:
                diagnosis_title = "TAKILMA / DONMA"
                subtitle = f"{hesitation_count} kez belirgin duraksama (Block) tespit edildi."
                color = "#c0392b" # Koyu Kırmızı
            
            # 3. Öncelik: RİTİM BOZUKLUĞU (Düzensiz, kaotik)
            elif cv_rhythm > 25.0:
                diagnosis_title = "ARİTMİK / DÜZENSİZ"
                subtitle = f"Ritim varyasyonu çok yüksek (%{cv_rhythm:.1f}). Hasta ritmi koruyamıyor."
                color = "#d35400" # Turuncu
            
            # 4. Öncelik: YAVAŞLAMA (Ağır Bradikinezi)
            elif dominant_freq < 1.0:
                diagnosis_title = "AĞIR BRADİKİNEZİ"
                subtitle = "Hareketler çok yavaş (1 Hz altı)."
                color = "#e67e22"
            
            # 5. Öncelik: TÜKENME (Sequence Effect)
            elif amp_slope < -2.0:
                diagnosis_title = "TÜKENME (FATIGUE)"
                subtitle = "Hareket genliği zamanla düşüyor (Sequence Effect)."
                color = "#f39c12" # Sarı
                
            # 6. Öncelik: NORMAL
            else:
                diagnosis_title = "NORMAL HAREKET"
                subtitle = f"Ritim düzenli (%{cv_rhythm:.1f}), takılma yok, genlik korunuyor."
                color = "#27ae60" # Yeşil
        
        # --- PDF RAPORLAMA ---
        report_filename = file_path.replace(".csv", "_GELISMIS_RAPOR.pdf")
        with PdfPages(report_filename) as pdf:
            fig = plt.figure(figsize=(8.27, 11.69))
            plt.suptitle(f"KLİNİK HAREKET ANALİZİ\nDosya: {os.path.basename(file_path)}", fontsize=16, weight='bold')
            
            # 1. GRAFİK: Zaman Serisi (Takılmaları Göster)
            ax1 = fig.add_subplot(311)
            ax1.plot(t_seconds, smooth_signal, label='Hız', color='#2980b9', linewidth=1.5)
            # Takılma olan yerleri işaretle
            if len(peaks) > 1:
                intervals = np.diff(t_seconds[peaks])
                threshold = np.mean(intervals) * 1.8
                # Piklerin zamanlarını al
                peak_ts = t_seconds[peaks]
                for i, interval in enumerate(intervals):
                    if interval > threshold:
                        # Takılma bölgesini boya
                        start_x = peak_ts[i]
                        end_x = peak_ts[i+1]
                        ax1.axvspan(start_x, end_x, color='#e74c3c', alpha=0.3, label='Tespit Edilen Takılma' if i==0 else "")
            
            ax1.set_title("1. Hareket Profili (Kırmızı Alanlar: Duraksama/Takılma)", fontsize=12, fontweight='bold')
            ax1.set_ylabel("Hız (°/sn)")
            ax1.legend(loc='upper right')
            ax1.grid(True, linestyle=':', alpha=0.6)

            # 2. GRAFİK: Ritim Kararlılığı (Yeni Grafik)
            ax2 = fig.add_subplot(312)
            if len(peaks) > 1:
                # Aralıkları çubuk olarak çiz
                intervals = np.diff(t_seconds[peaks])
                x_pos = range(1, len(intervals)+1)
                colors = ['#27ae60' if val < np.mean(intervals)*1.5 else '#c0392b' for val in intervals]
                
                ax2.bar(x_pos, intervals, color=colors, alpha=0.7)
                ax2.axhline(y=np.mean(intervals), color='gray', linestyle='--', label='Ortalama Süre')
                ax2.text(1, max(intervals)*0.9 if len(intervals)>0 else 0, f"CV (Düzensizlik): %{cv_rhythm:.1f}", fontweight='bold', bbox=dict(facecolor='white', alpha=0.8))

            ax2.set_title("2. Ritim Analizi (Çubuklar Eşit Olmalı)", fontsize=12, fontweight='bold')
            ax2.set_ylabel("İki Hareket Arası Süre (sn)")
            ax2.set_xlabel("Hareket Sırası")
            ax2.grid(True, linestyle=':', alpha=0.6)

            # 3. GRAFİK: Frekans Spektrumu
            ax3 = fig.add_subplot(313)
            ax3.fill_between(freqs, amps, color='#2c3e50', alpha=0.3)
            ax3.plot(freqs, amps, color='#2c3e50', linewidth=2)
            if len(amps) > 0:
                ax3.scatter([dominant_freq], [max_amp], color='#c0392b', s=60, zorder=5)
                ax3.text(dominant_freq, max_amp, f"  {dominant_freq:.1f} Hz", 
                         color='#c0392b', fontweight='bold', ha='left', va='center')

            ax3.set_title("3. Frekans Spektrumu", fontsize=12, fontweight='bold')
            ax3.set_xlabel("Frekans (Hz)") 
            ax3.set_ylabel("Güç")            
            ax3.set_xlim(0, 10) 
            ax3.grid(True, linestyle='--', alpha=0.7)

            # Tanı Kutusu
            fig.text(0.5, 0.02, f"TANI: {diagnosis_title}\n{subtitle}", ha='center', fontsize=12, 
                     bbox=dict(facecolor='white', edgecolor=color, boxstyle='round,pad=0.5', linewidth=2))

            plt.tight_layout(rect=[0, 0.05, 1, 0.95])
            pdf.savefig(fig)
            plt.close()
            print(f"✅ Gelişmiş Rapor Hazır: {report_filename}")

    except Exception as e:
        print(f"❌ Analiz Hatası: {e}")
        import traceback
        traceback.print_exc()