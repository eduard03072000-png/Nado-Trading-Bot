"""
NADO DEX Trading - ТЕСТ ПРАВИЛЬНОЙ АРХИТЕКТУРЫ
"""
import sys
import os

if os.name == 'nt':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

# Добавляем путь к модулям
sys.path.insert(0, r'C:\Project\Trading_bot')

from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.engine_client.types.execute import PlaceOrderParams
from nado_protocol.utils.execute import OrderParams
from nado_protocol.utils.order import build_appendix, OrderType
from decimal import Decimal
import config
import time

def test_order():
    """Тестируем размещение ордера"""
    
    # 1. Создаём клиента (бот использует свой ключ)
    mode = NadoClientMode.MAINNET
    client = create_nado_client(mode=mode, signer=config.get_nado_key())
    
    bot_address = client.context.signer.address
    print(f"🤖 Bot address: {bot_address}")
    
    # 2. Получаем subaccount ID пользователя
    user_subaccount = config.get_subaccount_id()
    if not user_subaccount:
        print("❌ NADO_SUBACCOUNT_ID не найден в .env!")
        return False
    
    print(f"📋 User subaccount: {user_subaccount}")
    
    # 3. Получаем цену SOL
    product_id = 8  # SOL-PERP
    price_data = client.market.get_latest_market_price(product_id)
    
    if not price_data or not hasattr(price_data, 'bid_x18'):
        print("❌ Не удалось получить цену")
        return False
    
    bid = Decimal(str(price_data.bid_x18)) / Decimal(10**18)
    ask = Decimal(str(price_data.ask_x18)) / Decimal(10**18)
    price = float((bid + ask) / 2)
    
    print(f"💰 SOL price: ${price:,.2f}")
    
    # 4. Готовим параметры ордера
    size = Decimal("0.5")
    leverage = Decimal("10")
    size_with_lev = size * leverage
    
    amount_x18 = int((size_with_lev * Decimal(10**18)).to_integral_value())
    
    # Округляем цену до кратного price_increment_x18
    price_increment_x18 = 10000000000000000  # 0.01 для SOL
    price_x18_raw = int((Decimal(str(price)) * Decimal(10**18)).to_integral_value())
    price_x18 = (price_x18_raw // price_increment_x18) * price_increment_x18
    
    appendix = build_appendix(
        order_type=OrderType.DEFAULT,
        isolated=False,
        reduce_only=False
    )
    
    expiration = int(time.time()) + 60
    
    # 5. КЛЮЧЕВОЕ: sender = user_subaccount (НЕ bot subaccount!)
    order = OrderParams(
        sender=user_subaccount,  # <<<--- ПОЛЬЗОВАТЕЛЬСКИЙ SUBACCOUNT!
        amount=amount_x18,
        priceX18=price_x18,
        expiration=expiration,
        appendix=appendix
    )
    
    params = PlaceOrderParams(
        product_id=product_id,
        order=order
    )
    
    print(f"\n🔄 Размещение ордера...")
    print(f"   Sender: {user_subaccount}")
    print(f"   Size: {size_with_lev} SOL")
    print(f"   Price: ${price:,.2f}")
    
    # 6. Размещаем!
    try:
        result = client.market.place_order(params)
        
        if result and hasattr(result, 'status'):
            print(f"\n✅ УСПЕХ! Status: {result.status}")
            return True
        else:
            print(f"\n❌ Ошибка: {result}")
            return False
    except Exception as e:
        print(f"\n❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("="*80)
    print("ТЕСТ: Размещение ордера на user subaccount")
    print("="*80)
    
    success = test_order()
    
    print("\n" + "="*80)
    if success:
        print("✅✅✅ РАБОТАЕТ! ✅✅✅")
    else:
        print("❌❌❌ НЕ РАБОТАЕТ ❌❌❌")
    print("="*80)
