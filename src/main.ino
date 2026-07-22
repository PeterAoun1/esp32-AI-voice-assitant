#include <WiFi.h>
#include <HTTPClient.h>
#include <SPIFFS.h>
#include "driver/i2s.h"
#include "driver/dac.h"

// --- CONFIGURATION ---
const char* ssid = "wifi name";
const char* password = "wifi password";
const char* welcomeUrl = "http://ip@:8888/welcome";
const char* serverUrl = "http://ip@:8888/process_voice";
const char* downloadUrl = "http://ip@:8888/reply.wav";
#define I2S_WS    27  
#define I2S_SCK   26  
#define I2S_SD    33  
#define SAMPLE_RATE 16000
#define RECORD_TIME 5 

#define DMA_BUFFER_SIZE 512 
int32_t rawBuffer[DMA_BUFFER_SIZE];
int16_t pcmBuffer[DMA_BUFFER_SIZE]; 

static inline uint32_t readLE32(File &f) {
  uint8_t b[4];
  if (f.read(b, 4) != 4) return 0;
  return (uint32_t)b[0] | ((uint32_t)b[1] << 8) | ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24);
}
static inline uint16_t readLE16(File &f) {
  uint8_t b[2];
  if (f.read(b, 2) != 2) return 0;
  return (uint16_t)b[0] | ((uint16_t)b[1] << 8);
}

bool parseWavHeader(File &f, uint16_t &fmt, uint16_t &ch, uint32_t &sr, uint16_t &bps, uint32_t &dataSz) {
  char riff[4], wave[4];
  if (f.read((uint8_t*)riff, 4) != 4) return false;
  if (strncmp(riff, "RIFF", 4) != 0) return false;
  readLE32(f);
  if (f.read((uint8_t*)wave, 4) != 4) return false;
  if (strncmp(wave, "WAVE", 4) != 0) return false;

  bool gotFmt = false, gotData = false;
  while (f.available()) {
    char id[4];
    if (f.read((uint8_t*)id, 4) != 4) return false;
    uint32_t sz = readLE32(f);

    if (strncmp(id, "fmt ", 4) == 0) {
      fmt = readLE16(f); ch = readLE16(f); sr = readLE32(f);
      readLE32(f); readLE16(f); bps = readLE16(f);
      if (sz > 16) f.seek(f.position() + (sz - 16));
      gotFmt = true;
    } else if (strncmp(id, "data", 4) == 0) {
      dataSz = sz; gotData = true; break;
    } else {
      f.seek(f.position() + sz);
    }
    if (sz & 1) f.seek(f.position() + 1);
  }
  return gotFmt && gotData;
}

bool playWavOnDAC25(const char *path) {
  File f = SPIFFS.open(path, FILE_READ);
  if (!f) return false; 

  uint16_t fmt = 0, ch = 0, bps = 0;
  uint32_t sr = 0, dataSz = 0;

  if (!parseWavHeader(f, fmt, ch, sr, bps, dataSz)) {
    f.close(); 
    return false;
  }

  dac_output_enable(DAC_CHANNEL_1); 
  dac_output_voltage(DAC_CHANNEL_1, 128); 

  uint32_t samplePeriod = 1000000UL / sr;
  uint32_t nextSample = micros();
  uint32_t played = 0;

  while (played < dataSz && f.available()) {
    uint8_t sample = 128;
    if (ch == 1) {
      if (f.read(&sample, 1) != 1) break; 
      played++;
    } else if (ch == 2) {
      uint8_t left, right;
      if (f.read(&left, 1) != 1 || f.read(&right, 1) != 1) break;
      sample = ((uint16_t)left + right) / 2; 
      played += 2;
    }

    while ((int32_t)(micros() - nextSample) < 0) { }
    dac_output_voltage(DAC_CHANNEL_1, sample);
    nextSample += samplePeriod;
  }

  dac_output_voltage(DAC_CHANNEL_1, 128);
  dac_output_disable(DAC_CHANNEL_1);
  f.close();
  return true;
}

bool downloadAndPlayReply() {
  HTTPClient http;
  http.begin(downloadUrl);
  int downloadCode = http.GET();
  bool ok = false;
  if (downloadCode == 200) {
    File f = SPIFFS.open("/reply.wav", FILE_WRITE);
    if (f) {
      http.writeToStream(&f);
      f.close();
      ok = playWavOnDAC25("/reply.wav");
    }
  } else {
    Serial.printf("Download failed, HTTP Error: %d\n", downloadCode);
  }
  http.end();
  return ok;
}

// Robot speaks first: offers story / count / alphabet
bool playWelcome() {
  Serial.println("\n>>> Asking server for welcome message...");
  HTTPClient http;
  http.begin(welcomeUrl);
  http.setTimeout(30000);
  int code = http.POST("");
  http.end();

  if (code != 200) {
    Serial.printf("Welcome failed, HTTP Error: %d\n", code);
    return false;
  }

  delay(300);
  return downloadAndPlayReply();
}

void recordAndProcess() {
  size_t bytesRead;
  File recordFile = SPIFFS.open("/recording.raw", FILE_WRITE);
  if (!recordFile) return;

  Serial.println("\n>>> Listening... Speak now!");
  uint32_t start = millis();

  while (millis() - start < (RECORD_TIME * 1000)) {
    i2s_read(I2S_NUM_0, rawBuffer, sizeof(rawBuffer), &bytesRead, portMAX_DELAY);
    int samplesRead = bytesRead / 4; 
    if (samplesRead > 0) {
      for (int i = 0; i < samplesRead; i++) {
        int32_t val = rawBuffer[i];
        val >>= 14; 
        pcmBuffer[i] = (int16_t)val;
      }
      recordFile.write((uint8_t*)pcmBuffer, samplesRead * 2);
    }
  }
  recordFile.close();

  File uploadFile = SPIFFS.open("/recording.raw", FILE_READ);
  if (!uploadFile) return;

  HTTPClient http;
  http.begin(serverUrl); 
  http.addHeader("Content-Type", "application/octet-stream");
  
  String lengthString = String(uploadFile.size());
  http.addHeader("Content-Length", lengthString.c_str());
  
  http.setTimeout(30000); 

  int code = http.sendRequest("POST", &uploadFile, uploadFile.size());
  uploadFile.close(); 
  http.end();
  
  if (code == 200) {
    delay(300); 
    downloadAndPlayReply();
  } else {
    Serial.printf("Server upload failed, HTTP Error: %d\n", code);
  }
}

void setup() {
  Serial.begin(115200);
  SPIFFS.begin(true);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) delay(500);

  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT, 
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 64
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK, 
    .ws_io_num = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE, 
    .data_in_num = I2S_SD
  };

  i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &pin_config);
  
  delay(1000);

  // 1) Robot starts the conversation with the activity menu
  playWelcome();

  // 2) Then keep talking: listen -> reply -> listen...
  while (true) {
    recordAndProcess();
    delay(500);
  }
}

void loop() {}
