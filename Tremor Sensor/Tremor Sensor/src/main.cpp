#include <Arduino.h>
#include <SPI.h>
#include <SparkFun_BMI270_Arduino_Library.h>

// --- PİN TANIMLAMALARI ---
#define LED_PIN     PB0
#define BMI270_CS   PB12
#define BMI270_SCK  PB13
#define BMI270_MISO PB14
#define BMI270_MOSI PB15
#define BATTERY_PIN PA0 // Batarya voltajı okuma pini (Donanımına göre değiştirebilirsin)

BMI270 imu;
bool sensorHazir = false;

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BATTERY_PIN, INPUT_ANALOG);

  // Sistemi oturtmak için kısa bekleme
  delay(1000);

  // SPI2 Yönlendirmesi
  SPI.setMOSI(BMI270_MOSI);
  SPI.setMISO(BMI270_MISO);
  SPI.setSCLK(BMI270_SCK);
  SPI.begin();

  pinMode(BMI270_CS, OUTPUT);
  digitalWrite(BMI270_CS, HIGH);

  // Sensörü Başlat
  if (imu.beginSPI(BMI270_CS) == 0) {
    sensorHazir = true;
    digitalWrite(LED_PIN, LOW); // Başarılı
  } else {
    sensorHazir = false;
    digitalWrite(LED_PIN, HIGH); // Hata: LED sabit yanar
  }
}

void loop() {
  // Elektrik/Batarya Yönetimi: 0-4095 arası ADC değerini okuyup (örnek) voltaja/yüzdeye çevirme
  int rawBat = analogRead(BATTERY_PIN);
  float bataryaYuzdesi = map(rawBat, 0, 4095, 0, 100); // Kendi voltaj bölücüne göre kalibre edersin

  if (sensorHazir) {
    imu.getSensorData();
    // Python'un beklediği virgüllü format: Ax,Ay,Az,Gx,Gy,Gz,Batarya
    Serial.print(imu.data.accelX); Serial.print(",");
    Serial.print(imu.data.accelY); Serial.print(",");
    Serial.print(imu.data.accelZ); Serial.print(",");
    Serial.print(imu.data.gyroX);  Serial.print(",");
    Serial.print(imu.data.gyroY);  Serial.print(",");
    Serial.print(imu.data.gyroZ);  Serial.print(",");
    Serial.println(bataryaYuzdesi);
  } else {
    // Sensör fiziksel olarak okunamazsa Python'a hata bayrağı gönder (Arayüz çökmez, uyarır)
    Serial.println("ERR,SENSOR_BULUNAMADI");
    delay(500); 
  }
  
  delay(20); // 50 Hz döngü
}