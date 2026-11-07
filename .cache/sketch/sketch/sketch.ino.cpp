#include <Arduino.h>
#line 1 "/home/arduino/ArduinoApps/sensx25live/sketch/sketch.ino"
#include <Arduino_RouterBridge.h>
#include <string.h>

constexpr size_t FRAME_SIZE = 53;
uint8_t frame[FRAME_SIZE];
size_t used = 0;
uint8_t reply[7] = {};
uint16_t grid[25] = {};
uint32_t sequence = 0, crcErrors = 0, lastFrame = 0, lastQuery = 0;
bool hasFrame = false, pending = false, awaitingReply = false;
int currentMode = -1, targetMode = -1, attempts = 0, modeError = 0;

#line 13 "/home/arduino/ArduinoApps/sensx25live/sketch/sketch.ino"
uint8_t crc8(const uint8_t* data, size_t length);
#line 23 "/home/arduino/ArduinoApps/sensx25live/sketch/sketch.ino"
uint16_t crc16(const uint8_t* data, size_t length);
#line 33 "/home/arduino/ArduinoApps/sensx25live/sketch/sketch.ino"
void sendCommand(uint8_t function, uint16_t value);
#line 42 "/home/arduino/ArduinoApps/sensx25live/sketch/sketch.ino"
bool setMode(int mode);
#line 60 "/home/arduino/ArduinoApps/sensx25live/sketch/sketch.ino"
String snapshot();
#line 72 "/home/arduino/ArduinoApps/sensx25live/sketch/sketch.ino"
void consumeByte(uint8_t value);
#line 117 "/home/arduino/ArduinoApps/sensx25live/sketch/sketch.ino"
void setup();
#line 130 "/home/arduino/ArduinoApps/sensx25live/sketch/sketch.ino"
void loop();
#line 13 "/home/arduino/ArduinoApps/sensx25live/sketch/sketch.ino"
uint8_t crc8(const uint8_t* data, size_t length) {
  uint8_t crc = 0;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; ++bit)
      crc = (crc & 1) ? (crc >> 1) ^ 0x8C : crc >> 1;
  }
  return crc;
}

uint16_t crc16(const uint8_t* data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; ++bit)
      crc = (crc & 1) ? (crc >> 1) ^ 0xA001 : crc >> 1;
  }
  return crc;
}

void sendCommand(uint8_t function, uint16_t value) {
  uint8_t command[8] = {1, function, 0x60, 0x05,
                        uint8_t(value >> 8), uint8_t(value), 0, 0};
  uint16_t crc = crc16(command, 6);
  command[6] = crc & 0xFF;
  command[7] = crc >> 8;
  Serial1.write(command, sizeof(command));
}

bool setMode(int mode) {
  if ((mode != 0 && mode != 1) || pending) return false;
  if (currentMode == mode) return true;

  // Mode writes persist in sensor memory; write only on user request.
  sendCommand(0x06, mode);
  currentMode = -1;
  targetMode = mode;
  pending = true;
  awaitingReply = false;
  attempts = 0;
  modeError = 0;
  lastQuery = millis();
  hasFrame = false;
  memset(reply, 0, sizeof(reply));
  return true;
}

String snapshot() {
  // A compact CSV string keeps the RPC response small.
  String result;
  result.reserve(230);
  result += String(sequence) + ",";
  result += String(hasFrame ? millis() - lastFrame : 0xFFFFFFFFUL) + ",";
  result += String(currentMode) + "," + String(pending ? 1 : 0) + ",";
  result += String(modeError) + "," + String(crcErrors);
  for (int i = 0; i < 25; ++i) result += "," + String(grid[i]);
  return result;
}

void consumeByte(uint8_t value) {
  // Detect a CRC-checked Modbus mode response between data frames.
  memmove(reply, reply + 1, 6);
  reply[6] = value;
  if (pending && awaitingReply && reply[0] == 1 &&
      reply[1] == 3 && reply[2] == 2 && reply[3] == 0 && reply[4] <= 1) {
    uint16_t crc = crc16(reply, 5);
    if (reply[5] == (crc & 0xFF) && reply[6] == (crc >> 8) &&
        (targetMode < 0 || reply[4] == targetMode)) {
      currentMode = reply[4];
      pending = false;
      awaitingReply = false;
      modeError = 0;
      hasFrame = false;
      used = 0;
    }
  }

  frame[used++] = value;
  while (used > 0 && (frame[0] != 0xFF ||
         (used >= 2 && frame[1] != 0xFF))) {
    --used;
    memmove(frame, frame + 1, used);
  }
  if (used < FRAME_SIZE) return;

  if (crc8(frame + 2, 50) == frame[52]) {
    // Rotate clockwise so the connector is at the bottom.
    for (int row = 0; row < 5; ++row) {
      for (int col = 0; col < 5; ++col) {
        int offset = 2 + ((4 - col) * 5 + row) * 2;
        grid[row * 5 + col] = (uint16_t(frame[offset]) << 8) | frame[offset + 1];
      }
    }
    ++sequence;
    lastFrame = millis();
    hasFrame = true;
    used = 0;
  } else {
    ++crcErrors;
    --used;
    memmove(frame, frame + 1, used);
  }
}

void setup() {
  Bridge.begin();
  Monitor.begin(115200);
  Serial1.begin(921600);
  Bridge.provide_safe("sensx_snapshot", snapshot);
  Bridge.provide_safe("sensx_set_mode", setMode);

  // Read the saved mode at startup without changing it.
  pending = true;
  lastQuery = millis();
  Monitor.println("SensX25 live receiver ready");
}

void loop() {
  for (int i = 0; i < 1024 && Serial1.available() > 0; ++i) {
    int value = Serial1.read();
    if (value >= 0) consumeByte(uint8_t(value));
  }

  // Poll without blocking incoming sensor frames.
  if (pending && millis() - lastQuery >= 300) {
    if (attempts >= 10) {
      pending = false;
      awaitingReply = false;
      currentMode = -1;
      modeError = 1;
    } else {
      sendCommand(0x03, 1);
      awaitingReply = true;
      ++attempts;
      lastQuery = millis();
    }
  }
}

