"""
ML-Based Auto Trading
Торговля на основе ML прогнозов
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from typing import Optional, Dict, List
from trading_dashboard import TradingDashboard, PRODUCTS
from tp_sl_calculator import TPSLCalculator
import logging

# Добавляем путь к ML модулю
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ml import TrendPredictor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MLAutoTrader:
    """Автоматическая торговля на основе ML прогнозов"""
    
    def __init__(
        self,
        dashboard: TradingDashboard,
        product_id: int,
        base_size: float,
        tp_percent: float = 1.0,
        sl_percent: float = 0.5,
        min_confidence: float = 0.7,
        lookback_days: int = 7
    ):
        self.dashboard = dashboard
        self.product_id = product_id
        self.base_size = base_size
        self.tp_percent = tp_percent
        self.sl_percent = sl_percent
        self.min_confidence = min_confidence
        self.lookback_days = lookback_days
        
        self.running = False
        self.predictor = TrendPredictor()
        self.calc = TPSLCalculator(leverage=dashboard.leverage)
        
        # История цен для ML
        self.price_history: List[Decimal] = []
        
        # Последний прогноз ML
        self.last_prediction = {"direction": "unknown", "confidence": 0}
        
    async def start(self):
        """Запустить ML торговлю"""
        self.running = True
        logger.info("🤖 ML Auto-Trader запущен!")
        logger.info(f"   Минимальная уверенность: {self.min_confidence:.0%}")
        
        # Загружаем историю цен
        await self._load_price_history()
        
        # Основной цикл
        while self.running:
            try:
                await self._trading_cycle()
                await asyncio.sleep(60)  # Проверка каждую минуту
            except Exception as e:
                logger.error(f"Ошибка в цикле: {e}")
                await asyncio.sleep(60)
    
    def stop(self):
        """Остановить ML торговлю"""
        self.running = False
        logger.info("🛑 ML Auto-Trader остановлен")
    
    async def _load_price_history(self):
        """Загрузить историю цен за N дней"""
        try:
            # В реальной версии получаем через API
            # Пока используем текущую цену как базу
            current_price = self.dashboard.get_market_price(self.product_id)
            
            if current_price:
                # Генерируем базовую историю (для теста)
                # В продакшене загружать через get_candlesticks
                for i in range(self.lookback_days * 24):  # По часам
                    # Имитация исторических данных
                    noise = Decimal(str(1 + (i % 10 - 5) * 0.001))
                    price = Decimal(str(current_price)) * noise
                    self.price_history.append(price)
                
                logger.info(f"📊 Загружено {len(self.price_history)} ценовых точек")
                
        except Exception as e:
            logger.error(f"Ошибка загрузки истории: {e}")
    
    async def _trading_cycle(self):
        """Основной цикл торговли"""
        try:
            # Обновляем историю цен
            current_price = self.dashboard.get_market_price(self.product_id)
            if current_price:
                self.price_history.append(Decimal(str(current_price)))
                
                # Ограничиваем размер истории
                if len(self.price_history) > self.lookback_days * 24 * 2:
                    self.price_history = self.price_history[-self.lookback_days * 24:]
            
            # Проверяем текущие позиции
            positions = self.dashboard.get_positions()
            our_positions = [
                p for p in positions 
                if p['product_id'] == self.product_id
            ]
            
            # Если есть позиция - управляем TP/SL
            if our_positions:
                for pos in our_positions:
                    await self._manage_position(pos)
                return
            
            # Нет позиций - проверяем ML сигнал
            await self._check_ml_signal()
            
        except Exception as e:
            logger.error(f"Ошибка торгового цикла: {e}")
    
    async def _check_ml_signal(self):
        """Проверить ML сигнал и открыть позицию"""
        try:
            if len(self.price_history) < 20:
                logger.info("Недостаточно данных для ML")
                return
            
            # Получаем прогноз
            direction, confidence = self.predictor.predict(self.price_history)
            
            # Сохраняем последний прогноз
            self.last_prediction = {"direction": direction, "confidence": confidence}
            
            symbol = PRODUCTS[self.product_id]
            logger.info(f"🧠 ML Прогноз для {symbol}: {direction.upper()} (уверенность: {confidence:.0%})")
            
            # Проверяем уверенность
            if confidence < self.min_confidence:
                logger.info(f"   ⚠️ Уверенность слишком низкая ({confidence:.0%} < {self.min_confidence:.0%})")
                return
            
            # Открываем позицию только при сильном сигнале
            if direction == "up":
                logger.info(f"   🟢 Открываем LONG позицию")
                await self._open_position(is_long=True)
            elif direction == "down":
                logger.info(f"   🔴 Открываем SHORT позицию")
                await self._open_position(is_long=False)
            else:
                logger.info(f"   ⏸️ Боковик - ждем")
                
        except Exception as e:
            logger.error(f"Ошибка проверки ML сигнала: {e}")
    
    async def _open_position(self, is_long: bool):
        """Открыть позицию с TP/SL"""
        try:
            # Размещаем ордер БЕЗ автоматического TP
            result = self.dashboard.place_order(
                self.product_id,
                self.base_size,
                is_long=is_long,
                custom_price=None,  # Маркет ордер
                auto_tp=False
            )
            
            if result:
                logger.info("✅ Позиция открыта")
                
                # Получаем актуальную цену входа
                current_price = self.dashboard.get_market_price(self.product_id)
                scenarios = self.calc.calculate_scenarios(
                    product_symbol=PRODUCTS[self.product_id],
                    entry_price=current_price,
                    size=self.base_size,
                    is_long=is_long
                )
                
                # Выбираем сценарий по заданным процентам
                selected = next(
                    (s for s in scenarios if s['tp_percent'] == self.tp_percent),
                    scenarios[0]
                )
                
                logger.info(f"   Entry: ${current_price:.2f}")
                logger.info(f"   TP: {selected['tp_percent']}% (${selected['tp_pnl']:+,.2f}) -> ${selected['tp_price']:.2f}")
                logger.info(f"   SL: {selected['sl_percent']}% (${selected['sl_pnl']:+,.2f}) -> ${selected['sl_price']:.2f}")
                logger.info(f"   ⚠️ TP/SL мониторятся автоматически, ордера не размещаются")
                
                # Сохраняем цены TP/SL для мониторинга
                self.dashboard.save_entry_price(
                    self.product_id, 
                    current_price, 
                    self.base_size * float(self.dashboard.leverage),
                    tp_price=selected['tp_price'],
                    sl_price=selected['sl_price']
                )
            else:
                logger.error("❌ Не удалось открыть позицию")
                
        except Exception as e:
            logger.error(f"Ошибка открытия позиции: {e}")
    
    async def _manage_position(self, position: Dict):
        """Управление позицией с TP/SL"""
        try:
            is_long = position['amount'] > 0
            entry_price = position.get('price', 0)
            current_price = self.dashboard.get_market_price(self.product_id)
            
            if not current_price or not entry_price:
                return
            
            # Расчет P&L в процентах
            if is_long:
                pnl_percent = ((current_price - entry_price) / entry_price) * 100
            else:
                pnl_percent = ((entry_price - current_price) / entry_price) * 100
            
            logger.info(f"📊 ML позиция: {'LONG' if is_long else 'SHORT'} P&L {pnl_percent:+.2f}%")
            
            # Проверка TP
            if pnl_percent >= self.tp_percent:
                logger.info(f"🎯 TP достигнут ({pnl_percent:+.2f}%)! Закрываем...")
                await self._close_position(position)
            
            # Проверка SL
            elif pnl_percent <= -self.sl_percent:
                logger.info(f"🛑 SL сработал ({pnl_percent:+.2f}%)! Закрываем...")
                await self._close_position(position)
                
        except Exception as e:
            logger.error(f"Ошибка управления позицией: {e}")
    
    async def _close_position(self, position: Dict):
        """Закрыть позицию"""
        try:
            size = abs(position['amount'])
            is_long = position['amount'] > 0
            
            result = self.dashboard.place_order(
                self.product_id,
                size / self.dashboard.leverage,
                is_long=not is_long,
                custom_price=None,
                auto_tp=False
            )
            
            if result:
                logger.info("✅ Позиция закрыта")
            else:
                logger.error("❌ Не удалось закрыть позицию")
                
        except Exception as e:
            logger.error(f"Ошибка закрытия: {e}")


# Тестирование
async def test_ml_trader():
    """Тестовый запуск"""
    dashboard = TradingDashboard()
    
    trader = MLAutoTrader(
        dashboard=dashboard,
        product_id=8,  # SOL-PERP
        base_size=0.5,
        tp_percent=1.0,  # TP 1%
        sl_percent=0.5,  # SL 0.5%
        min_confidence=0.7,  # Минимум 70% уверенности
        lookback_days=7
    )
    
    try:
        await trader.start()
    except KeyboardInterrupt:
        trader.stop()


if __name__ == "__main__":
    asyncio.run(test_ml_trader())
