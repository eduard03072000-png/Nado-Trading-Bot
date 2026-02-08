"""
Создание Bot Token (Linked Signer) для NADO DEX
"""
import sys
import config
from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.engine_client.types.execute import LinkSignerParams


def create_bot_token(subaccount_id):
    """Создать бот токен для субаккаунта"""
    try:
        network = config.get_network()
        mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
        client = create_nado_client(mode=mode, signer=config.get_nado_key())
        
        bot_address = client.context.signer.address
        
        print(f"Creating bot token:")
        print(f"  Bot address: {bot_address}")
        print(f"  Subaccount: {subaccount_id}")
        
        # Создаём параметры для link_signer
        params = LinkSignerParams(
            sender=subaccount_id,
            signer=bot_address
        )
        
        # Создаём токен
        result = client.subaccount.link_signer(params)
        
        print(f"\nOK Bot token created!")
        print(f"  Status: {result.status.value if hasattr(result, 'status') else 'success'}")
        
        return True
        
    except Exception as e:
        print(f"\nError creating token: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python create_bot_token.py <subaccount_id>")
        print("\nExample:")
        print("  python create_bot_token.py 0xb6da54b9cd60832d33d1a401933d48dee774dcfa64656661756c740000000000")
        sys.exit(1)
    
    subaccount_id = sys.argv[1]
    
    if not subaccount_id.startswith('0x') or len(subaccount_id) != 66:
        print("Error: Invalid subaccount format!")
        print("Subaccount must start with 0x and be 66 characters long")
        sys.exit(1)
    
    create_bot_token(subaccount_id)
