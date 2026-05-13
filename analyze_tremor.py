# DOSYA ADI: analyze_tremor.py

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt
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

# Stil Ayarları (Profesyonel Tıbbi Görünüm)
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans']
warnings.filterwarnings("ignore")

# --- AYARLAR ---
FS = 50.0               # Örnekleme Frekansı
TREMOR_BAND = (1.0, 12.0) # Genişletilmiş Tremor Aralığı (Hz)
ACC_SCALE_FACTOR = 16384.0 # LSB to g (Sensör ayarına göre değişebilir, genelde 16384)

# Renk Paleti
COLOR_SIGNAL = "#2c3e50"   # Koyu Lacivert
COLOR_TREMOR = "#c0392b"   # Tıbbi Kırmızı
COLOR_GRID_MAJOR = "#bdc3c7"
COLOR_GRID_MINOR = "#ecf0f1"

def butter_bandpass_filter(data, lowcut, highcut, fs, order=4):
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    y = filtfilt(b, a, data)
    return y

def calculate_fft_dominant(signal, fs):
    """Baskın frekansı ve gücünü bulur."""
    N = len(signal)
    yf = fft(signal)
    xf = fftfreq(N, 1 / fs)
    # Sadece pozitif ve tremor aralığındaki frekanslara bak
    idx = np.where((xf >= TREMOR_BAND[0]) & (xf <= TREMOR_BAND[1]))
    freqs = xf[idx]
    amps = 2.0/N * np.abs(yf[idx])
    
    dominant_freq = 0
    max_amp = 0
    if len(amps) > 0:
        peak_idx = np.argmax(amps)
        dominant_freq = freqs[peak_idx]
        max_amp = amps[peak_idx]
    return freqs, amps, dominant_freq, max_amp

def calculate_updrs_tremor(peak_acc_g, dominant_freq):
    """
    MDS-UPDRS - KESİN SONUÇLU VERSİYON
    Normal hareketlerde ve belirsiz durumlarda ısrarla 'NORMAL (0)' döndürür.
    """
    
    # ---------------------------------------------------------
    # 1. FREKANS VE İSTEMLİ HAREKET FİLTRESİ
    # ---------------------------------------------------------
    # Frekans 4 Hz'den küçükse (Su içme, el kaldırma vb.), 
    # ivme ne kadar büyük olursa olsun bu Parkinson değildir.
    if dominant_freq < 4.0:
        return 0, f"NORMAL - İstemli Hareket ({dominant_freq:.1f} Hz)"

    # ---------------------------------------------------------
    # 2. GÜRÜLTÜ FİLTRESİ
    # ---------------------------------------------------------
    # Yerçekiminin %4'ünden küçük titreşimler 'Gürültü'dür.
    NOISE_LIMIT = 0.025 
    if peak_acc_g < NOISE_LIMIT:
        return 0, "NORMAL (0) - Hareket Yok"

    # ---------------------------------------------------------
    # 3. SAĞLIKLI İNSAN TİTREMESİ (FİZYOLOJİK)
    # ---------------------------------------------------------
    # Çok hızlı (8-12 Hz) ama küçük titreşimler normaldir.
    if dominant_freq > 7.5 and peak_acc_g < 0.15:
        return 0, f"NORMAL - Fizyolojik Titreme ({dominant_freq:.1f} Hz)"

    # ---------------------------------------------------------
    # 4. PARKİNSON PUANLAMASI (MDS-UPDRS)
    # ---------------------------------------------------------
    
    if peak_acc_g > 0.30:
        return 4, f"ŞİDDETLİ (4) - ({dominant_freq:.1f} Hz)"
    elif peak_acc_g > 0.10:
        return 3, f"ORTA-CİDDİ (3) - ({dominant_freq:.1f} Hz)"
    elif peak_acc_g > 0.06:
        return 2, f"ORTA (2) - ({dominant_freq:.1f} Hz)"
        
    elif peak_acc_g > 0.03: 
        return 1, f"HAFİF (1) - ({dominant_freq:.1f} Hz)"
    else:
        return 0, "NORMAL (0) - Belirsiz"

def draw_score_bar(ax, label, score, y_pos, color, inverse=False):
    """Yatay performans skor çubuğu çizer."""
    ax.text(0, y_pos, label, fontsize=11, fontweight='bold', va='center', ha='left', color='#34495e')
    # Arka plan
    ax.add_patch(plt.Rectangle((0.25, y_pos - 0.15), 0.7, 0.3, color='#ecf0f1', alpha=1.0, transform=ax.transAxes))
    # Doluluk
    final_score = score if not inverse else 100.0 - score
    normalized_score = np.clip(final_score / 100.0, 0.02, 1.0) # En az %2 görünsün
    ax.add_patch(plt.Rectangle((0.25, y_pos - 0.15), 0.7 * normalized_score, 0.3, color=color, alpha=1.0, transform=ax.transAxes))
    # Skor yazısı
    ax.text(0.97, y_pos, f"%{int(final_score)}", fontsize=11, fontweight='bold', va='center', ha='right', color=color)

# ========================================================
# 📊 ANA ANALİZ FONKSİYONU (main_system.py tarafından çağrılır)
# ========================================================

def run_analysis(file_path, stim_params=None):
    print(f"\n{'='*60}")
    print(f"🌊 MDS-UPDRS TREMOR (TİTREME) ANALİZİ")
    print(f"{'='*60}")

    try:
        # 1. Veri Okuma
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

        # 2. KALİBRASYON UYGULAMA
        if CALIBRATION_EXIST:
            df['AccX'] -= kalibrasyon_verisi.OFFSET_AX
            df['AccY'] -= kalibrasyon_verisi.OFFSET_AY
            df['AccZ'] -= kalibrasyon_verisi.OFFSET_AZ
            df['GyroX'] -= kalibrasyon_verisi.OFFSET_GX
            df['GyroY'] -= kalibrasyon_verisi.OFFSET_GY
            df['GyroZ'] -= kalibrasyon_verisi.OFFSET_GZ

        # Zaman Ekseni
        t_seconds = np.arange(len(df)) / FS

        # 3. Sinyal İşleme
        acc_mag_g = np.sqrt(df['AccX']**2 + df['AccY']**2 + df['AccZ']**2) / ACC_SCALE_FACTOR
        tremor_signal_g = butter_bandpass_filter(acc_mag_g, TREMOR_BAND[0], TREMOR_BAND[1], FS)
        
        window_size = int(FS * 1.0)
        tremor_envelope = pd.Series(tremor_signal_g).rolling(window=window_size, center=True).std().fillna(0).values * np.sqrt(2)

        # 4. Metrik Hesaplama
        peak_tremor_g = np.percentile(tremor_envelope, 95) if len(tremor_envelope) > 0 else 0
        freqs_fft, amps_fft, dominant_freq, max_amp_fft = calculate_fft_dominant(tremor_signal_g, FS)

        # 5. MDS-UPDRS Skorlama
        updrs_score, updrs_desc = calculate_updrs_tremor(peak_tremor_g, dominant_freq)

        color_map = {0: "#27ae60", 1: "#f1c40f", 2: "#e67e22", 3: "#d35400", 4: "#c0392b"}
        status_color = color_map.get(updrs_score, "gray")
        is_parkinsonian = (4.0 <= dominant_freq <= 7.0) and (updrs_score > 0)

        print(f"🔹 Tepe Titreşim: {peak_tremor_g:.4f} g")
        print(f"🔹 Baskın Frekans: {dominant_freq:.1f} Hz")
        print(f"🔹 MDS-UPDRS Skoru: {updrs_score}")

        # --- PROFESYONEL PDF RAPOR ---
        report_filename = file_path.replace(".csv", "_TREMOR_KLINIK_RAPOR.pdf")
        with PdfPages(report_filename) as pdf:
            fig = plt.figure(figsize=(8.27, 11.69))

            # --- BAŞLIK ŞERİDİ ---
            header_ax = fig.add_axes([0, 0.92, 1, 0.08])
            header_ax.axis('off')
            header_ax.add_patch(plt.Rectangle((0, 0), 1, 1, color=status_color, transform=header_ax.transAxes, zorder=-1))
            title_text = f"MDS-UPDRS TREMOR RAPORU (Skor: {updrs_score})"
            if is_parkinsonian: title_text += " - PARKİNSON TİPİ BULGU"
            header_ax.text(0.5, 0.5, title_text, transform=header_ax.transAxes, fontsize=16, weight='bold', color='white', ha='center', va='center')

            # --- GRAFİK 1: Zaman Serisi ---
            ax1 = fig.add_axes([0.1, 0.68, 0.8, 0.20])
            ax1.plot(t_seconds, tremor_signal_g, color=COLOR_SIGNAL, alpha=0.3, linewidth=0.8, label='Anlık Titreşim')
            ax1.plot(t_seconds, tremor_envelope, color=COLOR_TREMOR, linewidth=1.5, label='Titreşim Şiddeti')
            ax1.axhline(y=peak_tremor_g, color=status_color, linestyle='--', linewidth=1, label=f'Tepe: {peak_tremor_g:.3f} g')
            
            ax1.set_title("1. Titreşim Zaman Serisi", fontsize=11, fontweight='bold', color=COLOR_SIGNAL, loc='left')
            ax1.set_ylabel("İvme (g)", fontweight='bold', fontsize=9)
            ax1.legend(loc='upper right', frameon=True, fontsize=9)
            ax1.grid(which='major', color=COLOR_GRID_MAJOR, linestyle='-', linewidth=0.8, alpha=0.8)
            ax1.minorticks_on()
            ax1.grid(which='minor', color=COLOR_GRID_MINOR, linestyle=':', linewidth=0.5)

            # --- GRAFİK 2: Frekans Spektrumu ---
            ax2 = fig.add_axes([0.1, 0.38, 0.8, 0.20])
            ax2.axvspan(4.0, 7.0, color='#f39c12', alpha=0.15, label='Parkinson Risk Aralığı (4-7 Hz)')
            ax2.plot(freqs_fft, amps_fft, color=COLOR_SIGNAL, linewidth=1.5)
            ax2.fill_between(freqs_fft, amps_fft, color=COLOR_SIGNAL, alpha=0.1)
            
            if updrs_score > 0 and max_amp_fft > 0:
                 ax2.scatter([dominant_freq], [max_amp_fft], color=COLOR_TREMOR, s=80, zorder=5)
                 shift_amount = 0.5 
                 ax2.text(dominant_freq + shift_amount, max_amp_fft + (max_amp_fft*0.05), f"{dominant_freq:.1f} Hz", 
                          color=COLOR_TREMOR, fontweight='bold', ha='center', fontsize=9)

            ax2.set_title("2. Frekans Analizi", fontsize=11, fontweight='bold', color=COLOR_SIGNAL, loc='left')
            ax2.set_xlabel("Frekans (Hz)", fontweight='bold', fontsize=9)
            ax2.set_ylabel("Güç", fontweight='bold', fontsize=9)
            ax2.set_xlim(TREMOR_BAND[0], TREMOR_BAND[1])
            ax2.grid(which='major', color=COLOR_GRID_MAJOR, linestyle='-', linewidth=0.8, alpha=0.8)

            # --- STİMÜLASYON BİLGİSİ (GÜVENLİ YÖNTEM) ---
            if stim_params:
                s1 = stim_params['ch1']
                s2 = stim_params['ch2']
                stim_text = (f"UYGULANAN STİMÜLASYON: "
                             f"Kanal 1 ({s1['hz']}Hz, {s1['pw']}us, {s1['amp']}uA) | "
                             f"Kanal 2 ({s2['hz']}Hz, {s2['pw']}us, {s2['amp']}uA)")
                
                # Sayfanın en altına (Y: 0.03) ortalayarak yazdırır, grafikleri bozmaz.
                fig.text(0.5, 0.03, stim_text, ha='center', va='center', fontsize=10, fontweight='bold',
                         bbox=dict(facecolor='#EBF5FB', edgecolor='#2980B9', boxstyle='round,pad=0.5'))

            # --- KLİNİK BİLGİ KUTUSU ---
            info_ax = fig.add_axes([0.1, 0.22, 0.8, 0.10])
            info_ax.axis('off')
            diagnosis_text = f"TIBBİ TANI: {updrs_desc}\n"
            if is_parkinsonian: diagnosis_text += "ÖNEMLİ: Titreme frekansı Parkinson (4-7 Hz) ile uyumludur."
            elif updrs_score > 0: diagnosis_text += "NOT: Titreme mevcuttur ancak tipik Parkinson frekansı dışındadır."
            
            info_ax.text(0.5, 0.5, diagnosis_text, ha='center', va='center', fontsize=10, color=COLOR_SIGNAL,
                         bbox=dict(facecolor='#f8f9fa', edgecolor=status_color, boxstyle='round,pad=0.8', linewidth=2))

            # --- YENİ EKLENEN BÖLÜM: BASKIN FREKANS GÖSTERGESİ ---
            # Frekans rengini belirle (4-7 Hz arası Kırmızı, yoksa Yeşil/Mavi)
            freq_color = "#c0392b" if (4.0 <= dominant_freq <= 7.0 and updrs_score > 0) else "#2980b9"
            fig.text(0.60, 0.18, f"BASKIN FREKANS: {dominant_freq:.1f} Hz", 
                     ha='right', va='center', fontsize=12, fontweight='bold', color='white',
                     bbox=dict(facecolor=freq_color, edgecolor='none', boxstyle='round,pad=0.4'))

            # --- PERFORMANS KARNESİ ---
            score_ax = fig.add_axes([0.1, 0.05, 0.8, 0.12])
            score_ax.axis('off')
            score_ax.set_title("PERFORMANS KARNESİ", fontsize=11, fontweight='bold', color=COLOR_SIGNAL, loc='left')

            steadiness_score = np.clip((1.0 - (peak_tremor_g / 0.15)) * 100, 0, 100)
            severity_score = np.clip((peak_tremor_g / 0.30) * 100, 0, 100)

            draw_score_bar(score_ax, "DURGUNLUK", steadiness_score, 0.7, "#27ae60")
            draw_score_bar(score_ax, "TİTREME ŞİDDETİ", severity_score, 0.3, "#c0392b")

            fig.text(0.5, 0.01, "MDS-UPDRS Kriterlerine Dayalı Bilgisayar Destekli Tanı (CAD) Çıktısıdır.", 
                     ha='center', fontsize=8, color='#95a5a6')

            pdf.savefig(fig)
            plt.close(fig)
            print(f"✅ Klinik Tremor Raporu Hazır: {report_filename}")

    except Exception as e:
        print(f"❌ Analiz Hatası: {e}")
        import traceback
        traceback.print_exc()