"""
Nado Gateway Client - простой HTTP клиент для Nado DEX API
Использует прямые HTTP запросы без зависимостей от официального SDK
"""
import aiohttp
import asyncio
from decimal import Decimal
from typing import Dict, List, Optional
import time
import logging
from eth_account import Account

# Импорт нашего EIP-712 модуля
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from nado_eip712 import (
    sign_order,
    address_to_sender_bytes32,
    INK_MAINNET_CHAIN_ID
)

logger = logging.getLogger(__name__)


class NadoGatewayClient:
    """
    HTTP клиент для Nado DEX Gateway API
    
    Использует:
    - EIP-712 для подписи ордеров
    - aiohttp для HTTP запросов
    - Прямую работу с Gateway API
    """
    
    def __init__(
        self,
        private_key: str,
        network: str = "mainnet",
        subaccount: str = "default"
    ):
        """
        Args:
            private_key: Приватный ключ (0x...)
            network: "mainnet" или "testnet"
            subaccount: Название субаккаунта
        """
        self.private_key = private_key
        self.account = Account.from_key(private_key)
        self.address = self.account.address
        self.subaccount = subaccount
        self.network = network
        
        # Sender для EIP-712
        self.sender = address_to_sender_bytes32(self.address, subaccount)
        
        # API URLs
        if network == "mainnet":
            self.gateway_url = "https://gateway.nado.xyz/v2"
            self.archive_url = "https://archive.nado.xyz/v2"
            self.chain_id = INK_MAINNET_CHAIN_ID  # 763373
        else:
            self.gateway_url = "https://gateway.test.nado.xyz/v2"
            self.archive_url = "https://archive.test.nado.xyz/v2"
            self.chain_id = 763373  # Testnet может быть другой
        
        logger.info(f"✅ NadoGatewayClient инициализирован")
        logger.info(f"   Network: {network}")
        logger.info(f"   Address: {self.address}")
        logger.info(f"   Gateway: {self.gateway_url}")
    
    # ═══════════════════════════════════════════════════════
    # ТОРГОВЫЕ ОПЕРАЦИИ
    # ═══════════════════════════════════════════════════════
    
    async def place_order(
        self,
        product_id: int,
        side: str,  # "buy" или "sell"
        price: Decimal,
        size: Decimal,
        order_type: str = "limit",  # "limit" или "market"
        post_only: bool = False,
        reduce_only: bool = False
    ) -> Optional[Dict]:
        """
        Разместить ордер
        
        Args:
            product_id: ID продукта (1=BTC, 4=SOL, etc)
            side: "buy" или "sell"
            price: Цена (для market = 0)
            size: Размер позиции
            order_type: "limit" или "market"
            post_only: Только maker ордер
            reduce_only: Только закрытие позиции
        
        Returns:
            Результат от API или None при ошибке
        """
        try:
            # Конвертация в X18 формат
            price_x18 = int(price * Decimal(10**18)) if price > 0 else 0
            amount_x18 = int(size * Decimal(10**18))
            
            # Для sell amount отрицательный
            if side == "sell":
                amount_x18 = -amount_x18
            
            # Параметры ордера
            expiration = int(time.time()) + 3600  # 1 час
            nonce = int(time.time() * 1000000)  # Микросекунды для уникальности
            
            # Appendix (битовые флаги)
            appendix = 0
            if post_only:
                appendix |= 1  # Бит 0 = post_only
            if reduce_only:
                appendix |= 2  # Бит 1 = reduce_only
            
            # Подписать ордер через EIP-712
            signature = sign_order(
                private_key=self.private_key,
                sender=self.sender,
                price_x18=price_x18,
                amount=amount_x18,
                expiration=expiration,
                nonce=nonce,
                appendix=appendix,
                product_id=product_id,
                chain_id=self.chain_id
            )
            
            # Payload для API
            payload = {
                "order": {
                    "sender": self.sender,
                    "priceX18": str(price_x18),
                    "amount": str(amount_x18),
                    "expiration": expiration,
                    "nonce": nonce,
                    "appendix": appendix
                },
                "signature": signature,
                "spotLeverage": False  # Для perps = False
            }
            
            # Отправить в Gateway
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.gateway_url}/execute",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"✅ Ордер размещен: {side} {size} @ {price}")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Ошибка размещения ордера: {response.status} - {error_text}")
                        return None
        
        except Exception as e:
            logger.error(f"❌ place_order exception: {e}")
            return None
    
    async def cancel_order(self, product_id: int, digest: str) -> bool:
        """
        Отменить ордер
        
        Args:
            product_id: ID продукта
            digest: Digest ордера (хэш)
        
        Returns:
            True если успешно
        """
        try:
            payload = {
                "productId": product_id,
                "digest": digest,
                "sender": self.sender
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.gateway_url}/cancel",
                    json=payload
                ) as response:
                    if response.status == 200:
                        logger.info(f"✅ Ордер отменен: {digest}")
                        return True
                    else:
                        error = await response.text()
                        logger.error(f"❌ Ошибка отмены: {error}")
                        return False
        
        except Exception as e:
            logger.error(f"❌ cancel_order exception: {e}")
            return False
    
    async def cancel_all_orders(self, product_id: Optional[int] = None) -> int:
        """
        Отменить все ордера
        
        Args:
            product_id: Если указан - только для этого продукта
        
        Returns:
            Количество отмененных ордеров
        """
        try:
            payload = {"sender": self.sender}
            if product_id is not None:
                payload["productId"] = product_id
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.gateway_url}/cancel_all",
                    json=payload
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        count = result.get("cancelled", 0)
                        logger.info(f"✅ Отменено ордеров: {count}")
                        return count
                    else:
                        return 0
        
        except Exception as e:
            logger.error(f"❌ cancel_all_orders exception: {e}")
            return 0
    
    # ═══════════════════════════════════════════════════════
    # ПОЛУЧЕНИЕ ДАННЫХ
    # ═══════════════════════════════════════════════════════
    
    async def get_account_balance(self) -> Optional[Dict]:
        """
        Получить баланс аккаунта
        
        Returns:
            Баланс и маржа или None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.gateway_url}/subaccount",
                    params={"address": self.address, "subaccount": self.subaccount}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Баланс получен: {data}")
                        return data
                    else:
                        error = await response.text()
                        logger.warning(f"⚠️ Ошибка получения баланса: {error}")
                        return None
        
        except Exception as e:
            logger.error(f"❌ get_account_balance exception: {e}")
            return None
    
    async def get_open_positions(self) -> Optional[List[Dict]]:
        """
        Получить открытые позиции
        
        Returns:
            Список позиций или пустой список
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.gateway_url}/positions",
                    params={"address": self.address, "subaccount": self.subaccount}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        positions = data.get("positions", [])
                        logger.info(f"✅ Получено позиций: {len(positions)}")
                        return positions
                    else:
                        logger.warning(f"⚠️ Ошибка получения позиций")
                        return []
        
        except Exception as e:
            logger.error(f"❌ get_open_positions exception: {e}")
            return []
    
    async def get_open_orders(self, product_id: Optional[int] = None) -> List[Dict]:
        """
        Получить открытые ордера
        
        Args:
            product_id: Если указан - только для этого продукта
        
        Returns:
            Список ордеров
        """
        try:
            params = {
                "address": self.address,
                "subaccount": self.subaccount
            }
            if product_id is not None:
                params["productId"] = product_id
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.gateway_url}/orders",
                    params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        orders = data.get("orders", [])
                        logger.info(f"✅ Получено ордеров: {len(orders)}")
                        return orders
                    else:
                        return []
        
        except Exception as e:
            logger.error(f"❌ get_open_orders exception: {e}")
            return []
    
    async def get_products(self) -> List[Dict]:
        """
        Получить список доступных продуктов
        
        Returns:
            Список продуктов
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.gateway_url}/products") as response:
                    if response.status == 200:
                        data = await response.json()
                        products = data.get("products", [])
                        logger.info(f"✅ Получено продуктов: {len(products)}")
                        return products
                    else:
                        return []
        
        except Exception as e:
            logger.error(f"❌ get_products exception: {e}")
            return []
    
    async def get_market_price(self, product_id: int) -> Optional[Decimal]:
        """
        Получить текущую рыночную цену
        
        Args:
            product_id: ID продукта
        
        Returns:
            Цена или None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.archive_url}/ticker",
                    params={"productId": product_id}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        price = Decimal(data.get("lastPrice", 0))
                        logger.info(f"✅ Цена продукта {product_id}: {price}")
                        return price
                    else:
                        return None
        
        except Exception as e:
            logger.error(f"❌ get_market_price exception: {e}")
            return None
    
    async def get_orderbook(self, product_id: int, depth: int = 10) -> Optional[Dict]:
        """
        Получить стакан ордеров
        
        Args:
            product_id: ID продукта
            depth: Глубина стакана
        
        Returns:
            {"bids": [...], "asks": [...]}
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.gateway_url}/orderbook",
                    params={"productId": product_id, "depth": depth}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Orderbook получен для продукта {product_id}")
                        return data
                    else:
                        return None
        
        except Exception as e:
            logger.error(f"❌ get_orderbook exception: {e}")
            return None
    
    # ═══════════════════════════════════════════════════════
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ═══════════════════════════════════════════════════════
    
    async def get_product_id_by_symbol(self, symbol: str) -> Optional[int]:
        """
        Получить product_id по символу
        
        Args:
            symbol: Символ типа "BTC-PERP", "SOL-PERP"
        
        Returns:
            product_id или None
        """
        products = await self.get_products()
        for product in products:
            if product.get("symbol") == symbol:
                return product.get("productId")
        
        logger.warning(f"⚠️ Продукт {symbol} не найден")
        return None
    
    async def market_buy(self, product_id: int, size: Decimal) -> Optional[Dict]:
        """
        Market buy (покупка по рынку)
        
        Args:
            product_id: ID продукта
            size: Размер позиции
        
        Returns:
            Результат или None
        """
        return await self.place_order(
            product_id=product_id,
            side="buy",
            price=Decimal(0),  # Market order
            size=size,
            order_type="market"
        )
    
    async def market_sell(self, product_id: int, size: Decimal) -> Optional[Dict]:
        """
        Market sell (продажа по рынку)
        
        Args:
            product_id: ID продукта
            size: Размер позиции
        
        Returns:
            Результат или None
        """
        return await self.place_order(
            product_id=product_id,
            side="sell",
            price=Decimal(0),  # Market order
            size=size,
            order_type="market"
        )
    
    async def close_position(self, product_id: int) -> bool:
        """
        Закрыть позицию (market order в противоположную сторону)
        
        Args:
            product_id: ID продукта
        
        Returns:
            True если успешно
        """
        try:
            # Получить открытые позиции
            positions = await self.get_open_positions()
            
            for pos in positions:
                if pos.get("productId") == product_id:
                    size = abs(Decimal(pos.get("size", 0)))
                    
                    if size > 0:
                        # Определить сторону закрытия
                        side = "sell" if Decimal(pos.get("size", 0)) > 0 else "buy"
                        
                        # Закрыть через market order
                        result = await self.place_order(
                            product_id=product_id,
                            side=side,
                            price=Decimal(0),
                            size=size,
                            order_type="market",
                            reduce_only=True
                        )
                        
                        if result:
                            logger.info(f"✅ Позиция закрыта: {product_id}")
                            return True
            
            logger.warning(f"⚠️ Позиция {product_id} не найдена")
            return False
        
        except Exception as e:
            logger.error(f"❌ close_position exception: {e}")
            return False


# ═══════════════════════════════════════════════════════
# ТЕСТИРОВАНИЕ
# ═══════════════════════════════════════════════════════

async def test_client():
    """Тест клиента"""
    
    # Тестовый ключ (НЕ используйте для реальных денег!)
    test_key = "0x98a424193ef94a9e2f573a545f657f393faa9420c4b81753c0cb0425f0917966"
    
    print("=" * 60)
    print("TEST NADO GATEWAY CLIENT")
    print("=" * 60)
    
    # Создать клиент для testnet
    client = NadoGatewayClient(
        private_key=test_key,
        network="testnet"
    )
    
    print(f"\nOK Client created")
    print(f"   Address: {client.address}")
    print(f"   Network: {client.network}")
    
    # Тест 1: Получить продукты
    print("\n1. Getting products...")
    products = await client.get_products()
    print(f"   Available products: {len(products)}")
    if products:
        for p in products[:3]:
            print(f"   - {p.get('symbol')}: ID={p.get('productId')}")
    
    # Тест 2: Получить баланс
    print("\n2. Getting balance...")
    balance = await client.get_account_balance()
    if balance:
        print(f"   Balance: {balance}")
    
    # Тест 3: Получить позиции
    print("\n3. Getting positions...")
    positions = await client.get_open_positions()
    print(f"   Open positions: {len(positions)}")
    
    # Тест 4: Получить цену
    print("\n4. Getting BTC price...")
    price = await client.get_market_price(1)  # BTC = product_id 1
    if price:
        print(f"   BTC price: ${price}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Запуск теста
    asyncio.run(test_client())
