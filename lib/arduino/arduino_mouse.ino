/*
 * Lunar LITE - Arduino HID mouse
 * Use with a board that supports Mouse (e.g. Leonardo, Micro, Pro Micro).
 * Protocol: 115200 baud
 *   M,dx,dy\n  = relative move (dx, dy)
 *   L\n        = left click
 * Install: Arduino IDE -> Sketch -> Include Library -> Mouse (built-in on Leonardo/Micro).
 */
#include "Mouse.h"

#define BAUD 115200
#define BUF_SIZE 32

char buf[BUF_SIZE];
int idx = 0;

void setup() {
  Serial.begin(BAUD);
  Mouse.begin();
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      buf[idx] = '\0';
      if (idx > 0) {
        if (buf[0] == 'M') {
          int dx = 0, dy = 0;
          sscanf(buf + 2, "%d,%d", &dx, &dy);
          Mouse.move(dx, dy, 0);
        } else if (buf[0] == 'L') {
          Mouse.click(MOUSE_LEFT);
        }
      }
      idx = 0;
    } else if (idx < BUF_SIZE - 1) {
      buf[idx++] = c;
    }
  }
}
