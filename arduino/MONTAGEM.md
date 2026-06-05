# VoidLog — Guia de Montagem do Hardware (RFID Only)

## Lista de Componentes

| Componente | Especificação | Qtd | Preço estimado |
|---|---|---|---|
| ESP32 DevKit V1 | com WiFi/Bluetooth | 1 | R$ 35–50 |
| Módulo RFID RC522 | SPI, 13,56 MHz | 1 | R$ 15–25 |
| Tags RFID (crachás/peças) | ISO 14443A | 5+ | R$ 2–5 cada |
| Teclado Membrana 4×4 | 16 teclas, conector flat | 1 | R$ 10–18 |
| Display LCD 16×2 | com módulo I2C PCF8574 | 1 | R$ 20–30 |
| Buzzer passivo 5V | — | 1 | R$ 3–8 |
| LED Verde 5mm | difuso | 1 | R$ 1 |
| LED Vermelho 5mm | difuso | 1 | R$ 1 |
| Resistor 220Ω | 1/4W | 2 | < R$ 1 |
| Resistor 10kΩ | 1/4W (pull-up BTN_RESET) | 1 | < R$ 1 |
| Botão tátil 6×6mm | reset físico | 1 | R$ 1 |
| Protoboard 830 pontos | ou PCB perfurada | 1 | R$ 20–35 |
| Jumpers macho-macho | kit 40 peças | 1 | R$ 10–15 |
| Cabo USB micro/USB-C | para programar o ESP32 | 1 | — |

**Custo total estimado: R$ 120–195**

> ℹ️ Esta versão **não usa leitor de código de barras**. Tanto operadores quanto peças
> são identificados exclusivamente por tags RFID RC522.

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

### Teclado Membrana 4×4 → ESP32

O teclado tem **8 pinos** no conector flat (4 linhas + 4 colunas).

```
Teclas:  [1][2][3][A]
         [4][5][6][B]
         [7][8][9][C]
         [*][0][#][D]

Conector (da esquerda para a direita):
  Pino 1 → Linha 1 (teclas 1,2,3,A)
  Pino 2 → Linha 2 (teclas 4,5,6,B)
  Pino 3 → Linha 3 (teclas 7,8,9,C)
  Pino 4 → Linha 4 (teclas *,0,#,D)
  Pino 5 → Coluna 1 (teclas 1,4,7,*)
  Pino 6 → Coluna 2 (teclas 2,5,8,0)
  Pino 7 → Coluna 3 (teclas 3,6,9,#)
  Pino 8 → Coluna 4 (teclas A,B,C,D)
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
| 8 (C4) | Coluna 4 | **GPIO 32** |

> ℹ️ A biblioteca **Keypad** configura linhas como saída e colunas como entrada com
> pull-up interno. Não são necessários resistores externos no teclado.
> As teclas A/B/C/D são reconhecidas pelo firmware mas ignoradas na entrada de
> setor/unidade — reservadas para uso futuro.

---

### LCD 16×2 I2C → ESP32

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
| Buzzer | **GPIO 15** | GND | — |
| LED Verde | **GPIO 17** → R 220Ω | GND | Resistor obrigatório |
| LED Vermelho | **GPIO 2** | GND | LED onboard, resistor opcional |
| Botão RESET | **GPIO 34** | GND | Adicione 10kΩ entre GPIO 34 e 3.3V |

> ⚠️ GPIO 34 não possui pull-up interno. O resistor de **10kΩ** para 3.3V é obrigatório
> para evitar leitura flutuante.

---

## Diagrama de Blocos

```
                    ┌─────────────────────────────────┐
                    │          ESP32 DevKit            │
                    │                                  │
  RC522 ────SPI─────│ GPIO 5/18/23/19/4               │
                    │                                  │
  Teclado 4×4 ──────│ GPIO 13,12,14,27 (linhas)       │
                    │ GPIO 26,25,33,32  (colunas)      │
                    │                                  │
  LCD I2C ───I2C────│ GPIO 21 (SDA), 22 (SCL)         │
                    │                                  │
  Buzzer ───────────│ GPIO 15                         │
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
[Ligar / RESET] → DIGITAR_SETOR
                      │
                      │ Digita 1–8 + pressiona #
                      ▼
                  DIGITAR_UNIDADE
                      │
                      │ Digita 1–5 + pressiona #
                      │ (* cancela → volta ao setor)
                      ▼
                  AGUARDAR_TAG ◄──── timeout 30s → DIGITAR_SETOR
                      │
                      │  Passa tag RFID (crachá OU peça)
                      │     • Crachá  → login / logout registrado
                      │     • Peça    → retirada / devolução registrada
                      ▼
                  RESULTADO (LCD 3s)
                      │
                      └──────────────► AGUARDAR_TAG

[Tecla *] em qualquer momento → DIGITAR_SETOR
[Botão RESET físico]           → DIGITAR_SETOR
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

## Configuração do Firmware

### 1. Instalar suporte ao ESP32 no Arduino IDE
Arquivo → Preferências → URLs adicionais:
```
https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
```
Ferramentas → Placa → Gerenciador de placas → buscar "esp32" → instalar

### 2. Selecionar a placa
Ferramentas → Placa → ESP32 Arduino → **ESP32 Dev Module**

### 3. Instalar bibliotecas
Ferramentas → Gerenciar Bibliotecas → instalar:
- `MFRC522` (by GithubCommunity)
- `LiquidCrystal_I2C` (by Frank de Brabander)
- `ArduinoJson` (by Benoit Blanchon)
- `Keypad` (by Mark Stanley, Alexander Brevig)

### 4. Editar o firmware
No arquivo `voidlog_esp32.ino`, altere as 3 linhas de configuração:
```cpp
const char* WIFI_SSID     = "SUA_REDE_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA_WIFI";
const char* API_HOST      = "http://192.168.1.100:5000";  // IP do servidor Flask
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
   - Passe o crachá do operador → LCD mostra `>> LOGIN OK`
   - Passe a tag da peça → LCD mostra `RETIRADA OK`
   - Passe a tag da peça novamente → LCD mostra `DEVOLUCAO OK`
   - Passe o crachá novamente → LCD mostra `<< LOGOUT OK`
   - Mostre o dashboard atualizando em tempo real

2. **Backup:** grave um vídeo do sistema funcionando caso a rede falhe.

3. **Tags de teste:** use cores diferentes para distinguir crachás (azul) de peças (vermelho) na demonstração.

4. **Caixa:** coloque tudo em uma caixa de MDF com recortes para o LCD, teclado e antena RFID.
