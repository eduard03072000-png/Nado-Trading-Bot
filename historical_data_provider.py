"""
Historical Data Provider - Binance Public API
Получение OHLCV данных для обучения ML модели
"""
import aiohttp
import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class HistoricalDataProvider:
    """Провайдер исторических данных через Binance API"""
    
    # Маппинг NADO продуктов на Binance символы
    PRODUCT_MAPPING = {
        2: "BTCUSDT",   # BTC-PERP
        4: "ETHUSDT",   # ETH-PERP
        8: "SOLUSDT",   # SOL-PERP
        20: "BNBUSDT"   # INK-PERP -> используем BNB как placeholder
    }
    
    def __init__(self):
        self.base_url = "https://api.binance.com"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_historical_klines(
        self,
        product_id: int,
        interval: str = "1h",
        days: int = 7
    ) -> List[Dict]:
        """
        Получить исторические свечи
        
        Args:
            product_id: ID продукта NADO (2=BTC, 4=ETH, 8=SOL, 20=INK)
            interval: Интервал (1m, 5m, 15m, 1h, 4h, 1d)
            days: Сколько дней назад
        
        Returns:
            List[Dict]: [{timestamp, open, high, low, close, volume}, ...]
        """
        try:
            symbol = self.PRODUCT_MAPPING.get(product_id)
            if not symbol:
                logger.error(f"Unknown product_id: {product_id}")
                return []
            
            # Вычисляем временной диапазон
            end_time = int(datetime.now().timestamp() * 1000)
            start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
            
            # Binance API endpoint
            url = f"{self.base_url}/api/v3/klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": start_time,
                "endTime": end_time,
                "limit": 1000  # Max 1000 свечей за запрос
            }
            
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error(f"Binance API error: {response.status}")
                    return []
                
                data = await response.json()
                
                # Преобразуем формат Binance в наш
                klines = []
                for candle in data:
                    klines.append({
                        'timestamp': datetime.fromtimestamp(candle[0] / 1000),
                        'open': float(candle[1]),
                        'high': float(candle[2]),
                        'low': float(candle[3]),
                        'close': float(candle[4]),
                        'volume': float(candle[5])
                    })
                
                logger.info(f"✅ Loaded {len(klines)} candles for {symbol} ({days}d, {interval})")
                return klines
                
        except Exception as e:
            logger.error(f"Error loading historical data: {e}")
            return []
    
    async def get_current_price(self, product_id: int) -> Optional[float]:
        """Получить текущую цену"""
        try:
            symbol = self.PRODUCT_MAPPING.get(product_id)
            if not symbol:
                return None
            
            url = f"{self.base_url}/api/v3/ticker/price"
            params = {"symbol": symbol}
            
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data['price'])
                return None
                
        except Exception as e:
            logger.error(f"Error getting current price: {e}")
            return None


# Standalone тестирование
async def test_provider():
    """Тест провайдера"""
    async with HistoricalDataProvider() as provider:
        # Тест 1: Получить 7 дней данных для BTC
        klines = await provider.get_historical_klines(
            product_id=2,  # BTC
            interval="1h",
            days=7
        )
        
        if klines:
            print(f"[OK] Loaded {len(klines)} candles")
            print(f"First: {klines[0]}")
            print(f"Last: {klines[-1]}")
        
        # Тест 2: Текущая цена
        price = await provider.get_current_price(2)
        if price:
            print(f"[OK] Current BTC price: ${price:,.2f}")


if __name__ == "__main__":
    asyncio.run(test_provider())
