# VoidLog v2 — Guia de Montagem do Hardware

## Lista de Componentes

| Componente | Especificação | Qtd | Preço estimado |
|---|---|---|---|
| ESP32 DevKit V1 | com WiFi/Bluetooth | 1 | R$ 35–50 |
| Módulo RFID RC522 | SPI, 13,56 MHz | 1 | R$ 15–25 |
| Tags RFID (crachás) | ISO 14443A | 5+ | R$ 2–5 cada |
| **Leitor de código de barras** | **Serial TTL/USB-TTL, 5V** | **1** | **R$ 40–80** |
| **Teclado Membrana 4x3** | **12 teclas, conector flat** | **1** | **R$ 8–15** |
| Display LCD 16x2 | com módulo I2C PCF8574 | 1 | R$ 20–30 |
| Buzzer passivo 5V | — | 1 | R$ 3–8 |
| LED Verde 5mm | difuso | 1 | R$ 1 |
| LED Vermelho 5mm | difuso | 1 | R$ 1 |
| Resistor 220Ω | 1/4W | 2 | < R$ 1 |
| Botão tátil 6x6mm | reset físico | 1 | R$ 1 |
| Protoboard 830 pontos | ou PCB perfurada | 1 | R$ 20–35 |
| Jumpers macho-macho | kit 40 peças | 1 | R$ 10–15 |
| Cabo USB micro/USB-C | para programar o ESP32 | 1 | — |

**Custo total estimado: R$ 160–270**

---

## Pinagem Completa

### RC522 (SPI) → ESP32

> ⚠️ CRÍTICO: O RC522 opera em **3.3V**. Conectar em 5V queima o módulo.

| RC522 | ESP32 GPIO | Observação |
|---|---|---|
| SDA (SS) | 5 | Slave Select |
| SCK | 18 | Clock SPI |
| MOSI | 23 | Dados → módulo |
| MISO | 19 | Dados ← módulo |
| RST | 4 | Reset |
| GND | GND | — |
| 3.3V | 3.3V | ← **apenas 3.3V!** |

---

### Leitor de Código de Barras (Serial TTL) → ESP32

O leitor envia os dados lidos via porta serial (TTL 3.3V ou 5V com conversor).

| Leitor Barcode | ESP32 GPIO | Observação |
|---|---|---|
| TX | **GPIO 16** (RX2) | Dados do leitor para o ESP32 |
| GND | GND | — |
| VCC | 5V (VIN) | A maioria dos leitores USB/TTL usa 5V |

> **Modelos recomendados:** GM65, DE2120, GM66, Waveshare Barcode Scanner.
> Configure o leitor para modo **contínuo** ou **trigger automático** com terminador `\n` (LF).
> Baud rate padrão: **9600**. Se o seu modelo usar diferente, altere `BARCODE_BAUD` no firmware.
>
> ⚠️ Se o leitor for USB (não TTL), use um módulo **CH340/CP2102** para converter USB→Serial e conecte ao GPIO 16.

---

### Teclado Membrana 4x3 → ESP32

O teclado tem **7 pinos** no conector flat (4 linhas + 3 colunas).

```
Teclas:  [1][2][3]
         [4][5][6]
         [7][8][9]
         [*][0][#]

Conector (da esquerda para a direita):
  Pino 1 → Linha 1 (teclas 1,2,3)
  Pino 2 → Linha 2 (teclas 4,5,6)
  Pino 3 → Linha 3 (teclas 7,8,9)
  Pino 4 → Linha 4 (teclas *,0,#)
  Pino 5 → Coluna 1 (teclas 1,4,7,*)
  Pino 6 → Coluna 2 (teclas 2,5,8,0)
  Pino 7 → Coluna 3 (teclas 3,6,9,#)
```

| Teclado Pino | Função | ESP32 GPIO |
|---|---|---|
| 1 (L1) | Linha 1 | **GPIO 13** |
| 2 (L2) | Linha 2 | **GPIO 12** |
| 3 (L3) | Linha 3 | **GPIO 14** |
| 4 (L4) | Linha 4 | **GPIO 27** |
| 5 (C1) | Coluna 1 | **GPIO 26** |
| 6 (C2) | Coluna 2 | **GPIO 25** |
| 7 (C3) | Coluna 3 | **GPIO 33** |

> ℹ️ A biblioteca **Keypad** já configura as linhas como saída e as colunas como entrada com pull-up interno. Não precisa de resistores externos.

---

### LCD 16x2 I2C → ESP32

| LCD I2C | ESP32 GPIO |
|---|---|
| SDA | **GPIO 21** |
| SCL | **GPIO 22** |
| VCC | 5V |
| GND | GND |

> Endereço I2C padrão: `0x27`. Se não funcionar, tente `0x3F`.
> Gire o trimpot azul no módulo I2C para ajustar o contraste.

---

### Periféricos → ESP32

| Componente | GPIO (+) | GPIO (−) | Obs |
|---|---|---|---|
| Buzzer | **GPIO 32** | GND | — |
| LED Verde | **GPIO 17** → R 220Ω | GND | Resistor obrigatório |
| LED Vermelho | **GPIO 2** | GND | LED onboard, resistor opcional |
| Botão RESET | **GPIO 34** | GND | GPIO 34 é input-only, sem pull-up |

> ⚠️ GPIO 34 não possui pull-up interno. Adicione um resistor de **10kΩ** entre GPIO 34 e 3.3V.

---

## Diagrama de Blocos

```
                    ┌─────────────────────────────────┐
                    │          ESP32 DevKit            │
                    │                                  │
  RC522 ────SPI─────│ GPIO 5/18/23/19/4               │
                    │                                  │
  Barcode ──UART────│ GPIO 16 (RX2)                   │
                    │                                  │
  Teclado 4x3 ──────│ GPIO 13,12,14,27 (linhas)       │
                    │ GPIO 26,25,33    (colunas)       │
                    │                                  │
  LCD I2C ───I2C────│ GPIO 21 (SDA), 22 (SCL)         │
                    │                                  │
  Buzzer ───────────│ GPIO 32                         │
  LED Verde ────────│ GPIO 17                         │
  LED Vermelho ─────│ GPIO 2                          │
  BTN Reset ────────│ GPIO 34                         │
                    │                                  │
                    │         WiFi ────────► API Flask │
                    └─────────────────────────────────┘
```

---

## Fluxo Operacional Completo

```
[Ligar] → DIGITAR_SETOR
              │
              │ Digita 1–8 no teclado + pressiona #
              ▼
          DIGITAR_UNIDADE
              │
              │ Digita 1–5 no teclado + pressiona #
              │ (* cancela e volta ao setor)
              ▼
          AGUARDAR_CRACHA  ←── timeout 30s → DIGITAR_SETOR
              │
              │ Operador passa crachá RFID
              │ API valida → login registrado
              ▼
          AGUARDAR_BARCODE  ←────────────────────────┐
              │                                       │
              ├── Lê código de barras da peça         │
              │   API registra retirada/devolução     │
              │   LCD exibe resultado por 3s ─────────┘
              │
              ├── Lê crachá RFID (troca de operador)
              │
              └── Tecla * → logout → AGUARDAR_CRACHA

[Botão RESET físico] → DIGITAR_SETOR (a qualquer momento)
```

---

## Mapeamento Setor/Unidade no Teclado

O operador digita o **número** correspondente e confirma com `#`:

**Setores:**
```
1 → Soldagem      5 → Montagem
2 → Corte         6 → Manutenção
3 → Usinagem      7 → Almoxarifado
4 → Furação       8 → Qualidade
```

**Unidades:**
```
1 → Centro        4 → Betim
2 → BH            5 → Ibirité
3 → Contagem
```

---

## Configuração do Código de Barras

O firmware suporta 3 formatos de barcode automaticamente:

| Formato | Exemplo | Resultado |
|---|---|---|
| Numérico puro | `"100"` | peca_code = 100 |
| Hex 4 chars | `"0064"` | peca_code = 100 (0x0064) |
| Alfanumérico | `"ABC-001"` | peca_code via CRC-16 |

> **Recomendação:** use barcodes numéricos de 1–5 dígitos (máx 65535) para mapeamento direto e previsível com os registros do banco de dados.

---

## Configuração do Arduino IDE

### 1. Instalar suporte ao ESP32
Arquivo → Preferências → URLs adicionais:
```
https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
```
Ferramentas → Gerenciador de placas → buscar "esp32" → instalar

### 2. Selecionar a placa
Ferramentas → Placa → ESP32 Arduino → **ESP32 Dev Module**

### 3. Instalar bibliotecas
Ferramentas → Gerenciar Bibliotecas → instalar:
- `MFRC522` (by GithubCommunity)
- `LiquidCrystal_I2C` (by Frank de Brabander)
- `ArduinoJson` (by Benoit Blanchon)
- **`Keypad` (by Mark Stanley, Alexander Brevig)** ← novo

### 4. Editar o firmware
No arquivo `voidlog_esp32.ino`, altere:
```cpp
const char* WIFI_SSID     = "SUA_REDE_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA_WIFI";
const char* API_HOST      = "http://192.168.1.100:5000";
#define BARCODE_BAUD  9600   // ajuste se seu leitor usar baud diferente
```

### 5. Upload
1. Conecte o ESP32 via USB
2. Ferramentas → Porta → selecione a porta correta
3. Clique em Upload (→)
4. Se travar em "Connecting...", segure o botão **BOOT** do ESP32 durante o upload

---

## Dicas para a Apresentação

1. **Demo ao vivo:**
   - Digite `4` + `#` (Furação)
   - Digite `2` + `#` (BH)
   - Passe o crachá → LCD mostra "LOGIN OK"
   - Leia o barcode da ferramenta → LCD mostra "RETIRADA OK"
   - Mostre o dashboard atualizando em tempo real

2. **Backup:** grave um vídeo do sistema funcionando caso a rede falhe.

3. **Barcodes de teste:** imprima etiquetas com barcodes dos números 100, 200, 300... e cole nas ferramentas de demonstração.

4. **Caixa:** coloque tudo em uma caixa de MDF com recortes para o LCD, teclado, leitor e antena RFID.
