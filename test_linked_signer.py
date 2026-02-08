"""
TEST: Bot uses BOT_PRIVATE_KEY as Linked Signer
"""
import sys
sys.path.insert(0, r'C:\Project\Trading_bot')

from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.engine_client.types.execute import PlaceOrderParams
from nado_protocol.utils.execute import OrderParams
from nado_protocol.utils.order import build_appendix, OrderType
from decimal import Decimal
import config
import time

# Создаём клиента с BOT_PRIVATE_KEY
mode = NadoClientMode.MAINNET
client = create_nado_client(mode=mode, signer=config.get_nado_key())

bot_address = client.context.signer.address
user_subaccount = config.get_subaccount_id()

print("="*80)
print("TEST: Bot as Linked Signer")
print("="*80)
print(f"Bot address: {bot_address}")
print(f"User subaccount: {user_subaccount}")
print()

# Получаем цену
product_id = 8  # SOL
price_data = client.market.get_latest_market_price(product_id)

bid = Decimal(str(price_data.bid_x18)) / Decimal(10**18)
ask = Decimal(str(price_data.ask_x18)) / Decimal(10**18)
price = float((bid + ask) / 2)

print(f"SOL price: ${price:,.2f}")
print()

# Готовим ордер
size = Decimal("0.5")
leverage = Decimal("10")
size_with_lev = size * leverage

amount_x18 = int((size_with_lev * Decimal(10**18)).to_integral_value())

price_increment_x18 = 10000000000000000
price_x18_raw = int((Decimal(str(price)) * Decimal(10**18)).to_integral_value())
price_x18 = (price_x18_raw // price_increment_x18) * price_increment_x18

appendix = build_appendix(
    order_type=OrderType.DEFAULT,
    isolated=False,
    reduce_only=False
)

expiration = int(time.time()) + 60

# ВАЖНО: sender = user_subaccount!
order = OrderParams(
    sender=user_subaccount,
    amount=amount_x18,
    priceX18=price_x18,
    expiration=expiration,
    appendix=appendix
)

params = PlaceOrderParams(
    product_id=product_id,
    order=order
)

print("Placing order...")
print(f"  Bot signing with: BOT_PRIVATE_KEY ({bot_address})")
print(f"  Trading on: {user_subaccount}")
print(f"  Size: {size_with_lev} SOL @ ${price:,.2f}")
print()

try:
    result = client.market.place_order(params)
    
    if result and hasattr(result, 'status'):
        print("="*80)
        print("SUCCESS!")
        print("="*80)
        print(f"Status: {result.status}")
        print()
        print("Bot is working with:")
        print("  - BOT_PRIVATE_KEY (Linked Signer)")
        print("  - Trading on user subaccount")
        print("  - NO access to NADO_PRIVATE_KEY needed!")
    else:
        print(f"FAILED: {result}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
