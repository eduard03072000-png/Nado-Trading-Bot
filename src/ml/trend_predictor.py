"""
ML модель для предсказания направления тренда
Использует исторические данные для прогнозирования движения цены
"""
import numpy as np
from typing import List, Tuple, Optional
from decimal import Decimal
import logging
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)


class TrendPredictor:
    """
    Класс для предсказания направления тренда
    """
    
    def __init__(self, model_path: Optional[str] = None):
        self.model = None
        self.model_path = model_path
        self.is_trained = False
        
        if model_path and Path(model_path).exists():
            self.load_model(model_path)
    
    def prepare_features(
        self,
        prices: List[Decimal],
        volumes: List[Decimal] = None,
        lookback: int = 20
    ) -> np.ndarray:
        """
        Подготовить признаки для модели
        
        Args:
            prices: История цен
            volumes: История объемов
            lookback: Количество периодов назад
        
        Returns:
            Массив признаков
        """
        if len(prices) < lookback:
            logger.warning(f"Недостаточно данных: {len(prices)} < {lookback}")
            return np.array([])
        
        # Конвертируем в numpy array
        price_array = np.array([float(p) for p in prices[-lookback:]])
        
        features = []
        
        # 1. Процентные изменения цены
        returns = np.diff(price_array) / price_array[:-1]
        features.extend(returns)
        
        # 2. Скользящие средние
        ma_5 = np.mean(price_array[-5:])
        ma_10 = np.mean(price_array[-10:])
        ma_20 = np.mean(price_array[-20:]) if len(price_array) >= 20 else ma_10
        
        features.extend([
            (price_array[-1] - ma_5) / ma_5,   # Отклонение от MA5
            (price_array[-1] - ma_10) / ma_10, # Отклонение от MA10
            (ma_5 - ma_10) / ma_10             # Пересечение MA5/MA10
        ])
        
        # 3. Волатильность
        volatility = np.std(returns)
        features.append(volatility)
        
        # 4. RSI (Relative Strength Index)
        rsi = self._calculate_rsi(price_array, period=14)
        features.append(rsi)
        
        # 5. MACD индикаторы
        if len(price_array) >= 26:
            macd, signal = self._calculate_macd(price_array)
            features.extend([macd, signal, macd - signal])
        else:
            features.extend([0, 0, 0])
        
        # 6. Объемы (если есть)
        if volumes and len(volumes) >= lookback:
            volume_array = np.array([float(v) for v in volumes[-lookback:]])
            volume_ma = np.mean(volume_array)
            volume_ratio = volume_array[-1] / volume_ma if volume_ma > 0 else 1
            features.append(volume_ratio)
        
        return np.array(features)
    
    def _calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """Рассчитать RSI индикатор"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_macd(
        self,
        prices: np.ndarray,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Tuple[float, float]:
        """Рассчитать MACD индикатор"""
        if len(prices) < slow:
            return 0.0, 0.0
        
        # Экспоненциальные скользящие средние
        ema_fast = self._ema(prices, fast)
        ema_slow = self._ema(prices, slow)
        
        macd_line = ema_fast - ema_slow
        
        # Signal line (EMA от MACD)
        # Упрощенная версия
        signal_line = macd_line * 0.8  # Приближение
        
        return macd_line, signal_line
    
    def _ema(self, prices: np.ndarray, period: int) -> float:
        """Рассчитать экспоненциальную скользящую среднюю"""
        if len(prices) < period:
            return np.mean(prices)
        
        multiplier = 2 / (period + 1)
        ema = np.mean(prices[:period])
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def predict(
        self,
        prices: List[Decimal],
        volumes: List[Decimal] = None
    ) -> Tuple[str, float]:
        """
        Предсказать направление тренда
        
        Returns:
            (направление, уверенность)
            направление: "up", "down", или "sideways"
            уверенность: 0.0 - 1.0
        """
        if not self.is_trained:
            logger.warning("⚠️ Модель не обучена, используем простой анализ")
            return self._simple_prediction(prices)
        
        # Подготовка признаков
        features = self.prepare_features(prices, volumes)
        
        if len(features) == 0:
            return "sideways", 0.5
        
        # Здесь будет предсказание через обученную модель
        # prediction = self.model.predict([features])
        
        # Пока используем простой анализ
        return self._simple_prediction(prices)
    
    def _simple_prediction(self, prices: List[Decimal]) -> Tuple[str, float]:
        """Простое предсказание на основе технических индикаторов"""
        if len(prices) < 20:
            return "sideways", 0.5
        
        price_array = np.array([float(p) for p in prices[-20:]])
        
        # Тренд на основе скользящих средних
        ma_5 = np.mean(price_array[-5:])
        ma_20 = np.mean(price_array[-20:])
        
        # RSI
        rsi = self._calculate_rsi(price_array, 14)
        
        # Краткосрочный тренд
        short_trend = (price_array[-1] - price_array[-5]) / price_array[-5]
        
        confidence = 0.5
        
        # Бычий сигнал
        if ma_5 > ma_20 and rsi < 70 and short_trend > 0:
            confidence = min(0.8, 0.5 + abs(short_trend) * 10)
            return "up", confidence
        
        # Медвежий сигнал
        elif ma_5 < ma_20 and rsi > 30 and short_trend < 0:
            confidence = min(0.8, 0.5 + abs(short_trend) * 10)
            return "down", confidence
        
        # Боковик
        else:
            return "sideways", 0.6
    
    def save_model(self, path: str):
        """Сохранить модель"""
        try:
            with open(path, 'wb') as f:
                pickle.dump(self.model, f)
            logger.info(f"✅ Модель сохранена: {path}")
        except Exception as e:
            logger.error(f"Ошибка сохранения модели: {e}")
    
    def load_model(self, path: str):
        """Загрузить модель"""
        try:
            with open(path, 'rb') as f:
                self.model = pickle.load(f)
            self.is_trained = True
            logger.info(f"✅ Модель загружена: {path}")
        except Exception as e:
            logger.error(f"Ошибка загрузки модели: {e}")
            self.is_trained = False
