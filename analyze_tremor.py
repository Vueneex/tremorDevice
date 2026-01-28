# DOSYA ADI: analyze_tremor.py
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates 
from scipy.signal import butter, filtfilt
from scipy.fft import fft, fftfreq
from matplotlib.backends.backend_pdf import PdfPages
import os
import datetime
import warnings
import traceback 

# Kalibrasyon Kontrolü (Varsa okur, yoksa geçer)
try:
    import kalibrasyon_verisi
    CALIBRATION_EXIST = True
except ImportError:
    CALIBRATION_EXIST = False

# Ayarlar
FS = 50.0                 
BASE_ACC_ESIK = 0.03       
BASE_GYRO_ESIK = 5.0       
DYNAMIC_FACTOR = 0.25      
MOVEMENT_VETO_LEVEL = 0.6  
ZAMAN_SINIRI = 2.0         
ACC_AGIRLIK = 0.3          
GYRO_AGIRLIK = 0.7         
REF_MAX_G = 0.5  

# --- YARDIMCI SINIFLAR ---
class Madgwick:
    def __init__(self, sampleperiod=0.01, beta=0.1):
        self.samplePeriod = sampleperiod
        self.beta = beta
        self.q = np.array([1.0, 0.0, 0.0, 0.0]) 
        
    def update(self, gx, gy, gz, ax, ay, az):
        q = self.q
        norm = np.sqrt(ax*ax + ay*ay + az*az)
        if norm == 0: return
        ax, ay, az = ax/norm, ay/norm, az/norm
        _2q0, _2q1, _2q2, _2q3 = 2*q[0], 2*q[1], 2*q[2], 2*q[3]
        _4q0, _4q1, _4q2 = 4*q[0], 4*q[1], 4*q[2]
        _8q1, _8q2 = 8*q[1], 8*q[2]
        q0q0, q1q1, q2q2, q3q3 = q[0]*q[0], q[1]*q[1], q[2]*q[2], q[3]*q[3]
        s0 = _4q0*q2q2 + _2q2*ax + _4q0*q1q1 - _2q1*ay
        s1 = _4q1*q3q3 - _2q3*ax + 4*q0q0*q[1] - _2q0*ay - _4q1 + _8q1*q1q1 + _8q1*q2q2 + _4q1*az
        s2 = 4*q0q0*q[2] + _2q0*ax + _4q2*q3q3 - _2q3*ay - _4q2 + _8q2*q1q1 + _8q2*q2q2 + _4q2*az
        s3 = _4q1*q[1]*q[3] - _2q1*ax + _4q2*q[2]*q[3] - _2q2*ay
        norm = np.sqrt(s0*s0 + s1*s1 + s2*s2 + s3*s3)
        if norm > 0:
            s0, s1, s2, s3 = s0/norm, s1/norm, s2/norm, s3/norm
        qDot0 = 0.5 * (-q[1]*gx - q[2]*gy - q[3]*gz) - self.beta * s0
        qDot1 = 0.5 * (q[0]*gx + q[2]*gz - q[3]*gy) - self.beta * s1
        qDot2 = 0.5 * (q[0]*gy - q[1]*gz + q[3]*gx) - self.beta * s2
        qDot3 = 0.5 * (q[0]*gz + q[1]*gy - q[2]*gx) - self.beta * s3
        q[0] += qDot0 * self.samplePeriod
        q[1] += qDot1 * self.samplePeriod
        q[2] += qDot2 * self.samplePeriod
        q[3] += qDot3 * self.samplePeriod
        norm = np.sqrt(q[0]*q[0] + q[1]*q[1] + q[2]*q[2] + q[3]*q[3])
        self.q = q / norm
        
    def get_gravity_vector(self):
        q = self.q
        return np.array([2*(q[1]*q[3] - q[0]*q[2]), 2*(q[0]*q[1] + q[2]*q[3]), q[0]**2 - q[1]**2 - q[2]**2 + q[3]**2])

def butter_filter(data, low, high, fs, btype='band', order=4):
    nyq = 0.5 * fs
    if btype == 'band':
        normal_low = low / nyq
        normal_high = high / nyq
        b, a = butter(order, [normal_low, normal_high], btype='band')
    elif btype == 'low':
        normal_high = low / nyq 
        b, a = butter(order, normal_high, btype='low')
    y = filtfilt(b, a, data)
    return y

def calculate_envelope(signal, fs):
    return pd.Series(signal).rolling(window=int(fs), center=True).std().fillna(0).values

def perform_fft_analysis_smart(signal, fs):
    n = len(signal)
    yf = fft(signal - np.mean(signal)) 
    xf = fftfreq(n, 1 / fs)
    idx = np.where((xf >= 3.5) & (xf <= 20)) 
    freqs = xf[idx]
    amps = 2.0/n * np.abs(yf[idx])
    peak_freq = 0
    if len(amps) > 0:
        peak_idx = np.argmax(amps)
        peak_freq = freqs[peak_idx]
    
    idx_plot = np.where((xf >= 1.0) & (xf <= 20))
    freqs_plot = xf[idx_plot]
    amps_plot = 2.0/n * np.abs(yf[idx_plot])
    return freqs_plot, amps_plot, peak_freq

# =========================================================
# 📊 ANA ANALİZ FONKSİYONU
# =========================================================
def run_analysis(file_path):
    print(f"\n{'='*60}")
    print(f"🌊 TREMOR (TİTREME) ANALİZİ BAŞLATILDI: {os.path.basename(file_path)}")
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

        # --- KALİBRASYON DÜZELTMESİ ---
        if CALIBRATION_EXIST:
            df['AccX'] -= kalibrasyon_verisi.OFFSET_AX
            df['AccY'] -= kalibrasyon_verisi.OFFSET_AY
            df['AccZ'] -= kalibrasyon_verisi.OFFSET_AZ
            df['GyroX'] -= kalibrasyon_verisi.OFFSET_GX
            df['GyroY'] -= kalibrasyon_verisi.OFFSET_GY
            df['GyroZ'] -= kalibrasyon_verisi.OFFSET_GZ

        # Zaman Ekseni
        dosya_zamani = os.path.getctime(file_path)
        baslangic_zamani = datetime.datetime.fromtimestamp(dosya_zamani)
        t_real = [baslangic_zamani + datetime.timedelta(seconds=i/FS) for i in range(len(df))]
        t_seconds = np.arange(len(df)) / FS 

        # Birim Çevirme
        ax_g = df['AccX'].values / 16384.0; ay_g = df['AccY'].values / 16384.0; az_g = df['AccZ'].values / 16384.0
        gx_rad = (df['GyroX'].values / 131.0) * (np.pi / 180.0); gy_rad = (df['GyroY'].values / 131.0) * (np.pi / 180.0); gz_rad = (df['GyroZ'].values / 131.0) * (np.pi / 180.0)

        # Madgwick
        madgwick = Madgwick(sampleperiod=(1.0/FS), beta=0.1)
        linear_acc = [] 
        for i in range(len(df)):
            madgwick.update(gx_rad[i], gy_rad[i], gz_rad[i], ax_g[i], ay_g[i], az_g[i])
            gravity_vec = madgwick.get_gravity_vector()
            lin_vec = np.array([ax_g[i], ay_g[i], az_g[i]]) - gravity_vec
            linear_acc.append(np.linalg.norm(lin_vec))
        linear_acc = np.array(linear_acc)
        
        # Filtreler
        acc_tremor_sig = butter_filter(linear_acc, 3.5, 7.5, FS, btype='band')
        move_sig = butter_filter(linear_acc, 2.0, None, FS, btype='low')
        gyro_mag_deg = np.sqrt(df['GyroX']**2 + df['GyroY']**2 + df['GyroZ']**2) / 131.0
        gyro_tremor_sig = butter_filter(gyro_mag_deg, 3.5, 7.5, FS, btype='band')

        env_acc_tremor = calculate_envelope(acc_tremor_sig, FS)
        env_gyro_tremor = calculate_envelope(gyro_tremor_sig, FS)
        env_move = calculate_envelope(move_sig, FS)
        
        fft_freqs, fft_amps, dominant_freq = perform_fft_analysis_smart(linear_acc, FS)

        raw_percent = (env_acc_tremor / REF_MAX_G) * 100.0
        env_acc_percent = np.clip(raw_percent, 0, 100.0)

        avg_movement_level = np.mean(env_move)
        dynamic_acc_esik = BASE_ACC_ESIK + (avg_movement_level * DYNAMIC_FACTOR)
        dynamic_gyro_esik = BASE_GYRO_ESIK + (avg_movement_level * 50.0 * DYNAMIC_FACTOR) 
        
        raw_dyn_esik = (dynamic_acc_esik / REF_MAX_G) * 100.0
        dynamic_acc_esik_percent = np.clip(raw_dyn_esik, 0, 100.0)

        dur_acc = np.sum(env_acc_tremor > dynamic_acc_esik) / FS
        dur_gyro = np.sum(env_gyro_tremor > dynamic_gyro_esik) / FS
        weighted_duration = (dur_acc * ACC_AGIRLIK) + (dur_gyro * GYRO_AGIRLIK)
        
        has_tremor = weighted_duration >= ZAMAN_SINIRI
        is_parkinson_freq = (3.5 <= dominant_freq <= 7.5)
        has_movement = avg_movement_level > 0.2
        
        diagnosis_title = "BELİRSİZ"
        diagnosis_color = "gray"
        status_box_color = "#ecf0f1" 

        if avg_movement_level > MOVEMENT_VETO_LEVEL:
            has_tremor = False
            diagnosis_title = "ŞİDDETLİ HAREKET"
            diagnosis_subtitle = "Hareket şiddeti analizi engelliyor."
            diagnosis_color = "#e67e22" 
            status_box_color = "#fdebd0"
        else:
            if has_tremor and is_parkinson_freq:
                diagnosis_title = "HASTALIK BULGUSU"
                diagnosis_subtitle = f"Parkinson Karakterli Titreme ({dominant_freq:.1f} Hz)"
                diagnosis_color = "#c0392b"
                status_box_color = "#fadbd8" 
            elif has_tremor and not is_parkinson_freq:
                 diagnosis_title = "FREKANS UYUMSUZ"
                 diagnosis_subtitle = "Titreme var ancak Parkinson frekansında değil."
                 diagnosis_color = "#f1c40f"
                 status_box_color = "#f9e79f"
            elif has_movement:
                diagnosis_title = "SAĞLIKLI HAREKET"
                diagnosis_subtitle = "Normal istemli hareket."
                diagnosis_color = "#27ae60" 
                status_box_color = "#d5f5e3"
            else:
                diagnosis_title = "DURGUN / SABİT"
                diagnosis_subtitle = "Cihaz sabit."
                diagnosis_color = "#7f8c8d" 
                status_box_color = "#eaeded"

        print(f"ADIM 5: Teşhis Konuldu -> {diagnosis_title}")

        # --- PDF ÇİZİMİ ---
        report_filename = file_path.replace(".csv", "_TREMOR_RAPOR.pdf")
        with PdfPages(report_filename) as pdf:
            fig = plt.figure(figsize=(8.27, 11.69)) 
            
            header_ax = fig.add_axes([0.1, 0.85, 0.8, 0.12]) 
            header_ax.axis('off')
            header_ax.add_patch(plt.Rectangle((0, 0), 1, 1, color=status_box_color, transform=header_ax.transAxes, zorder=-1, alpha=0.5))
            header_ax.text(0.05, 0.7, diagnosis_title, transform=header_ax.transAxes, fontsize=24, weight='bold', color=diagnosis_color)
            header_ax.text(0.05, 0.4, diagnosis_subtitle, transform=header_ax.transAxes, fontsize=12, color='#34495e')
            header_ax.text(0.95, 0.5, f"Tarih: {baslangic_zamani.strftime('%Y-%m-%d %H:%M')}\nMod: TREMOR", transform=header_ax.transAxes, fontsize=9, color='#7f8c8d', ha='right', va='center')

            # Grafik 1: Sarsıntı
            ax1 = fig.add_axes([0.1, 0.60, 0.8, 0.20])
            ax1.plot(t_real, env_acc_percent, color='#c0392b', linewidth=1.5, label='Şiddet (%)')
            ax1.set_ylim(0, 100)
            ax1.set_ylabel("Şiddet (%)", fontsize=9, fontweight='bold', color='#c0392b')
            ax1.tick_params(axis='y', labelcolor='#c0392b')
            ax1_right = ax1.twinx()
            ax1_right.set_ylim(0, REF_MAX_G)
            ax1_right.set_ylabel("İvme (g)", fontsize=9, color='#7f8c8d')
            ax1_right.tick_params(axis='y', labelcolor='#7f8c8d')
            ax1.axhline(y=dynamic_acc_esik_percent, color='#2980b9', linestyle='--', linewidth=1, label='Dinamik Eşik')
            ax1.fill_between(t_real, env_acc_percent, dynamic_acc_esik_percent, where=(env_acc_percent > dynamic_acc_esik_percent), color='#e74c3c', alpha=0.3)
            ax1.set_title("1. SARSINTI ANALİZİ (Çift Ölçek)", fontsize=10, weight='bold', loc='left', color='#2c3e50')
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            ax1.grid(True, linestyle=':', alpha=0.6)

            # Grafik 2: Dönme
            ax2 = fig.add_axes([0.1, 0.35, 0.8, 0.20])
            ax2.plot(t_seconds, env_gyro_tremor, color='#8e44ad', linewidth=1.5, label='Dönme Hızı')
            ax2.axhline(y=dynamic_gyro_esik, color='#2980b9', linestyle='--', linewidth=1)
            ax2.fill_between(t_seconds, env_gyro_tremor, dynamic_gyro_esik, where=(env_gyro_tremor > dynamic_gyro_esik), color='#9b59b6', alpha=0.3)
            ax2.set_ylim(0, 150)
            ax2.set_ylabel("Hız (°/sn)", fontsize=9)
            ax2.set_title("2. BİLEK DÖNME HIZI", fontsize=10, weight='bold', loc='left', color='#2c3e50')
            ax2.grid(True, linestyle=':', alpha=0.6)
            ax2.set_xticklabels([]) 

            # Grafik 3: Frekans
            ax3 = fig.add_axes([0.1, 0.10, 0.8, 0.20])
            ax3.plot(fft_freqs, fft_amps, color='#34495e', linewidth=1.5)
            if is_parkinson_freq and not (avg_movement_level > MOVEMENT_VETO_LEVEL):
                ax3.text(dominant_freq, max(fft_amps)*1.05, f'{dominant_freq:.1f} Hz', ha='center', fontsize=9, color='#c0392b', fontweight='bold')
            ax3.set_xlim(2, 10) 
            ax3.set_xticks(np.arange(2, 11, 1))
            ax3.set_ylabel("Güç", fontsize=9)
            ax3.set_xlabel("Frekans (Hz)", fontsize=9)
            ax3.set_title("3. FREKANS SPEKTRUMU (Odaklanmış: 2-10 Hz)", fontsize=10, weight='bold', loc='left', color='#2c3e50')
            ax3.grid(True, linestyle=':', alpha=0.6)

            fig.text(0.5, 0.02, "Analiz Türü: TREMOR (Titreme)", ha='center', fontsize=8, color='#95a5a6')
            pdf.savefig(fig)
            plt.close()
        
        print(f"✅ TREMOR PDF OLUŞTU: {report_filename}")

    except Exception as e:
        print("\n❌ PDF OLUŞTURMA HATASI:")
        print(traceback.format_exc())