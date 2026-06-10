/*
 * IoTAPS ESP32 - 3 LED Control
 * 
 * Connects to your local IoTAPS MQTT broker and:
 *   - Publishes telemetry (LED states) every 5 seconds
 *   - Listens for commands to toggle LED1, LED2, LED3
 *
 * Device Token: dT_cDW3aix7
 * Server: 157.51.92.102 (your local IP)
 * MQTT Port: 1883
 *
 * Wiring:
 *   GPIO 2  -> LED1 (built-in on most ESP32 boards)
 *   GPIO 4  -> LED2
 *   GPIO 5  -> LED3
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ============ CONFIGURATION ============
// WiFi
const char* WIFI_SSID     = "admin";      // <-- Change this
const char* WIFI_PASSWORD = "123456789";   // <-- Change this

// IoTAPS connection
const char* IOTAPS_SERVER = "157.51.92.102";        // Your local PC IP
const int   IOTAPS_PORT   = 1883;                   // MQTT port
const char* DEVICE_TOKEN  = "dT_cDW3aix7";         // Your device token

// Token is used as both MQTT username AND password
const char* MQTT_USER = "dT_cDW3aix7";
const char* MQTT_PASS = "dT_cDW3aix7";

// LED Pins
#define LED1_PIN 2    // Built-in LED (blue)
#define LED2_PIN 4    // External LED
#define LED3_PIN 5    // External LED

// Telemetry interval (ms)
#define TELEMETRY_INTERVAL 5000

// ============ MQTT TOPICS ============
// Format: iotaps/{org_id}/{device_id}/{type}
// For token-based auth, we use the token as the topic prefix
String topicTelemetry;
String topicCommand;
String topicAck;
String topicStatus;

// ============ GLOBALS ============
WiFiClient espClient;
PubSubClient mqtt(espClient);

bool led1State = false;
bool led2State = false;
bool led3State = false;

unsigned long lastTelemetry = 0;

// ============ SETUP ============
void setup() {
  Serial.begin(115200);
  delay(100);
  
  Serial.println();
  Serial.println("=================================");
  Serial.println("  IoTAPS ESP32 - 3 LED Control");
  Serial.println("=================================");
  Serial.printf("  Token: %s\n", DEVICE_TOKEN);
  Serial.printf("  Server: %s:%d\n", IOTAPS_SERVER, IOTAPS_PORT);
  Serial.println();

  // Setup LED pins
  pinMode(LED1_PIN, OUTPUT);
  pinMode(LED2_PIN, OUTPUT);
  pinMode(LED3_PIN, OUTPUT);
  
  digitalWrite(LED1_PIN, LOW);
  digitalWrite(LED2_PIN, LOW);
  digitalWrite(LED3_PIN, LOW);

  // Build MQTT topics using the token as identifier
  // You'll need to replace ORG_ID and DEVICE_ID with actual values from IoTAPS
  // For now, use token-based topics:
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
    sendTelemetry();
  }
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
    // Connect with token as both username and password
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
  StaticJsonDocument<256> doc;
  
  doc["led1"] = led1State ? 1 : 0;
  doc["led2"] = led2State ? 1 : 0;
  doc["led3"] = led3State ? 1 : 0;
  doc["uptime"] = millis() / 1000;
  doc["wifi_rssi"] = WiFi.RSSI();
  doc["free_heap"] = ESP.getFreeHeap();
  
  char buffer[256];
  serializeJson(doc, buffer);
  
  mqtt.publish(topicTelemetry.c_str(), buffer);
  Serial.printf("[TX] %s\n", buffer);
}

// ============ COMMAND HANDLER ============
void onCommand(char* topic, byte* payload, unsigned int length) {
  // Parse the JSON command
  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  
  if (err) {
    Serial.printf("[CMD] Parse error: %s\n", err.c_str());
    return;
  }
  
  const char* type = doc["type"] | "";
  const char* target = doc["target"] | "";  // "led1", "led2", "led3"
  int value = doc["value"] | -1;            // 1=ON, 0=OFF
  const char* cmdId = doc["command_id"] | "";
  
  Serial.printf("[CMD] type=%s target=%s value=%d\n", type, target, value);
  
  bool executed = false;
  
  // Handle LED commands
  if (strcmp(type, "digital_write") == 0 || strcmp(type, "toggle") == 0) {
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
    delay(100);
    digitalWrite(LED1_PIN, LOW);
    digitalWrite(LED2_PIN, LOW);
    digitalWrite(LED3_PIN, LOW);
    delay(100);
  }
}
