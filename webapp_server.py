"""
Flask API server for Telegram Mini App
"""
import os
import sys
import logging
from decimal import Decimal
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

sys.path.insert(0, '/root/trading_bot')

from dotenv import load_dotenv
load_dotenv('/root/trading_bot/.env')

from multi_wallet_dashboard import MultiWalletDashboard

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='/root/trading_bot/webapp', static_url_path='')
CORS(app)

_dashboards = {}

def get_dashboard(wallet_num=1):
    if wallet_num not in _dashboards:
        _dashboards[wallet_num] = MultiWalletDashboard()
    d = _dashboards[wallet_num]
    d.active_wallet = wallet_num
    return d

@app.route('/')
def index():
    return send_from_directory('/root/trading_bot/webapp', 'index.html')

@app.route('/api/balance')
def api_balance():
    try:
        wallet = int(request.args.get('wallet', 1))
        dash = get_dashboard(wallet)
        balance = dash.get_balance()
        if not balance:
            return jsonify({'ok': False, 'error': 'Failed to get balance'})
        return jsonify({
            'ok': True,
            'total_equity': balance.get('total_equity', balance.get('equity', 0)),
            'available': balance.get('health', 0),
            'unrealized_pnl': balance.get('unrealized_pnl', 0),
            'leverage': float(dash.leverage) if dash.leverage else 10
        })
    except Exception as e:
        logger.error(f"Balance error: {e}", exc_info=True)
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/positions')
def api_positions():
    try:
        wallet = int(request.args.get('wallet', 1))
        dash = get_dashboard(wallet)
        positions = dash.get_positions()
        if not positions:
            return jsonify({'ok': True, 'positions': []})
        result = []
        for p in positions:
            try:
                amount = float(p.get('amount', 0))
                side = 'LONG' if amount > 0 else 'SHORT'
                symbol = p.get('product', p.get('symbol', 'UNKNOWN'))
                if not symbol.endswith('-PERP'):
                    symbol = symbol + '-PERP'
                result.append({
                    'product_id': p.get('product_id', 0),
                    'symbol': symbol,
                    'side': side,
                    'size': abs(amount),
                    'entry_price': float(p.get('entry_price', 0) or 0),
                    'unrealized_pnl': float(p.get('unrealized_pnl', 0) or 0),
                })
            except Exception as pe:
                logger.warning(f"Position parse error: {pe}")
        return jsonify({'ok': True, 'positions': result})
    except Exception as e:
        logger.error(f"Positions error: {e}", exc_info=True)
        return jsonify({'ok': False, 'error': str(e)})

SYMBOL_TO_ID = {'BTC-PERP': 2, 'ETH-PERP': 4, 'SOL-PERP': 8}

@app.route('/api/prices')
def api_prices():
    try:
        dash = get_dashboard(1)
        prices = {}
        for sym, pid in SYMBOL_TO_ID.items():
            try:
                price = dash.get_market_price(pid)
                if price:
                    prices[sym] = float(price)
            except Exception as pe:
                logger.warning(f"Price error {sym}: {pe}")
        return jsonify({'ok': True, 'prices': prices})
    except Exception as e:
        logger.error(f"Prices error: {e}", exc_info=True)
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/trade', methods=['POST'])
def api_trade():
    try:
        data = request.json
        wallet = int(data.get('wallet', 1))
        side = data.get('side', 'LONG').upper()
        size = float(data.get('size', 0))
        symbol = data.get('symbol', 'ETH-PERP')
        lev = int(data.get('leverage', 10))

        if size <= 0:
            return jsonify({'ok': False, 'error': 'Invalid size'})

        product_id = SYMBOL_TO_ID.get(symbol)
        if not product_id:
            return jsonify({'ok': False, 'error': f'Unknown symbol: {symbol}'})

        dash = get_dashboard(wallet)
        if dash.leverage != lev:
            try:
                dash.set_leverage(lev)
            except Exception:
                pass

        is_long = side == 'LONG'
        result = dash.place_order(
            product_id=product_id,
            size=Decimal(str(size)),
            is_long=is_long
        )
        logger.info(f"Trade result: {result}")
        return jsonify({'ok': True, 'result': str(result)})
    except Exception as e:
        logger.error(f"Trade error: {e}", exc_info=True)
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/close', methods=['POST'])
def api_close():
    try:
        data = request.json
        wallet = int(data.get('wallet', 1))
        product_id = data.get('product_id')
        dash = get_dashboard(wallet)
        result = dash.close_position(product_id)
        logger.info(f"Close result: {result}")
        return jsonify({'ok': True, 'result': str(result)})
    except Exception as e:
        logger.error(f"Close error: {e}", exc_info=True)
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/health')
def health():
    return jsonify({'ok': True, 'status': 'running'})

if __name__ == '__main__':
    port = int(os.environ.get('WEBAPP_PORT', 8080))
    logger.info(f"Starting Mini App server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
