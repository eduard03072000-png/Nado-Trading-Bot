"""
Test: get trigger orders - correct params
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

print("=== Fetching ALL trigger orders ===")
try:
    params = ListTriggerOrdersParams(
        tx=ListTriggerOrdersTx(
            sender=sender_hex,
            recvTime=int(time.time() * 1000),
            nonce=None
        ),
        product_ids=[8],
        limit=50
    )
    result = client.market.get_trigger_orders(params)
    print(f"Result type: {type(result)}")
    
    # Показываем всё
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

# Попробуем со статусом pending
print("\n=== Fetching PENDING trigger orders ===")
try:
    params2 = ListTriggerOrdersParams(
        tx=ListTriggerOrdersTx(
            sender=sender_hex,
            recvTime=int(time.time() * 1000),
            nonce=None
        ),
        product_ids=[8],
        status_types=[TriggerOrderStatusType.PENDING],
        limit=50
    )
    result2 = client.market.get_trigger_orders(params2)
    print(f"Result: {result2}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# Попробуем по digest
print("\n=== Check by digest ===")
sl_digest = "0x8b3d2cc85b5d58124c357df78d0d861de6f1941d84152e29b37e20eca6dc4783"
try:
    params3 = ListTriggerOrdersParams(
        tx=ListTriggerOrdersTx(
            sender=sender_hex,
            recvTime=int(time.time() * 1000),
            nonce=None
        ),
        digests=[sl_digest],
        limit=10
    )
    result3 = client.market.get_trigger_orders(params3)
    print(f"Result: {result3}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
