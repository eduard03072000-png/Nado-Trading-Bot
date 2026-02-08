"""
Менеджер истории торговли с правильным расчётом P&L
"""
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional


class TradeHistoryManager:
    def __init__(self, history_file='trade_history.json'):
        self.history_file = history_file
        self.trades = self.load_history()
    
    def load_history(self) -> List[Dict]:
        """Загрузить историю из файла"""
        if not os.path.exists(self.history_file):
            return []
        
        try:
            with open(self.history_file, 'r') as f:
                return json.load(f)
        except:
            return []
    
    def save_history(self):
        """Сохранить историю в файл"""
        with open(self.history_file, 'w') as f:
            json.dump(self.trades, f, indent=2)
    
    def add_trade(self, 
                  symbol: str,
                  product_id: int,
                  side: str,  # "LONG" или "SHORT"
                  entry_price: float,
                  exit_price: float,
                  size: float,  # Базовый размер БЕЗ плеча
                  leverage: int,
                  entry_fee: float = 0,
                  exit_fee: float = 0,
                  timestamp: Optional[str] = None):
        """
        Добавить сделку с правильным расчётом P&L
        
        Args:
            symbol: Символ (например "SOL-PERP")
            product_id: ID продукта
            side: "LONG" или "SHORT"
            entry_price: Цена входа
            exit_price: Цена выхода
            size: Базовый размер БЕЗ плеча
            leverage: Плечо
            entry_fee: Комиссия входа (в USD)
            exit_fee: Комиссия выхода (в USD)
            timestamp: Время сделки (если None - текущее)
        """
        # Размер позиции С ПЛЕЧОМ
        position_size = size * leverage
        
        # Расчёт P&L
        if side == "LONG":
            # LONG: профит = (exit - entry) * size
            raw_pnl = (exit_price - entry_price) * position_size
        else:
            # SHORT: профит = (entry - exit) * size
            raw_pnl = (entry_price - exit_price) * position_size
        
        # Вычитаем комиссии
        net_pnl = raw_pnl - entry_fee - exit_fee
        
        # Процент от входа
        pnl_percent = (raw_pnl / (entry_price * position_size)) * 100
        
        # ROI от вложенного капитала (без плеча)
        invested_capital = entry_price * size
        roi_percent = (net_pnl / invested_capital) * 100
        
        trade = {
            'timestamp': timestamp or datetime.now().isoformat(),
            'symbol': symbol,
            'product_id': product_id,
            'side': side,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'size': size,  # Базовый размер
            'position_size': position_size,  # С плечом
            'leverage': leverage,
            'entry_fee': entry_fee,
            'exit_fee': exit_fee,
            'raw_pnl': raw_pnl,
            'net_pnl': net_pnl,
            'pnl_percent': pnl_percent,
            'roi_percent': roi_percent
        }
        
        self.trades.append(trade)
        self.save_history()
        
        return trade
    
    def get_trades_by_period(self, period: str) -> List[Dict]:
        """
        Получить сделки за период
        
        Args:
            period: "today", "yesterday", "week", "month", "all"
        """
        now = datetime.now()
        
        if period == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "yesterday":
            yesterday = now - timedelta(days=1)
            start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif period == "week":
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:  # "all"
            return self.trades
        
        # Фильтруем по дате
        filtered = []
        for trade in self.trades:
            trade_time = datetime.fromisoformat(trade['timestamp'])
            
            if period == "yesterday":
                if start <= trade_time < end:
                    filtered.append(trade)
            else:
                if trade_time >= start:
                    filtered.append(trade)
        
        return filtered
    
    def get_statistics(self, period: str = "all") -> Dict:
        """
        Получить статистику за период
        
        Returns:
            {
                'total_trades': int,
                'winning_trades': int,
                'losing_trades': int,
                'win_rate': float,
                'total_pnl': float,
                'total_fees': float,
                'avg_pnl': float,
                'avg_roi': float,
                'best_trade': float,
                'worst_trade': float,
                'total_volume': float
            }
        """
        trades = self.get_trades_by_period(period)
        
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'total_fees': 0,
                'avg_pnl': 0,
                'avg_roi': 0,
                'best_trade': 0,
                'worst_trade': 0,
                'total_volume': 0
            }
        
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t['net_pnl'] > 0)
        losing_trades = sum(1 for t in trades if t['net_pnl'] < 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        total_pnl = sum(t['net_pnl'] for t in trades)
        total_fees = sum(t['entry_fee'] + t['exit_fee'] for t in trades)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        
        roi_values = [t['roi_percent'] for t in trades]
        avg_roi = sum(roi_values) / len(roi_values) if roi_values else 0
        
        pnl_values = [t['net_pnl'] for t in trades]
        best_trade = max(pnl_values) if pnl_values else 0
        worst_trade = min(pnl_values) if pnl_values else 0
        
        total_volume = sum(t['entry_price'] * t['position_size'] for t in trades)
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'total_fees': total_fees,
            'avg_pnl': avg_pnl,
            'avg_roi': avg_roi,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'total_volume': total_volume
        }
    
    def clear_history(self):
        """Очистить всю историю"""
        self.trades = []
        self.save_history()
