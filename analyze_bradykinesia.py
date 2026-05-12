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
FS = 50.0               
LOW_PASS_CUTOFF = 5.0   
MIN_PEAK_HEIGHT = 15.0  
MIN_PEAK_DIST = 20      

def butter_lowpass_filter(data, cutoff, fs, order=4):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    y = filtfilt(b, a, data)
    return y

def calculate_slope(values):
    if len(values) < 2: return 0
    x = np.arange(len(values))
    slope, _ = np.polyfit(x, values, 1)
    return slope

def calculate_cv(values):
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

def calculate_updrs_bradykinesia(hesitation_count, amp_slope, cv_rhythm, max_amp):
    """MDS-UPDRS 3.6 Puanlama Motoru"""
    if max_amp < 15.0: return 4, "AĞIR (4) - Hareket Yok"
    if hesitation_count >= 3 or amp_slope < -20.0 or cv_rhythm > 40.0:
        return 3, "CİDDİ (3) - Sık Donma/Tükenme"
    if hesitation_count >= 1 or amp_slope < -8.0 or cv_rhythm > 25.0:
        return 2, "ORTA (2) - Belirgin Yorulma/Takılma"
    if amp_slope < -2.0 or cv_rhythm > 15.0:
        return 1, "HAFİF (1) - Ritimde Hafif Bozulma"
    return 0, "NORMAL (0) - Sorunsuz"

def draw_score_bar(ax, label, score, y_pos, color):
    """Yatay skor çubuğu çizer"""
    ax.text(0, y_pos, label, fontsize=12, fontweight='bold', va='center', ha='left')
    # Arka plan çubuğu (Gri)
    ax.add_patch(plt.Rectangle((0.2, y_pos - 0.15), 0.7, 0.3, color='#ecf0f1', alpha=1.0, transform=ax.transAxes))
    # Doluluk çubuğu (Renkli)
    normalized_score = np.clip(score / 100.0, 0, 1.0)
    ax.add_patch(plt.Rectangle((0.2, y_pos - 0.15), 0.7 * normalized_score, 0.3, color=color, alpha=1.0, transform=ax.transAxes))
    # Skor yazısı
    ax.text(0.92, y_pos, f"%{int(score)}", fontsize=12, fontweight='bold', va='center', color=color)

def run_analysis(file_path): 
    print(f"\n{'='*60}")
    print(f"🐢 MDS-UPDRS + PERFORMANS ANALİZİ")
    print(f"{'='*60}")

    try:
        # 1. Veri Okuma
        try: df = pd.read_csv(file_path, on_bad_lines='skip')
        except: df = pd.read_csv(file_path, error_bad_lines=False)

        # --- GELECEĞE HAZIR YAKLAŞIM ---
        # 72 sütunluk (12 IMU) veriyi bozmadan koru, ama şimdilik sadece IMU1'i analize sok.
        if "IMU1_AccX" in df.columns:
            df["AccX"] = df["IMU1_AccX"]
            df["AccY"] = df["IMU1_AccY"]
            df["AccZ"] = df["IMU1_AccZ"]
            df["GyroX"] = df["IMU1_GyroX"]
            df["GyroY"] = df["IMU1_GyroY"]
            df["GyroZ"] = df["IMU1_GyroZ"]
        else:
            # Eğer önceden alınmış sadece 6 sütunlu eski bir test CSV'si gelirse çökmemesi için:
            expected_cols = ["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ"]
            if len(df.columns) >= 6: 
                df.rename(columns=dict(zip(df.columns[:6], expected_cols)), inplace=True)

        # Sadece analiz edilecek ana sütunları sayısal değere çevir ve bozukları at
        for c in ["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ"]: 
            df[c] = pd.to_numeric(df[c], errors='coerce')
            
        df = df.dropna(subset=["AccX", "AccY", "AccZ", "GyroX", "GyroY", "GyroZ"]).reset_index(drop=True)

        # --- KALİBRASYON ---
        if CALIBRATION_EXIST:
            df['AccX'] -= kalibrasyon_verisi.OFFSET_AX
            df['AccY'] -= kalibrasyon_verisi.OFFSET_AY
            df['AccZ'] -= kalibrasyon_verisi.OFFSET_AZ
            df['GyroX'] -= kalibrasyon_verisi.OFFSET_GX
            df['GyroY'] -= kalibrasyon_verisi.OFFSET_GY
            df['GyroZ'] -= kalibrasyon_verisi.OFFSET_GZ

        t_seconds = np.arange(len(df)) / FS

        # Akıllı Eksen Seçimi
        gyro_data = df[['GyroX', 'GyroY', 'GyroZ']].values / 131.0 
        stds = np.std(gyro_data, axis=0)
        main_axis_idx = np.argmax(stds)
        raw_signal = gyro_data[:, main_axis_idx]
        
        smooth_signal = butter_lowpass_filter(raw_signal, LOW_PASS_CUTOFF, FS)
        abs_signal = np.abs(smooth_signal)
        peaks, _ = find_peaks(abs_signal, height=MIN_PEAK_HEIGHT, distance=MIN_PEAK_DIST)
        
        freqs, amps = calculate_fft(smooth_signal, FS)
        max_amp = 0
        if len(amps) > 0:
            max_amp = np.max(amps)

        # Değişkenler
        cv_rhythm = 0
        hesitation_count = 0
        amp_slope = 0
        
        # --- PERFORMANS SKORLARI ---
        score_speed = 0
        score_power = 0
        score_rhythm = 0

        if len(peaks) >= 3:
            peak_times = t_seconds[peaks]
            peak_amplitudes = abs_signal[peaks]
            intervals = np.diff(peak_times)
            mean_interval = np.mean(intervals)
            
            # Algoritmalar
            cv_rhythm = calculate_cv(intervals)
            cv_amp = calculate_cv(peak_amplitudes)
            amp_slope = calculate_slope(peak_amplitudes)
            
            # Takılma (Hassas: 1.5x)
            hesitation_threshold = mean_interval * 1.5
            hesitation_count = np.sum(intervals > hesitation_threshold)

            # --- SKOR HESAPLAMA MANTIĞI ---
            
            # 1. HIZ SKORU: Sıklıktan hesaplanır. 
            # Hedef: 3 Hz ve üzeri 100 puandır.
            duration = t_seconds[-1] - t_seconds[0]
            movement_freq = len(peaks) / duration
            score_speed = min((movement_freq / 2.0) * 100.0, 100.0)

            # 2. GÜÇ SKORU: Genlikten hesaplanır.
            # Hedef: Ortalama genlik 300 derece/sn ise 100 puandır.
            mean_amp_val = np.mean(peak_amplitudes)
            score_power = min((mean_amp_val / 300.0) * 100.0, 100.0)

            # 3. RİTİM SKORU: CV'den hesaplanır.
            # CV ne kadar düşükse o kadar iyi. CV>33 ise puan 0 olur.
            score_rhythm = max(100.0 - (cv_rhythm * 3.0), 0.0)

            # UPDRS
            updrs_score, updrs_desc = calculate_updrs_bradykinesia(hesitation_count, amp_slope, cv_rhythm, max_amp)
            
            color_map = {0: "#27ae60", 1: "#f1c40f", 2: "#e67e22", 3: "#d35400", 4: "#c0392b"}
            status_color = color_map.get(updrs_score, "gray")

            print(f"🔹 Hız: %{score_speed:.0f} | Güç: %{score_power:.0f} | Ritim: %{score_rhythm:.0f}")
            print(f"🔹 UPDRS: {updrs_score}")

        else:
            updrs_score = 4
            updrs_desc = "Hareket Yok"
            status_color = "#c0392b"
        
        # --- PDF RAPOR ---
        report_filename = file_path.replace(".csv", "_FINAL_RAPOR.pdf")
        with PdfPages(report_filename) as pdf:
            fig = plt.figure(figsize=(8.27, 11.69))
            
            # Başlık
            header_ax = fig.add_axes([0, 0.92, 1, 0.08])
            header_ax.axis('off')
            header_ax.add_patch(plt.Rectangle((0, 0), 1, 1, color=status_color, transform=header_ax.transAxes, zorder=-1))
            header_ax.text(0.5, 0.5, f"MDS-UPDRS KLİNİK RAPORU (Skor: {updrs_score})", transform=header_ax.transAxes, fontsize=18, weight='bold', color='white', ha='center', va='center')

            # Grafik 1: Hareket Profili
            ax1 = fig.add_axes([0.1, 0.65, 0.8, 0.20])
            ax1.plot(t_seconds, smooth_signal, color='#34495e', linewidth=1.2)
            if len(peaks) > 1:
                peak_ts = t_seconds[peaks]
                intervals = np.diff(peak_ts)
                threshold = np.mean(intervals) * 1.5
                for i, interval in enumerate(intervals):
                    if interval > threshold:
                        ax1.axvspan(peak_ts[i], peak_ts[i+1], color='#e74c3c', alpha=0.3)
            ax1.set_title("Hareket Profili (Kırmızı: Donma/Takılma)", fontsize=10, fontweight='bold')
            ax1.set_ylabel("Hız (°/sn)")
            ax1.grid(True, linestyle=':', alpha=0.6)

            # Grafik 2: Ritim
            ax2 = fig.add_axes([0.1, 0.40, 0.8, 0.15])
            if len(peaks) > 1:
                x_pos = range(1, len(intervals)+1)
                colors = ['#27ae60' if val < np.mean(intervals)*1.5 else '#c0392b' for val in intervals]
                ax2.bar(x_pos, intervals, color=colors, alpha=0.7)
                ax2.axhline(y=np.mean(intervals), color='gray', linestyle='--')
            ax2.set_title("Ritim Analizi", fontsize=10, fontweight='bold')
            ax2.set_ylabel("Süre (sn)")
            ax2.grid(True, linestyle=':', alpha=0.6)

            # UPDRS Bilgi Kutusu
            info_ax = fig.add_axes([0.1, 0.22, 0.8, 0.12])
            info_ax.axis('off')
            info_text = (
                f"TIBBİ TANI: {updrs_desc}\n"
                f"Takılma Sayısı: {hesitation_count} | Yorulma Eğimi: {amp_slope:.2f}"
            )
            info_ax.text(0.5, 0.5, info_text, ha='center', va='center', fontsize=12, 
                         bbox=dict(facecolor='#f8f9fa', edgecolor=status_color, boxstyle='round,pad=1', linewidth=2))

            # --- YENİ BÖLÜM: PERFORMANS KARNESİ ---
            score_ax = fig.add_axes([0.1, 0.05, 0.8, 0.15]) # Sayfanın en altı
            score_ax.axis('off')
            score_ax.set_title("PERFORMANS SKORLARI", fontsize=12, fontweight='bold', pad=20)
            
            # Skor Çubuklarını Çiz
            draw_score_bar(score_ax, "HIZ SKORU", score_speed, 0.8, "#3498db")   # Mavi
            draw_score_bar(score_ax, "GÜÇ SKORU", score_power, 0.5, "#9b59b6")   # Mor
            draw_score_bar(score_ax, "RİTİM SKORU", score_rhythm, 0.2, "#2ecc71") # Yeşil

            pdf.savefig(fig)
            plt.close()
            print(f"✅ Final Rapor Hazır: {report_filename}")

    except Exception as e:
        print(f"❌ Hata: {e}")
        import traceback
        traceback.print_exc()