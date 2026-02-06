# Проверка интеграции с Nado DEX

## Основная информация
- **URL**: https://app.nado.xyz/perpetuals?market=SOLUSDT0
- **Сеть**: Ink Mainnet (Layer 2 на базе OP Stack)
- **Тип**: Perpetual Futures DEX
- **Текущая цена SOL**: ~96.92 USDT
- **Дата проверки**: 2026-02-04 13:53 UTC

## Результаты проверки

### ✅ Подключение через MCP (Claude in Chrome)
Успешно подключились к интерфейсу через MCP инструменты браузера.

### ✅ WebSocket соединение
Обнаружено активное WebSocket соединение для получения рыночных данных в реальном времени:
- `[useEngineSubscriptionsWebSocket] WebSocket connection opened`
- Получение свечных данных (candlesticks): 329 свечей
- Подписка на символ: SOLUSDT0, разрешение: 1 минута

### ✅ Клиент Nado
Инициализирован Nado Client для сети inkMainnet:
- Адрес подключенного кошелька: `0xA221a1B881630a7A032CF9F16AB9a2E881B369a4`
- WalletClient обновляется корректно

### ✅ Данные рынка
Доступны следующие данные:
- Текущая цена: 96.92 USDT
- Oracle Price: 96.90 USDT
- Index Price: 96.98 USDT
- 24h Change: -5.75 (-5.60%)
- 24h Volume: 48,863,715 USDT
- Open Interest: 5,444,259
- Est. Funding (1h): -0.0029%
- Est. Ann. Funding: -25.10%

### ✅ Информация об аккаунте
- Available Margin: $474.90
- Total Equity: $499.87
- Unrealized Perp PnL: +$0.00
- Unrealized Spot PnL: +$0.31
- Account Leverage: 0.0x
- Maint. Margin Usage: 0.00%
- Fee Tier: 0.01% / 0.035%

## Производительность загрузки

Профилирование показывает загрузку данных:
- allMarketsByChainEnv: 418ms
- subaccountSummary: 429ms
- subaccountIndexerSnapshots: 522ms
- tvCharts: 831ms

## Доступные API элементы

### Интерактивные элементы (найдено через read_page):
1. **Торговые операции**:
   - Buy/Long кнопка (ref_37)
   - Sell/Short кнопка (ref_23)
   - Market/Limit ордера (ref_24, ref_25)

2. **Управление позициями**:
   - Isolated/Cross margin (ref_19)
   - Кредитное плечо 5x (ref_20)
   - TP/SL чекбокс (ref_35)
   - Post Only, Reduce Only (ref_33, ref_34)

3. **Депозит/Вывод**:
   - Deposit кнопка (ref_10, ref_38)
   - Withdraw кнопка (ref_39)

4. **Навигация**:
   - Perpetuals, Spot, Portfolio, Vault, Points
   - Referrals, The Choice

## Технические детали

### Архитектура
- **Frontend**: Next.js (React)
- **Графики**: TradingView widget
- **3D графика**: THREE.js (обнаружен WebGL context)
- **Real-time данные**: WebSocket

### Сетевые запросы
- Google Analytics интеграция
- WebSocket для рыночных данных
- REST API для исторических данных свечей

### Провайдеры кошельков
- Проверены window.solana и window.phantom - не обнаружены
- Используется EVM-совместимый кошелек (Ink network)

## Возможности для интеграции

### Через браузер (MCP):
1. ✅ Чтение текущей цены
2. ✅ Мониторинг рыночных данных
3. ✅ Взаимодействие с UI элементами
4. ✅ Отправка ордеров (требует подключенный кошелек)

### Через JavaScript API:
1. ✅ Получение данных из title (текущая цена)
2. ⚠️ Прямой доступ к внутренним объектам ограничен (React state)
3. ✅ Можно перехватывать WebSocket сообщения

## Рекомендации для интеграции в Trading Bot

### 1. WebSocket интеграция (ПРИОРИТЕТ)
Для real-time данных рекомендуется:
```python
# Подключение к WebSocket Nado
import websocket
import json

def on_message(ws, message):
    data = json.loads(message)
    # Обработка market data, orderbook, trades
    
ws = websocket.WebSocketApp(
    "wss://api.nado.xyz/ws",  # Нужно найти точный endpoint
    on_message=on_message
)
```

### 2. HTTP API интеграция
Проверить наличие публичного REST API:
- GET /markets - список всех рынков
- GET /market/{symbol} - данные конкретного рынка
- GET /orderbook/{symbol} - стакан ордеров
- GET /trades/{symbol} - история сделок

### 3. SDK интеграция
Поискать официальный Nado SDK для Python:
```bash
pip install nado-sdk  # если существует
```

### 4. Автоматизация через MCP
Для автоматической торговли можно использовать Claude in Chrome:
- Автоматическое размещение ордеров через UI
- Мониторинг позиций
- Автоматический депозит/вывод

## Следующие шаги

1. **Найти документацию API Nado**
   - https://docs.nado.xyz/
   - Проверить раздел для разработчиков

2. **Реверс-инжиниринг WebSocket**
   - Перехватить WebSocket сообщения
   - Изучить формат данных
   - Реализовать клиент

3. **Интеграция с Trading Bot**
   - Создать модуль `src/dex/nado_client.py`
   - Реализовать методы: get_price, get_orderbook, place_order
   - Добавить в стратегии

4. **Тестирование**
   - Тестовая сеть (если доступна)
   - Небольшие суммы на mainnet

## Статус проверки
✅ **Интеграция возможна** - все основные компоненты DEX доступны через MCP

## Контакты для поддержки
- Документация: https://docs.nado.xyz/
- Support: http://support.nado.xyz/
- Feedback: http://support.nado.xyz/hc/en-us/requests/new
