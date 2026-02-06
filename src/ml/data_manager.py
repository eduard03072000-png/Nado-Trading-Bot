"""
Утилита для работы с историческими данными
"""
import json
from pathlib import Path
from typing import List
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class HistoricalDataManager:
    """Менеджер для работы с историческими данными цен"""
    
    def __init__(self, data_dir: str = "data/historical"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def save_prices(self, symbol: str, prices: List[Decimal], timestamps: List[str] = None):
        """Сохранить историю цен"""
        filepath = self.data_dir / f"{symbol}_prices.json"
        
        data = {
            "symbol": symbol,
            "prices": [str(p) for p in prices],
            "timestamps": timestamps or [],
            "count": len(prices)
        }
        
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"✅ Сохранено {len(prices)} цен для {symbol}")
        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {e}")
    
    def load_prices(self, symbol: str) -> List[Decimal]:
        """Загрузить историю цен"""
        filepath = self.data_dir / f"{symbol}_prices.json"
        
        if not filepath.exists():
            logger.warning(f"⚠️ Файл {filepath} не найден")
            return []
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            prices = [Decimal(p) for p in data.get("prices", [])]
            logger.info(f"✅ Загружено {len(prices)} цен для {symbol}")
            return prices
            
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            return []
    
    def append_price(self, symbol: str, price: Decimal, timestamp: str = None):
        """Добавить новую цену к истории"""
        prices = self.load_prices(symbol)
        prices.append(price)
        
        # Ограничиваем размер истории (последние 10000 цен)
        if len(prices) > 10000:
            prices = prices[-10000:]
        
        self.save_prices(symbol, prices)
    
    def get_recent_prices(self, symbol: str, count: int = 100) -> List[Decimal]:
        """Получить последние N цен"""
        prices = self.load_prices(symbol)
        return prices[-count:] if prices else []
    
    def generate_sample_data(self, symbol: str, count: int = 1000, base_price: float = 50000):
        """Генерировать тестовые данные для обучения"""
        import numpy as np
        
        # Генерируем случайное блуждание с трендом
        prices = [base_price]
        
        for i in range(count - 1):
            # Случайное изменение с небольшим восходящим трендом
            change = np.random.normal(0.0005, 0.01)  # +0.05% тренд, 1% волатильность
            new_price = prices[-1] * (1 + change)
            prices.append(new_price)
        
        prices_decimal = [Decimal(str(p)) for p in prices]
        self.save_prices(symbol, prices_decimal)
        
        logger.info(f"✅ Сгенерировано {count} тестовых цен для {symbol}")
        return prices_decimal
