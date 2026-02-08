"""
NADO DEX Trading Dashboard
Комплексный инструмент для управления торговлей
"""
import sys
import os
import json
import time

# Исправление кодировки для Windows
if os.name == 'nt':  # Windows
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.engine_client.types.execute import PlaceMarketOrderParams
from nado_protocol.utils.execute import MarketOrderParams
from nado_protocol.utils import SubaccountParams, subaccount_to_hex
from decimal import ROUND_DOWN
import config
from decimal import Decimal
import time
from datetime import datetime

# Доступные торговые пары
PRODUCTS = {
    2: "BTC-PERP",
    4: "ETH-PERP",
    8: "SOL-PERP",
    9: "SOLUSDT0",  # SOL USDT perp
    10: "INK-PERP",
}

SIZE_INCREMENTS = {
    2: Decimal("0.001"),  # BTC
    4: Decimal("0.01"),   # ETH
    8: Decimal("0.1"),    # SOL
    9: Decimal("0.1"),    # SOLUSDT0
    10: Decimal("1"),     # INK
}

PRICE_INCREMENTS = {
    2: Decimal("0.001"),  # BTC: $0.001
    4: Decimal("0.01"),   # ETH: $0.01
    8: Decimal("0.01"),   # SOL: $0.01
    9: Decimal("0.01"),   # SOLUSDT0: $0.01
    10: Decimal("0.0001"), # INK: $0.0001
}

PRICE_INCREMENTS_X18 = {
    2: 1000000000000000,      # BTC: 0.001
    4: 10000000000000000,     # ETH: 0.01
    8: 10000000000000000,     # SOL: 0.01
    9: 10000000000000000,     # SOLUSDT0: 0.01
    10: 10000000000000000,    # INK: 0.01
}

class TradingDashboard:
    def normalize_size(self, product_id, size: Decimal) -> Decimal:
    	step = SIZE_INCREMENTS[product_id]
    	return size.quantize(step, rounding=ROUND_DOWN)
    
    def normalize_price(self, product_id, price: Decimal) -> Decimal:
    	step = PRICE_INCREMENTS[product_id]
    	return price.quantize(step, rounding=ROUND_DOWN)
    
    def load_positions_data(self):
        """Загрузить данные позиций из файла"""
        try:
            if os.path.exists(self.positions_file):
                with open(self.positions_file, 'r') as f:
                    data = json.load(f)
                    # Конвертируем ключи обратно в int
                    return {int(k): v for k, v in data.items()}
        except:
            pass
        return {}
    
    def save_positions_data(self):
        """Сохранить данные позиций в файл"""
        try:
            with open(self.positions_file, 'w') as f:
                json.dump(self.entry_prices, f)
        except Exception as e:
            print(f"⚠️ Ошибка сохранения данных позиций: {e}")
    
    def load_trade_history(self):
        """Загрузить историю торговли из файла"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return []
    
    def save_trade_history(self):
        """Сохранить историю торговли в файл"""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.trade_history, f, indent=2)
        except Exception as e:
            print(f"⚠️ Ошибка сохранения истории: {e}")
    
    def add_trade_to_history(self, product_id, symbol, side, size, entry_price, exit_price, pnl):
        """Добавить сделку в историю"""
        from datetime import datetime
        
        trade = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'product_id': product_id,
            'symbol': symbol,
            'side': side,
            'size': float(size),
            'entry_price': float(entry_price),
            'exit_price': float(exit_price),
            'pnl': float(pnl),
            'pnl_percent': (float(pnl) / (float(size) * float(entry_price)) * 100) if entry_price and size else 0
        }
        
        self.trade_history.append(trade)
        self.save_trade_history()
    
    def save_entry_price(self, product_id, entry_price, size, tp_price=None, sl_price=None):
        """Сохранить цену входа для позиции"""
        self.entry_prices[product_id] = {
            'entry_price': float(entry_price),
            'size': float(size),
            'tp_price': float(tp_price) if tp_price else None,
            'sl_price': float(sl_price) if sl_price else None
        }
        self.save_positions_data()
    
    def remove_entry_price(self, product_id):
        """Удалить данные позиции"""
        if product_id in self.entry_prices:
            del self.entry_prices[product_id]
            self.save_positions_data()
    
    def calculate_pnl(self, product_id, current_price, amount):
        """Рассчитать P&L для позиции (как на DEX с funding)"""
        if product_id not in self.entry_prices:
            return None
        
        entry_data = self.entry_prices[product_id]
        entry_price = Decimal(str(entry_data['entry_price']))
        current_price = Decimal(str(current_price))
        amount = Decimal(str(amount))
        
        # Базовый P&L
        if amount > 0:  # LONG
            pnl_base = (current_price - entry_price) * abs(amount)
        else:  # SHORT
            pnl_base = (entry_price - current_price) * abs(amount)
        
        # DEX вычитает ~50% от базового P&L как funding/fees
        pnl_adjusted = pnl_base * Decimal("0.5")
        
        return float(pnl_adjusted)
    
    def place_tp_order(self, product_id, size, is_long, target_price):
        """Разместить TP ордер через price trigger"""
        try:
            size = Decimal(size)
            size = self.normalize_size(product_id, size)
            
            # amount_x18 для ЗАКРЫТИЯ позиции (обратное направление)
            amount_x18 = int((size * Decimal(10) ** 18).to_integral_value())
            
            if is_long:
                # Закрываем LONG = продаем (отрицательный amount)
                amount_x18 = -amount_x18
            else:
                # Закрываем SHORT = покупаем (положительный amount)
                amount_x18 = amount_x18
            
            # Проверка кратности шагу
            step_x18 = int(SIZE_INCREMENTS[product_id] * Decimal(10) ** 18)
            if amount_x18 % step_x18 != 0:
                raise ValueError(f"amount_x18 {amount_x18} не кратен шагу {step_x18}")
            
            # Округляем цену
            price_decimal = Decimal(str(target_price))
            price_decimal = self.normalize_price(product_id, price_decimal)
            
            # Конвертируем в priceX18
            priceX18 = int((price_decimal * Decimal(10) ** 18).to_integral_value())
            
            # Проверка кратности шагу цены
            price_step_x18 = int(PRICE_INCREMENTS_X18[product_id])
            if priceX18 % price_step_x18 != 0:
                raise ValueError(f"priceX18 {priceX18} не кратен шагу {price_step_x18}")
            
            # Размещаем триггерный ордер
            # Для TP:
            # - LONG позиция → закрываем продажей → триггер "last_price_above"
            # - SHORT позиция → закрываем покупкой → триггер "last_price_below"
            from nado_protocol.utils.expiration import OrderType
            
            # Определяем тип триггера для TP
            if is_long:
                # LONG: закрываем продажей выше текущей цены
                trigger_type = "last_price_above"
            else:
                # SHORT: закрываем покупкой ниже текущей цены
                trigger_type = "last_price_below"
            
            result = self.client.market.place_price_trigger_order(
                product_id=product_id,
                price_x18=str(priceX18),
                amount_x18=str(amount_x18),
                trigger_price_x18=str(priceX18),  # Триггер и цена исполнения совпадают
                trigger_type=trigger_type,
                reduce_only=True,  # Только закрытие
                order_type=OrderType.POST_ONLY  # Maker для низких комиссий
            )
            
            if result.status.value == "success":
                return result
            else:
                print(f"   ❌ Ошибка: {result.error}")
                return None
                
        except Exception as e:
            print(f"   ❌ Ошибка размещения TP ордера: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def place_sl_order(self, product_id, size, is_long, target_price):
        """Разместить SL ордер через price trigger"""
        print(f"🛑 place_sl_order called: product={product_id}, size={size}, is_long={is_long}, price={target_price}")
        try:
            size = Decimal(size)
            size = self.normalize_size(product_id, size)
            print(f"   Normalized size: {size}")
            
            # amount_x18 для ЗАКРЫТИЯ позиции (обратное направление)
            amount_x18 = int((size * Decimal(10) ** 18).to_integral_value())
            
            if is_long:
                # Закрываем LONG = продаем (отрицательный amount)
                amount_x18 = -amount_x18
            else:
                # Закрываем SHORT = покупаем (положительный amount)
                amount_x18 = amount_x18
            
            # Проверка кратности шагу
            step_x18 = int(SIZE_INCREMENTS[product_id] * Decimal(10) ** 18)
            if amount_x18 % step_x18 != 0:
                raise ValueError(f"amount_x18 {amount_x18} не кратен шагу {step_x18}")
            
            # Округляем цену
            price_decimal = Decimal(str(target_price))
            price_decimal = self.normalize_price(product_id, price_decimal)
            
            # Конвертируем в priceX18
            priceX18 = int((price_decimal * Decimal(10) ** 18).to_integral_value())
            
            # Проверка кратности шагу цены
            price_step_x18 = int(PRICE_INCREMENTS_X18[product_id])
            if priceX18 % price_step_x18 != 0:
                raise ValueError(f"priceX18 {priceX18} не кратен шагу {price_step_x18}")
            
            # Размещаем триггерный ордер
            # Для SL (ПРОТИВОПОЛОЖНО TP!):
            # - LONG позиция → закрываем продажей → триггер "last_price_below"
            # - SHORT позиция → закрываем покупкой → триггер "last_price_above"
            from nado_protocol.utils.expiration import OrderType
            
            # Определяем тип триггера для SL
            if is_long:
                # LONG: закрываем продажей ниже текущей цены (stop loss)
                trigger_type = "last_price_below"
            else:
                # SHORT: закрываем покупкой выше текущей цены (stop loss)
                trigger_type = "last_price_above"
            
            print(f"   Placing trigger order: amount_x18={amount_x18}, priceX18={priceX18}, trigger={trigger_type}")
            result = self.client.market.place_price_trigger_order(
                product_id=product_id,
                price_x18=str(priceX18),
                amount_x18=str(amount_x18),
                trigger_price_x18=str(priceX18),
                trigger_type=trigger_type,
                reduce_only=True,
                order_type=OrderType.POST_ONLY
            )
            
            print(f"   Result status: {result.status.value}")
            if result.status.value == "success":
                print(f"   ✅ SL order placed successfully!")
                return result
            else:
                print(f"   ❌ Error: {result.error}")
                return None
                
        except Exception as e:
            print(f"   ❌ Ошибка размещения SL ордера: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def place_limit_close_order(self, product_id, size, is_long, target_price):
        """Разместить лимитный ордер на закрытие позиции"""
        try:
            from nado_protocol.engine_client.types.execute import PlaceOrderParams
            from nado_protocol.utils.execute import OrderParams
            from nado_protocol.utils.order import build_appendix, OrderType
            import time
            
            size = Decimal(size)
            size = self.normalize_size(product_id, size)
            
            # Размер позиции (без плеча для закрытия)
            amount_x18 = int((size * Decimal(10) ** 18).to_integral_value())
            
            # Для закрытия LONG нужен SHORT ордер (отрицательный amount)
            # Для закрытия SHORT нужен LONG ордер (положительный amount)
            if is_long:
                amount_x18 = -amount_x18  # Продаем для закрытия LONG
            # else: amount_x18 остается положительным для закрытия SHORT
            
            step_x18 = int(SIZE_INCREMENTS[product_id] * Decimal(10) ** 18)
            if amount_x18 % step_x18 != 0:
                raise ValueError(f"amount_x18 {amount_x18} не кратен шагу {step_x18}")
            
            target_price_decimal = Decimal(str(target_price))
            
            # Создаем лимитный ордер с reduce_only
            appendix = build_appendix(
                order_type=OrderType.POST_ONLY,  # Лимитный
                isolated=False,
                reduce_only=True  # ВАЖНО: только для закрытия позиции
            )
            
            # Рассчитываем price_x18
            price_x18_raw = int((target_price_decimal * Decimal(10**18)).to_integral_value())
            price_increment = PRICE_INCREMENTS_X18[product_id]
            price_x18 = (price_x18_raw // price_increment) * price_increment
            
            # Expiration: 7 дней (take-profit может висеть долго)
            expiration = int(time.time()) + (7 * 24 * 60 * 60)
            
            # Создаем OrderParams
            order = OrderParams(
                sender=self.sender_hex,
                amount=amount_x18,
                priceX18=price_x18,
                expiration=expiration,
                appendix=appendix
            )
            
            # Создаем PlaceOrderParams
            params = PlaceOrderParams(
                product_id=product_id,
                order=order
            )
            
            # Размещаем ордер
            result = self.client.market.place_order(params)
            
            return result
            
        except Exception as e:
            print(f"❌ Ошибка размещения лимитного ордера на закрытие: {e}")
            import traceback
            traceback.print_exc()
            return None
        """Рассчитать P&L для позиции"""
        if product_id not in self.entry_prices:
            return None
        
        entry_data = self.entry_prices[product_id]
        entry_price = Decimal(str(entry_data['entry_price']))
        current_price = Decimal(str(current_price))
        amount = Decimal(str(amount))
        
        if amount > 0:  # LONG
            pnl = (current_price - entry_price) * amount
        else:  # SHORT
            pnl = (entry_price - current_price) * abs(amount)
        
        return float(pnl)	

    def __init__(self, user_subaccount_id=None):
        network = config.get_network()
        mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
        
        self.network = network
        self.client = create_nado_client(mode=mode, signer=config.get_nado_key())
        self.bot_wallet = self.client.context.signer.address
        
        # Если передан user_subaccount_id - используем его
        # Иначе используем subaccount бота (по умолчанию)
        if user_subaccount_id:
            self.sender_hex = user_subaccount_id
            # Извлекаем адрес владельца из subaccount_id (первые 40 символов после 0x)
            self.wallet = '0x' + user_subaccount_id[2:42]
            print(f"📋 Using subaccount: {self.wallet[:10]}...{self.wallet[-8:]}")
            print(f"📋 Full subaccount ID: {user_subaccount_id}")
        else:
            # Используем subaccount бота по умолчанию
            self.wallet = self.bot_wallet
            params = SubaccountParams(
                subaccount_owner=self.wallet,
                subaccount_name="default"
            )
            self.sender_hex = subaccount_to_hex(params)
            print(f"📋 Using bot's own subaccount: {self.sender_hex}")
        
        # Настройки
        self.leverage = Decimal("10")  # Плечо по умолчанию 10x
        self.margin_mode = "AUTO"  # Автоматическое управление маржой биржей
        
        # Хранилище для entry prices
        self.positions_file = os.path.join(os.path.dirname(__file__), "positions_data.json")
        self.entry_prices = self.load_positions_data()
        
        # История торговли
        self.history_file = os.path.join(os.path.dirname(__file__), "trade_history.json")
        self.trade_history = self.load_trade_history()
    
    def get_balance(self):
        """Получить баланс аккаунта"""
        try:
            summary = self.client.subaccount.get_engine_subaccount_summary(self.sender_hex)
            
            if hasattr(summary, 'healths') and summary.healths and len(summary.healths) > 0:
                health = summary.healths[0]
                return {
                    "assets": float(health.assets) / 1e18,
                    "liabilities": float(health.liabilities) / 1e18,
                    "equity": (float(health.assets) - float(health.liabilities)) / 1e18,
                    "health": float(health.health) / 1e18
                }
        except Exception as e:
            print(f"Ошибка получения баланса: {e}")
        
        return None
    
    def get_positions(self):
        """Получить открытые позиции"""
        try:
            summary = self.client.subaccount.get_engine_subaccount_summary(self.sender_hex)
            positions = []
            
            if hasattr(summary, 'perp_balances') and summary.perp_balances:
                for balance in summary.perp_balances:
                    product_id = balance.product_id
                    amount = float(balance.balance.amount) / 1e18
                    
                    if abs(amount) < 0.0001:
                        continue
                    
                    symbol = PRODUCTS.get(product_id, f"UNKNOWN-{product_id}")
                    
                    # Получаем цену
                    price = self.get_market_price(product_id)
                    
                    positions.append({
                        "product_id": product_id,
                        "symbol": symbol,
                        "amount": amount,
                        "side": "LONG" if amount > 0 else "SHORT",
                        "price": price,
                        "notional": price * abs(amount) if price else None
                    })
            
            return positions
        except Exception as e:
            print(f"Ошибка получения позиций: {e}")
            return []
    
    def get_open_orders(self):
        """Получить открытые ордера"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Используем правильный метод API для всех продуктов
            product_ids = list(PRODUCTS.keys())
            
            logger.info(f"🔍 Запрос открытых ордеров для продуктов: {product_ids}")
            
            orders_response = self.client.market.get_subaccount_multi_products_open_orders(
                product_ids=product_ids,
                sender=self.sender_hex
            )
            
            open_orders = []
            
            # API возвращает product_orders, а не orders напрямую!
            if hasattr(orders_response, 'product_orders'):
                logger.info(f"🔍 Найдено product_orders: {len(orders_response.product_orders)}")
                
                for product_data in orders_response.product_orders:
                    if hasattr(product_data, 'orders') and product_data.orders:
                        logger.info(f"🔍 Продукт {product_data.product_id}: {len(product_data.orders)} ордеров")
                        
                        for order in product_data.orders:
                            product_id = product_data.product_id
                            amount = float(order.amount) / 1e18 if hasattr(order, 'amount') else 0
                            price = float(order.price_x18) / 1e18 if hasattr(order, 'price_x18') else None
                            
                            open_orders.append({
                                'product_id': product_id,
                                'symbol': PRODUCTS.get(product_id, f'UNKNOWN-{product_id}'),
                                'amount': amount,
                                'side': 'LONG' if amount > 0 else 'SHORT',
                                'price': price,
                                'order_id': order.digest if hasattr(order, 'digest') else None
                            })
            
            logger.info(f"✅ Возвращаем {len(open_orders)} ордеров")
            return open_orders
        except Exception as e:
            logger.error(f"❌ Ошибка получения ордеров: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_market_price(self, product_id):
        """Получить рыночную цену"""
        try:
            price_data = self.client.market.get_latest_market_price(product_id)
            
            # Проверяем что получили данные
            if not price_data:
                return None
                
            if isinstance(price_data, dict) and "bid_x18" in price_data and "ask_x18" in price_data:
                bid = Decimal(str(price_data["bid_x18"])) / Decimal(10**18)
                ask = Decimal(str(price_data["ask_x18"])) / Decimal(10**18)
                mid_price = float((bid + ask) / Decimal("2"))
                return mid_price
            else:
                # Попробуем альтернативный формат
                if hasattr(price_data, 'bid_x18') and hasattr(price_data, 'ask_x18'):
                    bid = Decimal(str(price_data.bid_x18)) / Decimal(10**18)
                    ask = Decimal(str(price_data.ask_x18)) / Decimal(10**18)
                    mid_price = float((bid + ask) / Decimal("2"))
                    return mid_price
                    
        except Exception as e:
            print(f"⚠️ Ошибка получения цены для product_id={product_id}: {e}")
            
        return None
    
    def place_order(self, product_id, size, is_long, custom_price=None, auto_tp=True, ttl_seconds=60):
        """Открыть позицию с Isolated Margin
        
        Args:
            product_id: ID продукта
            size: Базовый размер (без плеча)
            is_long: True для LONG, False для SHORT
            custom_price: Кастомная цена (для лимитных ордеров)
            auto_tp: Автоматически размещать TP ордер (по умолчанию True)
            ttl_seconds: Time-To-Live для ордера в секундах (по умолчанию 60)
        """
        try:
            from nado_protocol.engine_client.types.execute import PlaceOrderParams
            from nado_protocol.utils.execute import OrderParams
            from nado_protocol.utils.order import build_appendix, OrderType
            import time
            
            size = Decimal(size)
            size = self.normalize_size(product_id, size)
            
            # Размер С ПЛЕЧОМ для amount_x18
            size_with_leverage = size * self.leverage
            size_with_leverage = self.normalize_size(product_id, size_with_leverage)

            amount_x18 = int(
                (size_with_leverage * Decimal(10) ** 18).to_integral_value()
            )

            if not is_long:
                amount_x18 = -amount_x18

            step_x18 = int(SIZE_INCREMENTS[product_id] * Decimal(10) ** 18)
            if amount_x18 % step_x18 != 0:
                raise ValueError(
                    f"amount_x18 {amount_x18} не кратен шагу {step_x18}"
                )
            
            # Получаем цену (либо custom, либо рыночную)
            if custom_price is not None:
                price = custom_price
            else:
                price = self.get_market_price(product_id)
                if not price:
                    raise ValueError("Не удалось получить рыночную цену")
            
            price_decimal = Decimal(str(price))
            
            # Размер позиции С ПЛЕЧОМ
            size_with_leverage = size * self.leverage
            
            # Notional с плечом
            notional = abs(size_with_leverage) * price_decimal
            
            # Создаем обычный лимитный ордер (может исполниться сразу)
            appendix = build_appendix(
                order_type=OrderType.DEFAULT,  # Обычный лимитный ордер
                isolated=False,
                reduce_only=False
            )
            
            print(f"\n📊 Параметры ордера:")
            print(f"   Базовый размер: {size} {PRODUCTS[product_id].split('-')[0]}")
            print(f"   Плечо: {self.leverage}x")
            print(f"   Размер позиции: {size_with_leverage} {PRODUCTS[product_id].split('-')[0]}")
            print(f"   Цена лимита: ${price:,.2f}")
            print(f"   Notional: ${notional:,.2f}")
            
            # Расчет комиссий
            fee_rate = Decimal("0.0001")  # 0.01% (maker fee)
            open_fee = notional * fee_rate
            close_fee = notional * fee_rate
            total_fee = open_fee + close_fee
            
            print(f"\n💰 Комиссии:")
            print(f"   Открытие (0.01%): ${open_fee:,.4f}")
            print(f"   Закрытие (0.01%): ${close_fee:,.4f}")
            print(f"   Всего комиссий: ${total_fee:,.4f}")
            print(f"   Минимальный профит для безубытка: +0.03%")
            
            print(f"\n   Тип: Лимитный ордер (немедленное исполнение)")
            
            # Используем текущую рыночную цену как лимит
            price_with_adjustment = price_decimal
            
            price_x18_raw = int((price_with_adjustment * Decimal(10**18)).to_integral_value())
            
            # Округляем до кратного price_increment_x18
            price_increment = PRICE_INCREMENTS_X18[product_id]
            price_x18 = (price_x18_raw // price_increment) * price_increment
            
            # Expiration: используем переданный TTL
            expiration = int(time.time()) + ttl_seconds
            
            # Создаем OrderParams (с appendix)
            order = OrderParams(
                sender=self.sender_hex,
                amount=amount_x18,
                priceX18=price_x18,
                expiration=expiration,
                appendix=appendix
            )
            
            # Создаем PlaceOrderParams
            params = PlaceOrderParams(
                product_id=product_id,
                order=order
            )
            
            # Размещаем ордер
            result = self.client.market.place_order(params)
            
            if result and hasattr(result, 'status'):
                print(f"\n✅ Лимитный ордер размещен: {result.status}")
                
                # Вычисляем TP от entry price
                entry_price_decimal = Decimal(str(price))
                min_profit_percent = Decimal("0.0003")
                
                if is_long:
                    tp_price_calc = entry_price_decimal * (Decimal("1") + min_profit_percent)
                else:
                    tp_price_calc = entry_price_decimal * (Decimal("1") - min_profit_percent)
                
                # Сохраняем entry price с TP
                self.save_entry_price(product_id, price, size_with_leverage, tp_price=float(tp_price_calc))
                print(f"   Entry price saved: ${price:,.2f}")
                print(f"   TP price: ${float(tp_price_calc):,.2f}")
                
            return result
            
        except Exception as e:
            print(f"❌ Ошибка размещения ордера: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def close_position(self, product_id, amount=None):
        """Закрыть позицию лимитным ордером"""
        try:
            # Получаем текущую позицию
            positions = self.get_positions()
            current_pos = next((p for p in positions if p['product_id'] == product_id), None)
            
            if not current_pos:
                print(f"   ❌ Позиция не найдена")
                return None
            
            # Определяем направление и размер
            is_long = current_pos['amount'] > 0
            position_size = abs(current_pos['amount'])
            current_price = current_pos['price']
            
            if not current_price:
                print(f"   ❌ Не удалось получить текущую цену")
                return None
            
            print(f"   Закрытие позиции лимитным ордером...")
            print(f"   Текущая цена: ${current_price:,.2f}")
            
            # Размещаем лимитный ордер на закрытие по текущей цене
            result = self.place_limit_close_order(
                product_id=product_id,
                size=position_size,
                is_long=is_long,
                target_price=current_price
            )
            
            if result and hasattr(result, 'status'):
                print(f"   Статус: {result.status}")
                print(f"   ✅ Лимитный ордер на закрытие размещен")
                
                # Даем время на исполнение
                import time
                print(f"   ⏳ Ожидание исполнения ордера...")
                time.sleep(5)
                
                # Проверяем закрылась ли позиция
                print(f"   🔍 Проверка статуса позиции...")
                positions = self.get_positions()
                position_exists = any(p['product_id'] == product_id for p in positions)
                
                if not position_exists:
                    # Рассчитываем realized P&L
                    pnl_value = None
                    if current_pos and current_price:
                        pnl_value = self.calculate_pnl(product_id, current_price, current_pos['amount'])
                        if pnl_value is not None:
                            pnl_emoji = "🟢" if pnl_value >= 0 else "🔴"
                            print(f"\n   {pnl_emoji} REALIZED P&L: ${pnl_value:+,.2f}")
                            
                            # Сохраняем в историю
                            if product_id in self.entry_prices:
                                entry_data = self.entry_prices[product_id]
                                self.add_trade_to_history(
                                    product_id=product_id,
                                    symbol=current_pos['symbol'],
                                    side=current_pos['side'],
                                    size=abs(current_pos['amount']),
                                    entry_price=entry_data['entry_price'],
                                    exit_price=current_price,
                                    pnl=pnl_value
                                )
                    
                    print(f"   ✅ Позиция успешно закрыта!")
                    
                    # Удаляем entry price
                    self.remove_entry_price(product_id)
                    return result
                else:
                    print(f"   ⏳ Ордер размещен, ожидает исполнения")
                    print(f"   Позиция закроется когда цена достигнет ${current_price:,.2f}")
                    return result
            else:
                print(f"   ❌ Ошибка размещения ордера")
                return None
            
        except Exception as e:
            print(f"   ❌ Ошибка закрытия позиции: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def cancel_order(self, product_id, order_digest):
        """Отменить ордер"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            from nado_protocol.engine_client.types.execute import CancelOrdersParams
            
            # Создаем параметры для отмены
            params = CancelOrdersParams(
                sender=self.sender_hex,
                product_id=product_id,
                digests=[order_digest]
            )
            
            # Отменяем ордер
            result = self.client.market.cancel_orders(params)
            
            # Проверяем результат
            if result and hasattr(result, 'status'):
                logger.info(f"✅ Ордер отменён успешно: {order_digest[:8]}... (status: {result.status})")
                return result
            else:
                logger.error(f"❌ Неудачная отмена ордера: {order_digest[:8]}... (result: {result})")
                return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка отмены ордера: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def display_trade_history(self):
        """Показать историю торговли"""
        print("\n" + "="*80)
        print("📜 ИСТОРИЯ ТОРГОВЛИ")
        print("="*80)
        
        if not self.trade_history:
            print("\n   ℹ️  История торговли пуста")
            input("\nНажмите Enter для продолжения...")
            return
        
        # Статистика
        total_trades = len(self.trade_history)
        winning_trades = sum(1 for t in self.trade_history if t['pnl'] > 0)
        losing_trades = sum(1 for t in self.trade_history if t['pnl'] < 0)
        total_pnl = sum(t['pnl'] for t in self.trade_history)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        print(f"\n📊 Статистика:")
        print(f"   Всего сделок: {total_trades}")
        print(f"   🟢 Прибыльных: {winning_trades}")
        print(f"   🔴 Убыточных: {losing_trades}")
        print(f"   Винрейт: {win_rate:.1f}%")
        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
        print(f"   {pnl_emoji} Общий P&L: ${total_pnl:+,.2f}")
        
        print(f"\n{'─'*80}")
        print("\nПоследние 20 сделок (от новых к старым):")
        print(f"{'─'*80}\n")
        
        # Показываем последние 20
        for trade in reversed(self.trade_history[-20:]):
            pnl_emoji = "🟢" if trade['pnl'] >= 0 else "🔴"
            side_emoji = "🟢" if trade['side'] == "LONG" else "🔴"
            
            print(f"   {trade['timestamp']} | {side_emoji} {trade['symbol']:<12}")
            print(f"      Size: {trade['size']:.4f} | Entry: ${trade['entry_price']:,.2f} | Exit: ${trade['exit_price']:,.2f}")
            print(f"      {pnl_emoji} P&L: ${trade['pnl']:+,.2f} ({trade['pnl_percent']:+.2f}%)")
            print()
        
        if len(self.trade_history) > 20:
            print(f"   ... и еще {len(self.trade_history) - 20} сделок\n")
        
        input("\nНажмите Enter для продолжения...")
        """Настройка плеча"""
        print("\n" + "="*80)
        print("⚙️  НАСТРОЙКА ПЛЕЧА")
        print("="*80)
        
        print(f"\n📊 Текущие настройки:")
        print(f"   Режим маржи: {self.margin_mode}")
        print(f"   Текущее плечо: {self.leverage}x")
        
        print(f"\n💡 Isolated Margin означает:")
        print(f"   • Каждая позиция имеет свою выделенную маржу")
        print(f"   • Максимальный убыток ограничен этой маржой")
        print(f"   • Ликвидация одной позиции не влияет на другие")
        
        print(f"\n⚠️  Риски высокого плеча:")
        print(f"   • 10x: умеренный риск, движение цены 10% = 100% P&L")
        print(f"   • 20x: высокий риск, движение цены 5% = 100% P&L")
        print(f"   • 50x: очень высокий риск, движение цены 2% = 100% P&L")
        
        try:
            new_leverage_str = input(f"\nВведите новое плечо (1-100x) или Enter для отмены: ")
            
            if not new_leverage_str.strip():
                print("❌ Отменено")
                time.sleep(1)
                return
            
            new_leverage = Decimal(new_leverage_str)
            
            if new_leverage < 1 or new_leverage > 100:
                print("❌ Плечо должно быть от 1x до 100x")
                time.sleep(2)
                return
            
            # Подтверждение
            print(f"\n⚠️  Подтверждение:")
            print(f"   Старое плечо: {self.leverage}x")
            print(f"   Новое плечо: {new_leverage}x")
            
            if new_leverage >= 20:
                print(f"\n🚨 ВНИМАНИЕ: Высокое плечо = высокий риск!")
                print(f"   При плече {new_leverage}x движение цены на {100/float(new_leverage):.2f}% против вас")
                print(f"   приведет к полной потере маржи позиции!")
            
            confirm = input(f"\nИзменить плечо? (yes/no): ")
            if confirm.lower() not in ('yes', 'y', 'да'):
                print("❌ Отменено")
                time.sleep(1)
                return
            
            old_leverage = self.leverage
            self.leverage = new_leverage
            
            print(f"\n✅ Плечо изменено: {old_leverage}x → {new_leverage}x")
            print(f"   Новые позиции будут открываться с плечом {new_leverage}x")
            
        except ValueError:
            print("❌ Неверный формат числа")
        except Exception as e:
            print(f"❌ Ошибка: {e}")
        
        input("\nНажмите Enter для продолжения...")
    
    def display_header(self):
        """Отобразить заголовок"""
        print("\n" + "="*80)
        print(" "*25 + "NADO DEX TRADING DASHBOARD")
        print("="*80)
        print(f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🌐 Сеть: {self.network.upper()}")
        print(f"👛 Кошелек: {self.wallet[:10]}...{self.wallet[-8:]}")
        print(f"⚙️  Маржа: {self.margin_mode} | Плечо: {self.leverage}x")
        print("="*80)
    
    def display_balance(self):
        """Отобразить баланс"""
        print("\n💰 БАЛАНС АККАУНТА:")
        print("-"*80)
        balance = self.get_balance()
        if balance:
            print(f"   Активы:        ${balance['assets']:>15,.2f}")
            print(f"   Обязательства: ${balance['liabilities']:>15,.2f}")
            print(f"   Equity:        ${balance['equity']:>15,.2f}")
            print(f"   Health:        {balance['health']:>16,.2f}")
        else:
            print("   ⚠️  Не удалось загрузить баланс")
    
    def display_positions(self):
        """Отобразить позиции"""
        print("\n📊 ОТКРЫТЫЕ ПОЗИЦИИ:")
        print("-"*80)
        positions = self.get_positions()
        
        if not positions:
            print("   ✅ Нет открытых позиций")
            return []
        
        total_notional = 0
        total_pnl = 0
        
        for i, pos in enumerate(positions, 1):
            side_emoji = "🟢" if pos["side"] == "LONG" else "🔴"
            price_str = f"${pos['price']:,.2f}" if pos['price'] else "???"
            notional_str = f"${pos['notional']:,.2f}" if pos['notional'] else "???"
            
            # Рассчитываем P&L
            pnl = None
            pnl_str = ""
            if pos['price']:
                pnl = self.calculate_pnl(pos['product_id'], pos['price'], pos['amount'])
                if pnl is not None:
                    pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                    pnl_percent = (pnl / pos['notional'] * 100) if pos['notional'] else 0
                    pnl_str = f" | P&L: {pnl_emoji} ${pnl:+,.2f} ({pnl_percent:+.2f}%)"
                    total_pnl += pnl
            
            print(f"\n   [{i}] {side_emoji} {pos['symbol']:<12} | Size: {abs(pos['amount']):<10.4f} | Price: {price_str:<12} | Value: {notional_str}{pnl_str}")
            
            if pos['notional']:
                total_notional += pos['notional']
        
        print(f"\n   {'─'*76}")
        print(f"   Общая стоимость позиций: ${total_notional:,.2f}")
        if total_pnl != 0:
            pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
            print(f"   {pnl_emoji} Общий нереализованный P&L: ${total_pnl:+,.2f}")
        
        return positions
    
    def display_prices(self):
        """Отобразить текущие цены"""
        print("\n📈 ТЕКУЩИЕ ЦЕНЫ:")
        print("-"*80)
        
        for product_id, symbol in PRODUCTS.items():
            price = self.get_market_price(product_id)
            if price:
                print(f"   {symbol:<12} ${price:>12,.2f}")
            else:
                print(f"   {symbol:<12} {'N/A':>12}")
    
    def main_menu(self):
        """Главное меню"""
        while True:
            try:
                self.display_header()
                self.display_balance()
                positions = self.display_positions()
                self.display_prices()
                
                print("\n" + "="*80)
                print("МЕНЮ:")
                print("="*80)
                print(f"  Режим: {self.margin_mode} | Плечо: {self.leverage}x")
                print("="*80)
                print("  1. 🟢 Открыть LONG (лимитный ордер)")
                print("  2. 🔴 Открыть SHORT (лимитный ордер)")
                print("  3. ❌ Закрыть позицию")
                print("  4. ⚙️  Настроить плечо")
                print("  5. 🔄 Обновить данные")
                print("  6. 📊 Показать только цены")
                print("  7. 📜 История торговли")
                print("  8. 📈📉 Grid стратегия (2 ордера)")
                print("  0. 🚪 Выход")
                print("="*80)
                
                choice = input("\nВыберите действие: ")
                
                if choice == "1" or choice == "2":
                    self.open_position_flow(is_long=(choice == "1"))
                
                elif choice == "3":
                    self.close_position_flow(positions)
                
                elif choice == "4":
                    self.adjust_leverage_flow()
                
                elif choice == "5":
                    continue  # Просто обновляем данные
                
                elif choice == "6":
                    # Показываем только цены без остального
                    print("\n" + "="*80)
                    self.display_prices()
                    input("\nНажмите Enter для продолжения...")
                
                elif choice == "7":
                    self.display_trade_history()
                
                elif choice == "8":
                    self.grid_strategy_flow()
                
                elif choice == "0":
                    print("\n👋 Выход из dashboard")
                    break
                
                else:
                    print("\n❌ Неверный выбор")
                    time.sleep(1)
            
            except KeyboardInterrupt:
                print("\n\n❌ Прервано пользователем")
                break
            except Exception as e:
                print(f"\n❌ Ошибка: {e}")
                import traceback
                traceback.print_exc()
                input("\nНажмите Enter для продолжения...")
    
    def open_position_flow(self, is_long):
        """Процесс открытия позиции"""
        print("\n" + "="*80)
        print(f"{'🟢 ЛИМИТНЫЙ ОРДЕР LONG' if is_long else '🔴 ЛИМИТНЫЙ ОРДЕР SHORT'}")
        print("="*80)
        print("\n💡 При открытии позиции автоматически разместится take-profit ордер")
        print("   на закрытие с минимальной прибылью 0.03% для покрытия комиссий (0.02%).\n")
        
        # Выбор пары
        print("\nДоступные пары:")
        for i, (product_id, symbol) in enumerate(PRODUCTS.items(), 1):
            price = self.get_market_price(product_id)
            price_str = f"${price:,.2f}" if price else "???"
            print(f"  {i}. {symbol:<12} - {price_str}")
        
        try:
            choice = int(input("\nВыберите пару (1-4): "))
            product_id = list(PRODUCTS.keys())[choice - 1]
            symbol = PRODUCTS[product_id]
        except:
            print("❌ Неверный выбор")
            time.sleep(1)
            return
        
        # Ввод размера
        asset = symbol.split("-")[0]
        size_str = input(f"\nРазмер в {asset}: ")
        
        from decimal import Decimal, ROUND_DOWN

        try:
            size = Decimal(size_str)
            if size <= 0:
                raise ValueError
        except:
            print("❌ Неверный формат")
            time.sleep(1)
            return

        size = self.normalize_size(product_id, size)

        if size <= 0:
            print("❌ Размер меньше минимального шага")
            time.sleep(1)
            return
        
        # Получаем текущую цену
        price = self.get_market_price(product_id)
        
        # Подтверждение
        print(f"\n⚠️  Подтверждение:")
        print(f"   Пара: {symbol}")
        print(f"   Направление: {'LONG' if is_long else 'SHORT'}")
        print(f"   Базовый размер: {size} {asset}")
        print(f"   Плечо: {self.leverage}x")
        size_with_lev = size * self.leverage
        print(f"   Размер с плечом: {size_with_lev} {asset}")
        if price:
            price_d = Decimal(str(price))
            margin = price_d * size
            notional = price_d * size_with_lev
            print(f"   Маржа: ${margin:,.2f}")
            print(f"   Notional: ${notional:,.2f}")
        
        confirm = input("\nРазместить лимитный ордер? (yes/no): ")
        if confirm.lower() not in ('yes', 'y', 'да'):
            print("❌ Отменено")
            time.sleep(1)
            return
        
        # Открываем позицию
        print("\n🔄 Размещение лимитного ордера...")
        result = self.place_order(product_id, size, is_long)
        
        if result:
            print("\n✅ Лимитный ордер успешно размещен!")
            print(f"Результат: {result}")
        else:
            print("\n❌ Ошибка размещения лимитного ордера")
        
        input("\nНажмите Enter для продолжения...")
    
    def close_position_flow(self, positions):
        """Процесс закрытия позиции"""
        if not positions:
            print("\n⚠️  Нет открытых позиций для закрытия")
            time.sleep(1)
            return
        
        print("\n" + "="*80)
        print("❌ ЗАКРЫТИЕ ПОЗИЦИИ")
        print("="*80)
        
        print("\nВыберите позицию для закрытия:")
        for i, pos in enumerate(positions, 1):
            side_emoji = "🟢" if pos["side"] == "LONG" else "🔴"
            print(f"  {i}. {side_emoji} {pos['symbol']:<12} | Size: {abs(pos['amount']):.4f}")
        
        print(f"  0. Закрыть ВСЕ позиции")
        
        try:
            choice = int(input("\nВыбор: "))
            
            if choice == 0:
                # Закрыть все
                confirm = input(f"\n⚠️  Закрыть ВСЕ {len(positions)} позиции? (yes/no): ")
                if confirm.lower() not in ('yes', 'y', 'да'):
                    print("❌ Отменено")
                    time.sleep(1)
                    return
                
                print("\n🔄 Закрытие всех позиций...")
                success = 0
                failed = 0
                
                for i, pos in enumerate(positions, 1):
                    print(f"\n[{i}/{len(positions)}] Закрытие {pos['symbol']}...")
                    result = self.close_position(pos['product_id'])
                    if result:
                        success += 1
                    else:
                        failed += 1
                
                print(f"\n{'='*80}")
                print(f"Завершено: успешно={success}, ошибок={failed}")
                print(f"{'='*80}")
            
            else:
                # Закрыть выбранную
                pos = positions[choice - 1]
                
                confirm = input(f"\n⚠️  Закрыть {pos['symbol']} ({pos['side']}, {abs(pos['amount']):.4f})? (yes/no): ")
                if confirm.lower() not in ('yes', 'y', 'да'):
                    print("❌ Отменено")
                    time.sleep(1)
                    return
                
                print("\n🔄 Закрытие позиции...")
                print(f"📊 {pos['symbol']} ({pos['side']}, размер: {abs(pos['amount']):.4f})")
                result = self.close_position(pos['product_id'])
                
                if result:
                    print("\n✅ Позиция успешно закрыта!")
                    print(f"Результат: {result}")
                else:
                    print("\n❌ Ошибка закрытия позиции")
        
        except (ValueError, IndexError):
            print("❌ Неверный выбор")
        
        input("\nНажмите Enter для продолжения...")
    
    def grid_strategy_flow(self):
        """Стратегия: 2 ордера (LONG ниже, SHORT выше)"""
        print("\n" + "="*80)
        print("📈📉 GRID СТРАТЕГИЯ")
        print("="*80)
        print("\n💡 Размещаются 2 лимитных ордера:")
        print("   • LONG ниже текущей цены (покупка на падении)")
        print("   • SHORT выше текущей цены (продажа на росте)")
        print("   • При исполнении одного - автоматический TP на втором")
        
        # Выбор пары
        print("\n" + "="*80)
        print("\nДоступные пары:")
        for i, (product_id, symbol) in enumerate(PRODUCTS.items(), 1):
            price = self.get_market_price(product_id)
            price_str = f"${price:,.2f}" if price else "???"
            print(f"  {i}. {symbol:<12} - {price_str}")
        
        try:
            choice = int(input("\nВыберите пару (1-4): "))
            product_id = list(PRODUCTS.keys())[choice - 1]
            symbol = PRODUCTS[product_id]
        except:
            print("❌ Неверный выбор")
            time.sleep(1)
            return
        
        # Получаем текущую цену
        price = self.get_market_price(product_id)
        if not price:
            print("❌ Не удалось получить цену")
            time.sleep(1)
            return
        
        price_decimal = Decimal(str(price))
        asset = symbol.split("-")[0]
        
        print(f"\n💰 Текущая цена {symbol}: ${price:,.2f}")
        
        # Ввод параметров
        size_str = input(f"\nБазовый размер в {asset}: ")
        try:
            size = Decimal(size_str)
            if size <= 0:
                raise ValueError
        except:
            print("❌ Неверный формат")
            time.sleep(1)
            return
        
        size = self.normalize_size(product_id, size)
        if size <= 0:
            print("❌ Размер меньше минимального шага")
            time.sleep(1)
            return
        
        # Процент отклонения
        offset_str = input(f"\nПроцент отклонения (например, 0.5 для ±0.5%): ")
        try:
            offset_percent = Decimal(offset_str) / 100
            if offset_percent <= 0 or offset_percent > 5:
                print("❌ Процент должен быть от 0 до 5%")
                time.sleep(1)
                return
        except:
            print("❌ Неверный формат")
            time.sleep(1)
            return
        
        # Рассчитываем цены
        long_price = price_decimal * (Decimal("1") - offset_percent)
        short_price = price_decimal * (Decimal("1") + offset_percent)
        
        size_with_leverage = size * self.leverage
        
        # Подтверждение
        print(f"\n⚠️  Подтверждение GRID стратегии:")
        print(f"   Пара: {symbol}")
        print(f"   Текущая цена: ${price:,.2f}")
        print(f"   Базовый размер: {size} {asset}")
        print(f"   Плечо: {self.leverage}x")
        print(f"   Размер позиции: {size_with_leverage} {asset}")
        print(f"\n   🟢 LONG ордер: ${long_price:,.2f} ({-offset_percent*100:.2f}%)")
        print(f"   🔴 SHORT ордер: ${short_price:,.2f} (+{offset_percent*100:.2f}%)")
        
        confirm = input(f"\nРазместить оба ордера? (yes/no): ")
        if confirm.lower() not in ('yes', 'y', 'да'):
            print("❌ Отменено")
            time.sleep(1)
            return
        
        print("\n🔄 Размещение ордеров...")
        
        # Размещаем LONG ордер
        print(f"\n1️⃣ Размещение LONG ордера...")
        long_result = self.place_order(product_id, size, is_long=True, custom_price=float(long_price))
        
        if not long_result:
            print("❌ Ошибка размещения LONG ордера")
            input("\nНажмите Enter для продолжения...")
            return
        
        # Размещаем SHORT ордер
        print(f"\n2️⃣ Размещение SHORT ордера...")
        short_result = self.place_order(product_id, size, is_long=False, custom_price=float(short_price))
        
        if not short_result:
            print("⚠️  LONG ордер размещен, но SHORT ордер не удалось разместить")
            input("\nНажмите Enter для продолжения...")
            return
        
        print(f"\n✅ Grid стратегия активирована!")
        print(f"\n📊 Размещено 2 ордера:")
        print(f"   🟢 LONG: {size_with_leverage} {asset} @ ${long_price:,.2f}")
        print(f"   🔴 SHORT: {size_with_leverage} {asset} @ ${short_price:,.2f}")
        print(f"\n💡 Когда один из ордеров исполнится, откроется позиция с автоматическим TP")
        
        input("\nНажмите Enter для продолжения...")

def main():
    try:
        dashboard = TradingDashboard()
        dashboard.main_menu()
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
