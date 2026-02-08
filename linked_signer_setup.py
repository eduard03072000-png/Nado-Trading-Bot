"""
Automatic Linked Signer Setup
Sets up bot as authorized signer for user's subaccount
"""
from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.engine_client.types.execute import LinkSignerParams
from nado_protocol.utils.subaccount import subaccount_to_bytes
import config

def setup_linked_signer(
    user_main_private_key: str,
    bot_address: str,
    subaccount_id: str
) -> dict:
    """
    Setup bot as Linked Signer for user's subaccount
    
    SECURITY: User's main private key is ONLY used for this one-time setup
    After setup, only bot's key is needed for trading
    
    Args:
        user_main_private_key: User's MAIN wallet private key (temporary, for authorization)
        bot_address: Bot's wallet address to authorize
        subaccount_id: User's subaccount ID
    
    Returns:
        dict with success status and message
    """
    try:
        # Validate inputs
        if not user_main_private_key:
            return {
                'success': False,
                'error': 'User private key required for Linked Signer setup'
            }
        
        if not user_main_private_key.startswith('0x'):
            user_main_private_key = '0x' + user_main_private_key
        
        # Get network from config
        network = config.get_network()
        mode = NadoClientMode.MAINNET if network == "mainnet" else NadoClientMode.TESTNET
        
        # Create client with user's main key (for authorization)
        client = create_nado_client(mode=mode, signer=user_main_private_key)
        
        # Convert bot address to bytes32 format
        bot_address_bytes = subaccount_to_bytes(bot_address, "")
        
        # Create link parameters
        params = LinkSignerParams(
            sender=subaccount_id,
            signer=bot_address_bytes
        )
        
        print(f"🔗 Setting up Linked Signer...")
        print(f"   Subaccount: {subaccount_id}")
        print(f"   Bot address: {bot_address}")
        
        # Execute linking
        result = client.market.link_signer(params)
        
        if result and hasattr(result, 'status') and result.status == 'success':
            return {
                'success': True,
                'message': 'Linked Signer setup successful! Bot can now trade on your behalf.'
            }
        else:
            return {
                'success': False,
                'error': f'Setup failed: {result}'
            }
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': f'Setup error: {str(e)}'
        }
