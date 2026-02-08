"""
User Management System for NADO Trading Bot
Manages user registration, authentication, and Linked Signer setup
"""
import json
import os
import secrets
from typing import Optional, Dict
from eth_account import Account
from datetime import datetime

class UserManager:
    """Manages user accounts and their Linked Signers"""
    
    def __init__(self, db_file: str = "users_db.json"):
        self.db_file = os.path.join(os.path.dirname(__file__), db_file)
        self.users = self._load_database()
    
    def _load_database(self) -> Dict:
        """Load users database from file"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_database(self):
        """Save users database to file"""
        with open(self.db_file, 'w') as f:
            json.dump(self.users, f, indent=2)
    
    def is_user_registered(self, telegram_id: int) -> bool:
        """Check if user is already registered"""
        return str(telegram_id) in self.users
    
    def get_user_data(self, telegram_id: int) -> Optional[Dict]:
        """Get user data by telegram ID"""
        return self.users.get(str(telegram_id))
    
    def generate_bot_private_key(self) -> tuple:
        """
        Generate a new private key for bot (Linked Signer)
        Returns: (private_key_hex, address)
        """
        # Generate random private key
        private_key_bytes = secrets.token_bytes(32)
        account = Account.from_key(private_key_bytes)
        
        private_key_hex = "0x" + private_key_bytes.hex()
        address = account.address
        
        return private_key_hex, address
    
    def validate_subaccount_id(self, subaccount_id: str) -> bool:
        """
        Validate subaccount ID format
        Must be 66 characters (0x + 64 hex chars)
        """
        if not subaccount_id:
            return False
        
        # Remove 0x prefix if present
        if subaccount_id.startswith('0x'):
            subaccount_id = subaccount_id[2:]
        
        # Check length (64 hex chars = 32 bytes)
        if len(subaccount_id) != 64:
            return False
        
        # Check if valid hex
        try:
            int(subaccount_id, 16)
            return True
        except ValueError:
            return False
    
    def extract_wallet_from_subaccount(self, subaccount_id: str) -> str:
        """
        Extract wallet address from subaccount ID
        First 20 bytes (40 hex chars) = wallet address
        """
        if subaccount_id.startswith('0x'):
            subaccount_id = subaccount_id[2:]
        
        wallet = '0x' + subaccount_id[:40]
        return wallet
    
    def register_user(
        self,
        telegram_id: int,
        telegram_username: str,
        subaccount_id: str,
        account_name: Optional[str] = None
    ) -> Dict:
        """
        Register new user
        
        Args:
            telegram_id: User's Telegram ID
            telegram_username: User's Telegram username
            subaccount_id: NADO subaccount ID (0x...)
            account_name: Optional friendly name for account
        
        Returns:
            Dict with registration result
        """
        # Check if already registered
        if self.is_user_registered(telegram_id):
            return {
                'success': False,
                'error': 'User already registered'
            }
        
        # Validate subaccount ID
        if not self.validate_subaccount_id(subaccount_id):
            return {
                'success': False,
                'error': 'Invalid subaccount ID format. Must be 66 characters (0x + 64 hex)'
            }
        
        # Normalize subaccount ID
        if not subaccount_id.startswith('0x'):
            subaccount_id = '0x' + subaccount_id
        
        # Extract wallet address
        wallet_address = self.extract_wallet_from_subaccount(subaccount_id)
        
        # Generate bot private key for this user
        bot_private_key, bot_address = self.generate_bot_private_key()
        
        # Create user record
        user_data = {
            'telegram_id': telegram_id,
            'telegram_username': telegram_username,
            'account_name': account_name or f"User_{telegram_id}",
            'wallet_address': wallet_address,
            'subaccount_id': subaccount_id,
            'bot_private_key': bot_private_key,
            'bot_address': bot_address,
            'linked_signer_setup': False,
            'registered_at': datetime.now().isoformat(),
            'last_active': datetime.now().isoformat(),
            'leverage': 10
        }
        
        # Save to database
        self.users[str(telegram_id)] = user_data
        self._save_database()
        
        return {
            'success': True,
            'user_data': user_data
        }
    
    def update_linked_signer_status(self, telegram_id: int, status: bool):
        """Update Linked Signer setup status"""
        if str(telegram_id) in self.users:
            self.users[str(telegram_id)]['linked_signer_setup'] = status
            self._save_database()
    
    def update_last_active(self, telegram_id: int):
        """Update user's last active timestamp"""
        if str(telegram_id) in self.users:
            self.users[str(telegram_id)]['last_active'] = datetime.now().isoformat()
            self._save_database()
    
    def update_leverage(self, telegram_id: int, leverage: float):
        """Update user leverage"""
        if str(telegram_id) in self.users:
            self.users[str(telegram_id)]['leverage'] = leverage
            self._save_database()
    
    def get_leverage(self, telegram_id: int) -> float:
        """Get user leverage"""
        user = self.get_user_data(telegram_id)
        return user.get('leverage', 10) if user else 10
    
    def get_user_stats(self) -> Dict:
        """Get statistics about registered users"""
        total_users = len(self.users)
        users_with_linked_signer = sum(
            1 for u in self.users.values() 
            if u.get('linked_signer_setup', False)
        )
        
        return {
            'total_users': total_users,
            'users_with_linked_signer': users_with_linked_signer,
            'pending_setup': total_users - users_with_linked_signer
        }
    
    def delete_user(self, telegram_id: int) -> bool:
        """Delete user from database"""
        if str(telegram_id) in self.users:
            del self.users[str(telegram_id)]
            self._save_database()
            return True
        return False
