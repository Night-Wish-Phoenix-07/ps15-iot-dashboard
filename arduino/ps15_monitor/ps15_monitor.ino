// PS15 Edge IoT Monitor - Arduino Uno R3
// Libraries: "DHT sensor library" (Adafruit) and "LiquidCrystal I2C" (Frank de Brabander)
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DHT.h>

// ---------- Pins (from your wiring diagram) ----------
#define DHT_PIN     2
#define GREEN_LED   3
#define RED_LED     5
#define BUZZER_PIN  6    // D6 -> 1k -> BC547 base
#define RELAY_PIN   7
#define TRIG_PIN    9
#define ECHO_PIN    10
#define VIB_PIN     12
#define MQ2_PIN     A0
#define MQ135_PIN   A1   // LCD uses A4 (SDA) / A5 (SCL)

// ---------- Settings you may need to change ----------
#define LCD_ADDR          0x27     // try 0x3F if the LCD stays blank
#define VIB_ACTIVE        HIGH     // SW-420 gives HIGH on vibration; LOW for a micro/tilt switch
#define RELAY_ACTIVE_LOW  true     // set false if your relay switches the wrong way round
#define NEAR_CM           20
#define TEMP_LIMIT_C      35
#define MQ2_LIMIT         400      // relative value, tune it
#define MQ135_LIMIT       400
#define WARMUP_MS         60000UL
#define SEND_EVERY_MS     2000UL

#define F_SMOKE 1
#define F_AIR   2
#define F_NEAR  4
#define F_VIB   8
#define F_TEMP  16

DHT dht(DHT_PIN, DHT11);
LiquidCrystal_I2C lcd(LCD_ADDR, 16, 2);

float lastT = 0, lastH = 0;
bool vibSeen = false;
byte status = 0;   // 0 SAFE, 1 WARNING, 2 DANGER

void setRelay(bool on) {
  digitalWrite(RELAY_PIN, (on != RELAY_ACTIVE_LOW) ? HIGH : LOW);
}

float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long us = pulseIn(ECHO_PIN, HIGH, 30000UL);
  if (us == 0) return -1;
  return us * 0.0343 / 2.0;
}

void setup() {
  Serial.begin(9600);
  digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? HIGH : LOW);  // start with relay OFF
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(GREEN_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(VIB_PIN, INPUT);
  dht.begin();
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0); lcd.print(F("PS15 IoT Monitor"));
  lcd.setCursor(0, 1); lcd.print(F("Starting...     "));
  delay(1500);
}

void loop() {
  // ----- read sensors -----
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (!isnan(t)) lastT = t;
  if (!isnan(h)) lastH = h;
  float d = readDistanceCm();
  int mq2 = analogRead(MQ2_PIN);
  int mq135 = analogRead(MQ135_PIN);
  bool vib = vibSeen || (digitalRead(VIB_PIN) == VIB_ACTIVE);
  vibSeen = false;
  bool warm = millis() < WARMUP_MS;

  // ----- decide status -----
  int flags = 0;
  if (!warm && mq2 > MQ2_LIMIT)     flags |= F_SMOKE;
  if (!warm && mq135 > MQ135_LIMIT) flags |= F_AIR;
  if (d > 0 && d < NEAR_CM)         flags |= F_NEAR;
  if (vib)                          flags |= F_VIB;
  if (lastT > TEMP_LIMIT_C)         flags |= F_TEMP;

  if (flags & (F_SMOKE | F_AIR))                  status = 2;
  else if (flags & (F_NEAR | F_VIB | F_TEMP))     status = 1;
  else                                            status = 0;

  // ----- outputs -----
  digitalWrite(GREEN_LED, status == 0 ? HIGH : LOW);
  digitalWrite(RED_LED, status >= 1 ? HIGH : LOW);
  if (status != 2) digitalWrite(BUZZER_PIN, LOW);   // in DANGER it beeps in the wait loop below
  bool relayOn = (status == 2) || (flags & F_TEMP);
  setRelay(relayOn);

  // ----- LCD (16x2) -----
  char l1[20], l2[20];
  if (d < 0) snprintf(l1, sizeof(l1), "T%2d H%2d D---cm  ", (int)lastT, (int)lastH);
  else       snprintf(l1, sizeof(l1), "T%2d H%2d D%3dcm  ", (int)lastT, (int)lastH, (int)d);
  if (warm)  snprintf(l2, sizeof(l2), "Gas warming up..");
  else       snprintf(l2, sizeof(l2), "S%4d A%4d %s", mq2, mq135,
                      status == 0 ? "SAFE" : (status == 1 ? "WARN" : "DANG"));
  lcd.setCursor(0, 0); lcd.print(l1);
  lcd.setCursor(0, 1); lcd.print(l2);

  // ----- one CSV line for the computer -----
  // temperature,humidity,distance,mq2,mq135,flags,status,relay,warmup
  Serial.print(lastT, 1);  Serial.print(',');
  Serial.print(lastH, 1);  Serial.print(',');
  Serial.print(d, 1);      Serial.print(',');
  Serial.print(mq2);       Serial.print(',');
  Serial.print(mq135);     Serial.print(',');
  Serial.print(flags);     Serial.print(',');
  Serial.print(status);    Serial.print(',');
  Serial.print(relayOn ? 1 : 0); Serial.print(',');
  Serial.println(warm ? 1 : 0);

  // ----- wait, but keep watching for vibration and beep in DANGER -----
  unsigned long start = millis();
  while (millis() - start < SEND_EVERY_MS) {
    if (digitalRead(VIB_PIN) == VIB_ACTIVE) vibSeen = true;
    if (status == 2) digitalWrite(BUZZER_PIN, ((millis() / 250) % 2) ? HIGH : LOW);
    delay(10);
  }
}
