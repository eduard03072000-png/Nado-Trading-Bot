"""
Модуль для работы с Web3 и MetaMask
Управление кошельком и подписание транзакций
"""
from web3 import Web3
from eth_account import Account
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class Web3Manager:
    """Менеджер для работы с Web3 и подписания транзакций"""
    
    def __init__(self, rpc_url: str, private_key: str):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.account = Account.from_key(private_key)
        self.address = self.account.address
        
    def sign_transaction(self, transaction: Dict) -> Optional[str]:
        """Подписать транзакцию"""
        try:
            signed = self.account.sign_transaction(transaction)
            return signed.rawTransaction.hex()
        except Exception as e:
            logger.error(f"Ошибка подписи транзакции: {e}")
            return None
    
    def get_balance(self) -> float:
        """Получить баланс кошелька"""
        try:
            balance_wei = self.w3.eth.get_balance(self.address)
            return float(self.w3.from_wei(balance_wei, 'ether'))
        except Exception as e:
            logger.error(f"Ошибка получения баланса: {e}")
            return 0.0
    
    def is_connected(self) -> bool:
        """Проверить подключение к сети"""
        try:
            return self.w3.is_connected()
        except Exception as e:
            logger.error(f"Ошибка проверки подключения: {e}")
            return False
    
    def get_chain_id(self) -> Optional[int]:
        """Получить ID текущей сети"""
        try:
            return self.w3.eth.chain_id
        except Exception as e:
            logger.error(f"Ошибка получения chain_id: {e}")
            return None
    
    def get_nonce(self) -> int:
        """Получить nonce для следующей транзакции"""
        try:
            return self.w3.eth.get_transaction_count(self.address)
        except Exception as e:
            logger.error(f"Ошибка получения nonce: {e}")
            return 0
    
    async def send_transaction(
        self,
        to: str,
        value: float = 0,
        data: str = "0x",
        gas_limit: int = 100000
    ) -> Optional[str]:
        """
        Отправить транзакцию
        
        Args:
            to: Адрес получателя
            value: Сумма в ETH
            data: Данные транзакции (hex)
            gas_limit: Лимит газа
        
        Returns:
            Transaction hash или None
        """
        try:
            # Получаем актуальные данные
            nonce = self.get_nonce()
            chain_id = self.get_chain_id()
            gas_price = self.w3.eth.gas_price
            
            # Формируем транзакцию
            transaction = {
                'nonce': nonce,
                'to': Web3.to_checksum_address(to),
                'value': self.w3.to_wei(value, 'ether'),
                'gas': gas_limit,
                'gasPrice': gas_price,
                'chainId': chain_id,
                'data': data
            }
            
            # Подписываем
            signed_txn = self.account.sign_transaction(transaction)
            
            # Отправляем
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            logger.info(f"✅ Транзакция отправлена: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Ошибка отправки транзакции: {e}")
            return None
    
    def wait_for_transaction(self, tx_hash: str, timeout: int = 120) -> bool:
        """
        Ожидать подтверждения транзакции
        
        Args:
            tx_hash: Hash транзакции
            timeout: Таймаут в секундах
        """
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(
                tx_hash,
                timeout=timeout
            )
            
            if receipt['status'] == 1:
                logger.info(f"✅ Транзакция подтверждена: {tx_hash}")
                return True
            else:
                logger.error(f"❌ Транзакция провалена: {tx_hash}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка ожидания транзакции: {e}")
            return False
    
    def get_contract(self, address: str, abi: list):
        """
        Получить объект контракта
        
        Args:
            address: Адрес контракта
            abi: ABI контракта
        """
        try:
            checksum_address = Web3.to_checksum_address(address)
            return self.w3.eth.contract(address=checksum_address, abi=abi)
        except Exception as e:
            logger.error(f"Ошибка получения контракта: {e}")
            return None
    
    async def call_contract_function(
        self,
        contract_address: str,
        abi: list,
        function_name: str,
        *args,
        value: float = 0
    ) -> Optional[str]:
        """
        Вызвать функцию смарт-контракта
        
        Args:
            contract_address: Адрес контракта
            abi: ABI контракта
            function_name: Имя функции
            args: Аргументы функции
            value: Сумма ETH для отправки
        """
        try:
            contract = self.get_contract(contract_address, abi)
            if not contract:
                return None
            
            # Получаем функцию
            func = getattr(contract.functions, function_name)
            
            # Строим транзакцию
            transaction = func(*args).build_transaction({
                'from': self.address,
                'nonce': self.get_nonce(),
                'gas': 500000,
                'gasPrice': self.w3.eth.gas_price,
                'value': self.w3.to_wei(value, 'ether'),
                'chainId': self.get_chain_id()
            })
            
            # Подписываем и отправляем
            signed = self.account.sign_transaction(transaction)
            tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
            
            logger.info(f"✅ Функция {function_name} вызвана: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Ошибка вызова функции {function_name}: {e}")
            return None
    
    def read_contract(
        self,
        contract_address: str,
        abi: list,
        function_name: str,
        *args
    ):
        """
        Читать данные из контракта (без транзакции)
        
        Args:
            contract_address: Адрес контракта
            abi: ABI контракта
            function_name: Имя функции
            args: Аргументы функции
        """
        try:
            contract = self.get_contract(contract_address, abi)
            if not contract:
                return None
            
            func = getattr(contract.functions, function_name)
            return func(*args).call()
            
        except Exception as e:
            logger.error(f"Ошибка чтения из контракта: {e}")
            return None
    
    # ERC-20 стандартный ABI (минимальный)
    ERC20_ABI = [
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [
                {"name": "_spender", "type": "address"},
                {"name": "_value", "type": "uint256"}
            ],
            "name": "approve",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function"
        }
    ]
    
    def get_token_balance(self, token_address: str) -> float:
        """
        Получить баланс токена ERC-20
        
        Args:
            token_address: Адрес токена
        """
        try:
            balance = self.read_contract(
                token_address,
                self.ERC20_ABI,
                "balanceOf",
                self.address
            )
            
            if balance is not None:
                decimals = self.read_contract(
                    token_address,
                    self.ERC20_ABI,
                    "decimals"
                )
                return balance / (10 ** decimals)
            
        except Exception as e:
            logger.error(f"Ошибка получения баланса токена: {e}")
        return 0.0
    
    async def approve_token(
        self,
        token_address: str,
        spender_address: str,
        amount: float
    ) -> Optional[str]:
        """
        Одобрить использование токенов (approve)
        
        Args:
            token_address: Адрес токена
            spender_address: Кто может тратить
            amount: Количество токенов
        """
        try:
            # Получаем decimals
            decimals = self.read_contract(
                token_address,
                self.ERC20_ABI,
                "decimals"
            )
            
            # Конвертируем amount с учетом decimals
            amount_wei = int(amount * (10 ** decimals))
            
            tx_hash = await self.call_contract_function(
                token_address,
                self.ERC20_ABI,
                "approve",
                Web3.to_checksum_address(spender_address),
                amount_wei
            )
            
            return tx_hash
            
        except Exception as e:
            logger.error(f"Ошибка approve токена: {e}")
            return None
    
    def estimate_gas(self, transaction: Dict) -> int:
        """Оценить количество газа для транзакции"""
        try:
            return self.w3.eth.estimate_gas(transaction)
        except Exception as e:
            logger.error(f"Ошибка оценки газа: {e}")
            return 100000
    
    def get_gas_price(self) -> int:
        """Получить текущую цену газа"""
        try:
            return self.w3.eth.gas_price
        except Exception as e:
            logger.error(f"Ошибка получения цены газа: {e}")
            return 0
