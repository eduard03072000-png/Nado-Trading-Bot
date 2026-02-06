"""
Nado REST API Client - ПОЛНАЯ ВЕРСИЯ
Быстрая торговля через HTTP с EIP712 подписями
"""
import requests
import json
import time
from typing import Dict, Optional, Literal
from decimal import Decimal

# Импорт EIP712 модуля
import sys
import os
sys.path.append(os.path.dirname(__file__))
from nado_eip712 import sign_order, address_to_sender_bytes32, INK_MAINNET_CHAIN_ID


class NadoRESTClient:
    """
    REST API клиент для Nado DEX с EIP712 подписями
    БЫСТРЫЙ - <1 секунда на ордер
    """
    
    def __init__(
        self,
        private_key: str,
        mainnet: bool = True
    ):
        """
        Инициализация клиента
        
        Args:
            private_key: Приватный ключ кошелька (с 0x)
            mainnet: True = mainnet, False = testnet
        """
        self.private_key = private_key
        
        # Получить address из приватного ключа
        from eth_account import Account
        account = Account.from_key(private_key)
        self.address = account.address
        
        # Endpoints
        if mainnet:
            self.gateway_url = "https://gateway.prod.nado.xyz/v1"
            self.archive_url = "https://archive.prod.nado.xyz/v1"
            self.chain_id = INK_MAINNET_CHAIN_ID
        else:
            self.gateway_url = "https://gateway.test.nado.xyz/v1"
            self.archive_url = "https://archive.test.nado.xyz/v1"
            self.chain_id = 763373  # testnet
        
        # Sender bytes32
        self.sender = address_to_sender_bytes32(self.address, "default")
        
        # Nonce counter (millisecond timestamp)
        self._nonce = int(time.time() * 1000)
        
        print(f"🤖 Nado REST Client initialized")
        print(f"📍 Gateway: {self.gateway_url}")
        print(f"👛 Wallet: {self.address}")
        print(f"🔑 Sender: {self.sender}")
    
    def _get_nonce(self) -> int:
        """Получить следующий nonce"""
        self._nonce += 1
        return self._nonce
    
    def get_balance(self) -> Dict:
        """
        Получить баланс субаккаунта
        
        Returns:
            {
                "assets": float,
                "liabilities": float,
                "health": float,
                ...
            }
        """
        url = f"{self.gateway_url}/query"
        
        # POST запрос
        payload = {
            "type": "subaccount_info",
            "subaccount": self.sender
        }
        
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            resp.raise_for_status()
            data = resp.json()
            
            # Проверяем статус
            if data.get("status") != "success":
                return {"error": "API returned non-success status", "raw": data}
            
            # Парсим healths
            healths = data.get("data", {}).get("healths", [])
            if not healths:
                return {"error": "No health data", "raw": data}
            
            # Берём первый health (initial margin)
            health = healths[0]
            
            # Конвертируем из x18
            assets = float(health.get("assets", 0)) / 1e18
            liabilities = float(health.get("liabilities", 0)) / 1e18
            health_val = float(health.get("health", 0)) / 1e18
            
            return {
                "assets": assets,
                "liabilities": liabilities,
                "health": health_val,
                "available_margin": health_val,  # Health = доступная маржа
                "total_equity": assets - liabilities,
                "raw": data
            }
            
        except Exception as e:
            print(f"❌ Ошибка получения баланса: {e}")
            return {"error": str(e)}
    
    def get_positions(self) -> Dict:
        """
        Получить открытые позиции
        
        Returns:
            {
                "positions": [
                    {
                        "product_id": int,
                        "size": float,  # положительный = long, отрицательный = short
                        "entry_price": float,
                        "unrealized_pnl": float,
                        ...
                    }
                ]
            }
        """
        url = f"{self.gateway_url}/query"
        
        # POST запрос
        payload = {
            "type": "subaccount_info",
            "subaccount": self.sender
        }
        
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            resp.raise_for_status()
            data = resp.json()
            
            # Проверяем статус
            if data.get("status") != "success":
                return {"error": "API returned non-success status", "positions": []}
            
            positions = []
            
            # Парсим perp_balances
            perp_balances = data.get("data", {}).get("perp_balances", [])
            
            for item in perp_balances:
                product_id = item.get("product_id", 0)
                balance = item.get("balance", {})
                
                # Размер позиции
                amount_str = balance.get("amount", "0")
                amount_x18 = int(amount_str) if amount_str else 0
                size = float(amount_x18) / 1e18
                
                # Пропускаем нулевые позиции
                if size == 0:
                    continue
                
                # vQuoteBalance для entry price
                vquote_str = balance.get("v_quote_balance", "0")
                vquote_x18 = int(vquote_str) if vquote_str else 0
                entry_price = abs(float(vquote_x18) / 1e18 / size) if size != 0 else 0
                
                positions.append({
                    "product_id": product_id,
                    "size": size,
                    "entry_price": entry_price,
                    "unrealized_pnl": 0,  # TODO: рассчитать отдельно
                    "raw": item
                })
            
            return {
                "positions": positions,
                "count": len(positions)
            }
            
        except Exception as e:
            print(f"❌ Ошибка получения позиций: {e}")
            return {"error": str(e), "positions": []}
    
    def close_position(
        self,
        product_id: int,  # ID продукта
        size: Optional[float] = None  # Размер для закрытия (None = закрыть все)
    ) -> Dict:
        """
        Закрыть позицию через market ордер с reduce_only
        
        Args:
            product_id: ID продукта (1=SOL, 2=BTC, etc)
            size: Размер для закрытия (None = закрыть всю позицию)
        
        Returns:
            Response от API
        """
        print(f"\n{'='*60}")
        print(f"🔴 ЗАКРЫТИЕ ПОЗИЦИИ")
        print(f"{'='*60}")
        print(f"Продукт ID: {product_id}")
        
        # Получаем текущие позиции
        positions_data = self.get_positions()
        
        if "error" in positions_data:
            return {"error": f"Не удалось получить позиции: {positions_data['error']}"}
        
        # Ищем позицию по product_id
        position = None
        for pos in positions_data.get("positions", []):
            if pos["product_id"] == product_id:
                position = pos
                break
        
        if position is None:
            return {"error": f"Позиция по продукту {product_id} не найдена"}
        
        current_size = position["size"]
        
        print(f"📊 Текущая позиция: {current_size}")
        
        if current_size == 0:
            return {"error": "Позиция уже закрыта (размер = 0)"}
        
        # Определяем размер закрытия
        close_size = abs(size) if size is not None else abs(current_size)
        
        # Определяем сторону закрытия
        # Long позиция (size > 0) → закрываем через SELL
        # Short позиция (size < 0) → закрываем через BUY
        close_side = "sell" if current_size > 0 else "buy"
        
        print(f"📍 Закрываем: {close_size} через {close_side.upper()}")
        
        # Размещаем market ордер с reduce_only=True
        return self.place_market_order(
            product_id=product_id,
            side=close_side,
            size=close_size,
            reduce_only=True
        )
    
    def get_market_price(self, product_id: int) -> float:
        """
        Получить текущую рыночную цену (mid price)
        
        Args:
            product_id: ID продукта
            
        Returns:
            Текущая цена
        """
        url = f"{self.gateway_url}/query"
        
        payload = {
            "type": "market_info",
            "product_id": product_id
        }
        
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("status") == "success" and "data" in data:
                # Получаем mark price или index price
                mark_price_x18 = data["data"].get("mark_price_x18", "0")
                price = float(mark_price_x18) / 1e18
                return price
            
            return 0
            
        except Exception as e:
            print(f"❌ Ошибка получения цены: {e}")
            return 0
    
    def place_market_order(
        self,
        product_id: int,  # 1 = SOLUSDT0, 2 = BTCUSDT0
        side: Literal["buy", "sell"],  # "buy" = long, "sell" = short
        size: float,  # Размер в base asset (e.g. 1.1 SOL)
        reduce_only: bool = False
    ) -> Dict:
        """
        Разместить MARKET ордер (исполнится немедленно)
        
        Args:
            product_id: ID продукта (1=SOL, 2=BTC, etc)
            side: "buy" (long) или "sell" (short)
            size: Размер в base asset (например 1.1 для SOL)
            reduce_only: Только закрытие позиции
        
        Returns:
            Response от API
        """
        print(f"\n{'='*60}")
        print(f"📝 РАЗМЕЩЕНИЕ MARKET ОРДЕРА")
        print(f"{'='*60}")
        print(f"Продукт: {product_id}")
        print(f"Сторона: {side.upper()}")
        print(f"Размер: {size}")
        print(f"Reduce Only: {reduce_only}")
        
        # Получаем текущую рыночную цену
        print(f"\n📊 Получаю рыночную цену...")
        market_price = self.get_market_price(product_id)
        
        if market_price == 0:
            print(f"⚠️  Не удалось получить цену, использую 0 (pure market order)")
            price_x18 = 0
        else:
            # Для market ордера добавляем небольшой slippage
            # Buy: +0.5%, Sell: -0.5%
            if side == "buy":
                slippage_price = market_price * 1.005
            else:
                slippage_price = market_price * 0.995
            
            price_x18 = int(Decimal(str(slippage_price)) * Decimal(10**18))
            print(f"✅ Market Price: ${market_price:.2f}")
            print(f"✅ Order Price (with slippage): ${slippage_price:.2f}")
        
        # Convert to x18
        amount_x18 = int(Decimal(str(size)) * Decimal(10**18))
        
        # Negative for sell
        if side == "sell":
            amount_x18 = -amount_x18
        
        # Expiration (1 hour from now)
        expiration = int(time.time()) + 3600
        
        # Nonce
        nonce = self._get_nonce()
        
        # recv_time - ВЫЧИСЛЯЕМ СРАЗУ!
        recv_time = int(time.time() * 1000) + 30000  # +30 секунд
        
        # Appendix (битовые флаги)
        # Bit 0-15: version (ДОЛЖЕН БЫТЬ 1!)
        # Bit 16: reduce_only (1 = yes)
        appendix = 1  # Version 1 (обязательно!)
        if reduce_only:
            appendix |= (1 << 16)
        
        print(f"\n🔐 Подписываю ордер...")
        print(f"   Price: {price_x18} (market)")
        print(f"   Amount: {amount_x18}")
        print(f"   Nonce: {nonce}")
        print(f"   Recv Time: {recv_time}")
        
        # Sign order
        try:
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
            print(f"✅ Подпись: {signature[:20]}...{signature[-10:]}")
        except Exception as e:
            print(f"❌ Ошибка подписи: {e}")
            return {"error": f"Signing error: {e}"}
        
        # Build request
        payload = {
            "place_order": {
                "product_id": product_id,
                "order": {
                    "sender": self.sender,
                    "priceX18": str(price_x18),
                    "amount": str(amount_x18),
                    "expiration": str(expiration),
                    "nonce": str(nonce),
                    "appendix": str(appendix)
                },
                "signature": signature
            },
            "recv_time": str(recv_time)  # На верхнем уровне!
        }
        
        # Send to gateway
        url = f"{self.gateway_url}/execute"
        
        print(f"\n🚀 Отправка ордера на Nado...")
        
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept-Encoding": "gzip, br, deflate"
                },
                timeout=10
            )
            
            print(f"📡 HTTP Status: {resp.status_code}")
            
            resp.raise_for_status()
            result = resp.json()
            
            print(f"✅ Ответ получен!")
            print(json.dumps(result, indent=2))
            
            return result
            
        except Exception as e:
            print(f"❌ Ошибка размещения ордера: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return {"error": str(e)}


# Test
if __name__ == "__main__":
    print("="*60)
    print("🤖 NADO REST CLIENT - FULL TEST")
    print("="*60)
    
    # ВАЖНО: Замените на ваш приватный ключ!
    test_key = "YOUR_PRIVATE_KEY_HERE"
    
    client = NadoRESTClient(test_key, mainnet=True)
    
    # Test 1: Get balance
    print("\n" + "="*60)
    print("💰 ТЕСТ 1: Получение баланса")
    print("="*60)
    balance = client.get_balance()
    if "available_margin" in balance:
        print(f"✅ Available Margin: ${balance['available_margin']:.2f}")
        print(f"✅ Total Equity: ${balance['total_equity']:.2f}")
    else:
        print(f"❌ Ошибка: {balance}")
    
    # Test 2: Get positions
    print("\n" + "="*60)
    print("📊 ТЕСТ 2: Получение позиций")
    print("="*60)
    positions = client.get_positions()
    if "positions" in positions:
        print(f"✅ Найдено позиций: {positions['count']}")
        for pos in positions["positions"]:
            side = "LONG" if pos["size"] > 0 else "SHORT"
            print(f"   Product {pos['product_id']}: {side} {abs(pos['size']):.4f}")
            print(f"   Entry: ${pos['entry_price']:.2f}")
            print(f"   PnL: ${pos['unrealized_pnl']:.2f}")
    else:
        print(f"❌ Ошибка: {positions}")
    
    # Test 3: Place market buy order (COMMENTED FOR SAFETY)
    # Uncomment to test real order:
    # print("\n" + "="*60)
    # print("🚀 ТЕСТ 3: Открытие Long позиции")
    # print("="*60)
    # result = client.place_market_order(
    #     product_id=1,  # SOL
    #     side="buy",
    #     size=1.1,
    #     reduce_only=False
    # )
    # print(f"Результат: {result}")
    
    # Test 4: Close position (COMMENTED FOR SAFETY)
    # Uncomment to test real close:
    # print("\n" + "="*60)
    # print("🔴 ТЕСТ 4: Закрытие позиции")
    # print("="*60)
    # result = client.close_position(product_id=1)  # Close SOL position
    # print(f"Результат: {result}")
    
    print("\n" + "="*60)
    print("✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
    print("="*60)
    print("\nДоступные функции:")
    print("  - client.get_balance()")
    print("  - client.get_positions()")
    print("  - client.place_market_order(product_id, side, size)")
    print("  - client.close_position(product_id)")
    print("\n⚠️  Uncomment тестовые ордера для реальной торговли!")
    print("="*60)
