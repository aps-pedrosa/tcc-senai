/*
 * VoidLog — Firmware ESP32 v3.0 (RFID Only + Config Remota)
 * ═══════════════════════════════════════════════════════════════════
 *
 * NOVIDADES v3.0:
 *   • Setores e unidades são carregados do banco via API no boot.
 *     Nenhuma lista hardcoded — qualquer alteração no dashboard ou
 *     banco reflete automaticamente no ESP sem novo upload.
 *   • Terminal se registra automaticamente pelo MAC address.
 *   • Setor/unidade padrão configurável pelo dashboard (admin pode
 *     pré-configurar o terminal; ESP usa isso como valor inicial).
 *   • Resync periódico de config a cada CONFIG_SYNC_INTERVAL ms.
 *   • HTTP robusto: WiFiClient explícito + reconexão automática +
 *     retry com back-off — elimina o HTTP -1 por socket fechado.
 *
 * FLUXO:
 *   Boot → WiFi → GET /api/terminal/<id>/config → carrega listas
 *   1. Se admin pré-configurou setor/unidade → pula para AGUARDAR_TAG
 *      Senão → DIGITAR_SETOR → DIGITAR_UNIDADE
 *   2. Passa qualquer tag RFID  → UID enviado à API
 *        • Crachá de operador → login / logout registrado
 *        • Tag de peça        → retirada / devolução registrada
 *   3. LCD + Serial mostram resultado
 *   4. Tecla * → volta ao passo 1
 *   Botão RESET físico → reinicialização completa (passo 1)
 *
 * PAYLOAD (POST /api/rfid) — inalterado, compatível com routes/rfid.py:
 *   {
 *     "uid":            "04A3F21B7C8D90",
 *     "setor_codigo":   4,
 *     "unidade_codigo": 2,
 *     "terminal_id":    "ESP-AABBCC"
 *   }
 *
 * PINAGEM:
 *   RC522    SDA→5   SCK→18  MOSI→23  MISO→19  RST→4   3.3V  GND
 *   LCD I2C  SDA→21  SCL→22  VCC→5V  GND
 *   Teclado  LINHAS→13,12,14,27   COLUNAS→26,25,33,32
 *   Buzzer   GPIO 15
 *   LED Verde     GPIO 17
 *   LED Vermelho  GPIO 2  (LED onboard)
 *   Botão RESET   GPIO 34 (input-only, sem pull-up interno)
 *
 * BIBLIOTECAS:
 *   - MFRC522           (by GithubCommunity)
 *   - LiquidCrystal_I2C (by Frank de Brabander)
 *   - ArduinoJson       (by Benoit Blanchon)  ← v6+
 *   - Keypad            (by Mark Stanley, Alexander Brevig)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Keypad.h>

// ═══════════════════════════════════════════════════════════════════
// ★  ÚNICA CONFIGURAÇÃO NECESSÁRIA — só WiFi e IP do servidor
// ═══════════════════════════════════════════════════════════════════

const char* WIFI_SSID = "TurboNet-CASA-2G";
const char* WIFI_PASSWORD = "AA12A48A82M57";
const char* API_HOST = "192.168.100.23";
const int   API_PORT      = 5000;

// Firmware version reportada ao servidor
#define FIRMWARE_VER "3.0"

// Intervalo de resync de configuração com o servidor (ms)
#define CONFIG_SYNC_INTERVAL  60000UL   // 1 minuto

// Tempo (ms) que o resultado fica no LCD
#define T_RESULTADO           3000

// Timeout aguardando tag antes de voltar à seleção de setor (ms)
#define T_AGUARDAR_TAG        60000UL   // 1 minuto

// Tamanho máximo de setores/unidades carregados da API
#define MAX_SETORES   20
#define MAX_UNIDADES  20

// ═══════════════════════════════════════════════════════════════════
// PINOS
// ═══════════════════════════════════════════════════════════════════

#define RC522_SS    5
#define RC522_RST   4

#define KBD_ROWS 4
#define KBD_COLS 4
byte KBD_ROW_PINS[KBD_ROWS] = {13, 12, 14, 27};
byte KBD_COL_PINS[KBD_COLS] = {26, 25, 33, 32};

#define BUZZER    15
#define LED_OK    17
#define LED_ERR   2
#define BTN_RESET 34

// ═══════════════════════════════════════════════════════════════════
// TECLADO
// ═══════════════════════════════════════════════════════════════════

char KBD_MAP[KBD_ROWS][KBD_COLS] = {
  {'1','2','3','A'},
  {'4','5','6','B'},
  {'7','8','9','C'},
  {'*','0','#','D'}
};
Keypad teclado = Keypad(makeKeymap(KBD_MAP), KBD_ROW_PINS, KBD_COL_PINS, KBD_ROWS, KBD_COLS);

// ═══════════════════════════════════════════════════════════════════
// PERIFÉRICOS
// ═══════════════════════════════════════════════════════════════════

MFRC522           rfid(RC522_SS, RC522_RST);
LiquidCrystal_I2C lcd(0x27, 16, 2);
WiFiClient        wifiClient;   // cliente persistente — evita HTTP -1

// ═══════════════════════════════════════════════════════════════════
// DADOS CARREGADOS DO SERVIDOR (setores e unidades)
// ═══════════════════════════════════════════════════════════════════

struct ItemTabela {
  int    codigo;
  char   nome[20];
};

ItemTabela setores[MAX_SETORES];
ItemTabela unidades[MAX_UNIDADES];
int numSetores  = 0;
int numUnidades = 0;

// Configuração padrão pré-definida pelo admin no dashboard
int setorPadrao   = 0;   // 0 = não configurado
int unidadePadrao = 0;

// ═══════════════════════════════════════════════════════════════════
// MÁQUINA DE ESTADOS
// ═══════════════════════════════════════════════════════════════════

enum Estado {
  CARREGANDO_CONFIG,  // buscando config da API
  DIGITAR_SETOR,
  DIGITAR_UNIDADE,
  AGUARDAR_TAG,
  PROCESSANDO,
  RESULTADO
};

Estado estado = CARREGANDO_CONFIG;

int    setorSel    = 0;
int    unidadeSel  = 0;
String inputBuffer = "";

unsigned long tResultado      = 0;
unsigned long tAguardaTag     = 0;
unsigned long tUltimoSync     = 0;

String terminalId = "ESP-??????";

// ═══════════════════════════════════════════════════════════════════
// PROTÓTIPOS
// ═══════════════════════════════════════════════════════════════════

void   conectarWifi();
int   carregarConfig();   // returns int internally — declared bool for compat
void   aguardarAprovacao();
void   iniciarModoOperacao();
String httpGET(String path);
String httpPOST(String path, String payload);
void   exibirLCD(String l1, String l2);
void   exibirLCDInput(String titulo, String input, String hint);
void   bip(bool ok);
void   ledStatus(bool ok, int ms = 1500);
bool   chamarAPI(String uid, String &msgL1, String &msgL2, bool &sucesso);
String lerRFID();
void   processarTeclado(char tecla);
void   logUID(String uid);
String nomeSetor(int codigo);
String nomeUnidade(int codigo);

// ═══════════════════════════════════════════════════════════════════
// SETUP
// ═══════════════════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);
  Serial.println("\n\n╔═══════════════════════════════╗");
  Serial.println(  "║  VoidLog — RFID Only v3.0     ║");
  Serial.println(  "╚═══════════════════════════════╝");

  pinMode(BUZZER,    OUTPUT); digitalWrite(BUZZER,  LOW);
  pinMode(LED_OK,    OUTPUT); digitalWrite(LED_OK,  LOW);
  pinMode(LED_ERR,   OUTPUT); digitalWrite(LED_ERR, LOW);
  pinMode(BTN_RESET, INPUT);

  Wire.begin(21, 22);
  lcd.init();
  lcd.backlight();
  exibirLCD("VoidLog v3.0", "Iniciando...");

  SPI.begin();
  rfid.PCD_Init();
  Serial.println("[RFID] RC522 OK");

  conectarWifi();

  // Terminal ID via MAC
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char buf[13];
  sprintf(buf, "%02X%02X%02X", mac[3], mac[4], mac[5]);
  terminalId = "ESP-" + String(buf);
  Serial.println("[TERMINAL] ID:  " + terminalId);
  Serial.println("[TERMINAL] IP:  " + WiFi.localIP().toString());
  Serial.println("[TERMINAL] API: " + String(API_HOST) + ":" + String(API_PORT));
  Serial.println("─────────────────────────────────");

  // Carrega config do servidor — trata pendente/rejeitado
  exibirLCD("Registrando...", terminalId.substring(0, 16));
  aguardarAprovacao();   // bloqueia até aprovado ou timeout

  tUltimoSync = millis();
  iniciarModoOperacao();
}

// ═══════════════════════════════════════════════════════════════════
// LOOP PRINCIPAL
// ═══════════════════════════════════════════════════════════════════

void loop() {
/*
  // ── Botão RESET físico ─────────────────────────────────────────
  if (digitalRead(BTN_RESET) == LOW) {
    delay(50);
    if (digitalRead(BTN_RESET) == LOW) {
      Serial.println("\n[RESET] Reiniciando...");
      bip(true); delay(200); bip(true);
      while (digitalRead(BTN_RESET) == LOW) delay(10);
      ESP.restart();
    }
  }
*/

  // ── Resync periódico de configuração ──────────────────────────
  if (millis() - tUltimoSync > CONFIG_SYNC_INTERVAL) {
    Serial.println("[SYNC] Recarregando configuração do servidor...");
    int r = carregarConfig();
    if (r == 1) {
      Serial.println("[SYNC] ✓ Config atualizada");
      // Se o admin mudou setor/unidade padrão, aplica na próxima vez que voltar ao início
    } else if (r == -2) {
      // Terminal foi rejeitado depois de aprovado — para tudo
      exibirLCD("ACESSO", "REVOGADO");
      delay(5000);
      ESP.restart();
    }
    tUltimoSync = millis();
  }

  // ── Máquina de estados ─────────────────────────────────────────
  switch (estado) {

    case CARREGANDO_CONFIG:
      // Estado temporário — iniciarModoOperacao() sai dele no setup
      break;

    case DIGITAR_SETOR: {
      char t = teclado.getKey();
      if (t) processarTeclado(t);
      break;
    }

    case DIGITAR_UNIDADE: {
      char t = teclado.getKey();
      if (t) processarTeclado(t);
      break;
    }

    case AGUARDAR_TAG: {
      // Timeout
      if (millis() - tAguardaTag > T_AGUARDAR_TAG) {
        Serial.println("[TIMEOUT] Sem tag — reiniciando seleção");
        setorSel = 0; unidadeSel = 0; inputBuffer = "";
        iniciarModoOperacao();
        break;
      }

      // Tecla * → volta ao início
      char t = teclado.getKey();
      if (t == '*') {
        Serial.println("[KBD] * → reiniciando seleção");
        inputBuffer = "";
        iniciarModoOperacao();
        break;
      }

      // Tenta ler tag
      String uid = lerRFID();
      if (uid.length() == 0) break;

      logUID(uid);
      exibirLCD("Enviando...", uid.substring(0, 16));
      estado = PROCESSANDO;

      String l1, l2;
      bool sucesso;
      bool ok = chamarAPI(uid, l1, l2, sucesso);

      exibirLCD(l1, l2);
      bip(ok && sucesso);
      ledStatus(ok && sucesso, 1000);
      tResultado  = millis();
      tAguardaTag = millis();
      estado = RESULTADO;
      break;
    }

    case PROCESSANDO:
      break;

    case RESULTADO:
      if (millis() - tResultado > T_RESULTADO) {
        String ctx = nomeSetor(setorSel).substring(0, 7)
                   + "/" + nomeUnidade(unidadeSel).substring(0, 6);
        exibirLCD(ctx, "Passe a tag");
        estado = AGUARDAR_TAG;
      }
      break;
  }
}

// ═══════════════════════════════════════════════════════════════════
// CARREGA CONFIGURAÇÃO DO SERVIDOR
// ═══════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════
// ESTADO DE APROVAÇÃO DO TERMINAL
// Retorna: 1=aprovado/config OK, 0=erro rede, -1=pendente, -2=rejeitado
// ═══════════════════════════════════════════════════════════════════

int carregarConfig() {
  String path = "/api/terminal/" + terminalId + "/config?fw=" + FIRMWARE_VER;
  String body = httpGET(path);

  if (body.length() == 0) {
    Serial.println("[CONFIG] ✗ Resposta vazia / sem rede");
    return 0;
  }

  DynamicJsonDocument doc(4096);
  DeserializationError err = deserializeJson(doc, body);
  if (err) {
    Serial.println("[CONFIG] ✗ JSON inválido: " + String(err.c_str()));
    return 0;
  }

  const char* st = doc["status"] | "erro";

  if (strcmp(st, "pendente") == 0) {
    Serial.println("[CONFIG] ⏳ Terminal pendente — aguardando aprovação do admin");
    return -1;
  }

  if (strcmp(st, "rejeitado") == 0) {
    Serial.println("[CONFIG] ✗ Terminal REJEITADO pelo administrador");
    return -2;
  }

  if (strcmp(st, "ok") != 0) {
    Serial.println("[CONFIG] ✗ status inesperado: " + String(st));
    return 0;
  }

  // ── Aprovado — carrega listas ────────────────────────────────
  numSetores = 0;
  JsonArray arrS = doc["setores"].as<JsonArray>();
  for (JsonObject s : arrS) {
    if (numSetores >= MAX_SETORES) break;
    setores[numSetores].codigo = s["codigo"].as<int>();
    strlcpy(setores[numSetores].nome, s["nome"] | "?", 20);
    numSetores++;
  }

  numUnidades = 0;
  JsonArray arrU = doc["unidades"].as<JsonArray>();
  for (JsonObject u : arrU) {
    if (numUnidades >= MAX_UNIDADES) break;
    unidades[numUnidades].codigo = u["codigo"].as<int>();
    strlcpy(unidades[numUnidades].nome, u["nome"] | "?", 20);
    numUnidades++;
  }

  JsonObject term = doc["terminal"];
  setorPadrao   = term["setor_codigo"]   | 0;
  unidadePadrao = term["unidade_codigo"] | 0;

  Serial.printf("[CONFIG] ✓ %d setores, %d unidades | padrão setor=%d unidade=%d\n",
                numSetores, numUnidades, setorPadrao, unidadePadrao);

  return (numSetores > 0 && numUnidades > 0) ? 1 : 0;
}

// ═══════════════════════════════════════════════════════════════════
// AGUARDA APROVAÇÃO — exibe tela de espera, tenta a cada 10s
// ═══════════════════════════════════════════════════════════════════

void aguardarAprovacao() {
  while (true) {
    int r = carregarConfig();

    if (r == 1) {
      // Aprovado e config carregada
      bip(true);
      exibirLCD("Terminal", "APROVADO!");
      delay(1200);
      return;
    }

    if (r == -2) {
      // Rejeitado — fica em loop eterno exibindo mensagem
      exibirLCD("REJEITADO", "Contate o admin");
      Serial.println("[BOOT] Terminal rejeitado. Reiniciando em 60s...");
      delay(60000);
      ESP.restart();
    }

    if (r == -1) {
      // Pendente — pulsa no LCD e tenta de novo em 10s
      static bool flip = false;
      flip = !flip;
      exibirLCD(flip ? "Aguardando" : terminalId.substring(0, 16),
                flip ? "aprovacao admin" : "pendente...");
      Serial.println("[BOOT] Pendente — nova tentativa em 10s...");
      delay(10000);
      continue;
    }

    // r == 0: erro de rede — tenta reconectar e aguarda
    exibirLCD("Sem servidor", "Retry em 8s...");
    Serial.println("[BOOT] Erro de rede — aguardando 8s...");
    delay(8000);
  }
}

// ═══════════════════════════════════════════════════════════════════
// INICIA MODO DE OPERAÇÃO (decide se pede setor/unidade ou já vai)
// ═══════════════════════════════════════════════════════════════════

void iniciarModoOperacao() {
  // Se admin pré-configurou setor E unidade → usa direto
  if (setorPadrao > 0 && unidadePadrao > 0) {
    setorSel   = setorPadrao;
    unidadeSel = unidadePadrao;
    tAguardaTag = millis();
    String ctx = nomeSetor(setorSel).substring(0, 7)
               + "/" + nomeUnidade(unidadeSel).substring(0, 6);
    exibirLCD(ctx, "Passe a tag");
    estado = AGUARDAR_TAG;
    Serial.printf("[PRONTO] Auto: setor=%s unidade=%s\n",
                  nomeSetor(setorSel).c_str(), nomeUnidade(unidadeSel).c_str());
  } else {
    // Pede setor no teclado
    setorSel   = 0;
    unidadeSel = 0;
    inputBuffer = "";
    estado = DIGITAR_SETOR;
    String hint = "1-" + String(numSetores > 0 ? setores[numSetores-1].codigo : 8);
    exibirLCDInput("Setor (" + hint + "):", "", "# confirma");
    Serial.println("[ESTADO] Aguardando setor...");
  }
}

// ═══════════════════════════════════════════════════════════════════
// HTTP GET — cliente robusto (evita HTTP -1)
// ═══════════════════════════════════════════════════════════════════

String httpGET(String path) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Desconectado — reconectando...");
    conectarWifi();
    if (WiFi.status() != WL_CONNECTED) return "";
  }

  // Usa WiFiClient novo a cada chamada para evitar sockets antigos
  WiFiClient client;
  HTTPClient http;

  String url = "http://" + String(API_HOST) + ":" + String(API_PORT) + path;
  Serial.println("[HTTP] GET " + url);

  http.begin(client, url);
  http.setTimeout(8000);
  http.setConnectTimeout(5000);
  http.addHeader("Connection", "close");

  int code = http.GET();
  Serial.printf("[HTTP] GET %d\n", code);

  String body = "";
  if (code > 0) {
    body = http.getString();
  } else {
    Serial.println("[HTTP] ✗ Erro: " + String(http.errorToString(code)));
  }
  http.end();
  client.stop();
  return body;
}

// ═══════════════════════════════════════════════════════════════════
// HTTP POST — cliente robusto (evita HTTP -1)
// ═══════════════════════════════════════════════════════════════════

String httpPOST(String path, String payload) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Desconectado — reconectando...");
    conectarWifi();
    if (WiFi.status() != WL_CONNECTED) return "";
  }

  // Máximo 2 tentativas com back-off
  for (int tentativa = 1; tentativa <= 2; tentativa++) {
    WiFiClient client;
    HTTPClient http;

    String url = "http://" + String(API_HOST) + ":" + String(API_PORT) + path;
    if (tentativa > 1) Serial.println("[HTTP] Retry " + String(tentativa));
    Serial.println("[HTTP] POST " + url);

    http.begin(client, url);
    http.setTimeout(8000);
    http.setConnectTimeout(5000);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Connection", "close");

    int code = http.POST(payload);
    Serial.printf("[HTTP] POST %d\n", code);

    String body = "";
    if (code > 0) {
      body = http.getString();
      http.end();
      client.stop();
      return body;
    }

    Serial.println("[HTTP] ✗ Erro: " + String(http.errorToString(code)));
    http.end();
    client.stop();

    if (tentativa < 2) delay(800);
  }
  return "";
}

// ═══════════════════════════════════════════════════════════════════
// PROCESSAMENTO DO TECLADO
// ═══════════════════════════════════════════════════════════════════

void processarTeclado(char tecla) {
  Serial.printf("[KBD] '%c'  estado=%d  buffer=\"%s\"\n",
                tecla, estado, inputBuffer.c_str());

  // ── Setor ──────────────────────────────────────────────────────
  if (estado == DIGITAR_SETOR) {
    if (tecla == '#') {
      int val = inputBuffer.toInt();
      // Valida contra lista carregada do servidor
      bool valido = false;
      for (int i = 0; i < numSetores; i++) {
        if (setores[i].codigo == val) { valido = true; break; }
      }
      if (!valido) {
        bip(false);
        exibirLCDInput("Setor invalido!", "1-" + String(numSetores > 0 ? setores[numSetores-1].codigo : 8), "");
        delay(1200);
        inputBuffer = "";
        String hint = "1-" + String(numSetores > 0 ? setores[numSetores-1].codigo : 8);
        exibirLCDInput("Setor (" + hint + "):", "", "# confirma");
        return;
      }
      setorSel    = val;
      inputBuffer = "";
      bip(true);
      estado = DIGITAR_UNIDADE;
      String hint2 = "1-" + String(numUnidades > 0 ? unidades[numUnidades-1].codigo : 5);
      exibirLCDInput("Unidade(" + hint2 + "):", "", "# confirma");
      Serial.printf("[KBD] ✓ Setor: %d (%s)\n", setorSel, nomeSetor(setorSel).c_str());
    }
    else if (tecla == '*') {
      inputBuffer = "";
      String hint = "1-" + String(numSetores > 0 ? setores[numSetores-1].codigo : 8);
      exibirLCDInput("Setor (" + hint + "):", "", "# confirma");
    }
    else if (isDigit(tecla) && inputBuffer.length() < 2) {
      inputBuffer += tecla;
      String hint = "1-" + String(numSetores > 0 ? setores[numSetores-1].codigo : 8);
      exibirLCDInput("Setor (" + hint + "):", inputBuffer, "# confirma");
    }
  }

  // ── Unidade ────────────────────────────────────────────────────
  else if (estado == DIGITAR_UNIDADE) {
    if (tecla == '#') {
      int val = inputBuffer.toInt();
      bool valido = false;
      for (int i = 0; i < numUnidades; i++) {
        if (unidades[i].codigo == val) { valido = true; break; }
      }
      if (!valido) {
        bip(false);
        exibirLCDInput("Unid. invalida!", "1-" + String(numUnidades > 0 ? unidades[numUnidades-1].codigo : 5), "");
        delay(1200);
        inputBuffer = "";
        String hint = "1-" + String(numUnidades > 0 ? unidades[numUnidades-1].codigo : 5);
        exibirLCDInput("Unidade(" + hint + "):", "", "# confirma");
        return;
      }
      unidadeSel  = val;
      inputBuffer = "";
      bip(true); delay(80); bip(true);
      estado = AGUARDAR_TAG;
      tAguardaTag = millis();
      String ctx = nomeSetor(setorSel).substring(0, 7)
                 + "/" + nomeUnidade(unidadeSel).substring(0, 6);
      exibirLCD(ctx, "Passe a tag");
      Serial.printf("[KBD] ✓ Unidade: %d (%s)\n", unidadeSel, nomeUnidade(unidadeSel).c_str());
      Serial.println("─────────────────────────────────");
      Serial.printf("[PRONTO] %s / %s\n",
                    nomeSetor(setorSel).c_str(), nomeUnidade(unidadeSel).c_str());
    }
    else if (tecla == '*') {
      inputBuffer = "";
      estado = DIGITAR_SETOR;
      String hint = "1-" + String(numSetores > 0 ? setores[numSetores-1].codigo : 8);
      exibirLCDInput("Setor (" + hint + "):", "", "# confirma");
    }
    else if (isDigit(tecla) && inputBuffer.length() < 2) {
      inputBuffer += tecla;
      String hint = "1-" + String(numUnidades > 0 ? unidades[numUnidades-1].codigo : 5);
      exibirLCDInput("Unidade(" + hint + "):", inputBuffer, "# confirma");
    }
  }
}

// ═══════════════════════════════════════════════════════════════════
// LEITURA RFID
// ═══════════════════════════════════════════════════════════════════

String lerRFID() {
  if (!rfid.PICC_IsNewCardPresent()) return "";
  if (!rfid.PICC_ReadCardSerial())   return "";
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  Serial.printf("[RFID] UID: %s (%d bytes)\n", uid.c_str(), rfid.uid.size);
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  return uid;
}

// ═══════════════════════════════════════════════════════════════════
// LOG SERIAL DA TAG
// ═══════════════════════════════════════════════════════════════════

void logUID(String uid) {
  Serial.println("\n┌─────────────────────────────────┐");
  Serial.println(  "│          TAG RFID LIDA           │");
  Serial.println(  "├─────────────────────────────────┤");
  Serial.printf(   "│  UID     : %-22s│\n", uid.c_str());
  Serial.printf(   "│  Bytes   : %-22d│\n", uid.length() / 2);
  Serial.printf(   "│  Setor   : %d - %-18s│\n", setorSel,   nomeSetor(setorSel).c_str());
  Serial.printf(   "│  Unidade : %d - %-18s│\n", unidadeSel, nomeUnidade(unidadeSel).c_str());
  Serial.printf(   "│  Terminal: %-22s│\n", terminalId.c_str());
  Serial.println(  "└─────────────────────────────────┘");
}

// ═══════════════════════════════════════════════════════════════════
// CHAMADA À API — POST /api/rfid
// ═══════════════════════════════════════════════════════════════════

bool chamarAPI(String uid, String &msgL1, String &msgL2, bool &sucesso) {
  StaticJsonDocument<256> req;
  req["uid"]            = uid;
  req["setor_codigo"]   = setorSel;
  req["unidade_codigo"] = unidadeSel;
  req["terminal_id"]    = terminalId;

  String payload;
  serializeJson(req, payload);
  Serial.println("[API] Payload: " + payload);

  String body = httpPOST("/api/rfid", payload);

  if (body.length() == 0) {
    msgL1 = "Sem conexao";
    msgL2 = "Verifique rede";
    sucesso = false;
    return false;
  }

  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, body);
  if (err) {
    msgL1   = "JSON invalido";
    msgL2   = err.c_str();
    sucesso = false;
    return true;
  }

  const char* status = doc["status"] | "erro";
  const char* msg    = doc["msg"]    | "Sem resposta";
  const char* tipo   = doc["tipo"]   | "";
  const char* acao   = doc["acao"]   | "";

  sucesso = (strcmp(status, "ok") == 0);

  if (strcmp(tipo, "operador") == 0) {
    msgL1 = (strcmp(acao, "login") == 0) ? ">> LOGIN OK" : "<< LOGOUT OK";
  } else if (strcmp(tipo, "peca") == 0) {
    msgL1 = (strcmp(acao, "retirada") == 0) ? "RETIRADA OK" : "DEVOLUCAO OK";
  } else {
    msgL1 = sucesso ? "OK" : "ERRO";
  }
  msgL2 = String(msg).substring(0, 16);

  Serial.printf("[API] %s | tipo=%s acao=%s msg=%s\n",
                sucesso ? "✓" : "✗", tipo, acao, msg);
  return true;
}

// ═══════════════════════════════════════════════════════════════════
// WIFI
// ═══════════════════════════════════════════════════════════════════

void conectarWifi() {
  Serial.printf("[WiFi] Conectando a \"%s\"", WIFI_SSID);
  exibirLCD("Conectando WiFi", String(WIFI_SSID).substring(0, 16));
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int t = 0;
  while (WiFi.status() != WL_CONNECTED && t++ < 40) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("[WiFi] ✓ IP: " + WiFi.localIP().toString());
    exibirLCD("WiFi OK!", WiFi.localIP().toString());
  } else {
    Serial.println("[WiFi] ✗ Falhou");
    exibirLCD("WiFi FALHOU", "Sem rede!");
  }
  delay(1200);
}

// ═══════════════════════════════════════════════════════════════════
// HELPERS — nome de setor/unidade pelo código
// ═══════════════════════════════════════════════════════════════════

String nomeSetor(int codigo) {
  for (int i = 0; i < numSetores; i++)
    if (setores[i].codigo == codigo) return String(setores[i].nome);
  return String(codigo);
}

String nomeUnidade(int codigo) {
  for (int i = 0; i < numUnidades; i++)
    if (unidades[i].codigo == codigo) return String(unidades[i].nome);
  return String(codigo);
}

// ═══════════════════════════════════════════════════════════════════
// LCD
// ═══════════════════════════════════════════════════════════════════

void exibirLCD(String l1, String l2) {
  while (l1.length() < 16) l1 = " " + l1;
  while (l2.length() < 16) l2 = " " + l2;
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print(l1.substring(0, 16));
  lcd.setCursor(0, 1); lcd.print(l2.substring(0, 16));
}

void exibirLCDInput(String titulo, String input, String hint) {
  String l1 = titulo; while (l1.length() < 16) l1 += " ";
  String l2 = (hint.length() > 0 && input.length() == 0) ? hint : "> " + input;
  while (l2.length() < 16) l2 += " ";
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print(l1.substring(0, 16));
  lcd.setCursor(0, 1); lcd.print(l2.substring(0, 16));
}

// ═══════════════════════════════════════════════════════════════════
// BUZZER E LEDs
// ═══════════════════════════════════════════════════════════════════

void bip(bool ok) {
  if (ok) {
    digitalWrite(BUZZER, HIGH); delay(80); digitalWrite(BUZZER, LOW);
  } else {
    for (int i = 0; i < 3; i++) {
      digitalWrite(BUZZER, HIGH); delay(100);
      digitalWrite(BUZZER, LOW);  delay(100);
    }
  }
}

void ledStatus(bool ok, int ms) {
  digitalWrite(LED_OK,  ok  ? HIGH : LOW);
  digitalWrite(LED_ERR, !ok ? HIGH : LOW);
  delay(ms);
  digitalWrite(LED_OK,  LOW);
  digitalWrite(LED_ERR, LOW);
}
