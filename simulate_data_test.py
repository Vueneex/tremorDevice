# DOSYA ADI: simulate_data_test.py
from database import TestDatabase
import os
from datetime import datetime

def run_simulation():
    print("--- Veritabanı Simülasyon Testi Başlatılıyor ---")
    
    # 1. Veritabanı nesnesini başlat
    db = TestDatabase()
    if not db.conn:
        print("Hata: Veritabanına bağlanılamadı. Lütfen db_config.py ayarlarını kontrol edin.")
        return

    # 2. Test hastası bilgileri
    test_patient = {
        "protocol_no": "SIM-001",
        "name": "Simülasyon Test Hastası",
        "age": 45,
        "gender": "Erkek",
        "dominant_side": "Sağ",
        "onset_year": 2020,
        "diagnosis": "Parkinson Test",
        "doctor": "Dr. Antigravity",
        "phone": "555-000-0000",
        "history": "Bu bir simülasyon test kaydıdır. MySQL bağlantısını doğrulamak için oluşturulmuştur."
    }

    print(f"\n1. Hasta ekleniyor: {test_patient['name']}...")
    success = db.add_patient_with_details(
        test_patient["protocol_no"],
        test_patient["name"],
        test_patient["age"],
        test_patient["gender"],
        test_patient["dominant_side"],
        test_patient["onset_year"],
        test_patient["diagnosis"],
        test_patient["doctor"],
        test_patient["phone"],
        test_patient["history"]
    )

    if success:
        print("✅ Hasta başarıyla eklendi.")
    else:
        print("⚠️ Hasta zaten mevcut olabilir veya bir hata oluştu. Devam ediliyor...")

    # 3. Test kaydı ekleme
    print("\n2. Test verisi ekleniyor...")
    db.add_test(
        patient_name=test_patient["name"],
        test_type="Tremor Analizi (Simülasyon)",
        file_path="simule_test_verisi.csv",
        score=0.85,
        extra=12.4,
        notes="Otomatik simülasyon testi başarılı."
    )
    print("✅ Test verisi başarıyla eklendi.")

    # 4. Verileri geri okuma ve doğrulama
    print("\n3. Veriler doğrulanıyor...")
    patients = db.get_all_patients()
    if test_patient["name"] in patients:
        print(f"✅ '{test_patient['name']}' hasta listesinde bulundu.")
        
        details = db.get_patient_details(test_patient["name"])
        print(f"--- Detaylar ---")
        print(f"Protokol: {details['protocol_no']}")
        print(f"Doktor: {details['doctor_name']}")
        print(f"Klinik Öykü: {details['clinical_history']}")
    else:
        print("❌ Hata: Hasta listesinde bulunamadı!")

    print("\n--- Simülasyon Tamamlandı! ---")
    print("Şu an phpMyAdmin üzerinden veya gui_app.py uygulamasını açarak bu kaydı görebilirsin.")

if __name__ == "__main__":
    run_simulation()
