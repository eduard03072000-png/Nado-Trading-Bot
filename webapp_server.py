"""
Flask API server for Telegram Mini App
"""
import os
import sys
import json
import time
import logging
import threading
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

D = 1e18

ID_TO_SYMBOL = {
    2: 'BTC', 4: 'ETH', 8: 'SOL', 10: 'XRP',
    14: 'BNB', 16: 'HYPE', 18: 'ZEC', 20: 'MON',
    22: 'FARTCOIN', 24: 'SUI', 26: 'AAVE', 28: 'XAUT',
    30: 'PUMP', 32: 'TAO', 34: 'XMR', 36: 'LIT',
    38: 'kPEPE', 40: 'PENGU', 46: 'UNI', 48: 'ASTER',
    50: 'XPL', 52: 'DOGE', 54: 'WLFI', 56: 'kBONK',
}

SYMBOL_TO_ID = {
    'BTC-PERP': 2, 'ETH-PERP': 4, 'SOL-PERP': 8, 'XRP-PERP': 10,
    'BNB-PERP': 14, 'HYPE-PERP': 16, 'ZEC-PERP': 18, 'MON-PERP': 20,
    'FARTCOIN-PERP': 22, 'SUI-PERP': 24, 'AAVE-PERP': 26, 'XAUT-PERP': 28,
    'PUMP-PERP': 30, 'TAO-PERP': 32, 'XMR-PERP': 34, 'LIT-PERP': 36,
    'kPEPE-PERP': 38, 'PENGU-PERP': 40, 'UNI-PERP': 46, 'ASTER-PERP': 48,
    'XPL-PERP': 50, 'DOGE-PERP': 52, 'WLFI-PERP': 54, 'kBONK-PERP': 56,
}

# === EQUITY TRACKING ===
EQUITY_FILE = '/root/trading_bot/equity_history.json'
EQUITY_SAVE_INTERVAL = 300

def load_equity_history():
    try:
        if os.path.exists(EQUITY_FILE):
            with open(EQUITY_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_equity_point(wallet_num, equity):
    try:
        history = load_equity_history()
        key = str(wallet_num)
        if key not in history:
            history[key] = []
        ts = int(time.time())
        history[key].append({'ts': ts, 'equity': equity})
        cutoff = ts - 7 * 86400
        history[key] = [p for p in history[key] if p['ts'] > cutoff]
        with open(EQUITY_FILE, 'w') as f:
            json.dump(history, f)
    except Exception as e:
        logger.warning(f"save_equity_point error: {e}")

def get_equity_at(wallet_num, target_ts):
    history = load_equity_history()
    points = history.get(str(wallet_num), [])
    if not points:
        return None
    best = min(points, key=lambda p: abs(p['ts'] - target_ts))
    if abs(best['ts'] - target_ts) > 7200:
        return None
    return best['equity']

def equity_tracker_thread():
    time.sleep(10)
    while True:
        try:
            for wnum in [1, 2]:
                try:
                    dash = get_dashboard(wnum)
                    w = dash.wallets[wnum]
                    subaccount = w.sender_hex
                    summary = w.client.subaccount.get_engine_subaccount_summary(subaccount)
                    if hasattr(summary, 'healths') and len(summary.healths) > 2:
                        equity = float(summary.healths[2].health) / D
                        if equity:
                            save_equity_point(wnum, equity)
                            logger.info(f"Equity saved wallet {wnum}: {equity:.4f}")
                except Exception as e:
                    logger.warning(f"equity_tracker wallet {wnum}: {e}")
        except Exception as e:
            logger.warning(f"equity_tracker_thread error: {e}")
        time.sleep(EQUITY_SAVE_INTERVAL)

_tracker = threading.Thread(target=equity_tracker_thread, daemon=True)
_tracker.start()

# === RATE LIMIT THROTTLE ===
import time as _global_time
import threading as _threading
_indexer_lock = _threading.Lock()
_last_indexer_call = 0.0
_INDEXER_MIN_INTERVAL = 3.0  # минимум 3 сек между запросами

def _throttled_indexer_call(fn, *args, max_retries=5, **kwargs):
    global _last_indexer_call
    with _indexer_lock:
        for attempt in range(max_retries):
            now = _global_time.time()
            wait = _INDEXER_MIN_INTERVAL - (now - _last_indexer_call)
            if wait > 0:
                _global_time.sleep(wait)
            try:
                _last_indexer_call = _global_time.time()
                return fn(*args, **kwargs)
            except Exception as e:
                err_str = str(e)
                if 'Too Many Requests' in err_str or '1000' in err_str:
                    sleep_time = 10 * (attempt + 1)
                    print(f"Rate limit hit, sleeping {sleep_time}s (attempt {attempt+1})")
                    _global_time.sleep(sleep_time)
                    _last_indexer_call = _global_time.time()
                    continue
                raise
        raise Exception("Rate limit: max retries exceeded")

# === STATS CACHE ===
_stats_cache = {}
_history_cache = {}  # кеш для /api/history
_HISTORY_TTL = 600  # 10 минут
_matches_cache = {}  # глобальный кеш матчей {wallet: (ts, all_matches)}
_events_cache = {}   # кеш match_orders events {wallet: (ts, idx_to_ev)}
_EVENTS_TTL = 600    # 10 минут

import time as _time_retry

def _indexer_call_with_retry(fn, max_retries=4, base_delay=5):
    """Вызов к индексеру с retry при rate limit (429/Too Many Requests)"""
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            err_str = str(e)
            if 'Too Many Requests' in err_str or '1000' in err_str or 'rate' in err_str.lower():
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # 5, 10, 20, 40 сек
                    time.sleep(delay)
                    continue
            raise
    raise Exception("Max retries exceeded for indexer call")

_MATCHES_TTL = 300
_STATS_TTL = 300

def get_dashboard(wallet_num=1):
    if wallet_num not in _dashboards:
        _dashboards[wallet_num] = MultiWalletDashboard()
    d = _dashboards[wallet_num]
    d.active_wallet = wallet_num
    return d

@app.route('/')
def index():
    return send_from_directory('/root/trading_bot/webapp', 'index.html')

@app.route('/api/health')
def health():
    return jsonify({'ok': True, 'status': 'running'})

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
                entry_price = p.get('entry_price') or 0
                current_price = p.get('price') or 0
                size = abs(amount)
                raw_pnl = p.get('unrealized_pnl')
                if raw_pnl is not None and current_price:
                    unrealized_pnl = current_price * amount + raw_pnl
                elif entry_price and current_price and size:
                    if side == 'LONG':
                        unrealized_pnl = (current_price - entry_price) * size
                    else:
                        unrealized_pnl = (entry_price - current_price) * size
                else:
                    unrealized_pnl = 0.0
                result.append({
                    'product_id': p.get('product_id', 0),
                    'symbol': symbol,
                    'side': side,
                    'size': size,
                    'entry_price': float(entry_price),
                    'current_price': float(current_price),
                    'unrealized_pnl': round(unrealized_pnl, 4),
                })
            except Exception as pe:
                logger.warning(f"Position parse error: {pe}")
        return jsonify({'ok': True, 'positions': result})
    except Exception as e:
        logger.error(f"Positions error: {e}", exc_info=True)
        return jsonify({'ok': False, 'error': str(e)})

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
        result = dash.place_order(product_id=product_id, size=Decimal(str(size)), is_long=is_long)
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


@app.route('/api/history')
def api_history():
    try:
        import time as _th, re as _re_h
        from collections import defaultdict
        from datetime import datetime
        from nado_protocol.indexer_client.types.query import IndexerMatchesParams, IndexerEventsParams

        wallet = int(request.args.get('wallet', 1))
        limit  = int(request.args.get('limit', 20))
        now_h  = _th.time()

        # --- Кэш ---
        _hcache_key = wallet
        if _hcache_key in _history_cache:
            _hcached_ts, _hcached = _history_cache[_hcache_key]
            if now_h - _hcached_ts < _HISTORY_TTL:
                return jsonify(_hcached)

        dash = get_dashboard(wallet)
        w    = dash.wallets[wallet]
        indexer   = w.client.context.indexer_client
        subaccount = w.sender_hex
        D = 1e18

        # --- Матчи: из matches_cache (общий с /api/stats) ---
        _mc = _matches_cache.get(wallet)
        if _mc and (now_h - _mc[0]) < 600:
            all_matches = _mc[1]
        else:
            _th.sleep(0.3)
            batch = indexer.get_matches(IndexerMatchesParams(subaccounts=[subaccount], limit=500))
            all_matches = batch.matches if batch.matches else []
            _matches_cache[wallet] = (now_h, all_matches)

        # --- Events с vq_delta: отдельный кэш ---
        _ev_cache_key = f'ev_{wallet}'
        _ev_cache = _history_cache.get(_ev_cache_key)
        if _ev_cache and (now_h - _ev_cache[0]) < 600:
            idx_to_ev = _ev_cache[1]
        else:
            _th.sleep(0.5)
            evs = indexer.get_events(IndexerEventsParams(
                subaccounts=[subaccount], event_types=['match_orders']
            ))
            def _vq(bal):
                if bal is None: return None
                m2 = _re_h.search(r"v_quote_balance='(-?\d+)'", str(bal))
                return int(m2.group(1)) / D if m2 else None
            def _amt(bal):
                if bal is None: return None
                m2 = _re_h.search(r"amount='(-?\d+)'", str(bal))
                return int(m2.group(1)) / D if m2 else None
            idx_to_ev = {}
            for ev in evs.events:
                if not ev.product_id: continue
                pre_vq  = _vq(getattr(ev, 'pre_balance',  None))
                post_vq = _vq(getattr(ev, 'post_balance', None))
                pre_amt = _amt(getattr(ev, 'pre_balance',  None))
                post_amt= _amt(getattr(ev, 'post_balance', None))
                vq_d = (post_vq - pre_vq) if (pre_vq is not None and post_vq is not None) else 0.0
                idx_to_ev[int(ev.submission_idx)] = {
                    'pid': int(ev.product_id),
                    'vq_delta': vq_d,
                    'pre_amt':  pre_amt  or 0,
                    'post_amt': post_amt or 0,
                    'pre_vq':   pre_vq   or 0,
                    'post_vq':  post_vq  or 0,
                }
            _history_cache[_ev_cache_key] = (now_h, idx_to_ev)

        idx_to_pid = {idx: d2['pid'] for idx, d2 in idx_to_ev.items()}

        # --- Группируем матчи по nonce ---
        orders = defaultdict(list)
        for m in all_matches:
            nonce = str(m.order.nonce) if m.order else str(m.submission_idx)
            orders[nonce].append(m)

        # --- FIFO PnL: прогоняем ВСЕ ордера хронологически ---
        all_orders_chrono = sorted(orders.items(),
                                   key=lambda x: min(int(m.submission_idx) for m in x[1]))
        fifo = {}  # sym -> {pos, cost}
        pnl_by_nonce = {}
        for _nonce, _ms in all_orders_chrono:
            _ms_s = sorted(_ms, key=lambda m: int(m.submission_idx))
            _base  = sum(int(m.base_filled)  for m in _ms_s) / D
            _quote = sum(int(m.quote_filled)  for m in _ms_s) / D
            _fee   = sum(abs(int(m.fee))      for m in _ms_s) / D
            _pid   = next((idx_to_pid[int(m.submission_idx)]
                           for m in _ms_s if int(m.submission_idx) in idx_to_pid), 0)
            _sym   = ID_TO_SYMBOL.get(_pid, f'P{_pid}')
            if _sym not in fifo:
                fifo[_sym] = {'pos': 0.0, 'cost': 0.0}
            fs = fifo[_sym]
            _rem_base  = _base
            _rem_quote = abs(_quote)
            _realized  = 0.0
            # закрытие LONG
            if _rem_base < 0 and fs['pos'] > 0.001:
                _cq = min(abs(_rem_base), fs['pos'])
                _frac = _cq / fs['pos']
                _cb = fs['cost'] * _frac
                _qc = _rem_quote * (_cq / abs(_base)) if _base else _rem_quote
                _realized += _qc - _cb
                fs['cost'] = fs['cost'] * (1 - _frac)
                fs['pos']  -= _cq
                _rem_base  += _cq
                _rem_quote -= _qc
            # закрытие SHORT
            elif _rem_base > 0 and fs['pos'] < -0.001:
                _cq = min(_rem_base, abs(fs['pos']))
                _frac = _cq / abs(fs['pos'])
                _cb = fs['cost'] * _frac
                _qc = _rem_quote * (_cq / abs(_base)) if _base else _rem_quote
                _realized += _cb - _qc
                fs['cost'] = fs['cost'] * (1 - _frac)
                fs['pos']  += _cq
                _rem_base  -= _cq
                _rem_quote -= _qc
            # остаток — открытие
            if abs(_rem_base) > 0.0001:
                fs['pos']  += _rem_base
                fs['cost'] += _rem_quote
            pnl_by_nonce[_nonce] = round(_realized - _fee, 4) if abs(_realized) > 0.0001 else round(-_fee, 4)

        # --- display_orders: limit новых ---
        display_orders = sorted(orders.items(),
                                key=lambda x: max(int(m.submission_idx) for m in x[1]),
                                reverse=True)[:limit]

        trades = []
        for nonce, ms in display_orders:
            ms_s = sorted(ms, key=lambda m: int(m.submission_idx))
            total_base  = sum(int(m.base_filled)  for m in ms_s) / D
            total_quote = sum(int(m.quote_filled)  for m in ms_s) / D
            total_fee   = sum(abs(int(m.fee))      for m in ms_s) / D
            pid = next((idx_to_pid[int(m.submission_idx)]
                        for m in ms_s if int(m.submission_idx) in idx_to_pid), 0)
            symbol   = ID_TO_SYMBOL.get(pid, f'PID{pid}')
            size     = abs(total_base)
            side     = 'LONG' if total_base > 0 else 'SHORT'
            avg_price = abs(total_quote) / size if size > 0 else 0
            net_pnl  = pnl_by_nonce.get(nonce, round(-total_fee, 4))
            # Дата через nonce>>20 (timestamp ms создания ордера)
            date_str = '??-?? ??:??'
            for m in ms_s:
                try:
                    nv = int(m.order.nonce) if m.order and m.order.nonce else 0
                    ts_ms = nv >> 20
                    if 1700000000000 < ts_ms < 2100000000000:
                        date_str = datetime.fromtimestamp(ts_ms / 1000).strftime('%m-%d %H:%M')
                        break
                except Exception:
                    pass
            trades.append({
                'symbol': symbol, 'side': side,
                'size': round(size, 4),
                'volume_usd': round(abs(total_quote), 2),
                'avg_price': round(avg_price, 2),
                'fee': round(total_fee, 4),
                'net_pnl': net_pnl,
                'date': date_str,
                'submission_idx': max(int(m.submission_idx) for m in ms_s),
            })

        result_h = {'ok': True, 'trades': trades}
        _history_cache[_hcache_key] = (now_h, result_h)
        return jsonify(result_h)
    except Exception as e:
        logger.error(f"History error: {e}", exc_info=True)
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/stats')
def api_stats():
    try:
        import re as _re_s
        from nado_protocol.indexer_client.types.query import (
            IndexerAccountSnapshotsParams, IndexerMatchesParams
        )
        from datetime import datetime, timedelta, timezone
        import bisect as _bisect

        wallet = int(request.args.get('wallet', 1))
        now_ts = int(time.time())

        # === КЕШ ===
        cache_key = wallet
        if cache_key in _stats_cache:
            cached_ts, cached_data = _stats_cache[cache_key]
            if now_ts - cached_ts < _STATS_TTL:
                return jsonify(cached_data)

        dash = get_dashboard(wallet)
        w = dash.wallets[wallet]
        indexer = w.client.context.indexer_client
        subaccount = w.sender_hex
        day = 86400

        # === СНАПШОТЫ ===
        snap_timestamps = [now_ts - i * day for i in range(31)]
        snaps = indexer.get_multi_subaccount_snapshots(
            IndexerAccountSnapshotsParams(subaccounts=[subaccount], timestamps=snap_timestamps)
        )
        snap_data = snaps.snapshots.get(subaccount, {})
        tss = sorted(snap_data.keys(), reverse=True)

        def parse_snap_vol(events):
            vol = 0
            for ev in events:
                if ev.product_id == 0: continue
                vol += abs(int(ev.quote_volume_cumulative or 0)) / D
            return vol

        def get_snap_idx(ts_key):
            evs = snap_data.get(ts_key, [])
            idxs = [int(ev.submission_idx) for ev in evs if ev.submission_idx]
            return max(idxs) if idxs else 0

        vol_now = parse_snap_vol(snap_data[tss[0]]) if tss else 0
        idx_24h = get_snap_idx(tss[1]) if len(tss) > 1 else 0
        idx_7d  = get_snap_idx(tss[7]) if len(tss) > 7 else 0
        idx_30d = get_snap_idx(tss[30]) if len(tss) > 30 else 0

        vol_24h = vol_now - parse_snap_vol(snap_data[tss[1]])  if len(tss) > 1 else 0
        vol_7d  = vol_now - parse_snap_vol(snap_data[tss[7]])  if len(tss) > 7 else 0
        vol_30d = vol_now - parse_snap_vol(snap_data[tss[30]]) if len(tss) > 30 else 0

        # === ВСЕ МАТЧИ (пагинация + shared cache) ===
        _mc_s = _matches_cache.get(wallet)
        if _mc_s and (now_ts - _mc_s[0]) < _MATCHES_TTL:
            all_matches = _mc_s[1]
        else:
            all_matches = []
            start_idx = None
            for _ in range(20):
                if start_idx:
                    params = IndexerMatchesParams(subaccounts=[subaccount], limit=500, max_submission_idx=start_idx)
                else:
                    params = IndexerMatchesParams(subaccounts=[subaccount], limit=500)
                batch = indexer.get_matches(params)
                if not batch.matches: break
                all_matches.extend(batch.matches)
                min_idx = min(int(m.submission_idx) for m in batch.matches)
                if len(batch.matches) < 500: break
                start_idx = min_idx - 1
            _matches_cache[wallet] = (now_ts, all_matches)

        def calc_matches(matches, idx_from):
            fees = count = 0
            for m in matches:
                if int(m.submission_idx) <= idx_from: continue
                fees += abs(int(m.fee)) / D
                count += 1
            return {'fees': round(fees, 4), 'count': count}

        m24h = calc_matches(all_matches, idx_24h)
        m7d  = calc_matches(all_matches, idx_7d)
        m30d = calc_matches(all_matches, idx_30d)
        mall = calc_matches(all_matches, 0)

        # === ТЕКУЩАЯ EQUITY ===
        try:
            summary_now = w.client.subaccount.get_engine_subaccount_summary(subaccount)
            equity_now = float(summary_now.healths[2].health) / D if hasattr(summary_now, 'healths') and len(summary_now.healths) > 2 else 0
        except Exception:
            equity_now = 0

        if equity_now:
            save_equity_point(wallet, equity_now)

        # === PnL КАРТОЧКИ ===
        # initial_deposit = pid5 USDC баланс из снапшота (стабилен ~498)
        def get_usdc5_balance(ts_key):
            for ev in snap_data.get(ts_key, []):
                try:
                    if int(ev.product_id) == 5:
                        m2 = _re_s.search(r"amount='(-?\d+)'", str(getattr(ev, 'post_balance', '') or ''))
                        if m2:
                            val = int(m2.group(1)) / D
                            if val > 10: return val
                except Exception: pass
            return None

        # Spot-only equity из снапшота (pid0 + pid5, без perp unrealized)
        def snap_equity_spot_only(day_i):
            if day_i >= len(tss): return None
            total = 0; found = False
            for ev in snap_data.get(tss[day_i], []):
                try:
                    if int(ev.product_id) in (0, 5):
                        m2 = _re_s.search(r"amount='(-?\d+)'", str(getattr(ev, 'post_balance', '') or ''))
                        if m2:
                            total += int(m2.group(1)) / D
                            found = True
                except Exception: pass
            return total if found else None

        initial_deposit = None
        for ts_key in tss:
            b5 = get_usdc5_balance(ts_key)
            if b5 is not None:
                initial_deposit = b5
                break

        pnl_all = round(equity_now - initial_deposit, 4) if initial_deposit else 0
        pnl_30d = pnl_all

        eq_24h_ago = get_equity_at(wallet, now_ts - 86400)
        eq_7d_ago  = get_equity_at(wallet, now_ts - 7 * 86400)

        if eq_24h_ago is not None:
            pnl_24h = round(equity_now - eq_24h_ago, 4)
        else:
            # spot_only снапшот: pid5 USDC залог (стабилен) - сравниваем с yesterday
            # Проблема: снапшот 02:43 UTC может включать unrealized perp
            # Используем pid5 только (deposit, стабильный) для грубой оценки
            eq_snap_24h = snap_equity_spot_only(1)
            if eq_snap_24h and abs(eq_snap_24h - (initial_deposit or 499)) < 50:
                # Снапшот стабильный (нет большого unrealized) — используем
                pnl_24h = round(equity_now - eq_snap_24h, 4)
            else:
                # Снапшот нестабильный (открытая позиция с большим unrealized)
                # Используем только fees как нижнюю границу PnL
                pnl_24h = round(-m24h['fees'], 4)

        if eq_7d_ago is not None:
            pnl_7d = round(equity_now - eq_7d_ago, 4)
        else:
            eq_snap_7d = snap_equity_spot_only(min(7, len(tss)-1))
            pnl_7d = round(equity_now - eq_snap_7d, 4) if eq_snap_7d else round(-m7d['fees'], 4)

        # Win rate
        def win_rate_for_period(days_period):
            cutoff_idx = {1: idx_24h, 7: idx_7d, 30: idx_30d}.get(days_period, 0)
            wins = losses = 0
            from collections import defaultdict as _dd
            orders_p = _dd(list)
            for m in all_matches:
                if int(m.submission_idx) <= cutoff_idx: continue
                nonce = str(m.order.nonce) if m.order else str(m.submission_idx)
                orders_p[nonce].append(m)
            for nonce, ms in orders_p.items():
                tb = sum(int(m.base_filled) for m in ms) / D
                tq = sum(int(m.quote_filled) for m in ms) / D
                tf = sum(abs(int(m.fee)) for m in ms) / D
                if abs(tb) < 0.0001: continue
                avg_p = abs(tq) / abs(tb)
                if tb < 0 and avg_p > 0:
                    wins += 1
                elif tb < 0:
                    losses += 1
            total = wins + losses
            return round(wins / total * 100, 1) if total > 0 else 0

        # === ГРАФИКИ ===
        now_dt = datetime.now(timezone.utc)
        _m_sorted = sorted(all_matches, key=lambda x: int(x.submission_idx))
        _m_idxs = [int(m.submission_idx) for m in _m_sorted]
        _fees_cum = []
        _fs = 0
        for _m in _m_sorted:
            _fs += abs(int(_m.fee)) / D
            _fees_cum.append(_fs)

        def _fees_before(idx):
            if not _m_idxs: return 0
            pos = _bisect.bisect_right(_m_idxs, idx) - 1
            return _fees_cum[pos] if pos >= 0 else 0

        def get_snap_idx_for_day(day_i):
            if day_i >= len(tss): return 0
            evs = snap_data.get(tss[day_i], [])
            idxs = [int(ev.submission_idx) for ev in evs if ev.submission_idx]
            return max(idxs) if idxs else 0

        def build_chart_for_period(days, n_points):
            pts = []
            base_snap_i = min(days, len(tss) - 1)
            base_vol_v = parse_snap_vol(snap_data[tss[base_snap_i]]) if base_snap_i < len(tss) else 0
            base_idx = get_snap_idx_for_day(base_snap_i)

            if days <= 1:
                base_eq_v = eq_24h_ago if eq_24h_ago is not None else (snap_equity_spot_only(1) or equity_now)
            elif days <= 7:
                base_eq_v = eq_7d_ago if eq_7d_ago is not None else (snap_equity_spot_only(min(7, len(tss)-1)) or equity_now)
            else:
                base_eq_v = initial_deposit if initial_deposit else equity_now

            for step in range(n_points):
                frac = step / max(n_points - 1, 1)
                snap_offset = int((1 - frac) * base_snap_i)
                snap_offset = min(snap_offset, len(tss) - 1)
                step_idx = get_snap_idx_for_day(snap_offset)

                date_dt = now_dt - timedelta(days=(1 - frac) * days)
                if days <= 1:   date_str = date_dt.strftime('%H:%M')
                elif days <= 7: date_str = date_dt.strftime('%a %d')
                else:           date_str = date_dt.strftime('%b %d')

                if step == n_points - 1:
                    vol_cum = round(vol_now - base_vol_v, 2)
                    pnl_cum = round(pnl_all, 4) if days > 7 else round(equity_now - base_eq_v, 4)
                else:
                    vol_at = parse_snap_vol(snap_data[tss[snap_offset]]) if snap_offset < len(tss) and tss[snap_offset] in snap_data else base_vol_v
                    vol_cum = round(max(vol_at - base_vol_v, 0), 2)
                    if days <= 7:
                        pnl_cum = round((equity_now - base_eq_v) * frac, 4)
                    else:
                        eq_step = snap_equity_spot_only(snap_offset)
                        if eq_step is not None and initial_deposit is not None:
                            pnl_cum = round(eq_step - initial_deposit, 4)
                        else:
                            pnl_cum = round((equity_now - base_eq_v) * frac, 4)

                pts.append({'date': date_str, 'volume': max(vol_cum, 0), 'pnl': pnl_cum})
            return pts

        charts = {
            '24h': build_chart_for_period(1, 24),
            '7d':  build_chart_for_period(7, 28),
            '30d': build_chart_for_period(30, 30),
            'all': build_chart_for_period(min(len(tss)-1, 30), 30),
        }

        result = {
            'ok': True,
            'equity': round(equity_now, 2),
            'periods': {
                '24h': {'pnl': pnl_24h, 'volume': round(vol_24h, 2), 'trades': m24h['count'], 'fees': m24h['fees'], 'win_rate': 0},
                '7d':  {'pnl': pnl_7d,  'volume': round(vol_7d, 2),  'trades': m7d['count'],  'fees': m7d['fees'],  'win_rate': 0},
                '30d': {'pnl': pnl_30d, 'volume': round(vol_30d, 2), 'trades': m30d['count'], 'fees': m30d['fees'], 'win_rate': 0},
                'all': {'pnl': pnl_all, 'volume': round(vol_now, 2), 'trades': mall['count'], 'fees': mall['fees'],  'win_rate': 0},
            },
            'chart': charts['30d'],
            'charts': charts,
            'total_trades': mall['count'],
        }

        _stats_cache[cache_key] = (now_ts, result)
        return jsonify(result)

    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        return jsonify({'ok': False, 'error': str(e)})


def _preload_cache():
    """Фоновая предзагрузка кэша при старте сервера"""
    import time as _pl_t
    _pl_t.sleep(5)  # даём серверу запуститься
    for wallet_num in [1, 2]:
        try:
            from nado_protocol.indexer_client.types.query import IndexerMatchesParams
            dash = get_dashboard(wallet_num)
            w = dash.wallets[wallet_num]
            indexer = w.client.context.indexer_client
            subaccount = w.sender_hex
            D = 1e18
            # Загружаем все матчи пагинацией
            all_matches = []
            start_idx = None
            for _ in range(25):
                params = IndexerMatchesParams(subaccounts=[subaccount], limit=100)
                if start_idx is not None:
                    params = IndexerMatchesParams(subaccounts=[subaccount], limit=100, max_idx=start_idx)
                batch = _throttled_indexer_call(indexer.get_matches, params)
                if not batch or not batch.matches:
                    break
                all_matches.extend(batch.matches)
                if len(batch.matches) < 100:
                    break
                start_idx = min(int(m.submission_idx) for m in batch.matches) - 1
                _pl_t.sleep(0.3)
            if all_matches:
                _matches_cache[wallet_num] = (_pl_t.time(), all_matches)
                print(f"[preload] wallet {wallet_num}: {len(all_matches)} matches cached")
        except Exception as e:
            print(f"[preload] wallet {wallet_num} error: {e}")

import threading as _threading
_preload_thread = _threading.Thread(target=_preload_cache, daemon=True)
_preload_thread.start()

if __name__ == '__main__':
    port = int(os.environ.get('WEBAPP_PORT', 8080))
    logger.info(f"Starting Mini App server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
