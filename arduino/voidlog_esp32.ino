/*
 * VoidLog v2 — Firmware ESP32
 * ═══════════════════════════════════════════════════════════════════
 *
 * HARDWARE:
 *   - ESP32 DevKit V1
 *   - Módulo RFID RC522        → crachá do operador (SPI)
 *   - Leitor código de barras  → identificação da peça (Serial2/UART)
 *   - LCD 16x2 I2C             → feedback visual
 *   - Teclado Membrana 4x3     → seleção de setor e unidade
 *   - Buzzer passivo           → feedback sonoro
 *   - LED Verde + Vermelho     → status da operação
 *   - Botão RESET              → volta ao menu principal
 *
 * FLUXO OPERACIONAL:
 *   1. Operador digita setor no teclado  (1–8, confirmado com #)
 *   2. Operador digita unidade no teclado (1–5, confirmado com #)
 *   3. Operador passa o crachá RFID → login registrado na API
 *   4. Operador lê o código de barras da peça → movimentação registrada
 *   5. LCD exibe resultado; após 3s volta ao passo 4
 *   6. Para trocar operador: botão * no teclado → logout + volta ao passo 3
 *   7. Botão RESET físico → volta ao passo 1 (redefine setor/unidade)
 *
 * UID RFID — IDENTIFICAÇÃO COMPLETA:
 *   O firmware envia o UID COMPLETO da tag (todos os bytes lidos pelo RC522).
 *   Tags de 4 bytes → 8 chars hex  (ex: "04A3F21B")
 *   Tags de 7 bytes → 14 chars hex (ex: "04A3F21B7C8D90")
 *   Tags de 10 bytes → 20 chars hex
 *   A API usa o uid_raw completo como identificador primário, evitando
 *   colisões entre tags de fabricantes diferentes com mesmos B1+B2.
 *
 * PAYLOAD ENVIADO À API (POST /api/rfid):
 *   {
 *     "uid":            "04A3F21B7C8D90", ← UID COMPLETO da tag (todos os bytes)
 *     "setor_codigo":   4,                ← digitado no teclado
 *     "unidade_codigo": 2,                ← digitado no teclado
 *     "terminal_id":    "ESP-AABBCC"      ← MAC address do ESP32
 *   }
 *   O crachá do operador envia o mesmo payload com seu uid_raw completo.
 *   Barcodes de peças são convertidos para UID de 2 bytes (B1+B2).
 *
 * MAPEAMENTO DO TECLADO 4x3:
 *   ┌───┬───┬───┐
 *   │ 1 │ 2 │ 3 │
 *   ├───┼───┼───┤
 *   │ 4 │ 5 │ 6 │
 *   ├───┼───┼───┤
 *   │ 7 │ 8 │ 9 │
 *   ├───┼───┼───┤
 *   │ * │ 0 │ # │
 *   └───┴───┴───┘
 *   # = confirmar / Enter
 *   * = cancelar / limpar / logout de operador
 *
 * PINAGEM COMPLETA:
 *   RC522  SDA→5  SCK→18  MOSI→23  MISO→19  RST→4  3.3V  GND
 *   LCD I2C  SDA→21  SCL→22  VCC→5V  GND
 *   Barcode  TX→GPIO16 (RX2 do ESP32)  GND  VCC→5V (ou 3.3V — ver datasheet)
 *   Teclado  LINHAS→GPIO 13,12,14,27   COLUNAS→GPIO 26,25,33
 *   Buzzer   GPIO 32
 *   LED Verde  GPIO 17
 *   LED Vermelho GPIO 2 (LED onboard)
 *   Botão RESET  GPIO 34
 *
 * BIBLIOTECAS (instalar via Library Manager):
 *   - MFRC522  (by GithubCommunity)
 *   - LiquidCrystal_I2C  (by Frank de Brabander)
 *   - ArduinoJson  (by Benoit Blanchon)
 *   - Keypad  (by Mark Stanley, Alexander Brevig)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Keypad.h>

// ═══════════════════════════════════════════════════════════════════
// CONFIGURAÇÃO — EDITE AQUI
// ═══════════════════════════════════════════════════════════════════

const char* WIFI_SSID     = "SUA_REDE_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA_WIFI";
const char* API_HOST      = "http://192.168.1.100:5000";  // IP do servidor Flask

// Baud rate do leitor de barras (varia por modelo — comum: 9600 ou 115200)
#define BARCODE_BAUD  9600

// Tempo em ms que o resultado fica no LCD antes de voltar ao modo leitura
#define T_RESULTADO   3000

// Timeout para o crachá RFID ser lido após confirmação do setor/unidade
#define T_AGUARDAR_CRACHA  30000   // 30 segundos

// ═══════════════════════════════════════════════════════════════════
// PINOS
// ═══════════════════════════════════════════════════════════════════

// RC522 (SPI)
#define RC522_SS    5
#define RC522_RST   4

// LCD I2C (usa GPIO 21=SDA e 22=SCL — padrão ESP32)

// Código de barras → Serial2 (RX2 = GPIO 16, TX2 = GPIO 17)
// Apenas RX é necessário (ESP32 lê, leitor transmite)
#define BARCODE_RX  16
#define BARCODE_TX  17   // não usado, mas Serial2 exige declaração

// Teclado 4x3
//   Linhas  (saída):   L1→13  L2→12  L3→14  L4→27
//   Colunas (entrada): C1→26  C2→25  C3→33
#define KBD_ROWS 4
#define KBD_COLS 3
byte KBD_ROW_PINS[KBD_ROWS] = {13, 12, 14, 27};
byte KBD_COL_PINS[KBD_COLS] = {26, 25, 33};

// Periféricos
#define BUZZER    32
#define LED_OK    17   // verde
#define LED_ERR   2    // vermelho (LED onboard)
#define BTN_RESET 34   // botão físico de reset (INPUT_ONLY, sem pull-up interno)

// ═══════════════════════════════════════════════════════════════════
// TECLADO
// ═══════════════════════════════════════════════════════════════════

char KBD_MAP[KBD_ROWS][KBD_COLS] = {
  {'1','2','3'},
  {'4','5','6'},
  {'7','8','9'},
  {'*','0','#'}
};
Keypad teclado = Keypad(makeKeymap(KBD_MAP), KBD_ROW_PINS, KBD_COL_PINS, KBD_ROWS, KBD_COLS);

// ═══════════════════════════════════════════════════════════════════
// PERIFÉRICOS
// ═══════════════════════════════════════════════════════════════════

MFRC522           rfid(RC522_SS, RC522_RST);
LiquidCrystal_I2C lcd(0x27, 16, 2);

// ═══════════════════════════════════════════════════════════════════
// TABELAS (espelham database.py)
// ═══════════════════════════════════════════════════════════════════

const char* SETORES[]  = {
  "", "Soldagem", "Corte", "Usinagem", "Furacao",
  "Montagem", "Manutencao", "Almoxarifado", "Qualidade"
};
const char* UNIDADES[] = {
  "", "Centro", "BH", "Contagem", "Betim", "Ibirite"
};
const int NUM_SETORES  = 8;
const int NUM_UNIDADES = 5;

// ═══════════════════════════════════════════════════════════════════
// MÁQUINA DE ESTADOS
// ═══════════════════════════════════════════════════════════════════

enum Estado {
  DIGITAR_SETOR,      // operador digita número do setor no teclado
  DIGITAR_UNIDADE,    // operador digita número da unidade no teclado
  AGUARDAR_CRACHA,    // aguarda crachá RFID do operador
  AGUARDAR_BARCODE,   // operador logado — aguarda leitura do código de barras
  PROCESSANDO,        // enviando para a API
  RESULTADO           // exibindo resultado por T_RESULTADO ms
};

Estado estado = DIGITAR_SETOR;

// Contexto do terminal (definido pelo operador no teclado)
int setorSel   = 0;
int unidadeSel = 0;

// Operador logado
bool operadorLogado = false;
String operadorNome = "";

// Buffers de entrada do teclado
String inputBuffer = "";

// Controle de tempo
unsigned long tResultado     = 0;
unsigned long tAguardaCracha = 0;

// ID do terminal (gerado no setup a partir do MAC)
String terminalId = "ESP-??????";

// ═══════════════════════════════════════════════════════════════════
// PROTÓTIPOS
// ═══════════════════════════════════════════════════════════════════

void  conectarWifi();
void  exibirLCD(String l1, String l2);
void  exibirLCDInput(String titulo, String input, String hint);
void  bip(bool ok);
void  ledStatus(bool ok, int ms = 1500);
bool  chamarAPI(String uid, String &msgL1, String &msgL2, bool &sucesso);
String lerBarcode();
String lerRFID();           // retorna UID COMPLETO em hex maiúsculo
String barcodeParaUID(String barcode);
uint16_t crc16(String s);
void  processarTeclado(char tecla);

// ═══════════════════════════════════════════════════════════════════
// SETUP
// ═══════════════════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);

  // Periféricos
  pinMode(BUZZER,    OUTPUT); digitalWrite(BUZZER,  LOW);
  pinMode(LED_OK,    OUTPUT); digitalWrite(LED_OK,  LOW);
  pinMode(LED_ERR,   OUTPUT); digitalWrite(LED_ERR, LOW);
  pinMode(BTN_RESET, INPUT);  // GPIO 34 é input-only, sem pull-up interno

  // LCD
  Wire.begin(21, 22);
  lcd.init(); lcd.backlight();
  exibirLCD("VoidLog v2", "Iniciando...");

  // RFID
  SPI.begin();
  rfid.PCD_Init();
  Serial.println("[RFID] RC522 inicializado");

  // Código de barras (Serial2)
  Serial2.begin(BARCODE_BAUD, SERIAL_8N1, BARCODE_RX, BARCODE_TX);
  Serial.println("[BARCODE] Serial2 pronto @ " + String(BARCODE_BAUD));

  // WiFi
  conectarWifi();

  // Terminal ID a partir do MAC
  uint8_t mac[6]; WiFi.macAddress(mac);
  char macStr[13];
  sprintf(macStr, "%02X%02X%02X", mac[3], mac[4], mac[5]);
  terminalId = "ESP-" + String(macStr);
  Serial.println("[TERMINAL] ID: " + terminalId);

  // Inicia máquina de estados
  estado = DIGITAR_SETOR;
  exibirLCDInput("Setor (1-8):", "", "# confirma");
}

// ═══════════════════════════════════════════════════════════════════
// LOOP PRINCIPAL
// ═══════════════════════════════════════════════════════════════════

void loop() {

  // ── Botão RESET físico ─────────────────────────────────────────
  if (digitalRead(BTN_RESET) == LOW) {
    delay(50);
    if (digitalRead(BTN_RESET) == LOW) {
      Serial.println("[RESET] Voltando ao inicio...");
      operadorLogado = false; operadorNome = "";
      setorSel = 0; unidadeSel = 0;
      inputBuffer = "";
      estado = DIGITAR_SETOR;
      exibirLCDInput("Setor (1-8):", "", "# confirma");
      bip(true); delay(200); bip(true);
      while (digitalRead(BTN_RESET) == LOW) delay(10);
      return;
    }
  }

  // ── Máquina de estados ─────────────────────────────────────────

  switch (estado) {

    // ── DIGITAR_SETOR ─────────────────────────────────────────────
    case DIGITAR_SETOR: {
      char t = teclado.getKey();
      if (t) processarTeclado(t);
      break;
    }

    // ── DIGITAR_UNIDADE ───────────────────────────────────────────
    case DIGITAR_UNIDADE: {
      char t = teclado.getKey();
      if (t) processarTeclado(t);
      break;
    }

    // ── AGUARDAR_CRACHA ───────────────────────────────────────────
    case AGUARDAR_CRACHA: {
      // Timeout — volta ao início se nenhum crachá for lido
      if (millis() - tAguardaCracha > T_AGUARDAR_CRACHA) {
        Serial.println("[TIMEOUT] Aguardando crachá — reiniciando");
        estado = DIGITAR_SETOR; inputBuffer = "";
        exibirLCDInput("Setor (1-8):", "", "# confirma");
        break;
      }

      // Tecla * cancela e volta à seleção de setor
      char t = teclado.getKey();
      if (t == '*') {
        estado = DIGITAR_SETOR; inputBuffer = "";
        exibirLCDInput("Setor (1-8):", "", "# confirma");
        break;
      }

      // Tenta ler crachá RFID — envia UID COMPLETO
      String uid = lerRFID();
      if (uid.length() == 0) break;

      Serial.println("[CRACHA] UID completo: " + uid);
      exibirLCD("Verificando...", uid.substring(0, 16));
      estado = PROCESSANDO;

      String l1, l2; bool sucesso;
      bool ok = chamarAPI(uid, l1, l2, sucesso);

      if (ok && sucesso) {
        operadorLogado = true;
        operadorNome = l2.length() > 5 ? l2.substring(5) : l2;
        operadorNome.replace("!", "");
        exibirLCD(l1, l2);
        bip(true); ledStatus(true, 1000);
        delay(T_RESULTADO);
        String ctx = String(SETORES[setorSel]).substring(0,7)
                   + "/" + String(UNIDADES[unidadeSel]).substring(0,6);
        exibirLCD(ctx, "Leia o barcode");
        estado = AGUARDAR_BARCODE;
      } else {
        exibirLCD(l1, l2);
        bip(false); ledStatus(false, 1000);
        delay(T_RESULTADO);
        tAguardaCracha = millis();
        estado = AGUARDAR_CRACHA;
        String ctx = String(SETORES[setorSel]).substring(0,7)
                   + "/" + String(UNIDADES[unidadeSel]).substring(0,6);
        exibirLCD(ctx, "Passe o cracha");
      }
      break;
    }

    // ── AGUARDAR_BARCODE ─────────────────────────────────────────
    case AGUARDAR_BARCODE: {
      // Tecla * → logout do operador
      char t = teclado.getKey();
      if (t == '*') {
        Serial.println("[LOGOUT] Operador encerrou sessao via teclado");
        operadorLogado = false; operadorNome = "";
        estado = AGUARDAR_CRACHA;
        tAguardaCracha = millis();
        String ctx = String(SETORES[setorSel]).substring(0,7)
                   + "/" + String(UNIDADES[unidadeSel]).substring(0,6);
        exibirLCD(ctx, "Passe o cracha");
        bip(false);
        break;
      }

      // Verifica se chegou crachá RFID (troca de operador) — UID COMPLETO
      if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
        String uid = "";
        for (byte i = 0; i < rfid.uid.size; i++) {
          if (rfid.uid.uidByte[i] < 0x10) uid += "0";
          uid += String(rfid.uid.uidByte[i], HEX);
        }
        uid.toUpperCase();
        rfid.PICC_HaltA();
        rfid.PCD_StopCrypto1();

        Serial.println("[RFID] UID completo (modo barcode): " + uid
                       + " (" + String(rfid.uid.size) + " bytes)");
        estado = PROCESSANDO;
        exibirLCD("Verificando...", uid.substring(0, 16));

        String l1, l2; bool sucesso;
        bool ok = chamarAPI(uid, l1, l2, sucesso);
        exibirLCD(l1, l2);
        bip(ok && sucesso); ledStatus(ok && sucesso, 1000);
        delay(T_RESULTADO);

        if (ok && sucesso) {
          operadorNome = l2.length() > 5 ? l2.substring(5) : l2;
          operadorNome.replace("!", "");
        }

        String ctx = String(SETORES[setorSel]).substring(0,7)
                   + "/" + String(UNIDADES[unidadeSel]).substring(0,6);
        exibirLCD(ctx, "Leia o barcode");
        estado = AGUARDAR_BARCODE;
        break;
      }

      // Lê código de barras da peça
      String barcode = lerBarcode();
      if (barcode.length() == 0) break;

      Serial.println("[BARCODE] Lido: " + barcode);

      // Converte barcode → peca_code → uid hex de 2 bytes (B1+B2)
      // O UID enviado para barcodes contém apenas B1+B2 (sem bytes extras).
      // A API faz o fallback por peca_code quando uid_raw não é encontrado.
      String uid = barcodeParaUID(barcode);

      Serial.println("[BARCODE] UID calculado: " + uid);
      exibirLCD("Enviando...", barcode.substring(0, 16));
      estado = PROCESSANDO;

      String l1, l2; bool sucesso;
      bool ok = chamarAPI(uid, l1, l2, sucesso);

      exibirLCD(l1, l2);
      bip(ok && sucesso);
      ledStatus(ok && sucesso, 1500);
      tResultado = millis();
      estado = RESULTADO;
      break;
    }

    // ── PROCESSANDO ───────────────────────────────────────────────
    case PROCESSANDO:
      break;

    // ── RESULTADO ─────────────────────────────────────────────────
    case RESULTADO:
      if (millis() - tResultado > T_RESULTADO) {
        String ctx = String(SETORES[setorSel]).substring(0,7)
                   + "/" + String(UNIDADES[unidadeSel]).substring(0,6);
        exibirLCD(ctx, "Leia o barcode");
        estado = AGUARDAR_BARCODE;
      }
      break;
  }
}

// ═══════════════════════════════════════════════════════════════════
// PROCESSAMENTO DO TECLADO
// ═══════════════════════════════════════════════════════════════════

void processarTeclado(char tecla) {
  Serial.printf("[KBD] Tecla: %c  estado: %d  buffer: %s\n",
                tecla, estado, inputBuffer.c_str());

  if (estado == DIGITAR_SETOR) {
    if (tecla == '#') {
      int val = inputBuffer.toInt();
      if (val < 1 || val > NUM_SETORES) {
        bip(false);
        exibirLCDInput("Setor invalido!", "1 a " + String(NUM_SETORES), "");
        delay(1200);
        inputBuffer = "";
        exibirLCDInput("Setor (1-8):", "", "# confirma");
        return;
      }
      setorSel = val;
      inputBuffer = "";
      bip(true);
      estado = DIGITAR_UNIDADE;
      exibirLCDInput("Unidade (1-5):", "", "# confirma");
      Serial.printf("[KBD] Setor selecionado: %d (%s)\n", setorSel, SETORES[setorSel]);
    }
    else if (tecla == '*') {
      inputBuffer = "";
      exibirLCDInput("Setor (1-8):", "", "# confirma");
    }
    else if (isDigit(tecla)) {
      if (inputBuffer.length() < 2) {
        inputBuffer += tecla;
        exibirLCDInput("Setor (1-8):", inputBuffer, "# confirma");
      }
    }
  }

  else if (estado == DIGITAR_UNIDADE) {
    if (tecla == '#') {
      int val = inputBuffer.toInt();
      if (val < 1 || val > NUM_UNIDADES) {
        bip(false);
        exibirLCDInput("Unidade inval.!", "1 a " + String(NUM_UNIDADES), "");
        delay(1200);
        inputBuffer = "";
        exibirLCDInput("Unidade (1-5):", "", "# confirma");
        return;
      }
      unidadeSel = val;
      inputBuffer = "";
      bip(true); delay(80); bip(true);  // 2 bips = confirmado
      estado = AGUARDAR_CRACHA;
      tAguardaCracha = millis();
      String ctx = String(SETORES[setorSel]).substring(0,7)
                 + "/" + String(UNIDADES[unidadeSel]).substring(0,6);
      exibirLCD(ctx, "Passe o cracha");
      Serial.printf("[KBD] Unidade selecionada: %d (%s)\n", unidadeSel, UNIDADES[unidadeSel]);
    }
    else if (tecla == '*') {
      inputBuffer = "";
      estado = DIGITAR_SETOR;
      exibirLCDInput("Setor (1-8):", "", "# confirma");
    }
    else if (isDigit(tecla)) {
      if (inputBuffer.length() < 2) {
        inputBuffer += tecla;
        exibirLCDInput("Unidade (1-5):", inputBuffer, "# confirma");
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════════
// LEITURA DO RFID — RETORNA UID COMPLETO
// ═══════════════════════════════════════════════════════════════════
/*
 * lerRFID() retorna o UID COMPLETO da tag em hex maiúsculo.
 * Tags ISO 14443A podem ter 4, 7 ou 10 bytes:
 *   4 bytes  → 8  chars hex  (ex: "04A3F21B")
 *   7 bytes  → 14 chars hex  (ex: "04A3F21B7C8D90")
 *   10 bytes → 20 chars hex
 *
 * O UID completo é enviado para a API, que o armazena como uid_raw
 * e o usa como identificador primário da tag — evitando colisões
 * entre chips de fabricantes diferentes que compartilhem B1+B2.
 */

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
// LEITURA DO CÓDIGO DE BARRAS (Serial2)
// ═══════════════════════════════════════════════════════════════════

String lerBarcode() {
  if (!Serial2.available()) return "";

  String barcode = "";
  unsigned long t0 = millis();

  // Lê até '\n', '\r' ou timeout de 200ms
  while (millis() - t0 < 200) {
    if (Serial2.available()) {
      char c = (char)Serial2.read();
      if (c == '\n' || c == '\r') {
        if (barcode.length() > 0) break;
      } else {
        barcode += c;
      }
    }
  }
  // Limpa buffer residual
  while (Serial2.available()) Serial2.read();

  barcode.trim();
  return barcode;
}

// ═══════════════════════════════════════════════════════════════════
// CONVERSÃO BARCODE → UID (apenas para peças lidas por código de barras)
// ═══════════════════════════════════════════════════════════════════
/*
 * Barcodes de peças são convertidos para UID de 2 bytes (B1+B2).
 * A API usa o peca_code como fallback quando uid_raw não bate exato.
 *
 * Estratégias:
 *   1. Barcode numérico → peca_code = número  → uid="B1B2"
 *      Ex: "100" → peca_code=100 → uid="0064"
 *   2. Barcode hex 4 chars → B1+B2 direto
 *      Ex: "0064" → uid="0064"
 *   3. Barcode alfanumérico → CRC-16 → peca_code → uid="B1B2"
 */

String barcodeParaUID(String barcode) {
  barcode.trim();
  int peca = 0;

  // Estratégia 1: numérico puro
  bool ehNumerico = true;
  for (char c : barcode) { if (!isDigit(c)) { ehNumerico = false; break; } }
  if (ehNumerico && barcode.length() > 0) {
    long val = barcode.toInt();
    peca = (int)(val & 0xFFFF);
  }
  // Estratégia 2: hex de exatamente 4 chars (ex: "00A3")
  else if (barcode.length() == 4) {
    bool ehHex = true;
    for (char c : barcode) {
      if (!isHexadecimalDigit(c)) { ehHex = false; break; }
    }
    if (ehHex) {
      peca = (int)strtol(barcode.c_str(), nullptr, 16);
    } else {
      peca = crc16(barcode);
    }
  }
  // Estratégia 3: CRC-16
  else {
    peca = crc16(barcode);
  }

  // Gera UID de 2 bytes (B1+B2) — sem bytes extras
  char buf[5];
  sprintf(buf, "%02X%02X", (peca >> 8) & 0xFF, peca & 0xFF);
  return String(buf);
}

// CRC-16/CCITT para mapeamento de strings alfanuméricas a 16 bits
uint16_t crc16(String s) {
  uint16_t crc = 0xFFFF;
  for (char c : s) {
    crc ^= (uint16_t)c << 8;
    for (int i = 0; i < 8; i++)
      crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
  }
  return crc;
}

// ═══════════════════════════════════════════════════════════════════
// CHAMADA À API
// ═══════════════════════════════════════════════════════════════════

bool chamarAPI(String uid, String &msgL1, String &msgL2, bool &sucesso) {
  if (WiFi.status() != WL_CONNECTED) conectarWifi();

  // Monta payload — uid contém o UID COMPLETO (RFID) ou B1+B2 (barcode)
  StaticJsonDocument<256> req;
  req["uid"]            = uid;
  req["setor_codigo"]   = setorSel;
  req["unidade_codigo"] = unidadeSel;
  req["terminal_id"]    = terminalId;

  String payload;
  serializeJson(req, payload);
  Serial.println("[API] POST /api/rfid → " + payload);

  HTTPClient http;
  http.begin(String(API_HOST) + "/api/rfid");
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(6000);

  int    code = http.POST(payload);
  String body = http.getString();
  http.end();

  Serial.printf("[API] HTTP %d | %s\n", code, body.c_str());

  if (code <= 0) {
    msgL1 = "Sem conexao";
    msgL2 = "HTTP " + String(code);
    sucesso = false;
    return false;
  }

  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, body);
  if (err) {
    msgL1 = "JSON invalido";
    msgL2 = err.c_str();
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

  return true;
}

// ═══════════════════════════════════════════════════════════════════
// WIFI
// ═══════════════════════════════════════════════════════════════════

void conectarWifi() {
  exibirLCD("Conectando WiFi", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int t = 0;
  while (WiFi.status() != WL_CONNECTED && t++ < 30) {
    delay(500); Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Conectado! IP: " + WiFi.localIP().toString());
    exibirLCD("WiFi OK!", WiFi.localIP().toString());
  } else {
    Serial.println("\n[WiFi] FALHOU!");
    exibirLCD("WiFi FALHOU", "Sem rede");
  }
  delay(1200);
}

// ═══════════════════════════════════════════════════════════════════
// DISPLAY LCD
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
  String l2 = "> " + input;
  if (hint.length() > 0 && input.length() == 0) l2 = hint;
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
  digitalWrite(LED_OK, LOW); digitalWrite(LED_ERR, LOW);
}
