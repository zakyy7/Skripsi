#include <SPI.h>
#include <SD.h>
#include <TinyGPS++.h>
#include <SoftwareSerial.h>
#include <Wire.h>
#include "SSD1306Ascii.h"
#include "SSD1306AsciiAvrI2c.h"

// --- KONFIGURASI PIN ---
// GPS pakai SoftwareSerial (Karena TX/RX asli dipakai USB)
static const int RXPin = 4, TXPin = 3; 
SoftwareSerial gpsSerial(RXPin, TXPin);

// SD Card CS Pin
const int chipSelect = 10;

// Objek GPS & OLED
TinyGPSPlus gps;
SSD1306AsciiAvrI2c display;

// Variabel Kontrol
String lastTimeEntry = "";
unsigned long lastDisplayUpdate = 0;

// Command GPS 5Hz
const byte set5Hz[] = {0xB5, 0x62, 0x06, 0x08, 0x06, 0x00, 0xC8, 0x00, 0x01, 0x00, 0x01, 0x00, 0xDE, 0x6A};

void setup() {
  // 1. Serial Monitor (Laptop)
  Serial.begin(115200); 
  
  // 2. Serial GPS
  gpsSerial.begin(9600); 

  // 3. Inisialisasi OLED (Versi Ascii/Teks)
  display.begin(&Adafruit128x64, 0x3C);
  display.setFont(System5x7);
  display.clear();
  display.println("Booting Nano...");

  // 4. Inisialisasi SD Card
  Serial.print(F("Init SD Card..."));
  if (!SD.begin(chipSelect)) {
    Serial.println(F("GAGAL!"));
    display.clear();
    display.println("SD CARD ERROR!");
    while (1); // Berhenti total jika SD rusak
  }
  Serial.println(F("OK!"));
  
  // Buat Header CSV
  File dataFile = SD.open("log.csv", FILE_WRITE);
  if (dataFile) {
    if (dataFile.size() == 0) {
      dataFile.println(F("Date,Time,Lat,Lon,Speed"));
    }
    dataFile.close();
  }

  // 5. Ubah GPS ke 5Hz
  display.println("Set GPS 5Hz...");
  gpsSerial.write(set5Hz, sizeof(set5Hz));
  delay(1000);

  display.clear();
  display.println("SYSTEM READY");
  delay(1000);
}

void loop() {
  // BACA DATA GPS
  while (gpsSerial.available() > 0) {
    if (gps.encode(gpsSerial.read())) {
      
      // Jika waktu berubah (Update 5x sedetik)
      if (gps.time.isUpdated()) {
        processData();
      }
    }
  }
}

void processData() {
  // --- A. OLAH WAKTU ---
  int jam = gps.time.hour() + 7;
  if (jam >= 24) jam -= 24;

  // Manual String Building (Hemat Memori)
  String sTime = "";
  if (jam < 10) sTime += "0";
  sTime += String(jam) + ":";
  
  if (gps.time.minute() < 10) sTime += "0";
  sTime += String(gps.time.minute()) + ":";
  
  if (gps.time.second() < 10) sTime += "0";
  sTime += String(gps.time.second()) + ".";
  
  int cs = gps.time.centisecond() * 10;
  if (cs < 10) sTime += "00";
  else if (cs < 100) sTime += "0";
  sTime += String(cs);

  // Cek Duplikat
  if (sTime == lastTimeEntry) return;
  lastTimeEntry = sTime;

  // --- B. SIMPAN KE SD CARD ---
  String dataString = "";
  dataString += String(gps.date.day()) + "/" + String(gps.date.month()) + "/" + String(gps.date.year()) + ",";
  dataString += sTime + ",";
  dataString += String(gps.location.lat(), 6) + ",";
  dataString += String(gps.location.lng(), 6) + ",";
  dataString += String(gps.speed.kmph());

  File dataFile = SD.open("log.csv", FILE_WRITE);
  bool sdStatus = false;
  if (dataFile) {
    dataFile.println(dataString);
    dataFile.close();
    sdStatus = true;
    Serial.println(sTime); // Debug ke Serial Monitor
  }

  // --- C. UPDATE OLED ---
  if (millis() - lastDisplayUpdate > 200) {
    updateDisplay(jam, gps.time.minute(), gps.time.second(), gps.speed.kmph(), gps.satellites.value(), sdStatus);
    lastDisplayUpdate = millis();
  }
}

void updateDisplay(int h, int m, int s, double speed, int sat, bool sdOK) {
  display.setCursor(0, 0);
  display.print("Time: ");
  if(h<10) display.print("0"); display.print(h); display.print(":");
  if(m<10) display.print("0"); display.print(m); display.print(":");
  if(s<10) display.print("0"); display.print(s);
  
  display.setCursor(0, 1);
  display.print("Sat : "); display.print(sat); display.print("  ");

  display.set2X(); 
  display.setCursor(0, 3);
  display.print(speed, 1); display.print(" kmh");
  display.set1X(); 

  display.setCursor(0, 7);
  if (sdOK) display.print("REC [SD OK]");
  else      display.print("ERR [SD FAIL]");
}