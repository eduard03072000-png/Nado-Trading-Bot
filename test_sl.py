"""
Test SL trigger order - проверяем что реально отправляется на биржу
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import config
from decimal import Decimal
from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.utils.expiration import OrderType

# Init
network = config.get_network()
mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
client = create_nado_client(mode=mode, signer=config.get_nado_key())

# User subaccount
sender_hex = "0x45e293d6f82b6f94f8657a15dab479dcbe034b3964656661756c740000000000"

print(f"Network: {network}")
print(f"Bot wallet: {client.context.signer.address}")
print(f"Sender (user subaccount): {sender_hex}")

# Получаем позиции
from trading_dashboard import TradingDashboard, PRODUCTS
dash = TradingDashboard(sender_hex)

positions = dash.get_positions()
print(f"\n=== POSITIONS ===")
for p in positions:
    print(f"  {p['symbol']} {p['side']} amount={p['amount']} price={p['price']}")

if not positions:
    print("No positions found!")
    sys.exit(0)

# Берем первую позицию
pos = positions[0]
product_id = pos['product_id']
is_long = pos['side'] == 'LONG'
size = abs(pos['amount'])
current_price = pos['price']

print(f"\n=== TEST SL ORDER ===")
print(f"Product: {pos['symbol']} (id={product_id})")
print(f"Side: {pos['side']}")
print(f"Size: {size}")
print(f"Current price: ${current_price}")

# SL price: для SHORT - выше текущей цены (напр. +2%)
if is_long:
    sl_price = current_price * 0.98  # -2%
else:
    sl_price = current_price * 1.02  # +2%

print(f"SL price: ${sl_price:.2f}")

# Нормализуем
from trading_dashboard import SIZE_INCREMENTS, PRICE_INCREMENTS, PRICE_INCREMENTS_X18
from decimal import ROUND_DOWN

size_d = Decimal(str(size))
step = SIZE_INCREMENTS[product_id]
size_d = size_d.quantize(step, rounding=ROUND_DOWN)

price_d = Decimal(str(sl_price))
price_step = PRICE_INCREMENTS[product_id]
price_d = price_d.quantize(price_step, rounding=ROUND_DOWN)

amount_x18 = int((size_d * Decimal(10)**18).to_integral_value())
if is_long:
    amount_x18 = -amount_x18

# Trigger price
trigger_priceX18 = int((price_d * Decimal(10)**18).to_integral_value())
price_step_x18 = int(PRICE_INCREMENTS_X18[product_id])
trigger_priceX18 = (trigger_priceX18 // price_step_x18) * price_step_x18

# Exec price with slippage
slippage = Decimal("0.005")
if is_long:
    exec_price = price_d * (Decimal("1") - slippage)
else:
    exec_price = price_d * (Decimal("1") + slippage)
exec_price = exec_price.quantize(price_step, rounding=ROUND_DOWN)
exec_priceX18 = int((exec_price * Decimal(10)**18).to_integral_value())
exec_priceX18 = (exec_priceX18 // price_step_x18) * price_step_x18

if is_long:
    trigger_type = "last_price_below"
else:
    trigger_type = "last_price_above"

print(f"\nOrder params:")
print(f"  amount_x18: {amount_x18}")
print(f"  trigger_price: ${price_d} (x18: {trigger_priceX18})")
print(f"  exec_price: ${exec_price} (x18: {exec_priceX18})")
print(f"  trigger_type: {trigger_type}")
print(f"  sender: {sender_hex}")
print(f"  reduce_only: True")
print(f"  order_type: DEFAULT")

print(f"\n--- Sending order ---")
try:
    result = client.market.place_price_trigger_order(
        product_id=product_id,
        price_x18=str(exec_priceX18),
        amount_x18=str(amount_x18),
        trigger_price_x18=str(trigger_priceX18),
        trigger_type=trigger_type,
        sender=sender_hex,
        reduce_only=True,
        order_type=OrderType.DEFAULT
    )
    
    print(f"\n=== RESULT ===")
    print(f"Status: {result.status}")
    print(f"Status value: {result.status.value}")
    
    # Печатаем все атрибуты результата
    for attr in dir(result):
        if not attr.startswith('_'):
            try:
                val = getattr(result, attr)
                if not callable(val):
                    print(f"  {attr}: {val}")
            except:
                pass
                
except Exception as e:
    print(f"\n❌ EXCEPTION: {e}")
    import traceback
    traceback.print_exc()
