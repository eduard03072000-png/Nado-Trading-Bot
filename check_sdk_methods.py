"""
Управление Bot Tokens для NADO DEX
"""
import sys
import config
from nado_protocol.client import create_nado_client, NadoClientMode


def check_methods():
    """Проверить доступные методы для работы с токенами"""
    try:
        network = config.get_network()
        mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
        client = create_nado_client(mode=mode, signer=config.get_nado_key())
        
        print(f"All client.subaccount methods:")
        methods = [m for m in dir(client.subaccount) if not m.startswith('_')]
        for m in methods:
            print(f"  - {m}")
        
        print(f"\nToken/Link/Bot related methods:")
        token_methods = [m for m in methods if 'token' in m.lower() or 'link' in m.lower() or 'bot' in m.lower()]
        for m in token_methods:
            print(f"  OK {m}")
        
        return None
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == '__main__':
    check_methods()
