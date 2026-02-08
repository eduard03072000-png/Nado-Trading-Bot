"""
Test: get trigger orders + try different approach
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import config
from nado_protocol.client import create_nado_client, NadoClientMode
import inspect

network = config.get_network()
mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
client = create_nado_client(mode=mode, signer=config.get_nado_key())

sender_hex = "0x45e293d6f82b6f94f8657a15dab479dcbe034b3964656661756c740000000000"

# 1. Смотрим get_trigger_orders
print("=== get_trigger_orders signature ===")
sig = inspect.signature(client.market.get_trigger_orders)
print(f"Signature: {sig}")

# Смотрим ListTriggerOrdersParams
from nado_protocol.trigger_client.types.query import ListTriggerOrdersParams
print(f"\nListTriggerOrdersParams fields:")
for field_name, field in ListTriggerOrdersParams.__fields__.items():
    print(f"  {field_name}: {field.outer_type_} (default={field.default})")

# 2. Запрашиваем trigger orders
print("\n=== Fetching trigger orders ===")
try:
    params = ListTriggerOrdersParams(
        sender=sender_hex,
        product_id=8
    )
    result = client.market.get_trigger_orders(params)
    print(f"Result type: {type(result)}")
    print(f"Result: {result}")
    
    # Показываем все атрибуты
    for attr in dir(result):
        if not attr.startswith('_'):
            try:
                val = getattr(result, attr)
                if not callable(val):
                    print(f"  {attr}: {val}")
            except:
                pass
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# 3. Попробуем list_trigger_orders напрямую через trigger_client
print("\n=== list_trigger_orders via trigger_client ===")
tc = client.context.trigger_client
try:
    sig2 = inspect.signature(tc.list_trigger_orders)
    print(f"Signature: {sig2}")
    
    result2 = tc.list_trigger_orders(ListTriggerOrdersParams(
        sender=sender_hex,
        product_id=8
    ))
    print(f"Result: {result2}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# 4. Без product_id фильтра
print("\n=== All trigger orders (no product filter) ===")
try:
    result3 = tc.list_trigger_orders(ListTriggerOrdersParams(
        sender=sender_hex
    ))
    print(f"Result: {result3}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
