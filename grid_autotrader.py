"""
GRID AUTO-TRADER - С ОГРАНИЧЕНИЕМ ДОКУПОВ И ФИЛЬТРАЦИЕЙ ОРДЕРОВ
ЛОГИКА: После 2х исполнений в одну сторону - блокируем эту сторону
МЕТКИ: Каждый автогрид отслеживает только свои ордера
"""
import asyncio
import logging
from decimal import Decimal
import time
from trading_dashboard_v2 import TradingDashboard

logger = logging.getLogger(__name__)

PRODUCTS = {
    2: "BTC-PERP",
    4: "ETH-PERP",
    8: "SOL-PERP",
    20: "INK-PERP"
}

# Price increments для каждого продукта (в долларах)
PRICE_INCREMENTS = {
    2: 1.0,      # BTC: $1
    4: 0.1,      # ETH: $0.10
    8: 0.01,     # SOL: $0.01
    20: 0.0001   # INK: $0.0001
}

def round_to_increment(price: float, increment: float) -> float:
    """Округляет цену до ближайшего инкремента"""
    return round(price / increment) * increment

class GridAutoTrader:
    def __init__(
        self,
        dashboard: TradingDashboard,
        product_id: int,
        base_size: float,
        grid_offset: float = 0.1
    ):
        """
        Args:
            dashboard: Dashboard для торговли
            product_id: ID продукта (2=BTC, 4=ETH, 8=SOL, 20=INK)
            base_size: Базовый размер ордера (без плеча)
            grid_offset: Отступ от цены в % (например 0.5 = ±0.5%)
        """
        self.dashboard = dashboard
        self.product_id = product_id
        self.base_size = base_size
        self.grid_offset = grid_offset
        
        # Отслеживание своих ордеров по параметрам (price, size, side)
        self.my_orders = []  # Список словарей {'price': Decimal, 'size': Decimal, 'is_long': bool, 'time': float}
        
        self.running = False
        self.prev_size = 0
        self.entry_count = 0  # Сколько раз докупились
        self.position_side = None  # "LONG" или "SHORT"
        self.avg_entry_price = 0  # Средняя цена входа
        self.risk_check_start_time = None  # Когда начали отслеживать риск
    
    def _filter_my_orders(self, all_orders):
        """Фильтрует только свои ордера из всех ордеров по продукту"""
        if not self.my_orders:
            logger.info("🔍 Нет зарегистрированных ордеров для фильтрации")
            return []
        
        my_filtered = []
        tolerance = Decimal("0.001")  # Погрешность 0.1% для сравнения цен
        
        product_orders = [o for o in all_orders if o['product_id'] == self.product_id]
        
        for order in product_orders:
            order_price = Decimal(str(order['price']))
            order_size = abs(Decimal(str(order['amount'])))
            order_is_long = order['amount'] > 0
            
            # Проверяем совпадение с нашими записями
            for my_order in self.my_orders:
                price_match = abs(order_price - my_order['price']) / my_order['price'] < tolerance
                size_match = abs(order_size - my_order['size']) / my_order['size'] < tolerance
                side_match = order_is_long == my_order['is_long']
                
                if price_match and size_match and side_match:
                    my_filtered.append(order)
                    break
        
        logger.info(f"🔍 Фильтр: {len(product_orders)} всего → {len(my_filtered)} своих")
        return my_filtered
        
    async def start(self):
        """Запустить"""
        self.running = True
        logger.info("🤖 Grid START")
        
        # ОТМЕНЯЕМ все старые ордера перед стартом
        await self._cancel_all()
        await asyncio.sleep(1)
        
        # Первая Grid - оба направления
        await self._place_grid(place_long=True, place_short=True)
        
        # ВАЖНО: Запоминаем начальную позицию чтобы НЕ РЕАГИРОВАТЬ на неё
        initial_positions = self.dashboard.get_positions()
        initial_pos = next((p for p in initial_positions if p['product_id'] == self.product_id), None)
        initial_size = abs(initial_pos['amount']) if initial_pos else 0
        
        if initial_size > 0:
            logger.warning(f"⚠️ ОБНАРУЖЕНА СУЩЕСТВУЮЩАЯ ПОЗИЦИЯ: {initial_size:.2f} - ИГНОРИРУЕМ!")
            logger.warning(f"   Grid будет работать ТОЛЬКО с новыми позициями от своих ордеров")
        
        while self.running:
            try:
                await asyncio.sleep(3)
                
                # Получаем позицию
                positions = self.dashboard.get_positions()
                our_pos = next((p for p in positions if p['product_id'] == self.product_id), None)
                curr_size = abs(our_pos['amount']) if our_pos else 0
                
                # КРИТИЧНО: Вычитаем начальную позицию чтобы видеть только СВОИ изменения
                if initial_size > 0:
                    if curr_size <= initial_size:
                        # Позиция не выросла или уменьшилась - НЕ НАША
                        curr_size = 0
                        our_pos = None
                    else:
                        # Позиция выросла - вычитаем начальную
                        curr_size = curr_size - initial_size
                
                # Получаем открытые ордера
                orders = self.dashboard.get_open_orders()
                # ФИЛЬТРУЕМ только свои ордера
                our_orders = self._filter_my_orders(orders)
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
                        
                        # ВАЖНО: Проверяем сколько ордеров еще висит
                        # Если LONG позиция открылась, то должен был отмениться LONG ордер
                        # Проверяем есть ли еще LONG ордер - если НЕТ, значит fill был полный
                        same_side_orders = [o for o in our_orders if (o['amount'] > 0) == (curr_side == "LONG")]
                        
                        if len(same_side_orders) == 0:
                            # Ордер исполнился ПОЛНОСТЬЮ - размещаем новую Grid
                            logger.info(f"   ✅ Ордер исполнен ПОЛНОСТЬЮ - размещаем Grid")
                            await self._place_grid(place_long=True, place_short=True)
                        else:
                            # Ордер исполнился ЧАСТИЧНО - ждем полного fill
                            logger.info(f"   ⏳ ЧАСТИЧНОЕ исполнение - ждем полного fill (висит {len(same_side_orders)} ордеров той же стороны)")
                    
                    # Позиция растёт = докупились ИЛИ частичный fill
                    elif curr_size > self.prev_size:
                        added_size = curr_size - self.prev_size
                        curr_price = our_pos['price']
                        
                        # КРИТИЧНО: Проверяем что это НОВЫЙ ордер, а не частичный fill ПЕРВОГО ордера
                        same_side_orders = [o for o in our_orders if (o['amount'] > 0) == (curr_side == "LONG")]
                        expected_size_with_leverage = self.base_size * float(self.dashboard.leverage)
                        
                        # Если добавилось примерно base_size * leverage И это НЕ первый entry - это НОВЫЙ вход
                        # ВАЖНО: Первый вход может fill частями, и это НОРМАЛЬНО
                        is_new_entry = (abs(added_size - expected_size_with_leverage) < (expected_size_with_leverage * 0.3)) and (self.entry_count >= 1) and (curr_size > expected_size_with_leverage * 1.5)
                        
                        if is_new_entry:
                            # Это НОВЫЙ вход (докуп)
                            self.entry_count += 1
                            
                            # Пересчитываем среднюю цену входа
                            self.avg_entry_price = (self.prev_size * self.avg_entry_price + added_size * curr_price) / curr_size
                            
                            logger.info(f"📈 {curr_side} {self.prev_size:.2f} → {curr_size:.2f} (#{self.entry_count} - НОВЫЙ ВХОД)")
                            logger.info(f"   Средняя цена входа: ${self.avg_entry_price:.2f}")
                            self.prev_size = curr_size
                            
                            # Логика размещения новых ордеров
                            if self.entry_count == 2:
                                # Второй вход (докуп) - ОТМЕНЯЕМ ВСЁ, размещаем только противоположное на ПОЛНЫЙ размер позиции
                                # После этого третий вход НЕВОЗМОЖЕН - позиция закроется либо в плюс либо по риск-стопу
                                await self._cancel_all()
                                await asyncio.sleep(0.5)
                                self.risk_check_start_time = time.time()
                                
                                # ВАЖНО: Убираем плечо для размера ордера!
                                base_position_size = curr_size / float(self.dashboard.leverage)
                                
                                if curr_side == "LONG":
                                    logger.info(f"⚠️ Entry #2 (ПОСЛЕДНИЙ): размещаем SHORT {base_position_size:.2f} (закроет всю позицию)")
                                    await self._place_grid(place_long=False, place_short=True, long_size=0, short_size=base_position_size)
                                else:
                                    logger.info(f"⚠️ Entry #2 (ПОСЛЕДНИЙ): размещаем LONG {base_position_size:.2f} (закроет всю позицию)")
                                    await self._place_grid(place_long=True, place_short=False, long_size=base_position_size, short_size=0)
                        else:
                            # Это частичный fill старого ордера
                            logger.info(f"📊 {curr_side} {self.prev_size:.2f} → {curr_size:.2f} (ЧАСТИЧНЫЙ FILL +{added_size:.2f})")
                            self.prev_size = curr_size
                            
                            # Проверяем исполнился ли ордер ПОЛНОСТЬЮ
                            if len(same_side_orders) == 0:
                                logger.info(f"   ✅ Ордер исполнен ПОЛНОСТЬЮ - размещаем Grid")
                                await self._place_grid(place_long=True, place_short=True)
                    
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
                                    logger.info(f"⚠️ Цена ${curr_price:.2f} < ${threshold_price:.2f} (-0.5% от средней)")
                                    logger.info(f"🔴 РИСК: Цена ушла вниз → ЗАКРЫВАЕМ СРАЗУ")
                                    
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
                                        continue  # Переходим к следующей итерации цикла
                                else:
                                    logger.info(f"📊 {curr_side}: {curr_size:.2f} | {orders_count} ордеров")
                            
                            else:  # SHORT позиция
                                # SHORT позиция: проверяем рост цены выше средней на 0.5%
                                deviation = (curr_price - self.avg_entry_price) / self.avg_entry_price
                                threshold_price = self.avg_entry_price * 1.005
                                
                                if curr_price > threshold_price:
                                    logger.info(f"⚠️ Цена ${curr_price:.2f} > ${threshold_price:.2f} (+0.5% от средней)")
                                    logger.info(f"🔴 РИСК: Цена ушла вверх → ЗАКРЫВАЕМ СРАЗУ")
                                    
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
                                    continue  # Переходим к следующей итерации цикла
                                else:
                                    logger.info(f"📊 {curr_side}: {curr_size:.2f} | {orders_count} ордеров")
                        else:
                            logger.info(f"📊 {curr_side}: {curr_size:.2f} | {orders_count} ордеров (нет цены)")
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
            
            # Используем метод напрямую, если доступен (для MultiWalletDashboard)
            if hasattr(self.dashboard, 'cancel_product_orders'):
                self.dashboard.cancel_product_orders(params)
            else:
                # Fallback для обычного TradingDashboard
                self.dashboard.client.market.cancel_product_orders(params)
            
            # Очищаем список своих ордеров
            self.my_orders = []
            
            logger.info("✅ Ордера отменены")
        except Exception as e:
            logger.error(f"ERR отмена: {e}")
    
    async def _place_grid(self, place_long=True, place_short=True, long_size=None, short_size=None, append=False):
        """Разместить Grid с выбором направлений и custom размерами
        
        Args:
            place_long: Размещать ли LONG ордер
            place_short: Размещать ли SHORT ордер
            long_size: Размер LONG ордера (если None - используется base_size)
            short_size: Размер SHORT ордера (если None - используется base_size)
            append: Если True - добавляет к существующим меткам, если False - очищает список меток
        """
        try:
            symbol = PRODUCTS[self.product_id]
            price = self.dashboard.get_market_price(self.product_id)
            
            if not price:
                return
            
            offset = Decimal(str(self.grid_offset / 100))
            long_price_raw = float(Decimal(str(price)) * (Decimal("1") - offset))
            short_price_raw = float(Decimal(str(price)) * (Decimal("1") + offset))
            
            # Округляем до price increment
            increment = PRICE_INCREMENTS[self.product_id]
            long_price = round_to_increment(long_price_raw, increment)
            short_price = round_to_increment(short_price_raw, increment)
            
            placed = []
            
            # ВАЖНО: Очищаем или добавляем к списку в зависимости от режима
            if not append:
                self.my_orders = []
                logger.info("🔖 Очищен список меток (новая grid)")
            else:
                logger.info(f"🔖 Добавляем метки к существующим ({len(self.my_orders)} уже есть)")
            
            if place_long:
                size = long_size if long_size is not None else self.base_size
                logger.info(f"📊 {symbol} LONG {size:.2f} @ ${long_price:.2f}")
                long_ok = self.dashboard.place_order(
                    self.product_id,
                    size,
                    is_long=True,
                    custom_price=long_price,
                    auto_tp=False,  # Автогрид сам управляет выходом!
                    ttl_seconds=7*24*60*60
                )
                if long_ok:
                    placed.append(f"LONG {size:.2f}")
                    # ИСПРАВЛЕНО: Сохраняем размер С ПЛЕЧОМ, т.к. биржа возвращает его с плечом!
                    size_with_leverage = Decimal(str(size)) * Decimal(str(self.dashboard.leverage))
                    self.my_orders.append({
                        'price': Decimal(str(long_price)),
                        'size': size_with_leverage,
                        'is_long': True,
                        'time': time.time()
                    })
            
            if place_short:
                size = short_size if short_size is not None else self.base_size
                logger.info(f"📊 {symbol} SHORT {size:.2f} @ ${short_price:.2f}")
                short_ok = self.dashboard.place_order(
                    self.product_id,
                    size,
                    is_long=False,
                    custom_price=short_price,
                    auto_tp=False,  # Автогрид сам управляет выходом!
                    ttl_seconds=7*24*60*60
                )
                if short_ok:
                    placed.append(f"SHORT {size:.2f}")
                    # ИСПРАВЛЕНО: Сохраняем размер С ПЛЕЧОМ, т.к. биржа возвращает его с плечом!
                    size_with_leverage = Decimal(str(size)) * Decimal(str(self.dashboard.leverage))
                    self.my_orders.append({
                        'price': Decimal(str(short_price)),
                        'size': size_with_leverage,
                        'is_long': False,
                        'time': time.time()
                    })
            
            if placed:
                logger.info(f"✅ Grid OK: {' + '.join(placed)}")
                logger.info(f"🔖 Зарегистрировано ордеров: {len(self.my_orders)}")
            else:
                logger.error("❌ ERR")
                
        except Exception as e:
            logger.error(f"ERR: {e}")
