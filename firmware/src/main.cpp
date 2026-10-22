// ESP32 DevKit V1 + DWS-MH-02 water sensor (flow, temperature, TDS).
// Sends a reading every SAMPLE_MS to the home server. See README.md for wiring.
//
// Serial commands (115200 baud):
//   status          print a reading now
//   tds <ppm>       calibrate TDS: probe in a solution of known ppm
//   flowstart       start counting pulses for flow calibration
//   flowstop        stop, and save the count as pulses per liter (pour exactly 1 L in between)
//   ppl <n>         set pulses per liter directly
//
// Firmware updates over WiFi: pio run -e ota -t upload (see README.md).

#include <Arduino.h>
#include <ArduinoOTA.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <math.h>
#include <time.h>

#include "secrets.h"

// ------------------------------------------------------------------ pins --
constexpr int PIN_FLOW      = 27;  // flow pulse, through 10k/20k divider
constexpr int PIN_TDS_LO    = 25;  // TDS drive, through R_REF_LO to the sense node
constexpr int PIN_TDS_HI    = 33;  // TDS drive, through R_REF_HI to the sense node (optional)
constexpr int PIN_TDS_B     = 26;  // TDS drive, straight to the second electrode
constexpr int PIN_TDS_SENSE = 35;  // ADC1: sense node, also the first electrode
constexpr int PIN_TEMP      = 34;  // ADC1: node between 10k pull-up and thermistor

// --------------------------------------------------------------- circuit --
constexpr float VCC          = 3.3f;
constexpr float R_REF_LO     = 4700.0f;   // ohms, best for tap water
constexpr float R_REF_HI     = 47000.0f;  // ohms, best for filtered water
constexpr float RANGE_SWITCH = 14900.0f;  // sqrt(LO * HI): above this, HI is more precise
constexpr float TEMP_R_FIXED = 10000.0f;  // ohms, 3.3V -> PIN_TEMP
constexpr float NTC_R25      = 10000.0f;  // thermistor ohms at 25 C (measure yours)
constexpr float NTC_BETA     = 3950.0f;
constexpr float TDS_FACTOR   = 0.5f;      // ppm per uS/cm (common meter convention)

constexpr uint32_t SAMPLE_MS = 10000;

// ----------------------------------------------------------------- state --
Preferences prefs;
float cellK;           // probe cell constant, cm^-1 (set by "tds" calibration)
float pulsesPerLiter;  // set by "flowstop" or "ppl"

portMUX_TYPE pulseMux = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t isrPulses = 0;
uint32_t samplePulses = 0;  // pulses since the last reading
uint32_t calPulses = 0;     // pulses since "flowstart"
bool calibratingFlow = false;
float totalLiters = 0;

void IRAM_ATTR onPulse() {
  portENTER_CRITICAL_ISR(&pulseMux);
  isrPulses++;
  portEXIT_CRITICAL_ISR(&pulseMux);
}

void drainPulses() {
  portENTER_CRITICAL(&pulseMux);
  uint32_t n = isrPulses;
  isrPulses = 0;
  portEXIT_CRITICAL(&pulseMux);
  samplePulses += n;
  calPulses += n;
}

// --------------------------------------------------------------- sensors --
float readTempC() {
  uint32_t mv = 0;
  for (int i = 0; i < 32; i++) mv += analogReadMilliVolts(PIN_TEMP);
  float v = mv / 32000.0f;
  if (v < 0.05f || v > VCC - 0.05f) return NAN;  // open or shorted
  float r = TEMP_R_FIXED * v / (VCC - v);
  float invT = 1.0f / 298.15f + logf(r / NTC_R25) / NTC_BETA;
  float c = 1.0f / invT - 273.15f;
  return (c < 0.0f || c > 80.0f) ? NAN : c;  // outside water range = not wired / faulty
}

// Details of the last TDS read, for the "status" command.
float lastVf = 0, lastVr = 0, lastRef = R_REF_LO;

// Resistance of the water using one reference resistor. The other reference
// pin floats so it doesn't load the sense node. Polarity flips every sample so
// no net DC flows (DC would corrode the electrodes and drift).
float measureOhms(int drivePin, int idlePin, float rRef) {
  constexpr int CYCLES = 32;
  // The ESP32 ADC flattens out below ~0.15 V and above ~3.05 V, so readings
  // there mean "out of range", not a real value.
  constexpr float V_MIN = 0.15f, V_MAX = 3.05f;
  pinMode(idlePin, INPUT);
  pinMode(drivePin, OUTPUT);

  float sum = 0, sumVf = 0, sumVr = 0;
  int good = 0;
  for (int i = 0; i < CYCLES; i++) {
    digitalWrite(drivePin, HIGH);
    digitalWrite(PIN_TDS_B, LOW);
    delayMicroseconds(100);
    float vf = analogReadMilliVolts(PIN_TDS_SENSE) / 1000.0f;

    digitalWrite(drivePin, LOW);
    digitalWrite(PIN_TDS_B, HIGH);
    delayMicroseconds(100);
    float vr = analogReadMilliVolts(PIN_TDS_SENSE) / 1000.0f;

    // forward: VCC -> rRef -> node -> water -> 0V
    // reverse: VCC -> water -> node -> rRef -> 0V
    sumVf += vf;
    sumVr += vr;
    if (vf > V_MIN && vf < V_MAX && vr > V_MIN && vr < V_MAX) {
      float rf = rRef * vf / (VCC - vf);
      float rr = rRef * (VCC - vr) / vr;
      sum += (rf + rr) / 2;
      good++;
    }
  }
  digitalWrite(drivePin, LOW);
  digitalWrite(PIN_TDS_B, LOW);
  lastVf = sumVf / CYCLES;
  lastVr = sumVr / CYCLES;
  lastRef = rRef;
  return good ? sum / good : INFINITY;  // INFINITY = dry probe, open wire or very pure water
}

// Auto-range: try 4.7k first; for high-resistance (low-ppm) water switch to
// 47k. If the 47k resistor isn't fitted, that reading fails and 4.7k is kept.
float readWaterOhms() {
  float r = measureOhms(PIN_TDS_LO, PIN_TDS_HI, R_REF_LO);
  if (isinf(r) || r > RANGE_SWITCH) {
    float vf = lastVf, vr = lastVr;
    float rHi = measureOhms(PIN_TDS_HI, PIN_TDS_LO, R_REF_HI);
    if (!isinf(rHi)) return rHi;
    lastVf = vf; lastVr = vr; lastRef = R_REF_LO;
  }
  return r;
}

float compensation(float tempC) {
  return 1.0f + 0.02f * ((isnan(tempC) ? 25.0f : tempC) - 25.0f);
}

float tdsPpm(float ohms, float tempC) {
  if (isinf(ohms)) return 0;
  float ec = cellK / ohms * 1e6f;  // uS/cm at water temperature
  return ec / compensation(tempC) * TDS_FACTOR;
}

// ---------------------------------------------------------------- buffer --
struct Reading {
  time_t ts;
  float flowLpm, liters, totalLiters, tempC, tdsPpm;
};

constexpr size_t BUF_CAP = 1000;  // ~2.7 hours at 10 s if the server is down
Reading buf[BUF_CAP];
size_t bufHead = 0, bufCount = 0;

void pushReading(const Reading& r) {
  buf[(bufHead + bufCount) % BUF_CAP] = r;
  if (bufCount < BUF_CAP) bufCount++;
  else bufHead = (bufHead + 1) % BUF_CAP;  // full: drop the oldest
}

void appendNum(String& s, float v, int digits) {
  if (isnan(v) || isinf(v)) s += "null";
  else s += String(v, digits);
}

void sendPending() {
  if (bufCount == 0 || WiFi.status() != WL_CONNECTED) return;
  size_t n = min(bufCount, (size_t)50);

  String body = "[";
  for (size_t i = 0; i < n; i++) {
    const Reading& r = buf[(bufHead + i) % BUF_CAP];
    char ts[25];
    struct tm t;
    gmtime_r(&r.ts, &t);
    strftime(ts, sizeof ts, "%Y-%m-%dT%H:%M:%SZ", &t);
    if (i) body += ",";
    body += "{\"device_id\":\"" DEVICE_ID "\",\"ts\":\"";
    body += ts;
    body += "\",\"flow_lpm\":";   appendNum(body, r.flowLpm, 3);
    body += ",\"liters\":";       appendNum(body, r.liters, 4);
    body += ",\"total_liters\":"; appendNum(body, r.totalLiters, 3);
    body += ",\"temp_c\":";       appendNum(body, r.tempC, 2);
    body += ",\"tds_ppm\":";      appendNum(body, r.tdsPpm, 1);
    body += "}";
  }
  body += "]";

  HTTPClient http;
  http.setTimeout(5000);
  http.begin(SERVER_URL "/api/readings");
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  int code = http.POST(body);
  http.end();

  if (code >= 200 && code < 300) {
    bufHead = (bufHead + n) % BUF_CAP;
    bufCount -= n;
  } else {
    Serial.printf("send failed (%d), %u buffered\n", code, (unsigned)bufCount);
  }
}

// ---------------------------------------------------------------- serial --
void printStatus() {
  float t = readTempC();
  float ohms = readWaterOhms();
  Serial.printf("temp %.2f C | water %.0f ohm (ref %.1fk, fwd %.3f V, rev %.3f V) | TDS %.1f ppm | cellK %.4f | ppl %.1f | wifi %s\n",
                t, ohms, lastRef / 1000, lastVf, lastVr, tdsPpm(ohms, t), cellK, pulsesPerLiter,
                WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString().c_str() : "down");
}

void handleSerial() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();

  if (line == "status") {
    printStatus();
  } else if (line.startsWith("tds ")) {
    float ppm = line.substring(4).toFloat();
    float t = readTempC();
    float ohms = readWaterOhms();
    if (ppm <= 0 || isinf(ohms)) { Serial.println("need probe in solution and ppm > 0"); return; }
    cellK = ppm / TDS_FACTOR * compensation(t) * ohms / 1e6f;
    prefs.putFloat("cellK", cellK);
    Serial.printf("saved cellK = %.4f\n", cellK);
  } else if (line == "flowstart") {
    drainPulses();
    calPulses = 0;
    calibratingFlow = true;
    Serial.println("pour exactly 1 L, then type flowstop");
  } else if (line == "flowstop" && calibratingFlow) {
    drainPulses();
    calibratingFlow = false;
    if (calPulses == 0) { Serial.println("no pulses seen - check wiring"); return; }
    pulsesPerLiter = calPulses;
    prefs.putFloat("ppl", pulsesPerLiter);
    Serial.printf("saved pulses per liter = %u\n", (unsigned)calPulses);
  } else if (line.startsWith("ppl ")) {
    float v = line.substring(4).toFloat();
    if (v <= 0) { Serial.println("ppl must be > 0"); return; }
    pulsesPerLiter = v;
    prefs.putFloat("ppl", pulsesPerLiter);
    Serial.printf("saved pulses per liter = %.1f\n", pulsesPerLiter);
  } else if (line.length()) {
    Serial.println("commands: status | tds <ppm> | flowstart | flowstop | ppl <n>");
  }
}

// ------------------------------------------------------------------- ota --
// Starts once WiFi is up (mDNS needs a network), then listens for uploads.
bool otaStarted = false;

void handleOta() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (!otaStarted) {
    ArduinoOTA.setHostname(DEVICE_ID);
    ArduinoOTA.setPassword(OTA_PASS);
    ArduinoOTA.onStart([] { Serial.println("ota: update starting"); });
    ArduinoOTA.onEnd([] { Serial.println("ota: done, rebooting"); });
    ArduinoOTA.onError([](ota_error_t e) { Serial.printf("ota: error %u\n", e); });
    ArduinoOTA.begin();
    otaStarted = true;
    Serial.printf("ota: ready at %s.local (%s)\n", DEVICE_ID, WiFi.localIP().toString().c_str());
  }
  ArduinoOTA.handle();
}

// ------------------------------------------------------------------ main --
uint32_t lastSampleMs = 0;

void setup() {
  Serial.begin(115200);

  prefs.begin("water", false);
  cellK = prefs.getFloat("cellK", 1.0f);
  pulsesPerLiter = prefs.getFloat("ppl", 450.0f);  // placeholder until calibrated

  pinMode(PIN_TDS_LO, OUTPUT);
  pinMode(PIN_TDS_HI, INPUT);
  pinMode(PIN_TDS_B, OUTPUT);
  digitalWrite(PIN_TDS_LO, LOW);
  digitalWrite(PIN_TDS_B, LOW);
  analogSetPinAttenuation(PIN_TDS_SENSE, ADC_11db);
  analogSetPinAttenuation(PIN_TEMP, ADC_11db);

  pinMode(PIN_FLOW, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_FLOW), onPulse, RISING);

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  configTime(0, 0, "pool.ntp.org", "time.google.com");

  lastSampleMs = millis();
  Serial.println("water sensor started; type 'status' for a reading");
}

void loop() {
  handleOta();
  handleSerial();
  drainPulses();

  uint32_t now = millis();
  if (now - lastSampleMs >= SAMPLE_MS) {
    float elapsedMin = (now - lastSampleMs) / 60000.0f;
    lastSampleMs = now;

    time_t ts = time(nullptr);
    if (ts > 1700000000) {  // wait until NTP has set the clock
      float liters = samplePulses / pulsesPerLiter;
      samplePulses = 0;
      totalLiters += liters;

      float t = readTempC();
      Reading r{ts, liters / elapsedMin, liters, totalLiters, t, tdsPpm(readWaterOhms(), t)};
      pushReading(r);
      Serial.printf("flow %.2f L/min | %.2f L total | %.2f C | %.1f ppm\n",
                    r.flowLpm, r.totalLiters, r.tempC, r.tdsPpm);
    }
    sendPending();
  }
  delay(5);
}
