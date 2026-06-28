/*
 * VoidLog — Firmware ESP32 Terminal de Manutenção v1.0
 * ═══════════════════════════════════════════════════════════════════
 *
 * DESCRIÇÃO:
 *   Terminal dedicado à manutenção de equipamentos. Conectado a um
 *   computador via USB Serial, recebe comandos JSON e exibe
 *   feedbacks no LCD. Permite que o técnico adicione descrições e
 *   informações de manutenção antes de enviar ao servidor.
 *
 * FLUXO:
 *   Boot → WiFi → Registra como tipo='manutencao' no servidor
 *   1. Lê tag RFID do equipamento
 *   2. Exibe no LCD e envia pelo Serial para o computador
 *   3. Computador (interface web/desktop) adiciona descrição e
 *      envia de volta via Serial: { "cmd": "manutencao", ... }
 *   4. ESP envia para /api/manutencao/terminal
 *   5. Resultado exibido no LCD
 *
 *   Tecla # → Forçar toggle de manutenção sem computador
 *   Tecla * → Cancela operação atual
 *   Tecla A → Mudar tipo: entrada
 *   Tecla B → Mudar tipo: saída
 *   Tecla D (longo 3s) → Descobre servidor por broadcast
 *   Tecla C → Seleciona outro MAC/servidor (modo configuração)
 *
 * PROTOCOLO SERIAL (115200 baud):
 *   ESP → PC  : JSON com evento de leitura
 *     {"evento":"leitura","uid":"04AABB","equipamento":"Serra Fita","status":"em_manutencao","tipo_acao":"saida"}
 *
 *   PC → ESP  : JSON com comando de manutenção
 *     {"cmd":"manutencao","tipo":"entrada","descricao":"Troca de correia","tecnico":"Carlos"}
 *     {"cmd":"cancelar"}
 *     {"cmd":"ping"}
 *
 *   ESP → PC  : JSON com resultado
 *     {"evento":"resultado","ok":true,"msg":"Equipamento entrou em manutencao"}
 *     {"evento":"resultado","ok":false,"msg":"Erro: ..."}
 *
 * PINAGEM (igual ao terminal normal):
 *   RC522    SDA→5   SCK→18  MOSI→23  MISO→19  RST→4   3.3V  GND
 *   LCD I2C  SDA→21  SCL→22  VCC→5V  GND
 *   Teclado  LINHAS→13,12,14,27   COLUNAS→26,25,33,32
 *   Buzzer   GPIO 15
 *   LED Verde     GPIO 17
 *   LED Vermelho  GPIO 2
 *
 * BIBLIOTECAS:
 *   - MFRC522          (by GithubCommunity)
 *   - LiquidCrystal_I2C (by Frank de Brabander)
 *   - ArduinoJson      (by Benoit Blanchon) v6+
 *   - Keypad           (by Mark Stanley, Alexander Brevig)
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
#include <esp_wifi.h>

// ═══════════════════════════════════════════════════════════════════
// ★  CONFIGURAÇÃO — apenas WiFi. Servidor descoberto por MAC/mDNS.
// ═══════════════════════════════════════════════════════════════════

const char* WIFI_SSID     = "SUA_REDE_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA_WIFI";

// Fallback: IP fixo caso a descoberta falhe
const char* API_HOST_FALLBACK = "192.168.1.100";
const int   API_PORT          = 5000;

#define FIRMWARE_VER      "1.0-manut"
#define CONFIG_SYNC_INTERVAL  60000UL
#define T_RESULTADO           3000
#define T_AGUARDAR_CMD        30000UL   // Aguarda PC 30s após leitura
#define SERIAL_BAUD           115200

// ═══════════════════════════════════════════════════════════════════
// Pinos
// ═══════════════════════════════════════════════════════════════════
#define SS_PIN   5
#define RST_PIN  4
#define PIN_BUZZ 15
#define PIN_LED_G 17
#define PIN_LED_R 2

// Teclado 4×4
const byte ROWS = 4, COLS = 4;
char hexaKeys[ROWS][COLS] = {
  {'1','2','3','A'},
  {'4','5','6','B'},
  {'7','8','9','C'},
  {'*','0','#','D'}
};
byte rowPins[ROWS] = {13,12,14,27};
byte colPins[COLS] = {26,25,33,32};

MFRC522           mfrc522(SS_PIN, RST_PIN);
LiquidCrystal_I2C lcd(0x27, 16, 2);
Keypad            kpd = Keypad(makeKeymap(hexaKeys), rowPins, colPins, ROWS, COLS);

// ═══════════════════════════════════════════════════════════════════
// Estado global
// ═══════════════════════════════════════════════════════════════════
enum Estado {
  BOOT,
  AGUARDAR_TAG,
  AGUARDAR_CMD_PC,
  RESULTADO,
  MODO_CONFIG_MAC,
};

Estado estado      = BOOT;
String myMAC       = "";
String apiHost     = "";
String uidLido     = "";
String tipoAcao    = "toggle";  // "entrada", "saida", "toggle"
unsigned long tResultado  = 0;
unsigned long tAguardaCmd = 0;
unsigned long tLastSync   = 0;
bool serverOk      = false;
bool aguardandoPC  = false;

// Buffer Serial para receber JSON do PC
String serialBuf = "";

// ═══════════════════════════════════════════════════════════════════
// setup
// ═══════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(SERIAL_BAUD);

  pinMode(PIN_BUZZ, OUTPUT);
  pinMode(PIN_LED_G, OUTPUT);
  pinMode(PIN_LED_R, OUTPUT);
  digitalWrite(PIN_LED_R, LOW);
  digitalWrite(PIN_LED_G, LOW);

  Wire.begin(21, 22);
  lcd.init(); lcd.backlight();
  lcd.print("VoidLog Manut");
  lcd.setCursor(0,1); lcd.print("Iniciando...");

  SPI.begin(); mfrc522.PCD_Init();

  conectarWiFi();
  myMAC = WiFi.macAddress();
  myMAC.replace(":", "");

  // Descobre servidor
  descobrirServidor();

  // Registra como terminal de manutenção
  if (registrarTerminal()) {
    serverOk = true;
    lcd.clear(); lcd.print("Pronto!");
    lcd.setCursor(0,1); lcd.print(myMAC.substring(0,8));
    // Anuncia ao PC
    enviarPCJson("pronto", myMAC, "", "", "");
    delay(1500);
  } else {
    lcd.clear(); lcd.print("Sem servidor");
    lcd.setCursor(0,1); lcd.print("Modo offline");
  }

  estado = AGUARDAR_TAG;
  exibirTelaEspera();
}

// ═══════════════════════════════════════════════════════════════════
// loop
// ═══════════════════════════════════════════════════════════════════
void loop() {
  char key = kpd.getKey();
  lerSerial();
  syncConfig();

  switch (estado) {
    case AGUARDAR_TAG:
      handleAguardaTag(key);
      break;
    case AGUARDAR_CMD_PC:
      handleAguardaCmd(key);
      break;
    case RESULTADO:
      if (millis() - tResultado > T_RESULTADO) {
        estado = AGUARDAR_TAG;
        exibirTelaEspera();
      }
      break;
    case MODO_CONFIG_MAC:
      handleModoConfigMAC(key);
      break;
    default:
      break;
  }
}

// ═══════════════════════════════════════════════════════════════════
// Tela de espera
// ═══════════════════════════════════════════════════════════════════
void exibirTelaEspera() {
  lcd.clear();
  lcd.print("MANUTENCAO");
  lcd.setCursor(0,1);
  if (tipoAcao == "entrada")      lcd.print("[A]=ENT [B]=SAI");
  else if (tipoAcao == "saida")   lcd.print("[A]=ENT [B]=SAI");
  else                            lcd.print("Passe o equip.");
}

// ═══════════════════════════════════════════════════════════════════
// AGUARDAR TAG
// ═══════════════════════════════════════════════════════════════════
void handleAguardaTag(char key) {
  if (key == 'A') { tipoAcao = "entrada"; exibirTelaEspera(); beep(80); return; }
  if (key == 'B') { tipoAcao = "saida";   exibirTelaEspera(); beep(80); return; }
  if (key == 'C') { estado = MODO_CONFIG_MAC; lcd.clear(); lcd.print("Config MAC"); return; }
  if (key == 'D') { descobrirServidor(); return; }
  if (key == '#') {
    // Modo manual: entrada UID pelo teclado (facilita testes sem RFID)
    lcd.clear(); lcd.print("UID manual:"); lcd.setCursor(0,1);
    uidLido = lerEntradaTeclado(8);
    if (uidLido.length() >= 4) processarUID();
    return;
  }

  if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) return;

  // Lê UID
  uidLido = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) uidLido += "0";
    uidLido += String(mfrc522.uid.uidByte[i], HEX);
  }
  uidLido.toUpperCase();
  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();

  beep(100);
  processarUID();
}

// ═══════════════════════════════════════════════════════════════════
// Processa UID lido (consulta servidor e aguarda comando do PC)
// ═══════════════════════════════════════════════════════════════════
void processarUID() {
  lcd.clear(); lcd.print("Lendo...");
  lcd.setCursor(0,1); lcd.print(uidLido.substring(0,16));

  // Consulta equipamento na API
  String equipNome = "";
  bool emManut = false;
  bool found = consultarEquipamento(uidLido, equipNome, emManut);

  // Determina ação padrão
  String acaoSugerida = tipoAcao;
  if (tipoAcao == "toggle") {
    acaoSugerida = emManut ? "saida" : "entrada";
  }

  // Mostra no LCD
  lcd.clear();
  if (found) {
    lcd.print(equipNome.substring(0,16));
    lcd.setCursor(0,1);
    lcd.print(emManut ? "EM MANUT > SAI?" : "LIVRE > ENTR?");
  } else {
    lcd.print("UID: "+uidLido.substring(0,8));
    lcd.setCursor(0,1);
    lcd.print("Nao cadastrado");
  }

  // Envia evento ao PC via Serial
  enviarPCJson("leitura", uidLido, equipNome, emManut?"em_manutencao":"livre", acaoSugerida);

  // Aguarda resposta do PC
  estado = AGUARDAR_CMD_PC;
  tAguardaCmd = millis();
  aguardandoPC = true;
}

// ═══════════════════════════════════════════════════════════════════
// AGUARDAR COMANDO DO PC
// ═══════════════════════════════════════════════════════════════════
void handleAguardaCmd(char key) {
  // Timeout → auto-ação sem descrição
  if (millis() - tAguardaCmd > T_AGUARDAR_CMD) {
    lcd.clear(); lcd.print("Timeout...");
    lcd.setCursor(0,1); lcd.print("Auto-toggle");
    enviarManutencao(uidLido, tipoAcao == "toggle" ? "toggle" : tipoAcao, "", "");
    return;
  }

  // Tecla * cancela
  if (key == '*') {
    aguardandoPC = false;
    estadoResultado("Cancelado", false);
    return;
  }

  // Tecla # confirma sem descrição
  if (key == '#') {
    aguardandoPC = false;
    enviarManutencao(uidLido, tipoAcao, "", "");
    return;
  }

  // Aguarda JSON do PC (processado em lerSerial → processarCmdPC)
  int seg = (T_AGUARDAR_CMD - (millis() - tAguardaCmd)) / 1000;
  if (millis() % 1000 < 50) {  // atualiza display 1×/s
    lcd.setCursor(0,1);
    lcd.print("Ag PC " + String(seg) + "s  # pula");
  }
}

// ═══════════════════════════════════════════════════════════════════
// Lê caracteres do Serial e monta JSON
// ═══════════════════════════════════════════════════════════════════
void lerSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBuf.length() > 2) {
        processarCmdPC(serialBuf);
        serialBuf = "";
      }
    } else {
      serialBuf += c;
      if (serialBuf.length() > 512) serialBuf = "";  // overflow guard
    }
  }
}

void processarCmdPC(const String& json) {
  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, json);
  if (err) {
    Serial.println("{\"evento\":\"erro\",\"msg\":\"JSON invalido\"}");
    return;
  }

  const char* cmd = doc["cmd"];
  if (!cmd) return;

  if (strcmp(cmd, "ping") == 0) {
    Serial.println("{\"evento\":\"pong\",\"mac\":\"" + myMAC + "\"}");
    return;
  }

  if (strcmp(cmd, "cancelar") == 0) {
    aguardandoPC = false;
    estadoResultado("Cancelado PC", false);
    return;
  }

  if (strcmp(cmd, "manutencao") == 0 && estado == AGUARDAR_CMD_PC) {
    aguardandoPC = false;
    String tipo    = doc["tipo"]     | "toggle";
    String desc    = doc["descricao"]| "";
    String tecnico = doc["tecnico"]  | "";
    enviarManutencao(uidLido, tipo, desc, tecnico);
    return;
  }

  if (strcmp(cmd, "servidor") == 0) {
    // PC informa o IP do servidor
    String host = doc["host"] | "";
    if (host.length() > 0) {
      apiHost = host;
      Serial.println("{\"evento\":\"servidor_ok\",\"host\":\"" + apiHost + "\"}");
    }
    return;
  }
}

// ═══════════════════════════════════════════════════════════════════
// Envia evento ao PC em JSON
// ═══════════════════════════════════════════════════════════════════
void enviarPCJson(const String& evento, const String& uid,
                  const String& equip, const String& status,
                  const String& acao) {
  StaticJsonDocument<256> doc;
  doc["evento"]      = evento;
  doc["uid"]         = uid;
  doc["equipamento"] = equip;
  doc["status"]      = status;
  doc["tipo_acao"]   = acao;
  doc["mac"]         = myMAC;
  serializeJson(doc, Serial);
  Serial.println();
}

// ═══════════════════════════════════════════════════════════════════
// Envia manutenção ao servidor
// ═══════════════════════════════════════════════════════════════════
void enviarManutencao(const String& uid, const String& tipo,
                      const String& desc, const String& tecnico) {
  lcd.clear(); lcd.print("Enviando...");

  if (apiHost.isEmpty()) {
    estadoResultado("Sem servidor", false);
    return;
  }

  WiFiClient client;
  HTTPClient http;
  String url = "http://" + apiHost + ":" + String(API_PORT) + "/api/manutencao/terminal";

  // Monta JSON
  StaticJsonDocument<256> body;
  body["terminal_id"] = myMAC;
  body["uid_raw"]     = uid;
  body["tipo"]        = tipo;
  body["descricao"]   = desc;
  body["tecnico"]     = tecnico;
  String bodyStr;
  serializeJson(body, bodyStr);

  http.begin(client, url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(8000);

  int code = http.POST(bodyStr);
  String resp = http.getString();
  http.end();

  StaticJsonDocument<256> rdoc;
  bool ok = (code == 200);
  String msg = "Erro HTTP " + String(code);

  if (deserializeJson(rdoc, resp) == DeserializationError::Ok) {
    if (rdoc.containsKey("acao")) {
      String acao = rdoc["acao"].as<String>();
      String nome = rdoc["nome"].as<String>();
      msg = (acao == "entrada") ? "ENTROU manut:" : "SAIU manut:";
      msg += nome.substring(0, 10);
      ok = true;
    } else if (rdoc.containsKey("erro")) {
      msg = rdoc["erro"].as<String>();
    } else if (rdoc.containsKey("aviso")) {
      msg = rdoc["aviso"].as<String>();
      ok = true;
    }
  }

  // Reporta ao PC
  StaticJsonDocument<128> res;
  res["evento"] = "resultado";
  res["ok"]     = ok;
  res["msg"]    = msg;
  res["uid"]    = uid;
  serializeJson(res, Serial);
  Serial.println();

  estadoResultado(msg, ok);
}

// ═══════════════════════════════════════════════════════════════════
// Consulta equipamento na API (retorna nome e status)
// ═══════════════════════════════════════════════════════════════════
bool consultarEquipamento(const String& uid, String& nome, bool& emManut) {
  if (apiHost.isEmpty()) return false;

  WiFiClient client;
  HTTPClient http;
  String url = "http://" + apiHost + ":" + String(API_PORT)
             + "/api/equipamentos?uid=" + uid;
  http.begin(client, url);
  http.setTimeout(5000);
  int code = http.GET();
  if (code != 200) { http.end(); return false; }

  String resp = http.getString();
  http.end();

  DynamicJsonDocument doc(1024);
  if (deserializeJson(doc, resp) != DeserializationError::Ok) return false;
  if (!doc.is<JsonArray>() || doc.size() == 0) return false;

  JsonObject eq = doc[0];
  nome    = eq["nome"]          | "";
  emManut = (int)eq["em_manutencao"] == 1;
  return true;
}

// ═══════════════════════════════════════════════════════════════════
// Resultado no LCD
// ═══════════════════════════════════════════════════════════════════
void estadoResultado(const String& msg, bool ok) {
  lcd.clear();
  lcd.print(ok ? "OK" : "ERRO");
  lcd.setCursor(0,1);
  lcd.print(msg.substring(0, 16));
  if (ok) { beep(200); led(PIN_LED_G, 200); }
  else    { beep(80);beep(80);led(PIN_LED_R,200); }
  tResultado = millis();
  estado = RESULTADO;
}

// ═══════════════════════════════════════════════════════════════════
// Descobre servidor na rede local
// Tenta GET /api/terminais/descobrir?mac=<MAC> em range de IPs.
// Na prática o PC com a interface pode enviar {"cmd":"servidor","host":"x"}.
// ═══════════════════════════════════════════════════════════════════
void descobrirServidor() {
  lcd.clear(); lcd.print("Descobrindo...");
  Serial.println("{\"evento\":\"descobrir\",\"mac\":\"" + myMAC + "\"}");

  // Primeiro tenta IPs comuns (.1, .100, .200)
  IPAddress localIP = WiFi.localIP();
  String base = String(localIP[0])+"."+String(localIP[1])+"."+String(localIP[2])+".";
  int tentativas[] = {1, 100, 200, 101, 10, 50};

  for (int t : tentativas) {
    String host = base + String(t);
    if (tentarServidor(host)) {
      apiHost = host;
      lcd.clear(); lcd.print("Servidor:");
      lcd.setCursor(0,1); lcd.print(apiHost);
      Serial.println("{\"evento\":\"servidor_encontrado\",\"host\":\"" + apiHost + "\"}");
      beep(150); delay(1000);
      return;
    }
  }

  // Fallback
  apiHost = String(API_HOST_FALLBACK);
  lcd.clear(); lcd.print("Fallback IP:");
  lcd.setCursor(0,1); lcd.print(apiHost);
  delay(1500);
}

bool tentarServidor(const String& host) {
  WiFiClient client;
  HTTPClient http;
  String url = "http://" + host + ":" + String(API_PORT)
             + "/api/terminais/descobrir?mac=" + myMAC;
  http.begin(client, url);
  http.setTimeout(1500);
  int code = http.GET();
  String resp = http.getString();
  http.end();
  if (code != 200) return false;
  StaticJsonDocument<128> doc;
  if (deserializeJson(doc, resp) != DeserializationError::Ok) return false;
  return strcmp(doc["servidor"] | "", "voidlog") == 0;
}

// ═══════════════════════════════════════════════════════════════════
// Registra terminal como tipo=manutencao
// ═══════════════════════════════════════════════════════════════════
bool registrarTerminal() {
  if (apiHost.isEmpty()) return false;

  WiFiClient client;
  HTTPClient http;
  String url = "http://" + apiHost + ":" + String(API_PORT) + "/api/terminais/registro";

  StaticJsonDocument<128> body;
  body["terminal_id"]  = myMAC;
  body["tipo"]         = "manutencao";
  body["firmware_ver"] = FIRMWARE_VER;
  String bodyStr;
  serializeJson(body, bodyStr);

  http.begin(client, url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(6000);
  int code = http.POST(bodyStr);

  if (code == 200 || code == 202) {
    String resp = http.getString();
    StaticJsonDocument<128> doc;
    if (deserializeJson(doc, resp) == DeserializationError::Ok) {
      // Verifica se foi aprovado; se pendente, aguarda admin
      String status = doc["status"] | "pendente";
      if (status == "pendente") {
        lcd.clear(); lcd.print("Aguardando");
        lcd.setCursor(0,1); lcd.print("aprovacao admin");
        delay(3000);
      }
    }
    http.end();
    return true;
  }
  http.end();
  return false;
}

// ═══════════════════════════════════════════════════════════════════
// Modo configuração de MAC/servidor
// ═══════════════════════════════════════════════════════════════════
String macDigitado = "";
void handleModoConfigMAC(char key) {
  if (key == '*') {
    // Cancela
    estado = AGUARDAR_TAG;
    macDigitado = "";
    exibirTelaEspera();
    return;
  }
  if (key == '#') {
    // Executa descoberta novamente
    descobrirServidor();
    estado = AGUARDAR_TAG;
    return;
  }
  if (key == 'D') {
    // D = descobrir broadcasting
    lcd.clear(); lcd.print("Broadcast...");
    descobrirServidor();
    estado = AGUARDAR_TAG;
    return;
  }
  // Qualquer outro: mostra instrução
  lcd.clear();
  lcd.print("# = Descobrir");
  lcd.setCursor(0,1);
  lcd.print("* = Cancelar");
}

// ═══════════════════════════════════════════════════════════════════
// Sync periódico
// ═══════════════════════════════════════════════════════════════════
void syncConfig() {
  if (millis() - tLastSync < CONFIG_SYNC_INTERVAL) return;
  tLastSync = millis();
  if (!apiHost.isEmpty()) registrarTerminal();
}

// ═══════════════════════════════════════════════════════════════════
// WiFi
// ═══════════════════════════════════════════════════════════════════
void conectarWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lcd.clear(); lcd.print("Conectando WiFi");
  int t = 0;
  while (WiFi.status() != WL_CONNECTED && t < 20) {
    delay(500); t++;
    lcd.setCursor(t % 16, 1); lcd.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    lcd.clear(); lcd.print("WiFi OK");
    lcd.setCursor(0,1); lcd.print(WiFi.localIP().toString());
    beep(150); delay(800);
  } else {
    lcd.clear(); lcd.print("Sem WiFi!");
    lcd.setCursor(0,1); lcd.print("Modo offline");
    delay(2000);
  }
}

// ═══════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════
void beep(int ms) {
  digitalWrite(PIN_BUZZ, HIGH); delay(ms); digitalWrite(PIN_BUZZ, LOW);
}
void led(int pin, int ms) {
  digitalWrite(pin, HIGH); delay(ms); digitalWrite(pin, LOW);
}

// Lê entrada de texto pelo teclado (até maxChars dígitos hex)
String lerEntradaTeclado(int maxChars) {
  String s = "";
  const char hexMap[] = "0123456789ABCDEF";
  lcd.setCursor(0,1); lcd.print("                ");
  lcd.setCursor(0,1);
  while (s.length() < (size_t)maxChars) {
    char k = kpd.waitForKey();
    if (k == '*') return "";
    if (k == '#') break;
    if (k >= '0' && k <= '9') { s += k; lcd.print(k); }
    else if (k == 'A') { s += 'A'; lcd.print('A'); }
    else if (k == 'B') { s += 'B'; lcd.print('B'); }
    else if (k == 'C') { s += 'C'; lcd.print('C'); }
    else if (k == 'D') { s += 'D'; lcd.print('D'); }
  }
  return s;
}
