"""
Модуль для работы с Nado DEX API
Обеспечивает интеграцию с фьючерсной платформой Nado
"""
import aiohttp
import asyncio
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import time
import logging

logger = logging.getLogger(__name__)


class NadoAPI:
    """Класс для взаимодействия с Nado DEX"""
    
    def __init__(self, api_url: str = "https://api.nado.xyz"):
        self.api_url = api_url
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            self.session = None

    async def _ensure_session(self):
        """Создаём сессию лениво, если ещё не существует"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    # Маппинг символов DEX -> Binance тикеры
    _BINANCE_SYMBOL_MAP = {
        "BTC-USDT":  "BTCUSDT",
        "ETH-USDT":  "ETHUSDT",
        "SOL-USDT":  "SOLUSDT",
        "DOGE-USDT": "DOGEUSDT",
        "LINK-USDT": "LINKUSDT",
        "AVAX-USDT": "AVAXUSDT",
    }
    # CoinGecko id для fallback
    _COINGECKO_ID_MAP = {
        "BTC-USDT":  "bitcoin",
        "ETH-USDT":  "ethereum",
        "SOL-USDT":  "solana",
        "DOGE-USDT": "dogecoin",
        "LINK-USDT": "chainlink",
        "AVAX-USDT": "avalanche-2",
    }

    async def get_market_price(self, symbol: str) -> Optional[Decimal]:
        """Получить текущую рыночную цену через Binance (primary) / CoinGecko (fallback)"""
        await self._ensure_session()

        # --- Primary: Binance ---
        binance_sym = self._BINANCE_SYMBOL_MAP.get(symbol, symbol.replace("-", ""))
        try:
            async with self.session.get(
                f"https://api.binance.com/api/v3/ticker/price",
                params={"symbol": binance_sym},
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price = Decimal(data["price"])
                    if price > 0:
                        return price
        except Exception as e:
            logger.warning(f"Binance price fetch failed: {e}")

        # --- Fallback: CoinGecko ---
        cg_id = self._COINGECKO_ID_MAP.get(symbol)
        if cg_id:
            try:
                async with self.session.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={"ids": cg_id, "vs_currencies": "usd"},
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = Decimal(str(data[cg_id]["usd"]))
                        if price > 0:
                            logger.info(f"Цена из CoinGecko fallback: {price}")
                            return price
            except Exception as e:
                logger.warning(f"CoinGecko price fetch failed: {e}")

        logger.error(f"Не удалось получить цену для {symbol}")
        return None
    
    async def get_orderbook(self, symbol: str, depth: int = 20) -> Optional[Dict]:
        """Получить ордербук (стакан заявок)"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.api_url}/v1/orderbook/{symbol}",
                params={"depth": depth}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "bids": [(Decimal(p), Decimal(v)) for p, v in data.get("bids", [])],
                        "asks": [(Decimal(p), Decimal(v)) for p, v in data.get("asks", [])]
                    }
        except Exception as e:
            logger.error(f"Ошибка получения ордербука: {e}")
        return None
    
    async def get_24h_stats(self, symbol: str) -> Optional[Dict]:
        """Получить статистику за 24 часа"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.api_url}/v1/market/{symbol}/stats"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "volume_24h": Decimal(str(data.get("volume", 0))),
                        "high_24h": Decimal(str(data.get("high", 0))),
                        "low_24h": Decimal(str(data.get("low", 0))),
                        "price_change_24h": Decimal(str(data.get("change", 0)))
                    }
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
        return None
    
    async def open_long_position(
        self,
        symbol: str,
        size: Decimal,
        price: Decimal,
        leverage: int = 1,
        order_type: str = "limit"
    ) -> Optional[Dict]:
        """
        Открыть лонг позицию (ставка на рост)
        
        Args:
            symbol: Торговая пара (например "BTC-USDT")
            size: Размер позиции
            price: Цена входа (для limit ордера)
            leverage: Плечо (1-100x)
            order_type: Тип ордера ("limit" или "market")
        """
        try:
            await self._ensure_session()
            payload = {
                "symbol": symbol,
                "side": "long",
                "size": str(size),
                "price": str(price),
                "leverage": leverage,
                "type": order_type
            }
            
            async with self.session.post(
                f"{self.api_url}/v1/positions/open",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ Лонг позиция открыта: {data.get('position_id')}")
                    return data
                else:
                    error = await response.text()
                    logger.error(f"❌ Ошибка открытия лонг: {error}")
        except Exception as e:
            logger.error(f"Ошибка open_long_position: {e}")
        return None
    
    async def open_short_position(
        self,
        symbol: str,
        size: Decimal,
        price: Decimal,
        leverage: int = 1,
        order_type: str = "limit"
    ) -> Optional[Dict]:
        """
        Открыть шорт позицию (ставка на падение)
        
        Args:
            symbol: Торговая пара
            size: Размер позиции
            price: Цена входа (для limit ордера)
            leverage: Плечо (1-100x)
            order_type: Тип ордера ("limit" или "market")
        """
        try:
            await self._ensure_session()
            payload = {
                "symbol": symbol,
                "side": "short",
                "size": str(size),
                "price": str(price),
                "leverage": leverage,
                "type": order_type
            }
            
            async with self.session.post(
                f"{self.api_url}/v1/positions/open",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ Шорт позиция открыта: {data.get('position_id')}")
                    return data
                else:
                    error = await response.text()
                    logger.error(f"❌ Ошибка открытия шорт: {error}")
        except Exception as e:
            logger.error(f"Ошибка open_short_position: {e}")
        return None
    
    async def close_position(self, position_id: str, price: Optional[Decimal] = None) -> Optional[Dict]:
        """
        Закрыть позицию
        
        Args:
            position_id: ID позиции
            price: Цена закрытия (None для market ордера)
        """
        try:
            await self._ensure_session()
            payload = {
                "position_id": position_id,
                "type": "market" if price is None else "limit"
            }
            
            if price:
                payload["price"] = str(price)
            
            async with self.session.post(
                f"{self.api_url}/v1/positions/close",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ Позиция закрыта: {position_id}")
                    return data
                else:
                    error = await response.text()
                    logger.error(f"❌ Ошибка закрытия позиции: {error}")
        except Exception as e:
            logger.error(f"Ошибка close_position: {e}")
        return None
    
    async def set_take_profit(self, position_id: str, tp_price: Decimal) -> Optional[Dict]:
        """
        Установить Take Profit для позиции
        
        Args:
            position_id: ID позиции
            tp_price: Цена Take Profit
        """
        try:
            await self._ensure_session()
            payload = {
                "position_id": position_id,
                "take_profit": str(tp_price)
            }
            
            async with self.session.post(
                f"{self.api_url}/v1/positions/set-tp",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ TP установлен: {position_id} @ {tp_price}")
                    return data
                else:
                    error = await response.text()
                    logger.error(f"❌ Ошибка установки TP: {error}")
        except Exception as e:
            logger.error(f"Ошибка set_take_profit: {e}")
        return None
    
    async def set_stop_loss(self, position_id: str, sl_price: Decimal) -> Optional[Dict]:
        """
        Установить Stop Loss для позиции
        
        Args:
            position_id: ID позиции
            sl_price: Цена Stop Loss
        """
        try:
            await self._ensure_session()
            payload = {
                "position_id": position_id,
                "stop_loss": str(sl_price)
            }
            
            async with self.session.post(
                f"{self.api_url}/v1/positions/set-sl",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ SL установлен: {position_id} @ {sl_price}")
                    return data
                else:
                    error = await response.text()
                    logger.error(f"❌ Ошибка установки SL: {error}")
        except Exception as e:
            logger.error(f"Ошибка set_stop_loss: {e}")
        return None

    async def get_open_positions(self) -> Optional[List[Dict]]:
        """Получить все открытые позиции"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.api_url}/v1/positions/open"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("positions", [])
        except Exception as e:
            logger.error(f"Ошибка get_open_positions: {e}")
        return None
    
    async def get_position_info(self, position_id: str) -> Optional[Dict]:
        """Получить информацию о конкретной позиции"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.api_url}/v1/positions/{position_id}"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "position_id": data.get("id"),
                        "symbol": data.get("symbol"),
                        "side": data.get("side"),
                        "size": Decimal(str(data.get("size", 0))),
                        "entry_price": Decimal(str(data.get("entry_price", 0))),
                        "current_price": Decimal(str(data.get("current_price", 0))),
                        "pnl": Decimal(str(data.get("pnl", 0))),
                        "pnl_percent": Decimal(str(data.get("pnl_percent", 0))),
                        "take_profit": Decimal(str(data.get("take_profit", 0))) if data.get("take_profit") else None,
                        "stop_loss": Decimal(str(data.get("stop_loss", 0))) if data.get("stop_loss") else None,
                        "leverage": data.get("leverage", 1),
                        "created_at": data.get("created_at")
                    }
        except Exception as e:
            logger.error(f"Ошибка get_position_info: {e}")
        return None
    
    async def get_trade_history(self, limit: int = 50) -> Optional[List[Dict]]:
        """Получить историю сделок"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.api_url}/v1/trades/history",
                params={"limit": limit}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("trades", [])
        except Exception as e:
            logger.error(f"Ошибка get_trade_history: {e}")
        return None
    
    async def get_account_balance(self) -> Optional[Dict]:
        """Получить баланс аккаунта"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.api_url}/v1/account/balance"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "total_balance": Decimal(str(data.get("total", 0))),
                        "available_balance": Decimal(str(data.get("available", 0))),
                        "margin_used": Decimal(str(data.get("margin_used", 0))),
                        "unrealized_pnl": Decimal(str(data.get("unrealized_pnl", 0)))
                    }
        except Exception as e:
            logger.error(f"Ошибка get_account_balance: {e}")
        return None
    
    async def get_trading_fees(self, symbol: str) -> Optional[Dict]:
        """Получить информацию о комиссиях для торговой пары"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.api_url}/v1/fees/{symbol}"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "maker_fee": Decimal(str(data.get("maker_fee", 0))),
                        "taker_fee": Decimal(str(data.get("taker_fee", 0))),
                        "funding_rate": Decimal(str(data.get("funding_rate", 0)))
                    }
        except Exception as e:
            logger.error(f"Ошибка get_trading_fees: {e}")
        return None
    
    async def get_available_markets(self) -> Optional[List[Dict]]:
        """Получить список всех доступных рынков на Nado DEX"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.api_url}/v1/markets"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    markets = []
                    for market in data.get("markets", []):
                        markets.append({
                            "symbol": market.get("symbol"),
                            "base": market.get("base"),
                            "quote": market.get("quote"),
                            "min_size": Decimal(str(market.get("min_size", 0))),
                            "max_leverage": market.get("max_leverage", 1),
                            "active": market.get("active", True)
                        })
                    logger.info(f"📊 Загружено рынков: {len(markets)}")
                    return markets
        except Exception as e:
            logger.error(f"Ошибка get_available_markets: {e}")
        return None
    
    async def get_market_info(self, symbol: str) -> Optional[Dict]:
        """Получить детальную информацию о конкретном рынке"""
        try:
            await self._ensure_session()
            async with self.session.get(
                f"{self.api_url}/v1/market/{symbol}/info"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "symbol": data.get("symbol"),
                        "min_order_size": Decimal(str(data.get("min_order_size", 0))),
                        "max_order_size": Decimal(str(data.get("max_order_size", 0))),
                        "price_precision": data.get("price_precision", 2),
                        "size_precision": data.get("size_precision", 4),
                        "max_leverage": data.get("max_leverage", 1),
                        "funding_interval": data.get("funding_interval", 8),
                        "status": data.get("status", "active")
                    }
        except Exception as e:
            logger.error(f"Ошибка get_market_info: {e}")
        return None
    
    async def get_trade_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 50
    ) -> Optional[List[Dict]]:
        """
        Получить историю сделок
        
        Args:
            symbol: Торговая пара (если None - все пары)
            limit: Количество записей (максимум 100)
        """
        try:
            await self._ensure_session()
            params = {"limit": min(limit, 100)}
            if symbol:
                params["symbol"] = symbol
                
            async with self.session.get(
                f"{self.api_url}/v1/trades/history",
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    trades = []
                    for trade in data.get("trades", []):
                        trades.append({
                            "trade_id": trade.get("id"),
                            "symbol": trade.get("symbol"),
                            "side": trade.get("side"),
                            "size": Decimal(str(trade.get("size", 0))),
                            "entry_price": Decimal(str(trade.get("entry_price", 0))),
                            "exit_price": Decimal(str(trade.get("exit_price", 0))),
                            "profit": Decimal(str(trade.get("profit", 0))),
                            "timestamp": trade.get("timestamp")
                        })
                    return trades
        except Exception as e:
            logger.error(f"Ошибка get_trade_history: {e}")
        return None
    
    async def cancel_order(self, order_id: str) -> bool:
        """Отменить конкретный ордер по ID"""
        try:
            await self._ensure_session()
            async with self.session.delete(
                f"{self.api_url}/v1/orders/{order_id}"
            ) as response:
                if response.status == 200:
                    logger.info(f"✅ Ордер {order_id} отменен")
                    return True
                else:
                    error = await response.text()
                    logger.error(f"❌ Ошибка отмены ордера {order_id}: {error}")
        except Exception as e:
            logger.error(f"Ошибка cancel_order: {e}")
        return False
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """
        Отменить все открытые ордера
        
        Args:
            symbol: Если указан - отменяет только для этой пары
        
        Returns:
            Количество отмененных ордеров
        """
        try:
            await self._ensure_session()
            params = {}
            if symbol:
                params["symbol"] = symbol
                
            async with self.session.delete(
                f"{self.api_url}/v1/orders/all",
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    cancelled = data.get("cancelled_count", 0)
                    logger.info(f"✅ Отменено ордеров: {cancelled}")
                    return cancelled
        except Exception as e:
            logger.error(f"Ошибка cancel_all_orders: {e}")
        return 0
    
    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        size: Decimal,
        price: Decimal,
        leverage: int = 1
    ) -> Optional[Dict]:
        """
        Разместить лимитный ордер
        
        Args:
            symbol: Торговая пара
            side: "long" или "short"
            size: Размер позиции
            price: Цена исполнения
            leverage: Плечо
        """
        try:
            await self._ensure_session()
            payload = {
                "symbol": symbol,
                "side": side,
                "type": "limit",
                "size": str(size),
                "price": str(price),
                "leverage": leverage
            }
            
            async with self.session.post(
                f"{self.api_url}/v1/orders/limit",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ Лимит ордер размещен: {data.get('order_id')}")
                    return data
                else:
                    error = await response.text()
                    logger.error(f"❌ Ошибка размещения ордера: {error}")
        except Exception as e:
            logger.error(f"Ошибка place_limit_order: {e}")
        return None
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> Optional[List[Dict]]:
        """Получить список открытых ордеров"""
        try:
            await self._ensure_session()
            params = {}
            if symbol:
                params["symbol"] = symbol
                
            async with self.session.get(
                f"{self.api_url}/v1/orders/open",
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("orders", [])
        except Exception as e:
            logger.error(f"Ошибка get_open_orders: {e}")
        return None
