"""
Test: get trigger orders - fixed recvTime
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import config
from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.trigger_client.types.query import (
    ListTriggerOrdersParams, ListTriggerOrdersTx,
    TriggerOrderStatusType
)

network = config.get_network()
mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
client = create_nado_client(mode=mode, signer=config.get_nado_key())

sender_hex = "0x45e293d6f82b6f94f8657a15dab479dcbe034b3964656661756c740000000000"

# recvTime = 90 секунд в будущем (в секундах!)
recv_time = int(time.time()) + 90

# Показываем доступные статусы
print("Available status types:")
for s in TriggerOrderStatusType:
    print(f"  {s.name} = {s.value}")

print(f"\n=== Fetching ALL trigger orders (recvTime={recv_time}) ===")
try:
    params = ListTriggerOrdersParams(
        tx=ListTriggerOrdersTx(
            sender=sender_hex,
            recvTime=recv_time,
            nonce=None
        ),
        product_ids=[8],
        limit=50
    )
    result = client.market.get_trigger_orders(params)
    print(f"Status: {result.status}")
    
    if hasattr(result, 'orders'):
        print(f"Orders count: {len(result.orders)}")
        for i, order in enumerate(result.orders):
            print(f"\n--- Order {i+1} ---")
            for attr in dir(order):
                if not attr.startswith('_'):
                    try:
                        val = getattr(order, attr)
                        if not callable(val):
                            print(f"  {attr}: {val}")
                    except:
                        pass
    else:
        print(f"Full result: {result}")
                
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# По digest
print("\n=== Check by digest ===")
sl_digest = "0x8b3d2cc85b5d58124c357df78d0d861de6f1941d84152e29b37e20eca6dc4783"
try:
    params3 = ListTriggerOrdersParams(
        tx=ListTriggerOrdersTx(
            sender=sender_hex,
            recvTime=recv_time,
            nonce=None
        ),
        digests=[sl_digest],
        limit=10
    )
    result3 = client.market.get_trigger_orders(params3)
    print(f"Status: {result3.status}")
    if hasattr(result3, 'orders'):
        print(f"Orders: {len(result3.orders)}")
        for o in result3.orders:
            print(f"  {o}")
    else:
        print(f"Full: {result3}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
