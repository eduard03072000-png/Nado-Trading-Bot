"""
Test: проверяем trigger orders через API
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import config
from nado_protocol.client import create_nado_client, NadoClientMode

network = config.get_network()
mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
client = create_nado_client(mode=mode, signer=config.get_nado_key())

sender_hex = "0x45e293d6f82b6f94f8657a15dab479dcbe034b3964656661756c740000000000"

print("=== Checking trigger client methods ===")

# Посмотрим какие методы есть у trigger_client
tc = client.context.trigger_client
if tc:
    print(f"Trigger client exists: {type(tc)}")
    methods = [m for m in dir(tc) if not m.startswith('_') and callable(getattr(tc, m))]
    print(f"Methods: {methods}")
    
    # Попробуем получить открытые trigger orders
    for method_name in methods:
        if 'get' in method_name.lower() or 'list' in method_name.lower() or 'query' in method_name.lower() or 'open' in method_name.lower():
            print(f"\n  Found query method: {method_name}")
else:
    print("NO trigger client!")

print("\n=== Checking market methods for trigger orders ===")
market_methods = [m for m in dir(client.market) if not m.startswith('_') and ('trigger' in m.lower() or 'stop' in m.lower())]
print(f"Trigger-related market methods: {market_methods}")

# Проверим все market методы с "get" или "open"  
market_query = [m for m in dir(client.market) if not m.startswith('_') and ('get' in m.lower() or 'query' in m.lower() or 'list' in m.lower())]
print(f"\nAll query methods on market: {market_query}")

# Попробуем получить trigger orders
print("\n=== Trying to get trigger orders ===")
for method_name in market_query:
    if 'trigger' in method_name.lower():
        method = getattr(client.market, method_name)
        print(f"\nCalling {method_name}...")
        try:
            # Попробуем разные варианты вызова
            import inspect
            sig = inspect.signature(method)
            print(f"  Signature: {sig}")
        except Exception as e:
            print(f"  Error: {e}")

# Проверяем subaccount methods
print("\n=== Subaccount methods ===")
sub_methods = [m for m in dir(client.subaccount) if not m.startswith('_') and callable(getattr(client.subaccount, m))]
print(f"Methods: {sub_methods}")

# Попробуем получить open orders (включая triggers)
print("\n=== Open orders check ===")
try:
    orders = client.market.get_subaccount_multi_products_open_orders(
        product_ids=[8],
        sender=sender_hex
    )
    print(f"Open orders result type: {type(orders)}")
    print(f"Open orders: {orders}")
except Exception as e:
    print(f"Error getting open orders: {e}")

# Проверяем digest нашего SL ордера
print("\n=== Check SL order by digest ===")
sl_digest = "0x8b3d2cc85b5d58124c357df78d0d861de6f1941d84152e29b37e20eca6dc4783"
try:
    # Ищем метод для проверки ордера по digest
    for method_name in market_query:
        if 'order' in method_name.lower():
            print(f"  Found: {method_name}")
except Exception as e:
    print(f"Error: {e}")
