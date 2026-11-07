// SensX25 -> Arduino App Lab (UNO Q)
// MCU side: reads sensor frames over UART (D0/D1), validates CRC,
// and sends the latest frame to the Python side via the Bridge ~20x per second.

#include <Arduino_RouterBridge.h>

// Keep whichever one worked in your test sketch (Serial or Serial1)
#define SENSOR_SERIAL Serial

const uint8_t FRAME_LEN = 53;
uint8_t buf[FRAME_LEN];
uint8_t idx = 0;

uint16_t pixels[25];            // p0..p24 in the order sent
bool newFrame = false;
unsigned long goodFrames = 0, badCrc = 0;
unsigned long lastSend = 0;
const unsigned long SEND_INTERVAL_MS = 50;   // 20 Hz to Python

uint8_t crc8_maxim(const uint8_t *data, uint8_t len) {
  uint8_t crc = 0;
  for (uint8_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (uint8_t b = 0; b < 8; b++)
      crc = (crc & 1) ? (crc >> 1) ^ 0x8C : (crc >> 1);
  }
  return crc;
}

void handleByte(uint8_t b) {
  if (idx == 0) { if (b == 0xFF) buf[idx++] = b; return; }
  if (idx == 1) { if (b == 0xFF) buf[idx++] = b; else idx = 0; return; }

  buf[idx++] = b;
  if (idx < FRAME_LEN) return;

  if (crc8_maxim(&buf[2], 50) == buf[52]) {
    for (uint8_t i = 0; i < 25; i++)
      pixels[i] = ((uint16_t)buf[2 + 2 * i] << 8) | buf[3 + 2 * i];
    goodFrames++;
    newFrame = true;
    idx = 0;
  } else {
    badCrc++;
    // Re-sync on the next FF FF inside the buffer
    uint8_t start = 0;
    for (uint8_t i = 1; i < FRAME_LEN - 1; i++) {
      if (buf[i] == 0xFF && buf[i + 1] == 0xFF) { start = i; break; }
    }
    if (start) {
      idx = FRAME_LEN - start;
      memmove(buf, &buf[start], idx);
    } else {
      idx = (buf[FRAME_LEN - 1] == 0xFF) ? 1 : 0;
      if (idx) buf[0] = 0xFF;
    }
  }
}

void setup() {
  Bridge.begin();
  SENSOR_SERIAL.begin(921600);
}

void loop() {
  while (SENSOR_SERIAL.available()) {
    handleByte((uint8_t)SENSOR_SERIAL.read());
  }

  if (newFrame && millis() - lastSend >= SEND_INTERVAL_MS) {
    lastSend = millis();
    newFrame = false;

    // Send as one comma-separated string in the order sent: "p0,p1,...,p24"
    String msg;
    msg.reserve(130);
    for (uint8_t i = 0; i < 25; i++) {
      msg += pixels[i];
      if (i < 24) msg += ',';
    }
    Bridge.notify("sensx_frame", msg);
  }
}
