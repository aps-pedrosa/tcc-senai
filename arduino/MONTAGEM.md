# VoidLog — Guia de Montagem do Hardware

## Lista de componentes

| Componente | Especificação | Qtd | Preço estimado |
|---|---|---|---|
| ESP32 DevKit V1 | com WiFi/Bluetooth | 1 | R$ 35–50 |
| Módulo RFID RC522 | SPI, 13,56 MHz | 1 | R$ 15–25 |
| Tags RFID (cartões/adesivos) | ISO 14443A | 10+ | R$ 2–5 cada |
| Display LCD 16x2 | com módulo I2C PCF8574 | 1 | R$ 20–30 |
| Rotary Encoder KY-040 | com botão integrado | 1 | R$ 8–15 |
| Buzzer 5V passivo | ativo ou passivo | 1 | R$ 3–8 |
| LED Verde 5mm | difuso | 1 | R$ 1 |
| LED Vermelho 5mm | difuso | 1 | R$ 1 |
| Resistor 220Ω | 1/4W | 2 | < R$ 1 |
| Botão tátil 6x6mm | push button | 1 | R$ 1 |
| Protoboard 400 pontos | ou PCB perfurada | 1 | R$ 15–25 |
| Jumpers macho-macho | kit 40 peças | 1 | R$ 10–15 |
| Cabo USB micro/USB-C | para programar o ESP32 | 1 | — |

**Custo total estimado: R$ 110–170**

---

## Pinagem completa

### RC522 (SPI) → ESP32

> ⚠️ CRÍTICO: O RC522 opera em 3.3V. Conectar em 5V queima o módulo.

| RC522 | ESP32 GPIO | Observação |
|---|---|---|
| SDA (SS) | 5 | Slave Select do SPI |
| SCK | 18 | Clock SPI |
| MOSI | 23 | Dados para o módulo |
| MISO | 19 | Dados do módulo |
| RST | 4 | Reset do módulo |
| GND | GND | — |
| 3.3V | 3.3V | ← apenas 3.3V! |

### LCD 16x2 I2C (PCF8574) → ESP32

| LCD I2C | ESP32 GPIO | Observação |
|---|---|---|
| SDA | 21 | I2C Data |
| SCL | 22 | I2C Clock |
| VCC | 5V | LCD precisa de 5V |
| GND | GND | — |

> Nota: O barramento I2C (GPIO 21/22) pode ter vários dispositivos ao mesmo tempo.
> O endereço padrão do PCF8574 é `0x27`. Se o display não ligar, tente `0x3F`.

### Rotary Encoder KY-040 → ESP32

| Encoder | ESP32 GPIO | Observação |
|---|---|---|
| CLK (A) | 34 | Interrupção (input only) |
| DT  (B) | 35 | Interrupção (input only) |
| SW  (botão) | 32 | Pull-up interno ativado |
| + (VCC) | 3.3V | — |
| GND | GND | — |

> GPIOs 34 e 35 no ESP32 são input-only (sem pull-up interno).
> O KY-040 já tem resistores pull-up próprios — sem problema.

### Periféricos → ESP32

| Componente | Pino (+) | Pino (−) | Obs |
|---|---|---|---|
| Buzzer | GPIO 25 | GND | — |
| LED Verde | GPIO 26 → R 220Ω | GND | Resistor em série obrigatório |
| LED Vermelho | GPIO 27 → R 220Ω | GND | Resistor em série obrigatório |
| Botão Reset | GPIO 33 | GND | Pull-up interno ativado no código |

---

## Passo a passo de montagem na protoboard

### 1. Alimentação da protoboard

Conecte as trilhas de alimentação:
- Trilha (+) vermelha → 3.3V do ESP32
- Trilha (−) preta → GND do ESP32
- Trilha (+) azul → 5V do ESP32 (pino VIN ou 5V)

### 2. Posicionamento do ESP32

Encaixe o ESP32 no centro da protoboard, com os pinos
de cada lado ficando na faixa de furos da protoboard.

### 3. Módulo RC522

Posicione o RC522 no canto superior esquerdo da protoboard.
Faça as conexões com jumpers seguindo a tabela SPI acima.
Use jumpers curtos e de cores diferentes para cada sinal.

### 4. Display LCD I2C

O módulo I2C fica na parte superior direita.
São apenas 4 fios: VCC (5V), GND, SDA, SCL.
Se o display não ligar, gire o trimpot azul do módulo I2C
para ajustar o contraste.

### 5. Rotary Encoder KY-040

Posicione na parte esquerda da protoboard.
Conecte CLK e DT nos GPIOs 34 e 35 (interrupção).
O botão SW vai para GPIO 32.

### 6. LEDs com resistores

Para cada LED:
1. Encaixe o LED na protoboard (perna longa = anodo = +)
2. Conecte um resistor 220Ω entre o anodo e o fio do GPIO
3. Conecte o catodo (perna curta) ao GND

### 7. Buzzer

Conecte o pino (+) ao GPIO 25 e o (−) ao GND.
Se o buzzer for ativo (com oscilador interno), ele vai apitar
com digitalWrite HIGH. Se for passivo, o código já usa
digitalWrite, o que funciona para bips simples.

### 8. Botão de Reset

Conecte um terminal ao GPIO 33 e o outro ao GND.
O pull-up interno é ativado no código (`INPUT_PULLUP`).

---

## Como funciona o firmware

### Máquina de estados

```
[Ligar] → SELECIONAR_SETOR
              ↓ (girar encoder = muda setor)
              ↓ (pressionar botão do encoder)
         SELECIONAR_UNIDADE
              ↓ (girar encoder = muda unidade)
              ↓ (pressionar botão do encoder)
         AGUARDAR_LEITURA  ←─────────────────────┐
              ↓ (tag RFID aproximada)              │
         PROCESSANDO                               │
              ↓ (resposta da API recebida)         │
         EXIBIR_RESULTADO ──── após 3 segundos ───┘

[Botão Reset físico] → volta para SELECIONAR_SETOR (qualquer momento)
```

### Lógica dos bytes do UID

O firmware lê **apenas os 2 primeiros bytes** da tag RFID
(que identificam a peça — B1 e B2).

Os bytes B3 (setor) e B4 (unidade) são injetados pelo firmware
a partir da seleção física no encoder rotativo.

Assim, a mesma tag pode pertencer a setores diferentes
dependendo de onde o leitor está configurado.

Exemplo: Tag com UID bruto `0064`
- Configurado para Furação / Ibirité → UID enviado: `00640405`
- Configurado para Usinagem / BH     → UID enviado: `00640302`

### Display LCD — mensagens

| Estado | Linha 1 | Linha 2 |
|---|---|---|
| Seleção de setor | `>> Setor:` | nome do setor atual |
| Seleção de unidade | `>> Unidade:` | nome da unidade atual |
| Aguardando tag | `Furacao/BH` | `Aprox. a tag...` |
| Processando | `Enviando...` | UID completo |
| Login de operador | `>> LOGIN OK` | `Ola, [nome]!` |
| Logout de operador | `<< LOGOUT OK` | `Tchau, [nome]!` |
| Retirada | `RETIRADA OK` | nome da ferramenta |
| Devolução | `DEVOLUCAO OK` | nome da ferramenta |
| Erro | `ERRO` | mensagem da API |

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

### 4. Editar o firmware

No arquivo `VoidLog.ino`, altere:
```cpp
const char* WIFI_SSID     = "SUA_REDE_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA_WIFI";
const char* API_HOST      = "http://192.168.1.100:5000";
```

Para descobrir o IP do seu PC com Flask rodando:
- Windows: `ipconfig` no CMD
- Linux/Mac: `hostname -I` no terminal

### 5. Fazer upload

1. Conecte o ESP32 via USB
2. Selecione a porta correta em Ferramentas → Porta
3. Clique em Upload (→)
4. Se travar em "Connecting...", segure o botão BOOT do ESP32
   durante o upload

---

## Teste rápido sem protoboard

Para testar o firmware antes de montar o circuito:
1. Suba o código apenas com WiFi e LCD
2. Abra o Monitor Serial (115200 baud)
3. Verifique se o ESP32 conecta ao WiFi e o IP aparece
4. Use a aba "Terminal RFID" do dashboard para simular
   leituras e testar as respostas da API

---

## Dicas para a apresentação do TCC

1. **Caixa física**: coloque tudo em uma caixa de MDF ou
   impressa em 3D. O visual profissional impressiona a banca.

2. **Demo ao vivo**: prepare o roteiro:
   - Selecionar setor "Furação" no encoder → bip de confirmação
   - Selecionar unidade "Ibirité" → dois bips
   - Passar crachá → LCD mostra "LOGIN OK"
   - Passar ferramenta → LCD mostra "RETIRADA OK"
   - Mostrar o dashboard atualizando em tempo real no notebook

3. **Dados fictícios**: o banco já vem populado com 80+
   movimentações de exemplo para os gráficos ficarem cheios.

4. **Backup**: tenha um vídeo gravado do sistema funcionando
   caso a rede falhe na apresentação.
