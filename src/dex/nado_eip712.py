"""
Nado EIP712 Signing Module
Подписи для ордеров на Nado DEX
"""
from eth_account import Account
from eth_account.messages import encode_structured_data
from typing import Dict
import time


# Ink Mainnet Chain ID
INK_MAINNET_CHAIN_ID = 763373


def get_order_verifying_contract(product_id: int) -> str:
    """
    Получить verifying contract для ордера
    
    Args:
        product_id: ID продукта (1=SOL, 2=BTC, etc)
    
    Returns:
        Contract address
    """
    # Для place_order verifying contract = product_id в виде address
    # Например: product_id=1 -> 0x0000000000000000000000000000000000000001
    return f"0x{product_id:040x}"


def create_eip712_domain(
    verifying_contract: str,
    chain_id: int = INK_MAINNET_CHAIN_ID
) -> Dict:
    """
    Создать EIP712 domain для Nado
    
    Args:
        verifying_contract: Contract address
        chain_id: Chain ID (default: Ink Mainnet)
    
    Returns:
        Domain dict
    """
    return {
        "name": "Nado",
        "version": "0.0.1",
        "chainId": chain_id,
        "verifyingContract": verifying_contract
    }


def create_order_types() -> Dict:
    """
    Создать types для Order
    
    Returns:
        Types dict
    """
    return {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"}
        ],
        "Order": [
            {"name": "sender", "type": "bytes32"},
            {"name": "priceX18", "type": "int128"},
            {"name": "amount", "type": "int128"},
            {"name": "expiration", "type": "uint64"},
            {"name": "nonce", "type": "uint64"},
            {"name": "appendix", "type": "uint128"}
        ]
    }


def sign_order(
    private_key: str,
    sender: str,  # bytes32
    price_x18: int,
    amount: int,  # positive=buy, negative=sell
    expiration: int,
    nonce: int,
    appendix: int,
    product_id: int,
    chain_id: int = INK_MAINNET_CHAIN_ID
) -> str:
    """
    Подписать ордер через EIP712
    
    Args:
        private_key: Приватный ключ (с 0x)
        sender: Sender bytes32 (address + subaccount)
        price_x18: Цена * 10^18 (0 для market)
        amount: Размер * 10^18 (negative = sell)
        expiration: Unix timestamp
        nonce: Уникальный nonce
        appendix: Битовые флаги ордера
        product_id: ID продукта
        chain_id: Chain ID
    
    Returns:
        Signature hex string (0x...)
    """
    # Verifying contract
    verifying_contract = get_order_verifying_contract(product_id)
    
    # Domain
    domain = create_eip712_domain(verifying_contract, chain_id)
    
    # Types
    types = create_order_types()
    
    # Message
    message = {
        "sender": sender,
        "priceX18": price_x18,
        "amount": amount,
        "expiration": expiration,
        "nonce": nonce,
        "appendix": appendix
    }
    
    # Typed data
    typed_data = {
        "types": types,
        "primaryType": "Order",
        "domain": domain,
        "message": message
    }
    
    # Sign
    account = Account.from_key(private_key)
    encoded = encode_structured_data(primitive=typed_data)
    signed = account.sign_message(encoded)
    
    return signed.signature.hex()


def address_to_sender_bytes32(address: str, subaccount: str = "default") -> str:
    """
    Конвертировать address + subaccount в bytes32
    
    Format: address (20 bytes) + subaccount (12 bytes) = 32 bytes
    
    Args:
        address: Ethereum address (0x...)
        subaccount: Subaccount name (default: "default")
    
    Returns:
        bytes32 hex string
    """
    # Remove 0x
    addr_hex = address[2:].lower()
    
    # Convert subaccount to bytes (UTF-8)
    subaccount_bytes = subaccount.encode('utf-8')
    
    # Pad to 12 bytes (24 hex chars)
    subaccount_hex = subaccount_bytes.hex().ljust(24, '0')
    
    # Combine
    return "0x" + addr_hex + subaccount_hex


# Test
if __name__ == "__main__":
    print("="*60)
    print("🔐 NADO EIP712 SIGNING TEST")
    print("="*60)
    
    # Test data
    test_address = "0x45E293D6F82b6f94F8657A15daB479dcbE034b39"
    test_key = "YOUR_PRIVATE_KEY"
    
    # Convert to sender
    sender = address_to_sender_bytes32(test_address, "default")
    print(f"\n📍 Address: {test_address}")
    print(f"📍 Sender: {sender}")
    
    # Sign test order
    signature = sign_order(
        private_key=test_key,
        sender=sender,
        price_x18=92000000000000000000,  # $92 * 10^18
        amount=1100000000000000000,  # 1.1 SOL * 10^18
        expiration=int(time.time()) + 3600,
        nonce=int(time.time() * 1000),
        appendix=0,  # 0 = normal order
        product_id=1  # SOL
    )
    
    print(f"\n✅ Signature: {signature}")
    print("="*60)
