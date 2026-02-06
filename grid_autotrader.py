"""
Grid Auto-Trading Bot
Автоматическая торговля Grid стратегией с TP/SL
"""
import asyncio
import time
from decimal import Decimal
from typing import Optional, Dict
from trading_dashboard import TradingDashboard, PRODUCTS
from tp_sl_calculator import TPSLCalculator
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GridAutoTrader:
    """Автоматическая Grid торговля"""
    
    def __init__(
        self,
        dashboard: TradingDashboard,
        product_id: int,
        base_size: float,
        grid_offset: float = 0.5,
        tp_percent: float = 0.5,
        sl_percent: float = 0.3,
        max_positions: int = 2
    ):
        self.dashboard = dashboard
        self.product_id = product_id
        self.base_size = base_size
        self.grid_offset = grid_offset  # % отклонение для Grid ордеров
        self.tp_percent = tp_percent
        self.sl_percent = sl_percent
        self.max_positions = max_positions
        
        self.running = False
        self.active_grids = {}  # {order_id: grid_info}
        self.calc = TPSLCalculator(leverage=dashboard.leverage)
        self.tp_placed = False  # Флаг что TP уже размещен
        
    async def start(self):
        """Запустить автоторговлю"""
        self.running = True
        logger.info("🤖 Grid Auto-Trader запущен!")
        
        # Размещаем первую Grid сетку
        await self._place_grid()
        
        # Основной цикл мониторинга
        while self.running:
            try:
                await self._monitor_positions()
                await asyncio.sleep(10)  # Проверка каждые 10 секунд
            except Exception as e:
                logger.error(f"Ошибка в цикле: {e}")
                await asyncio.sleep(30)
    
    def stop(self):
        """Остановить автоторговлю"""
        self.running = False
        logger.info("🛑 Grid Auto-Trader остановлен")
    
    async def _place_grid(self):
        """Разместить Grid ордера"""
        try:
            symbol = PRODUCTS[self.product_id]
            price = self.dashboard.get_market_price(self.product_id)
            
            if not price:
                logger.error("Не удалось получить цену")
                return
            
            # Цены для Grid
            offset_mult = Decimal(str(self.grid_offset / 100))
            long_price = float(Decimal(str(price)) * (Decimal("1") - offset_mult))
            short_price = float(Decimal(str(price)) * (Decimal("1") + offset_mult))
            
            logger.info(f"\n📊 Размещение Grid для {symbol}")
            logger.info(f"   Текущая цена: ${price:,.2f}")
            logger.info(f"   Базовый размер: {self.base_size}")  # НОВОЕ ЛОГИРОВАНИЕ
            logger.info(f"   LONG @ ${long_price:,.2f}")
            logger.info(f"   SHORT @ ${short_price:,.2f}")
            
            # Размещаем LONG ордер с TTL 1 час
            long_result = self.dashboard.place_order(
                self.product_id,
                self.base_size,
                is_long=True,
                custom_price=long_price,
                auto_tp=False,  # БЕЗ автоматического TP
                ttl_seconds=3600  # 1 час
            )
            
            # Сохраняем entry price для LONG
            if long_result:
                self.dashboard.save_entry_price(self.product_id, long_price, self.base_size)
            
            # Размещаем SHORT ордер с TTL 1 час
            short_result = self.dashboard.place_order(
                self.product_id,
                self.base_size,
                is_long=False,
                custom_price=short_price,
                auto_tp=False,  # БЕЗ автоматического TP
                ttl_seconds=3600  # 1 час
            )
            
            # Сохраняем entry price для SHORT
            if short_result:
                self.dashboard.save_entry_price(self.product_id, short_price, self.base_size)
            
            if long_result and short_result:
                logger.info("✅ Grid ордера размещены")
            else:
                logger.error("❌ Ошибка размещения Grid")
                
        except Exception as e:
            logger.error(f"Ошибка размещения Grid: {e}")
    
    async def _monitor_positions(self):
        """Мониторинг позиций и управление TP/SL"""
        try:
            # Проверяем открытые ордера
            orders = self.dashboard.get_open_orders()
            our_orders = [
                o for o in orders 
                if o.get('product_id') == self.product_id
            ]
            
            # Проверяем позиции
            positions = self.dashboard.get_positions()
            our_positions = [
                p for p in positions 
                if p['product_id'] == self.product_id
            ]
            
            # Если нет позиций и нет ордеров - размещаем новую Grid
            if not our_positions and not our_orders:
                logger.info("Нет активных позиций и ордеров, размещаем новую Grid...")
                self.tp_placed = False  # Сбрасываем флаг
                await self._place_grid()
                return
            
            # Если есть только ордера (нет позиций) - ждем исполнения
            if our_orders and not our_positions:
                logger.info(f"⏳ Ждем исполнения {len(our_orders)} Grid ордеров...")
                self.tp_placed = False  # Сбрасываем флаг
                return
            
            # Если есть позиция
            if our_positions:
                position = our_positions[0]
                
                # Если TP еще не размещен
                if not self.tp_placed:
                    # Отменяем ВСЕ ордера (это Grid ордера)
                    if our_orders:
                        logger.info(f"🗑️ Отменяем {len(our_orders)} Grid ордеров...")
                        for order in our_orders:
                            try:
                                self.dashboard.cancel_order(self.product_id, order['order_id'])
                                logger.info(f"✅ Отменен ордер {order['side']} @ ${order['price']:.2f}")
                            except Exception as e:
                                logger.error(f"Ошибка отмены ордера: {e}")
                    
                    # Размещаем TP
                    logger.info("📈 Размещаем TP ордер...")
                    await self._place_tp_sl_for_position(position)
                    self.tp_placed = True  # Устанавливаем флаг
                    return
                else:
                    # TP уже размещен, мониторим P&L
                    logger.info(f"✅ TP установлен, мониторим позицию...")
                    await self._manage_position(position)
                    return
                
        except Exception as e:
            logger.error(f"Ошибка мониторинга: {e}")
    
    async def _place_tp_sl_for_position(self, position: Dict):
        """Размещение TP и SL для новой позиции"""
        try:
            is_long = position['amount'] > 0
            size = abs(position['amount'])
            product_id = position['product_id']
            
            # Получаем entry_price из сохранённых данных dashboard
            entry_data = self.dashboard.entry_prices.get(product_id)
            
            if not entry_data:
                logger.warning("Entry price не найден в данных, используем текущую цену как entry")
                entry_price = position.get('price', 0)
                # Сохраняем entry price
                self.dashboard.save_entry_price(product_id, entry_price, size)
            else:
                entry_price = entry_data.get('entry_price', 0)
            
            if not entry_price:
                logger.error("Не удалось получить entry_price")
                return
            
            # Вычисляем TP и SL цены
            if is_long:
                tp_price = entry_price * (1 + self.tp_percent / 100)
                sl_price = entry_price * (1 - self.sl_percent / 100)
            else:
                tp_price = entry_price * (1 - self.tp_percent / 100)
                sl_price = entry_price * (1 + self.sl_percent / 100)
            
            logger.info(f"📈 Размещаем TP/SL для {'LONG' if is_long else 'SHORT'} позиции")
            logger.info(f"   Entry: ${entry_price:.2f}")
            logger.info(f"   TP: ${tp_price:.2f} ({self.tp_percent:+.1f}%)")
            logger.info(f"   SL: ${sl_price:.2f} ({-self.sl_percent:.1f}%)")
            
            # Размещаем TP ордер
            self.dashboard.place_tp_order(
                self.product_id,
                size,
                is_long,
                tp_price
            )
            
            logger.info(f"✅ TP/SL размещены")
            
        except Exception as e:
            logger.error(f"Ошибка размещения TP/SL: {e}")
    
    async def _manage_position(self, position: Dict):
        """Управление одной позицией с TP/SL"""
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
            
            logger.info(f"📊 {'LONG' if is_long else 'SHORT'} позиция: P&L {pnl_percent:+.2f}%")
            
            # Проверка TP
            if pnl_percent >= self.tp_percent:
                logger.info(f"🎯 TP достигнут! Закрываем позицию...")
                await self._close_position_market(position)
                
                # После закрытия - размещаем новую Grid
                await asyncio.sleep(5)
                await self._place_grid()
            
            # Проверка SL
            elif pnl_percent <= -self.sl_percent:
                logger.info(f"🛑 SL сработал! Закрываем позицию...")
                await self._close_position_market(position)
                
                # После закрытия - размещаем новую Grid
                await asyncio.sleep(5)
                await self._place_grid()
                
        except Exception as e:
            logger.error(f"Ошибка управления позицией: {e}")
    
    async def _close_position_market(self, position: Dict):
        """Закрыть позицию по маркету"""
        try:
            size = abs(position['amount'])
            is_long = position['amount'] > 0
            
            # Закрываем в обратном направлении
            result = self.dashboard.place_order(
                self.product_id,
                size / self.dashboard.leverage,  # Базовый размер
                is_long=not is_long,  # Обратное направление
                custom_price=None,  # Маркет
                auto_tp=False
            )
            
            if result:
                logger.info("✅ Позиция закрыта")
                return True
            else:
                logger.error("❌ Не удалось закрыть позицию")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка закрытия позиции: {e}")
            return False


# Тестирование
async def test_grid_autotrader():
    """Тестовый запуск"""
    dashboard = TradingDashboard()
    
    # Параметры для SOL-PERP
    trader = GridAutoTrader(
        dashboard=dashboard,
        product_id=8,  # SOL-PERP
        base_size=0.5,
        grid_offset=0.5,  # ±0.5%
        tp_percent=0.5,   # TP = 0.5%
        sl_percent=0.3    # SL = 0.3%
    )
    
    try:
        await trader.start()
    except KeyboardInterrupt:
        trader.stop()


if __name__ == "__main__":
    asyncio.run(test_grid_autotrader())
