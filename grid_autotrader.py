"""
GRID AUTO-TRADER - С ОГРАНИЧЕНИЕМ ДОКУПОВ
ЛОГИКА: После 2х исполнений в одну сторону - блокируем эту сторону
"""
import asyncio
import logging
from decimal import Decimal
import time
from trading_dashboard import TradingDashboard

logger = logging.getLogger(__name__)

PRODUCTS = {
    2: "BTC-PERP",
    4: "ETH-PERP",
    8: "SOL-PERP",
    20: "INK-PERP"
}

class GridAutoTrader:
    def __init__(
        self,
        dashboard: TradingDashboard,
        product_id: int,
        base_size: float,
        grid_offset: float = 0.1,
        max_positions: int = 3
    ):
        self.dashboard = dashboard
        self.product_id = product_id
        self.base_size = base_size
        self.grid_offset = grid_offset
        self.max_positions = max_positions
        
        self.running = False
        self.prev_size = 0
        self.entry_count = 0  # Сколько раз докупились
        self.position_side = None  # "LONG" или "SHORT"
        self.avg_entry_price = 0  # Средняя цена входа
        self.risk_check_start_time = None  # Когда начали отслеживать риск
        
    async def start(self):
        """Запустить"""
        self.running = True
        logger.info("🤖 Grid START")
        
        # ОТМЕНЯЕМ все старые ордера перед стартом
        await self._cancel_all()
        await asyncio.sleep(1)
        
        # Первая Grid - оба направления
        await self._place_grid(place_long=True, place_short=True)
        
        while self.running:
            try:
                await asyncio.sleep(3)
                
                # Получаем позицию
                positions = self.dashboard.get_positions()
                our_pos = next((p for p in positions if p['product_id'] == self.product_id), None)
                curr_size = abs(our_pos['amount']) if our_pos else 0
                
                # Получаем открытые ордера
                orders = self.dashboard.get_open_orders()
                our_orders = [o for o in orders if o['product_id'] == self.product_id]
                orders_count = len(our_orders)
                
                # Проверяем позицию
                if our_pos:
                    curr_side = our_pos['side']  # "LONG" или "SHORT"
                    
                    # Позиция открылась впервые
                    if self.prev_size == 0:
                        curr_price = our_pos['price']
                        logger.info(f"📊 Открыт {curr_side}: {curr_size:.2f} @ ${curr_price:.2f}")
                        self.prev_size = curr_size
                        self.entry_count = 1
                        self.position_side = curr_side
                        self.avg_entry_price = curr_price  # Первая цена входа
                        self.risk_check_start_time = None
                        
                        # Размещаем Grid: оба направления
                        await self._place_grid(place_long=True, place_short=True)
                    
                    # Позиция растёт = докупились
                    elif curr_size > self.prev_size:
                        self.entry_count += 1
                        curr_price = our_pos['price']
                        
                        # Пересчитываем среднюю цену входа
                        # avg = (prev_size * avg_price + added_size * curr_price) / curr_size
                        added_size = curr_size - self.prev_size
                        self.avg_entry_price = (self.prev_size * self.avg_entry_price + added_size * curr_price) / curr_size
                        
                        logger.info(f"📈 {curr_side} {self.prev_size:.2f} → {curr_size:.2f} (#{self.entry_count})")
                        logger.info(f"   Средняя цена входа: ${self.avg_entry_price:.2f}")
                        self.prev_size = curr_size
                        
                        # Логика размещения новых ордеров
                        if self.entry_count == 1:
                            # Первое открытие - ДОБАВЛЯЕМ ещё LONG + SHORT (не отменяя старые)
                            logger.info(f"   Добавляем ещё Grid: LONG + SHORT")
                            await self._place_grid(place_long=True, place_short=True, long_size=self.base_size, short_size=self.base_size)
                        elif self.entry_count == 2:
                            # Второй вход (докуп) - ОТМЕНЯЕМ ВСЁ, размещаем только противоположное на весь размер
                            await self._cancel_all()
                            await asyncio.sleep(0.5)
                            self.risk_check_start_time = time.time()
                            
                            if curr_side == "LONG":
                                logger.info(f"⚠️ Entry #2: размещаем SHORT {curr_size:.2f} (вся позиция)")
                                await self._place_grid(place_long=False, place_short=True, long_size=0, short_size=curr_size)
                            else:
                                logger.info(f"⚠️ Entry #2: размещаем LONG {curr_size:.2f} (вся позиция)")
                                await self._place_grid(place_long=True, place_short=False, long_size=curr_size, short_size=0)
                        elif self.entry_count >= 3:
                            # Третий вход - уже есть защита 0.5%, ничего не размещаем
                            logger.info(f"⏸️ ЛИМИТ докупов ({self.entry_count})")
                    
                    # ПРОВЕРКА РИСКА: После entry #2 отслеживаем отклонение цены на 0.5%
                    if self.entry_count >= 2 and self.risk_check_start_time is not None:
                        curr_price = self.dashboard.get_market_price(self.product_id)
                        
                        if curr_price:
                            # Вычисляем отклонение от средней цены входа
                            if curr_side == "LONG":
                                # LONG позиция: проверяем падение цены ниже средней на 0.5%
                                deviation = (self.avg_entry_price - curr_price) / self.avg_entry_price
                                threshold_price = self.avg_entry_price * 0.995
                                
                                if curr_price < threshold_price:
                                    elapsed_min = (time.time() - self.risk_check_start_time) / 60
                                    logger.info(f"⚠️ Цена ${curr_price:.2f} < ${threshold_price:.2f} (-0.5% от средней)")
                                    logger.info(f"   Прошло {elapsed_min:.1f} мин")
                                    
                                    if elapsed_min >= 5:
                                        logger.info(f"🔴 РИСК: Цена ушла вниз > 5 мин → ЗАКРЫВАЕМ")
                                        await self._cancel_all()
                                        await asyncio.sleep(1)
                                        result = self.dashboard.close_position(self.product_id)
                                        
                                        if result:
                                            logger.info("✅ Позиция закрыта по риску")
                                            self.prev_size = 0
                                            self.entry_count = 0
                                            self.position_side = None
                                            self.avg_entry_price = 0
                                            self.risk_check_start_time = None
                                            await asyncio.sleep(2)
                                            await self._place_grid(place_long=True, place_short=True, long_size=self.base_size, short_size=self.base_size)
                            
                            else:  # SHORT позиция
                                # SHORT позиция: проверяем рост цены выше средней на 0.5%
                                deviation = (curr_price - self.avg_entry_price) / self.avg_entry_price
                                threshold_price = self.avg_entry_price * 1.005
                                
                                if curr_price > threshold_price:
                                    elapsed_min = (time.time() - self.risk_check_start_time) / 60
                                    logger.info(f"⚠️ Цена ${curr_price:.2f} > ${threshold_price:.2f} (+0.5% от средней)")
                                    logger.info(f"   Прошло {elapsed_min:.1f} мин")
                                    
                                    if elapsed_min >= 5:
                                        logger.info(f"🔴 РИСК: Цена ушла вверх > 5 мин → ЗАКРЫВАЕМ")
                                        await self._cancel_all()
                                        await asyncio.sleep(1)
                                        result = self.dashboard.close_position(self.product_id)
                                        
                                        if result:
                                            logger.info("✅ Позиция закрыта по риску")
                                            self.prev_size = 0
                                            self.entry_count = 0
                                            self.position_side = None
                                            self.avg_entry_price = 0
                                            self.risk_check_start_time = None
                                            await asyncio.sleep(2)
                                            await self._place_grid(place_long=True, place_short=True, long_size=self.base_size, short_size=self.base_size)
                                    else:
                                        logger.info(f"📊 {curr_side}: {curr_size:.2f} | Риск +{deviation*100:.2f}% (ждём 5 мин)")
                        else:
                            logger.info(f"📊 {curr_side}: {curr_size:.2f} | {orders_count} ордеров")
                    else:
                        logger.info(f"📊 {curr_side}: {curr_size:.2f} | {orders_count} ордеров")
                    
                    # Ордера пропали но позиция есть
                    if orders_count == 0 and curr_size > 0:
                        logger.info(f"⚠️ Ордера пропали ({curr_side}: {curr_size:.2f}) → НОВАЯ GRID")
                        
                        # Размещаем ТОЛЬКО противоположное направление
                        if curr_side == "LONG":
                            await self._place_grid(place_long=False, place_short=True, long_size=0, short_size=self.base_size)
                        else:
                            await self._place_grid(place_long=True, place_short=False, long_size=self.base_size, short_size=0)
                    else:
                        logger.info(f"📊 {curr_side}: {curr_size:.2f} | {orders_count} ордеров")
                else:
                    # Позиция закрылась - СБРОС
                    if self.prev_size > 0:
                        logger.info(f"✅ Позиция {self.position_side} закрыта → СБРОС + НОВАЯ GRID")
                        self.prev_size = 0
                        self.entry_count = 0
                        self.position_side = None
                        self.avg_entry_price = 0
                        self.risk_check_start_time = None
                        
                        await self._cancel_all()
                        await asyncio.sleep(2)
                        
                        # После закрытия - снова оба направления
                        await self._place_grid(place_long=True, place_short=True, long_size=self.base_size, short_size=self.base_size)
                    
                    # Ордера пропали без позиции
                    elif orders_count == 0:
                        logger.info("⚠️ Нет ордеров → НОВАЯ GRID")
                        await self._place_grid(place_long=True, place_short=True, long_size=self.base_size, short_size=self.base_size)
                    else:
                        logger.info(f"⏳ Нет позиции | {orders_count} ордеров")
                
            except Exception as e:
                logger.error(f"ERR: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(5)
    
    def stop(self):
        self.running = False
        logger.info("🛑 Grid STOP")
    
    async def _cancel_all(self):
        """Отменить все ордера"""
        try:
            from nado_protocol.engine_client.types.execute import CancelProductOrdersParams
            
            params = CancelProductOrdersParams(
                sender=self.dashboard.sender_hex,
                productIds=[self.product_id]
            )
            
            self.dashboard.client.market.cancel_product_orders(params)
            logger.info("✅ Ордера отменены")
        except Exception as e:
            logger.error(f"ERR отмена: {e}")
    
    async def _place_grid(self, place_long=True, place_short=True, long_size=None, short_size=None):
        """Разместить Grid с выбором направлений и custom размерами"""
        try:
            symbol = PRODUCTS[self.product_id]
            price = self.dashboard.get_market_price(self.product_id)
            
            if not price:
                return
            
            offset = Decimal(str(self.grid_offset / 100))
            long_price = float(Decimal(str(price)) * (Decimal("1") - offset))
            short_price = float(Decimal(str(price)) * (Decimal("1") + offset))
            
            placed = []
            
            if place_long:
                size = long_size if long_size is not None else self.base_size
                logger.info(f"📊 {symbol} LONG {size:.2f} @ ${long_price:.2f}")
                long_ok = self.dashboard.place_order(
                    self.product_id,
                    size,
                    is_long=True,
                    custom_price=long_price,
                    ttl_seconds=7*24*60*60
                )
                if long_ok:
                    placed.append(f"LONG {size:.2f}")
            
            if place_short:
                size = short_size if short_size is not None else self.base_size
                logger.info(f"📊 {symbol} SHORT {size:.2f} @ ${short_price:.2f}")
                short_ok = self.dashboard.place_order(
                    self.product_id,
                    size,
                    is_long=False,
                    custom_price=short_price,
                    ttl_seconds=7*24*60*60
                )
                if short_ok:
                    placed.append(f"SHORT {size:.2f}")
            
            if placed:
                logger.info(f"✅ Grid OK: {' + '.join(placed)}")
            else:
                logger.error("❌ ERR")
                
        except Exception as e:
            logger.error(f"ERR: {e}")
