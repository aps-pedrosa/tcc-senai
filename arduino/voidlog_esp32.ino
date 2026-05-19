/*
 * VoidLog — Firmware ESP32
 * ─────────────────────────────────────────────────────────────────
 * Hardware:
 *   ESP32 DevKit V1 + RC522 (SPI) + LCD 16x2 I2C + Rotary Encoder KY-040
 *   + Buzzer + LED Verde + LED Vermelho + Botão Reset
 *
 * Bibliotecas (instalar via Library Manager):
 *   MFRC522, LiquidCrystal_I2C, ArduinoJson
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ── WiFi ──────────────────────────────────────────────────────────
const char* WIFI_SSID     = "SUA_REDE_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA_WIFI";
const char* API_HOST      = "http://192.168.1.100:5000";

// ── Pinos ─────────────────────────────────────────────────────────
#define RC522_SS    5
#define RC522_RST   4
#define ENC_CLK    34
#define ENC_DT     35
#define ENC_SW     32
#define BTN_RESET  33
#define BUZZER     25
#define LED_OK     26
#define LED_ERR    27

// ── Periféricos ───────────────────────────────────────────────────
MFRC522           rfid(RC522_SS, RC522_RST);
LiquidCrystal_I2C lcd(0x27, 16, 2);

// ── Tabelas (espelham uid_parser.py) ─────────────────────────────
const char* SETORES[]  = {"","Soldagem","Corte","Usinagem","Furacao",
                           "Montagem","Manutencao","Almoxarifado","Qualidade"};
const char* UNIDADES[] = {"","Und.Centro","Und.BH","Und.Contagem",
                           "Und.Betim","Und.Ibirite"};
const int NUM_SETORES  = 8;
const int NUM_UNIDADES = 5;

// ── Máquina de estados ────────────────────────────────────────────
enum Estado { SEL_SETOR, SEL_UNIDADE, AGUARDAR, PROCESSANDO, RESULTADO };
Estado estado = SEL_SETOR;

int setorSel   = 1;
int unidadeSel = 1;

// ── Encoder ───────────────────────────────────────────────────────
volatile int encPos = 0;
int encPosUlt       = 0;
int clkUlt;
unsigned long tDebounce    = 0;
unsigned long tDebounceBtn = 0;
const unsigned long DEB = 50;

// ── Resultado ─────────────────────────────────────────────────────
unsigned long tResultado = 0;
const unsigned long T_RESULTADO = 3000;

// ── Protótipos ────────────────────────────────────────────────────
void conectarWifi();
void exibirLCD(String l1, String l2);
void bip(bool ok);
void ledStatus(bool ok);
void IRAM_ATTR encISR();
int  lerEnc(int mn, int mx, int atual);
void chamarAPI(String uid);

// ──────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);

  pinMode(BUZZER,   OUTPUT); digitalWrite(BUZZER,  LOW);
  pinMode(LED_OK,   OUTPUT); digitalWrite(LED_OK,  LOW);
  pinMode(LED_ERR,  OUTPUT); digitalWrite(LED_ERR, LOW);
  pinMode(ENC_SW,    INPUT_PULLUP);
  pinMode(BTN_RESET, INPUT_PULLUP);
  pinMode(ENC_CLK,   INPUT);
  pinMode(ENC_DT,    INPUT);
  clkUlt = digitalRead(ENC_CLK);

  attachInterrupt(digitalPinToInterrupt(ENC_CLK), encISR, CHANGE);

  Wire.begin(21, 22);
  lcd.init(); lcd.backlight();
  exibirLCD("VoidLog v1.0", "Iniciando...");

  SPI.begin();
  rfid.PCD_Init();

  conectarWifi();

  estado = SEL_SETOR;
  exibirLCD(">> Setor:", SETORES[setorSel]);
}

// ──────────────────────────────────────────────────────────────────
void loop() {

  // Reset físico: volta sempre para seleção de setor
  if (digitalRead(BTN_RESET) == LOW && millis() - tDebounceBtn > DEB) {
    tDebounceBtn = millis();
    estado = SEL_SETOR;
    encPos = setorSel - 1;
    exibirLCD(">> Setor:", SETORES[setorSel]);
    return;
  }

  // ── SEL_SETOR ───────────────────────────────────────────────────
  if (estado == SEL_SETOR) {
    int novo = lerEnc(0, NUM_SETORES - 1, setorSel - 1);
    if (novo != setorSel - 1) {
      setorSel = novo + 1;
      exibirLCD(">> Setor:", SETORES[setorSel]);
    }
    if (digitalRead(ENC_SW) == LOW && millis() - tDebounce > DEB) {
      tDebounce = millis();
      while (digitalRead(ENC_SW) == LOW) delay(10);
      estado = SEL_UNIDADE;
      encPos = unidadeSel - 1;
      exibirLCD(">> Unidade:", UNIDADES[unidadeSel]);
      bip(true);
    }
  }

  // ── SEL_UNIDADE ─────────────────────────────────────────────────
  else if (estado == SEL_UNIDADE) {
    int novo = lerEnc(0, NUM_UNIDADES - 1, unidadeSel - 1);
    if (novo != unidadeSel - 1) {
      unidadeSel = novo + 1;
      exibirLCD(">> Unidade:", UNIDADES[unidadeSel]);
    }
    if (digitalRead(ENC_SW) == LOW && millis() - tDebounce > DEB) {
      tDebounce = millis();
      while (digitalRead(ENC_SW) == LOW) delay(10);
      estado = AGUARDAR;
      String l1 = String(SETORES[setorSel]).substring(0,7) + "/" +
                  String(UNIDADES[unidadeSel]).substring(4,10);
      exibirLCD(l1, "Aprox. a tag...");
      bip(true); delay(100); bip(true);
    }
  }

  // ── AGUARDAR RFID ───────────────────────────────────────────────
  else if (estado == AGUARDAR) {
    if (!rfid.PICC_IsNewCardPresent()) return;
    if (!rfid.PICC_ReadCardSerial())   return;

    // Lê apenas os 2 primeiros bytes da tag (B1+B2 = peca_code)
    String peca = "";
    for (byte i = 0; i < 2 && i < rfid.uid.size; i++) {
      if (rfid.uid.uidByte[i] < 0x10) peca += "0";
      peca += String(rfid.uid.uidByte[i], HEX);
    }
    peca.toUpperCase();

    // B3 e B4 vêm da seleção física do encoder — não da tag
    char b3[3], b4[3];
    sprintf(b3, "%02X", setorSel);
    sprintf(b4, "%02X", unidadeSel);
    String uid = peca + String(b3) + String(b4);

    Serial.println("[RFID] UID: " + uid +
                   "  (peca=" + peca +
                   " setor=0x" + String(b3) +
                   " unidade=0x" + String(b4) + ")");

    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();

    estado = PROCESSANDO;
    exibirLCD("Enviando...", uid);
    chamarAPI(uid);
  }

  // ── RESULTADO ───────────────────────────────────────────────────
  else if (estado == RESULTADO) {
    if (millis() - tResultado > T_RESULTADO) {
      String l1 = String(SETORES[setorSel]).substring(0,7) + "/" +
                  String(UNIDADES[unidadeSel]).substring(4,10);
      exibirLCD(l1, "Aprox. a tag...");
      estado = AGUARDAR;
    }
  }
}

// ──────────────────────────────────────────────────────────────────
void chamarAPI(String uid) {
  if (WiFi.status() != WL_CONNECTED) conectarWifi();

  HTTPClient http;
  http.begin(String(API_HOST) + "/api/rfid");
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(5000);

  String payload = "{\"uid\":\"" + uid + "\"}";
  int code = http.POST(payload);
  String body = http.getString();
  http.end();

  Serial.printf("[HTTP] %d | %s\n", code, body.c_str());

  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, body);

  bool ok = false;
  String l1 = "Erro de rede";
  String l2 = "";

  if (code > 0 && !err) {
    const char* status = doc["status"] | "erro";
    const char* msg    = doc["msg"]    | "Sem resposta";
    const char* tipo   = doc["tipo"]   | "";
    const char* acao   = doc["acao"]   | "";
    ok = (strcmp(status, "ok") == 0);

    if (strcmp(tipo, "operador") == 0)
      l1 = strcmp(acao, "login") == 0 ? ">> LOGIN OK" : "<< LOGOUT OK";
    else if (strcmp(tipo, "ferramenta") == 0)
      l1 = strcmp(acao, "retirada") == 0 ? "RETIRADA OK" : "DEVOLUCAO OK";
    else
      l1 = ok ? "OK" : "ERRO";

    l2 = String(msg).substring(0, 16);
  }

  exibirLCD(l1, l2);
  bip(ok);
  ledStatus(ok);
  tResultado = millis();
  estado = RESULTADO;
}

// ──────────────────────────────────────────────────────────────────
void conectarWifi() {
  exibirLCD("WiFi...", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int t = 0;
  while (WiFi.status() != WL_CONNECTED && t++ < 20) { delay(500); Serial.print("."); }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] IP: " + WiFi.localIP().toString());
    exibirLCD("WiFi OK!", WiFi.localIP().toString());
  } else {
    exibirLCD("WiFi FALHOU!", "Sem rede");
  }
  delay(1000);
}

void exibirLCD(String l1, String l2) {
  l1 = ("                " + l1 + "                ").substring(8, 24);
  l2 = ("                " + l2 + "                ").substring(8, 24);
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print(l1.substring(0, 16));
  lcd.setCursor(0, 1); lcd.print(l2.substring(0, 16));
}

void bip(bool ok) {
  if (ok) { digitalWrite(BUZZER, HIGH); delay(80); digitalWrite(BUZZER, LOW); }
  else    { for (int i=0;i<3;i++){digitalWrite(BUZZER,HIGH);delay(100);digitalWrite(BUZZER,LOW);delay(100);} }
}

void ledStatus(bool ok) {
  digitalWrite(LED_OK,  ok  ? HIGH : LOW);
  digitalWrite(LED_ERR, !ok ? HIGH : LOW);
  delay(1500);
  digitalWrite(LED_OK, LOW); digitalWrite(LED_ERR, LOW);
}

void IRAM_ATTR encISR() {
  int clk = digitalRead(ENC_CLK);
  if (clk != clkUlt) {
    encPos += (digitalRead(ENC_DT) != clk) ? 1 : -1;
    clkUlt = clk;
  }
}

int lerEnc(int mn, int mx, int atual) {
  int delta = encPos - encPosUlt;
  if (!delta) return atual;
  encPosUlt = encPos;
  int novo = atual + (delta > 0 ? 1 : -1);
  if (novo > mx) novo = mn;
  if (novo < mn) novo = mx;
  return novo;
}
