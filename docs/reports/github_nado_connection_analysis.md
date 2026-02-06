# Как GitHub бот подключен к Nado DEX

**Анализ репозитория**: https://github.com/Furia-cell/nado_bot

---

## 🔑 КЛЮЧЕВОЕ ОТКРЫТИЕ

GitHub бот использует **ОФИЦИАЛЬНЫЙ Nado Protocol SDK**: `nado-protocol`

---

## 1. Архитектура подключения

### Схема работы:

```
┌─────────────────────┐
│   nado_bot          │
│  (ваш GitHub)       │
└──────────┬──────────┘
           │
           ├─── import nado_protocol SDK
           │    pip install nado-protocol
           │
           ├─── create_nado_client()
           │    ↓
           │    mode: "mainnet" или "testnet"
           │    signer: private_key
           │    context_opts: endpoints (опционально)
           │
           └─── Официальные Nado endpoints:
                • RPC Node
                • Engine Endpoint
                • Indexer Endpoint  
                • Trigger Endpoint
```

---

## 2. Код подключения (nado_client.py)

### Импорты:
```python
from nado_protocol.client import NadoClientMode, create_nado_client
from nado_protocol.client.context import NadoClientContextOpts
```

### Создание клиента:
```python
def create_client(
    network: str,                    # "mainnet" или "testnet"
    private_key: str,                # Ваш приватный ключ
    rpc_node_url: Optional[str] = None,
    engine_endpoint_url: Optional[str] = None,
    indexer_endpoint_url: Optional[str] = None,
    trigger_endpoint_url: Optional[str] = None,
):
    # Парсим режим (mainnet/testnet)
    mode = _parse_mode(network, NadoClientMode)
    
    # Опциональные настройки endpoints
    context_opts = None
    if any([rpc_node_url, engine_endpoint_url, 
            indexer_endpoint_url, trigger_endpoint_url]):
        context_opts = NadoClientContextOpts(
            rpc_node_url=rpc_node_url,
            engine_endpoint_url=engine_endpoint_url,
            indexer_endpoint_url=indexer_endpoint_url,
            trigger_endpoint_url=trigger_endpoint_url,
        )
    
    # Создаем клиент через SDK
    return create_nado_client(
        mode=mode, 
        signer=private_key, 
        context_opts=context_opts
    )
```

---

## 3. Конфигурация (config.yaml)

```yaml
# Сеть подключения
NETWORK: "mainnet"

# Имя субаккаунта
SUBACCOUNT_NAME: "default"

# Метка стратегии
STRATEGY_LABEL: "default_strategy(balanced)"

# Endpoints (null = использовать дефолтные из SDK)
RPC_NODE_URL: null
ENGINE_ENDPOINT_URL: null
INDEXER_ENDPOINT_URL: null
TRIGGER_ENDPOINT_URL: null

# ID продукта для торговли
PRODUCT_ID: 4

# Источник цен
PRICE_SOURCE: "latest_market_price"
USE_MARK_PRICE: false

# Параметры ордеров
ORDER_SIZE: "0.12"
BASE_SPREAD_BPS: 10
MIN_SPREAD_BPS: 6
MAX_SPREAD_BPS: 80
```

**Важно**: Все endpoints установлены в `null`, что означает использование **дефолтных endpoints из SDK**!

---

## 4. Зависимости (requirements.txt)

```
nado-protocol     # ОФИЦИАЛЬНЫЙ SDK
pyyaml
requests
matplotlib
```

---

## 5. Основные функции клиента

### Получение цен:
```python
def get_mid_bid_ask(client, product_id: int, use_mark_price: bool = False):
    # Получает bid/ask цены из Nado
    prices = client.perp.get_prices(product_id)
    
    if use_mark_price:
        # Mark price для маржинальной торговли
        prices = client.market.get_latest_market_price(product_id)
    
    return (bid + ask) / Decimal("2"), bid, ask
```

### Размещение ордеров:
```python
# Через SDK напрямую
client.perp.place_order(...)
```

### Получение позиций:
```python
# Через SDK
client.perp.get_positions(...)
```

---

## 6. Как это работает

### Шаг 1: Установка SDK
```bash
pip install nado-protocol
```

### Шаг 2: Инициализация клиента
```python
from bot.nado_client import create_client

client = create_client(
    network="mainnet",
    private_key="YOUR_PRIVATE_KEY"
)
```

### Шаг 3: Использование API
```python
# Получить цену
price = client.market.get_latest_market_price(product_id=4)

# Разместить ордер
client.perp.place_order(...)

# Получить позиции
positions = client.perp.get_positions()
```

---

## 7. Сравнение с вашим локальным ботом

| Аспект | GitHub (nado_bot) | Локальный (Trading_bot) |
|--------|-------------------|-------------------------|
| **SDK** | ✅ nado-protocol (официальный) | ❌ Самописный |
| **Подключение** | ✅ Прямое к Nado DEX | ❌ Через Binance API |
| **Торговля** | ✅ Реальная на Nado | ❌ Только мониторинг |
| **Endpoints** | ✅ Официальные Nado | ❌ REST API (404) |
| **Private key** | ✅ Используется | ✅ Есть, но не используется |

---

## 8. ЧТО НУЖНО СДЕЛАТЬ В ВАШЕМ БОТЕ

### Вариант 1: Использовать nado-protocol SDK (РЕКОМЕНДУЕТСЯ)

#### Установка:
```bash
cd C:\Project\Trading_bot
pip install nado-protocol
```

#### Замена в коде:
```python
# СТАРЫЙ КОД (не работает):
from src.dex.nado_api import NadoAPI
nado_api = NadoAPI("https://api.nado.xyz")  # 404 ошибка

# НОВЫЙ КОД (работает):
from nado_protocol.client import create_nado_client, NadoClientMode

client = create_nado_client(
    mode=NadoClientMode.MAINNET,
    signer=private_key,
    context_opts=None  # Использовать дефолтные endpoints
)

# Получить цену:
price = client.market.get_latest_market_price(product_id=4)

# Разместить ордер:
client.perp.place_order(
    product_id=4,
    size=Decimal("0.1"),
    price=Decimal("97000"),
    side="buy"
)
```

---

## 9. Структура файлов для интеграции

Создайте новый файл: `C:\Project\Trading_bot\src\dex\nado_protocol_client.py`

```python
"""
Клиент Nado DEX через официальный SDK
"""
from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.client.context import NadoClientContextOpts
from decimal import Decimal
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class NadoProtocolClient:
    """Обертка над официальным Nado Protocol SDK"""
    
    def __init__(
        self, 
        network: str = "mainnet",
        private_key: str = None,
        rpc_node_url: Optional[str] = None,
        engine_endpoint_url: Optional[str] = None,
        indexer_endpoint_url: Optional[str] = None,
        trigger_endpoint_url: Optional[str] = None
    ):
        mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
        
        context_opts = None
        if any([rpc_node_url, engine_endpoint_url, indexer_endpoint_url, trigger_endpoint_url]):
            context_opts = NadoClientContextOpts(
                rpc_node_url=rpc_node_url,
                engine_endpoint_url=engine_endpoint_url,
                indexer_endpoint_url=indexer_endpoint_url,
                trigger_endpoint_url=trigger_endpoint_url
            )
        
        self.client = create_nado_client(
            mode=mode,
            signer=private_key,
            context_opts=context_opts
        )
        logger.info(f"✅ Nado Protocol Client подключен к {network}")
    
    async def get_market_price(self, product_id: int) -> Optional[Decimal]:
        """Получить рыночную цену"""
        try:
            price_data = self.client.market.get_latest_market_price(product_id)
            if price_data:
                return Decimal(str(price_data))
        except Exception as e:
            logger.error(f"Ошибка получения цены: {e}")
        return None
    
    async def place_order(
        self, 
        product_id: int,
        side: str,  # "buy" или "sell"
        size: Decimal,
        price: Decimal,
        order_type: str = "limit"
    ):
        """Разместить ордер"""
        try:
            result = self.client.perp.place_order(
                product_id=product_id,
                side=side,
                size=str(size),
                price=str(price),
                order_type=order_type
            )
            logger.info(f"✅ Ордер размещен: {result}")
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка размещения ордера: {e}")
            return None
```

---

## 10. Итоговый план интеграции

### Шаг 1: Установить SDK
```bash
pip install nado-protocol
```

### Шаг 2: Создать новый клиент
Файл: `src/dex/nado_protocol_client.py` (код выше)

### Шаг 3: Обновить конфигурацию
```json
{
  "dex": {
    "name": "Nado",
    "network": "mainnet",
    "use_official_sdk": true
  },
  "wallet": {
    "private_key": "98a424193ef94a9e2f573a545f657f393faa9420c4b81753c0cb0425f0917966"
  }
}
```

### Шаг 4: Обновить TradingBot
```python
# В src/bot/trading_bot.py

# БЫЛО:
from dex.nado_api import NadoAPI
self.nado_api = NadoAPI(self.config["dex"]["api_endpoint"])

# СТАЛО:
from dex.nado_protocol_client import NadoProtocolClient
self.nado_client = NadoProtocolClient(
    network=self.config["dex"]["network"],
    private_key=self.config["wallet"]["private_key"]
)
```

### Шаг 5: Тестирование
```python
# Получить цену
price = await self.nado_client.get_market_price(product_id=4)
print(f"Цена SOL: ${price}")

# Разместить тестовый ордер
result = await self.nado_client.place_order(
    product_id=4,
    side="buy",
    size=Decimal("0.01"),
    price=Decimal("96.50")
)
```

---

## 11. Документация

**Официальная документация Nado Protocol**:
- SDK: https://github.com/nado-protocol/python-sdk (возможно)
- Docs: https://docs.nado.xyz
- PyPI: https://pypi.org/project/nado-protocol/

---

## 12. Заключение

**GitHub бот подключается к Nado через:**
1. ✅ Официальный SDK: `nado-protocol`
2. ✅ Private key для подписи транзакций
3. ✅ Режим mainnet/testnet
4. ✅ Дефолтные endpoints из SDK

**Ваш локальный бот должен:**
1. ❌ Перестать использовать Binance API
2. ✅ Установить `nado-protocol`
3. ✅ Использовать тот же подход, что и GitHub бот
4. ✅ Реальная торговля станет возможна!

---

## Следующие шаги:

1. Установить `pip install nado-protocol`
2. Создать `nado_protocol_client.py`
3. Обновить `trading_bot.py`
4. Протестировать на testnet
5. Запустить на mainnet
