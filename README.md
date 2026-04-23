<img width="1920" height="500" alt="banner_void" src="https://github.com/user-attachments/assets/b22fa42c-5652-4e83-83ee-4bda1d091210" />

## Sobre o projeto

O **Voidlog** é um sistema físico-digital desenvolvido para transformar o controle de consumo de ferramentas industriais em um processo **inteligente, preditivo e orientado a dados**.

A solução integra **IoT (ESP32 + sensores)** com **análise estatística e visualização em tempo real**, permitindo:

* rastrear retiradas de ferramentas
* prever consumo futuro
* detectar anomalias de uso
* otimizar níveis de estoque

Este projeto foi desenvolvido no contexto do **Desafio Indústria Parceira — TSEA**, com foco em inovação aplicada à Indústria 4.0.

---

## Problema

Em ambientes industriais, o controle de ferramentas e insumos frequentemente apresenta:

* baixa rastreabilidade no ponto de uso
* falta de previsibilidade no consumo
* desperdícios não identificados
* decisões reativas de reposição

Esses fatores impactam diretamente a eficiência operacional, custos e confiabilidade do processo produtivo.

---

## Solução

O Voidlog propõe uma arquitetura integrada que:

1. **Captura dados no chão de fábrica** via ESP32 e sensores
2. **Transmite eventos em tempo real** via rede local
3. **Armazena histórico de consumo** em banco de dados
4. **Aplica modelos estatísticos** para previsão e análise
5. **Exibe insights em dashboard inteligente**

---

## Diferencial

> O Voidlog não apenas registra dados — ele transforma dados em decisão.

Principais diferenciais:

*  **Previsão de consumo (forecasting)**
*  **Detecção de anomalias**
*  **Otimização de estoque**
*  **Arquitetura IoT escalável**
*  Integração entre hardware, software e análise de dados

---

## Arquitetura do sistema

```text
Operador
   ↓
ESP32 + Sensores
   ↓
(MQTT / HTTP)
   ↓
Backend API
   ↓
Banco de Dados
   ↓
Pipeline de Dados
   ↓
Modelos Estatísticos
   ↓
Dashboard Inteligente
```

---

## Tecnologias utilizadas

### Hardware

* ESP32
* Sensor de peso (Load Cell + HX711)
* Sensor de abertura (fim de curso)
* RFID (opcional)

---

### Backend

* Python (Flask / FastAPI)
* Pandas / NumPy
* Statsmodels / Prophet
* MQTT (Mosquitto)

---

### Banco de Dados

* SQLite / MySQL

---

### Frontend

* Dashboard web (React / Flask templates)
* Figma (prototipação)

---

## Funcionalidades

* Registro automático de retirada de itens
* Visualização de consumo em tempo real
* Previsão de demanda futura
* Identificação de padrões anômalos
* Indicador de risco de ruptura
* Recomendação de estoque ideal

---

## Demonstração (MVP)

O MVP demonstra:

* envio de eventos via ESP32
* armazenamento em banco de dados
* processamento de dados
* dashboard com insights

Fluxo demonstrado:

```text
Retirada simulada → Evento enviado → Banco atualizado → Dashboard reage → Alerta gerado
```

---

## Preview (em breve)

> Adicione aqui screenshots do dashboard, arquitetura e protótipo físico.

---

## Estrutura do repositório

```text
voidlog/
│
├── hardware/          # Código do ESP32
├── backend/           # API e lógica de negócio
├── data/              # Scripts e modelos estatísticos
├── dashboard/         # Interface do usuário
├── docs/              # Documentação e diagramas
└── README.md
```

---

## Como executar

### 1. Clonar o repositório

```bash
git clone https://github.com/seu-usuario/voidlog.git
cd voidlog
```

---

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
python app.py
```

---

### 3. Broker MQTT (opcional)

```bash
mosquitto
```

---

### 4. ESP32

* Carregar código via Arduino IDE / PlatformIO
* Configurar Wi-Fi e endpoint da API

---

### 5. Dashboard

```bash
cd dashboard
npm install
npm run dev
```

---

## Futuras melhorias

* Integração com ERP industrial
* Machine Learning avançado
* Interface mobile
* Identificação automática por visão computacional
* Deploy em nuvem (AWS / Azure)
* Suporte a múltiplas unidades industriais

---

## Impacto

O Voidlog contribui para:

* redução de desperdícios
* aumento da previsibilidade
* melhoria da tomada de decisão
* evolução digital da indústria

---

## Equipe

* Arthur Pedrosa dos Santos
* Isaque Almeida Pamplona
* Leonardo Belém Nascimento

---

## Pitch

> O Voidlog transforma o almoxarifado industrial em um sistema inteligente, capaz de prever o consumo, detectar desperdícios e apoiar decisões estratégicas em tempo real.

---
