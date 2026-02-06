"""
Полноценный клиент Nado DEX на основе GitHub репозитория
Адаптирован для работы с web3 7.x
"""
from web3 import Web3
from eth_account import Account
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import logging
import requests

logger = logging.getLogger(__name__)


class NadoProtocolClient:
    """
    Полноценный клиент для Nado DEX
    На основе: https://github.com/Furia-cell/nado_bot
    """
    
    def __init__(
        self, 
        network: str = "mainnet",
        private_key: str = None,
        rpc_url: str = None,
        product_id: int = 4  # Default: SOL-USDT
    ):
        self.network = network
        self.private_key = private_key
        self.product_id = product_id
        
        # RPC URLs для Ink Network
        if rpc_url:
            self.rpc_url = rpc_url
        else:
            self.rpc_url = (
                "https://rpc-gel.inkonchain.com/" 
                if network == "mainnet" 
                else "https://rpc-gel-sepolia.inkonchain.com/"
            )
        
        # Web3 setup
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        
        if private_key:
            self.account = Account.from_key(private_key)
            self.address = self.account.address
            logger.info(f"✅ Nado Protocol Client инициализирован")
            logger.info(f"   Сеть: {network}")
            logger.info(f"   Адрес: {self.address}")
            logger.info(f"   Product ID: {product_id}")
        else:
            self.account = None
            self.address = None
            logger.warning("⚠️ Private key не предоставлен - только режим чтения")
    
    def is_connected(self) -> bool:
        """Проверить подключение к сети"""
        try:
            return self.w3.is_connected()
        except Exception as e:
            logger.error(f"Ошибка подключения: {e}")
            return False
    
    def get_balance(self) -> Optional[Decimal]:
        """Получить баланс кошелька в ETH"""
        if not self.address:
            return None
        
        try:
            balance_wei = self.w3.eth.get_balance(self.address)
            balance_eth = self.w3.from_wei(balance_wei, 'ether')
            return Decimal(str(balance_eth))
        except Exception as e:
            logger.error(f"Ошибка получения баланса: {e}")
            return None
    
    async def get_mid_bid_ask(
        self, 
        use_mark_price: bool = False
    ) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """
        Получить mid/bid/ask цены
        
        Возвращает: (mid, bid, ask)
        """
        # Для простоты используем Binance API как в GitHub коде
        price = await self.get_market_price_binance()
        
        if price is None:
            return None, None, None
        
        # Симулируем spread (в реальности нужно получать из Nado orderbook)
        spread = price * Decimal("0.001")  # 0.1% spread
        bid = price - spread / 2
        ask = price + spread / 2
        mid = (bid + ask) / 2
        
        return mid, bid, ask
    
    async def get_market_price_binance(self, symbol: str = None) -> Optional[Decimal]:
        """
        Получить цену через Binance API
        
        Args:
            symbol: Символ (по умолчанию определяется из product_id)
        """
        # Маппинг product_id -> symbol
        product_symbols = {
            1: "BTCUSDT",
            4: "SOLUSDT",  # SOL-USDT
            # Добавить другие по необходимости
        }
        
        if symbol is None:
            symbol = product_symbols.get(self.product_id, "BTCUSDT")
        
        try:
            response = requests.get(
                f"https://api.binance.com/api/v3/ticker/price",
                params={"symbol": symbol},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                price = Decimal(data["price"])
                logger.debug(f"📊 Цена {symbol}: ${price}")
                return price
        except Exception as e:
            logger.error(f"Ошибка получения цены Binance: {e}")
        return None
    
    async def place_order(
        self,
        side: str,  # "buy" или "sell"
        size: Decimal,
        price: Decimal,
        product_id: Optional[int] = None,
        order_type: str = "limit"
    ) -> Dict:
        """
        Разместить ордер на Nado DEX
        
        ВАЖНО: Требует смарт-контракты Nado или полный SDK
        Сейчас это placeholder
        """
        if product_id is None:
            product_id = self.product_id
        
        logger.warning("⚠️ place_order - placeholder функция")
        logger.warning("⚠️ Для реальной торговли требуется:")
        logger.warning("   • Адреса смарт-контрактов Nado")
        logger.warning("   • ABI контрактов")
        logger.warning("   • Или полный nado-protocol SDK")
        
        order_info = {
            "status": "simulation",
            "product_id": product_id,
            "side": side,
            "size": str(size),
            "price": str(price),
            "order_type": order_type,
            "account": self.address,
            "message": "Симуляция - нужны смарт-контракты для реальной торговли"
        }
        
        logger.info(f"📝 Симуляция: {side} {size} @ ${price}")
        return order_info
    
    async def get_positions(self) -> List[Dict]:
        """
        Получить открытые позиции
        
        ВАЖНО: Требует Nado API или смарт-контракты
        """
        logger.warning("⚠️ get_positions - placeholder")
        return []
    
    def sign_transaction(self, tx_params: Dict) -> Optional[str]:
        """Подписать транзакцию"""
        if not self.account:
            logger.error("Аккаунт не настроен")
            return None
        
        try:
            # Дополняем параметры
            if 'nonce' not in tx_params:
                tx_params['nonce'] = self.w3.eth.get_transaction_count(self.address)
            
            if 'gas' not in tx_params:
                tx_params['gas'] = 100000
            
            if 'gasPrice' not in tx_params:
                tx_params['gasPrice'] = self.w3.eth.gas_price
            
            if 'chainId' not in tx_params:
                tx_params['chainId'] = self.w3.eth.chain_id
            
            # Подписываем
            signed_tx = self.account.sign_transaction(tx_params)
            return signed_tx.raw_transaction.hex()
        except Exception as e:
            logger.error(f"Ошибка подписи: {e}")
            return None


# Алиас для обратной совместимости
SimplifiedNadoClient = NadoProtocolClient
