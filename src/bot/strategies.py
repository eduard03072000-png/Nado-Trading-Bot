"""
Торговые стратегии для бота
"""
from decimal import Decimal
from typing import List, Dict, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    LONG = "long"
    SHORT = "short"


class OrderType(Enum):
    LIMIT = "limit"
    MARKET = "market"


class GridStrategy:
    """
    Стратегия сетки ордеров
    Открывает лонги и шорты около рыночной цены с небольшим профитом
    """
    
    def __init__(
        self,
        max_orders_per_side: int = 3,
        price_deviation: Decimal = Decimal("0.007"),  # 0.7%
        take_profit: Decimal = Decimal("0.008"),      # 0.8%
        stop_loss: Decimal = Decimal("0.005")         # 0.5%
    ):
        self.max_orders_per_side = max_orders_per_side
        self.price_deviation = price_deviation
        self.take_profit = take_profit
        self.stop_loss = stop_loss
    
    def generate_grid_orders(
        self,
        market_price: Decimal,
        order_size: Decimal
    ) -> Dict[str, List[Dict]]:
        """
        Генерировать сетку ордеров около рыночной цены
        
        Args:
            market_price: Текущая рыночная цена
            order_size: Размер каждого ордера
        
        Returns:
            Словарь с лонг и шорт ордерами
        """
        long_orders = []
        short_orders = []
        
        # Генерируем лонг ордера (ниже рыночной цены)
        for i in range(self.max_orders_per_side):
            deviation = self.price_deviation * (i + 1)
            entry_price = market_price * (Decimal("1") - deviation)
            tp_price = entry_price * (Decimal("1") + self.take_profit)
            sl_price = entry_price * (Decimal("1") - self.stop_loss)
            
            long_orders.append({
                "side": OrderSide.LONG.value,
                "type": OrderType.LIMIT.value,
                "entry_price": entry_price,
                "size": order_size,
                "take_profit": tp_price,
                "stop_loss": sl_price
            })
        
        # Генерируем шорт ордера (выше рыночной цены)
        for i in range(self.max_orders_per_side):
            deviation = self.price_deviation * (i + 1)
            entry_price = market_price * (Decimal("1") + deviation)
            tp_price = entry_price * (Decimal("1") - self.take_profit)
            sl_price = entry_price * (Decimal("1") + self.stop_loss)
            
            short_orders.append({
                "side": OrderSide.SHORT.value,
                "type": OrderType.LIMIT.value,
                "entry_price": entry_price,
                "size": order_size,
                "take_profit": tp_price,
                "stop_loss": sl_price
            })
        
        logger.info(f"📊 Сгенерировано: {len(long_orders)} лонгов, {len(short_orders)} шортов")
        
        return {
            "longs": long_orders,
            "shorts": short_orders
        }


class TrailingProfitStrategy:
    """
    Стратегия динамического смещения Take Profit
    Когда позиция достигает определенной прибыли, TP постепенно смещается дальше
    """
    
    def __init__(
        self,
        activation_percent: Decimal = Decimal("0.01"),  # 1% активация
        trail_step: Decimal = Decimal("0.003")           # 0.3% шаг смещения
    ):
        self.activation_percent = activation_percent
        self.trail_step = trail_step
    
    def should_update_tp(
        self,
        entry_price: Decimal,
        current_price: Decimal,
        current_tp: Decimal,
        side: str
    ) -> Tuple[bool, Decimal]:
        """
        Проверить, нужно ли обновить TP
        
        Returns:
            (нужно_обновить, новый_TP)
        """
        if side == "long":
            # Для лонга: цена растет
            profit_percent = (current_price - entry_price) / entry_price
            
            if profit_percent >= self.activation_percent:
                # Сдвигаем TP выше
                new_tp = current_price * (Decimal("1") + self.trail_step)
                
                # Обновляем только если новый TP лучше текущего
                if new_tp > current_tp:
                    logger.info(f"📈 Trailing TP (LONG): {current_tp} -> {new_tp}")
                    return True, new_tp
        
        else:  # short
            # Для шорта: цена падает
            profit_percent = (entry_price - current_price) / entry_price
            
            if profit_percent >= self.activation_percent:
                # Сдвигаем TP ниже
                new_tp = current_price * (Decimal("1") - self.trail_step)
                
                # Обновляем только если новый TP лучше текущего
                if new_tp < current_tp:
                    logger.info(f"📉 Trailing TP (SHORT): {current_tp} -> {new_tp}")
                    return True, new_tp
        
        return False, current_tp


class VolumeMakerStrategy:
    """
    Стратегия максимизации объема с минимальными затратами
    Быстро закрывает позиции при небольшой прибыли для увеличения оборота
    """
    
    def __init__(
        self,
        min_profit_margin: Decimal = Decimal("0.003"),  # 0.3% минимальная маржа
        quick_close_percent: Decimal = Decimal("0.005"), # 0.5% быстрое закрытие
        partial_close_percent: Decimal = Decimal("0.5")  # 50% частичное закрытие
    ):
        self.min_profit_margin = min_profit_margin
        self.quick_close_percent = quick_close_percent
        self.partial_close_percent = partial_close_percent
    
    def should_close_position(
        self,
        entry_price: Decimal,
        current_price: Decimal,
        side: str,
        maker_fee: Decimal = Decimal("0.0002"),  # 0.02% maker
        taker_fee: Decimal = Decimal("0.0005")   # 0.05% taker
    ) -> Tuple[bool, str, Decimal]:
        """
        Проверить, нужно ли закрыть позицию
        
        Returns:
            (закрыть, тип_закрытия, процент_закрытия)
            тип_закрытия: "full" или "partial"
        """
        total_fee = maker_fee + taker_fee
        
        if side == "long":
            profit_percent = (current_price - entry_price) / entry_price
        else:  # short
            profit_percent = (entry_price - current_price) / entry_price
        
        # Учитываем комиссии
        net_profit = profit_percent - total_fee
        
        # Быстрое полное закрытие
        if net_profit >= self.quick_close_percent:
            logger.info(f"⚡ Быстрое закрытие: прибыль {net_profit*100:.2f}%")
            return True, "full", Decimal("1.0")
        
        # Частичное закрытие при минимальной прибыли
        elif net_profit >= self.min_profit_margin:
            logger.info(f"📊 Частичное закрытие: прибыль {net_profit*100:.2f}%")
            return True, "partial", self.partial_close_percent
        
        return False, "none", Decimal("0")
    
    def calculate_optimal_size(
        self,
        balance: Decimal,
        risk_percent: Decimal = Decimal("0.02")  # 2% риска на сделку
    ) -> Decimal:
        """Рассчитать оптимальный размер позиции для максимизации оборота"""
        # Для максимизации объема используем небольшие позиции
        optimal_size = balance * risk_percent
        return optimal_size


class RangeTradingStrategy:
    """
    Стратегия торговли в диапазоне
    Определяет уровни поддержки и сопротивления, торгует отскоки
    """
    
    def __init__(
        self,
        lookback_periods: int = 50,
        range_threshold: Decimal = Decimal("0.02")  # 2% диапазон
    ):
        self.lookback_periods = lookback_periods
        self.range_threshold = range_threshold
        self.support_level: Decimal = Decimal("0")
        self.resistance_level: Decimal = Decimal("0")
    
    def detect_range(self, price_history: List[Decimal]) -> Tuple[Decimal, Decimal]:
        """
        Определить уровни поддержки и сопротивления
        
        Args:
            price_history: История цен
        
        Returns:
            (уровень_поддержки, уровень_сопротивления)
        """
        if len(price_history) < self.lookback_periods:
            return Decimal("0"), Decimal("0")
        
        # Берем последние N периодов
        recent_prices = price_history[-self.lookback_periods:]
        
        # Определяем минимум и максимум
        support = min(recent_prices)
        resistance = max(recent_prices)
        
        # Проверяем, что диапазон достаточно широкий
        range_size = (resistance - support) / support
        
        if range_size >= self.range_threshold:
            self.support_level = support
            self.resistance_level = resistance
            logger.info(f"📊 Диапазон: {support:.2f} - {resistance:.2f} ({range_size*100:.1f}%)")
            return support, resistance
        
        return Decimal("0"), Decimal("0")
    
    def get_trading_signal(
        self,
        current_price: Decimal,
        tolerance: Decimal = Decimal("0.005")  # 0.5% толерантность
    ) -> Tuple[str, Decimal]:
        """
        Получить торговый сигнал
        
        Returns:
            (сигнал, целевая_цена)
            сигнал: "buy", "sell", или "none"
        """
        if self.support_level == 0 or self.resistance_level == 0:
            return "none", Decimal("0")
        
        # Проверяем близость к поддержке (сигнал на покупку)
        support_distance = abs(current_price - self.support_level) / self.support_level
        if support_distance <= tolerance:
            target = self.resistance_level
            logger.info(f"🟢 Сигнал BUY у поддержки: {current_price:.2f}")
            return "buy", target
        
        # Проверяем близость к сопротивлению (сигнал на продажу)
        resistance_distance = abs(current_price - self.resistance_level) / self.resistance_level
        if resistance_distance <= tolerance:
            target = self.support_level
            logger.info(f"🔴 Сигнал SELL у сопротивления: {current_price:.2f}")
            return "sell", target
        
        return "none", Decimal("0")
