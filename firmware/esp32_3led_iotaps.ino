/*
 * IoTAPS ESP32 - Demo Device
 * 
 * Features:
 *   - 3 LEDs with separate ON/OFF toggle control
 *   - 1 LED with PWM brightness (slider control, 0-255)
 *   - Dummy temperature sensor (random realistic values)
 *   - Dummy voltage sensor (random realistic values)
 *
 * Commands supported:
 *   {"type":"on",  "target":"led1"}           → LED1 ON
 *   {"type":"off", "target":"led1"}           → LED1 OFF
 *   {"type":"on",  "target":"led2"}           → LED2 ON
 *   {"type":"off", "target":"led2"}           → LED2 OFF
 *   {"type":"on",  "target":"led3"}           → LED3 ON
 *   {"type":"off", "target":"led3"}           → LED3 OFF
 *   {"type":"value","target":"brightness","value":128}  → PWM 0-255
 *   {"type":"digital_write","target":"led1","value":1}  → Legacy format
 *
 * Telemetry published every 5s:
 *   {"led1":0/1, "led2":0/1, "led3":0/1, "brightness":0-255,
 *    "temperature":20-45, "voltage":3.0-3.6, "uptime":sec,
 *    "wifi_rssi":dBm, "free_heap":bytes}
 *
 * Wiring:
 *   GPIO 2  → LED1 (built-in blue LED, toggle)
 *   GPIO 4  → LED2 (external, toggle)
 *   GPIO 5  → LED3 (external, toggle)
 *   GPIO 18 → LED4 (PWM brightness, slider)
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ============ CONFIGURATION ============
// WiFi
const char* WIFI_SSID     = "admin";
const char* WIFI_PASSWORD = "123456789";

// IoTAPS connection
const char* IOTAPS_SERVER = "mqtt.iotaps.com";       // MQTT subdomain (DNS-only, bypasses Cloudflare)
const int   IOTAPS_PORT   = 1883;                   // MQTT port
const char* DEVICE_TOKEN  = "dT_4rB9EvnN";         // Your device token

// Token is used as both MQTT username AND password
const char* MQTT_USER = "dT_4rB9EvnN";
const char* MQTT_PASS = "dT_4rB9EvnN";

// LED Pins
#define LED1_PIN 2    // Built-in LED (blue) - toggle
#define LED2_PIN 4    // External LED - toggle
#define LED3_PIN 5    // External LED - toggle
#define LED4_PIN 18   // PWM LED - brightness slider

// PWM settings for LED4
#define PWM_CHANNEL 0
#define PWM_FREQ 5000
#define PWM_RESOLUTION 8  // 0-255

// Telemetry interval (ms)
#define TELEMETRY_INTERVAL 5000

// ============ MQTT TOPICS ============
String topicTelemetry;
String topicCommand;
String topicAck;
String topicStatus;

// ============ GLOBALS ============
WiFiClient espClient;
PubSubClient mqtt(espClient);

// LED states
bool led1State = false;
bool led2State = false;
bool led3State = false;
int brightnessValue = 0;  // 0-255 for PWM LED4

// Simulated sensors
float temperature = 25.0;
float voltage = 3.3;

unsigned long lastTelemetry = 0;

// ============ SETUP ============
void setup() {
  Serial.begin(115200);
  delay(100);
  
  Serial.println();
  Serial.println("=================================");
  Serial.println("  IoTAPS ESP32 - Demo Device");
  Serial.println("=================================");
  Serial.printf("  Token: %s\n", DEVICE_TOKEN);
  Serial.printf("  Server: %s:%d\n", IOTAPS_SERVER, IOTAPS_PORT);
  Serial.println("  Features:");
  Serial.println("    - 3x Toggle LEDs (GPIO 2,4,5)");
  Serial.println("    - 1x PWM LED Brightness (GPIO 18)");
  Serial.println("    - Temperature sensor (simulated)");
  Serial.println("    - Voltage sensor (simulated)");
  Serial.println("=================================\n");

  // Setup LED pins (toggle)
  pinMode(LED1_PIN, OUTPUT);
  pinMode(LED2_PIN, OUTPUT);
  pinMode(LED3_PIN, OUTPUT);
  
  digitalWrite(LED1_PIN, LOW);
  digitalWrite(LED2_PIN, LOW);
  digitalWrite(LED3_PIN, LOW);

  // Setup PWM for brightness LED
  ledcSetup(PWM_CHANNEL, PWM_FREQ, PWM_RESOLUTION);
  ledcAttachPin(LED4_PIN, PWM_CHANNEL);
  ledcWrite(PWM_CHANNEL, 0);

  // Build MQTT topics
  topicTelemetry = String("iotaps/") + DEVICE_TOKEN + "/telemetry";
  topicCommand   = String("iotaps/") + DEVICE_TOKEN + "/command";
  topicAck       = String("iotaps/") + DEVICE_TOKEN + "/ack";
  topicStatus    = String("iotaps/") + DEVICE_TOKEN + "/status";

  // Connect WiFi
  connectWiFi();
  
  // Setup MQTT
  mqtt.setServer(IOTAPS_SERVER, IOTAPS_PORT);
  mqtt.setCallback(onCommand);
  mqtt.setBufferSize(512);
  
  // Connect MQTT
  connectMQTT();
}

// ============ LOOP ============
void loop() {
  // Maintain connections
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }
  if (!mqtt.connected()) {
    connectMQTT();
  }
  mqtt.loop();

  // Send telemetry periodically
  if (millis() - lastTelemetry >= TELEMETRY_INTERVAL) {
    lastTelemetry = millis();
    updateSensors();
    sendTelemetry();
  }
}

// ============ SENSOR SIMULATION ============
void updateSensors() {
  // Simulate temperature: slowly drifts between 20-45°C with small random noise
  temperature += random(-10, 11) * 0.1;  // ±1.0°C drift
  temperature = constrain(temperature, 20.0, 45.0);
  
  // Simulate voltage: small fluctuation around 3.3V (like a battery)
  voltage += random(-5, 6) * 0.01;  // ±0.05V drift
  voltage = constrain(voltage, 3.0, 3.6);
}

// ============ WiFi ============
void connectWiFi() {
  Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WiFi] FAILED! Retrying in 5s...");
    delay(5000);
  }
}

// ============ MQTT ============
void connectMQTT() {
  Serial.printf("[MQTT] Connecting to %s:%d...\n", IOTAPS_SERVER, IOTAPS_PORT);
  
  // LWT (Last Will) - marks device offline if connection drops
  String lwt = topicStatus;
  
  while (!mqtt.connected()) {
    if (mqtt.connect(DEVICE_TOKEN, MQTT_USER, MQTT_PASS, lwt.c_str(), 1, true, "{\"status\":\"offline\"}")) {
      Serial.println("[MQTT] Connected!");
      
      // Subscribe to command topic
      mqtt.subscribe(topicCommand.c_str());
      Serial.printf("[MQTT] Subscribed: %s\n", topicCommand.c_str());
      
      // Publish online status
      mqtt.publish(topicStatus.c_str(), "{\"status\":\"online\"}", true);
      
      // Flash all LEDs once to indicate connection
      flashAllLeds();
      
    } else {
      Serial.printf("[MQTT] Failed (rc=%d). Retrying in 3s...\n", mqtt.state());
      delay(3000);
    }
  }
}

// ============ TELEMETRY ============
void sendTelemetry() {
  StaticJsonDocument<384> doc;
  
  // LED toggle states
  doc["led1"] = led1State ? 1 : 0;
  doc["led2"] = led2State ? 1 : 0;
  doc["led3"] = led3State ? 1 : 0;
  
  // PWM brightness value
  doc["brightness"] = brightnessValue;
  
  // Simulated sensors
  doc["temperature"] = round(temperature * 10.0) / 10.0;  // 1 decimal
  doc["voltage"] = round(voltage * 100.0) / 100.0;        // 2 decimals
  
  // System info
  doc["uptime"] = millis() / 1000;
  doc["wifi_rssi"] = WiFi.RSSI();
  doc["free_heap"] = ESP.getFreeHeap();
  
  char buffer[384];
  serializeJson(doc, buffer);
  
  mqtt.publish(topicTelemetry.c_str(), buffer);
  Serial.printf("[TX] %s\n", buffer);
}

// ============ COMMAND HANDLER ============
void onCommand(char* topic, byte* payload, unsigned int length) {
  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  
  if (err) {
    Serial.printf("[CMD] Parse error: %s\n", err.c_str());
    return;
  }
  
  const char* type = doc["type"] | "";
  const char* target = doc["target"] | "";
  int value = doc["value"] | -1;
  const char* cmdId = doc["command_id"] | "";
  
  Serial.printf("[CMD] type=%s target=%s value=%d\n", type, target, value);
  
  bool executed = false;
  
  // === TOGGLE COMMANDS (on/off) ===
  if (strcmp(type, "on") == 0 || strcmp(type, "off") == 0) {
    bool turnOn = (strcmp(type, "on") == 0);
    
    if (strcmp(target, "led1") == 0 || strlen(target) == 0) {
      led1State = turnOn;
      digitalWrite(LED1_PIN, led1State ? HIGH : LOW);
      executed = true;
      Serial.printf("[LED1] %s\n", turnOn ? "ON" : "OFF");
    }
    if (strcmp(target, "led2") == 0) {
      led2State = turnOn;
      digitalWrite(LED2_PIN, led2State ? HIGH : LOW);
      executed = true;
      Serial.printf("[LED2] %s\n", turnOn ? "ON" : "OFF");
    }
    if (strcmp(target, "led3") == 0) {
      led3State = turnOn;
      digitalWrite(LED3_PIN, led3State ? HIGH : LOW);
      executed = true;
      Serial.printf("[LED3] %s\n", turnOn ? "ON" : "OFF");
    }
  }
  
  // === BRIGHTNESS/SLIDER COMMAND (value 0-255) ===
  else if (strcmp(type, "value") == 0) {
    if (strcmp(target, "brightness") == 0 || strcmp(target, "led4") == 0 || strlen(target) == 0) {
      brightnessValue = constrain(value, 0, 255);
      ledcWrite(PWM_CHANNEL, brightnessValue);
      executed = true;
      Serial.printf("[BRIGHTNESS] Set to %d\n", brightnessValue);
    }
  }
  
  // === LEGACY digital_write FORMAT ===
  else if (strcmp(type, "digital_write") == 0 || strcmp(type, "toggle") == 0) {
    if (strcmp(target, "led1") == 0) {
      led1State = (value == 1);
      digitalWrite(LED1_PIN, led1State ? HIGH : LOW);
      executed = true;
    } else if (strcmp(target, "led2") == 0) {
      led2State = (value == 1);
      digitalWrite(LED2_PIN, led2State ? HIGH : LOW);
      executed = true;
    } else if (strcmp(target, "led3") == 0) {
      led3State = (value == 1);
      digitalWrite(LED3_PIN, led3State ? HIGH : LOW);
      executed = true;
    } else if (strcmp(target, "brightness") == 0 || strcmp(target, "led4") == 0) {
      brightnessValue = constrain(value, 0, 255);
      ledcWrite(PWM_CHANNEL, brightnessValue);
      executed = true;
    }
  }
  
  // Send ACK back to IoTAPS
  if (strlen(cmdId) > 0) {
    StaticJsonDocument<128> ack;
    ack["command_id"] = cmdId;
    ack["status"] = executed ? "executed" : "failed";
    ack["target"] = target;
    ack["value"] = value;
    
    char ackBuf[128];
    serializeJson(ack, ackBuf);
    mqtt.publish(topicAck.c_str(), ackBuf);
    Serial.printf("[ACK] %s\n", ackBuf);
  }
  
  // Send immediate telemetry update after command
  sendTelemetry();
}

// ============ HELPERS ============
void flashAllLeds() {
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED1_PIN, HIGH);
    digitalWrite(LED2_PIN, HIGH);
    digitalWrite(LED3_PIN, HIGH);
    ledcWrite(PWM_CHANNEL, 255);
    delay(100);
    digitalWrite(LED1_PIN, LOW);
    digitalWrite(LED2_PIN, LOW);
    digitalWrite(LED3_PIN, LOW);
    ledcWrite(PWM_CHANNEL, 0);
    delay(100);
  }
}
