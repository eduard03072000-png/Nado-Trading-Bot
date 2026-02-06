"""
База данных для хранения статистики торговли
SQLite database для всех сделок и аналитики
"""
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TradingDatabase:
    """
    Класс для работы с базой данных торговой статистики
    """
    
    def __init__(self, db_path: str = "data/trading.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = None
        self._init_database()
    
    def _init_database(self):
        """Инициализация базы данных"""
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        cursor = self.connection.cursor()
        
        # Таблица сделок
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT UNIQUE,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                size REAL NOT NULL,
                leverage INTEGER DEFAULT 1,
                take_profit REAL,
                stop_loss REAL,
                profit REAL DEFAULT 0,
                profit_percent REAL DEFAULT 0,
                status TEXT DEFAULT 'open',
                open_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                close_time TIMESTAMP,
                strategy TEXT,
                notes TEXT
            )
        """)
        
        # Таблица дневной статистики
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                total_trades INTEGER DEFAULT 0,
                profitable_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                total_volume REAL DEFAULT 0,
                total_profit REAL DEFAULT 0,
                win_rate REAL DEFAULT 0,
                avg_profit REAL DEFAULT 0,
                max_profit REAL DEFAULT 0,
                max_loss REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица событий
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                description TEXT,
                data TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.connection.commit()
        logger.info("✅ База данных инициализирована")
    
    def add_trade(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        entry_price: Decimal,
        size: Decimal,
        leverage: int = 1,
        take_profit: Decimal = None,
        stop_loss: Decimal = None,
        strategy: str = None
    ) -> bool:
        """Добавить новую сделку"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO trades (
                    trade_id, symbol, side, entry_price, size, leverage,
                    take_profit, stop_loss, strategy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_id, symbol, side, float(entry_price), float(size), leverage,
                float(take_profit) if take_profit else None,
                float(stop_loss) if stop_loss else None,
                strategy
            ))
            self.connection.commit()
            logger.info(f"✅ Сделка добавлена в БД: {trade_id}")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"⚠️ Сделка {trade_id} уже существует")
            return False
        except Exception as e:
            logger.error(f"Ошибка добавления сделки: {e}")
            return False
    
    def close_trade(
        self,
        trade_id: str,
        exit_price: Decimal,
        profit: Decimal,
        profit_percent: Decimal
    ) -> bool:
        """Закрыть сделку"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                UPDATE trades SET
                    exit_price = ?,
                    profit = ?,
                    profit_percent = ?,
                    status = 'closed',
                    close_time = CURRENT_TIMESTAMP
                WHERE trade_id = ?
            """, (float(exit_price), float(profit), float(profit_percent), trade_id))
            self.connection.commit()
            
            # Обновляем дневную статистику
            self._update_daily_stats()
            
            logger.info(f"✅ Сделка закрыта: {trade_id}, прибыль: {profit}")
            return True
        except Exception as e:
            logger.error(f"Ошибка закрытия сделки: {e}")
            return False
    
    def get_open_trades(self) -> List[Dict]:
        """Получить все открытые сделки"""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM trades WHERE status = 'open' ORDER BY open_time DESC")
        return [dict(row) for row in cursor.fetchall()]
    
    def get_today_stats(self) -> Dict:
        """Получить статистику за сегодня"""
        today = datetime.now().strftime('%Y-%m-%d')
        cursor = self.connection.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as profitable_trades,
                SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(size * entry_price) as total_volume,
                SUM(profit) as total_profit,
                AVG(profit) as avg_profit,
                MAX(profit) as max_profit,
                MIN(profit) as min_profit
            FROM trades
            WHERE DATE(close_time) = ? AND status = 'closed'
        """, (today,))
        
        row = cursor.fetchone()
        if row:
            total = row['total_trades'] or 0
            profitable = row['profitable_trades'] or 0
            win_rate = (profitable / total * 100) if total > 0 else 0
            
            return {
                'total_trades': total,
                'profitable_trades': profitable,
                'losing_trades': row['losing_trades'] or 0,
                'total_volume': row['total_volume'] or 0,
                'total_profit': row['total_profit'] or 0,
                'avg_profit': row['avg_profit'] or 0,
                'max_profit': row['max_profit'] or 0,
                'min_profit': row['min_profit'] or 0,
                'win_rate': win_rate
            }
        return {}
    
    def get_all_time_stats(self) -> Dict:
        """Получить статистику за все время"""
        cursor = self.connection.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as profitable_trades,
                SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(size * entry_price) as total_volume,
                SUM(profit) as total_profit,
                AVG(profit) as avg_profit,
                MAX(profit) as max_profit,
                MIN(profit) as min_profit
            FROM trades
            WHERE status = 'closed'
        """)
        
        row = cursor.fetchone()
        if row:
            total = row['total_trades'] or 0
            profitable = row['profitable_trades'] or 0
            win_rate = (profitable / total * 100) if total > 0 else 0
            
            return {
                'total_trades': total,
                'profitable_trades': profitable,
                'losing_trades': row['losing_trades'] or 0,
                'total_volume': row['total_volume'] or 0,
                'total_profit': row['total_profit'] or 0,
                'avg_profit': row['avg_profit'] or 0,
                'max_profit': row['max_profit'] or 0,
                'min_profit': row['min_profit'] or 0,
                'win_rate': win_rate
            }
        return {}
    
    def get_recent_trades(self, limit: int = 50) -> List[Dict]:
        """Получить последние сделки"""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM trades 
            WHERE status = 'closed'
            ORDER BY close_time DESC 
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
    
    def _update_daily_stats(self):
        """Обновить дневную статистику"""
        today = datetime.now().strftime('%Y-%m-%d')
        stats = self.get_today_stats()
        
        if not stats:
            return
        
        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO daily_stats (
                date, total_trades, profitable_trades, losing_trades,
                total_volume, total_profit, win_rate, avg_profit,
                max_profit, max_loss
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            today,
            stats['total_trades'],
            stats['profitable_trades'],
            stats['losing_trades'],
            stats['total_volume'],
            stats['total_profit'],
            stats['win_rate'],
            stats['avg_profit'],
            stats['max_profit'],
            abs(stats['min_profit'])
        ))
        self.connection.commit()
    
    def add_event(self, event_type: str, description: str, data: str = None):
        """Добавить событие в лог"""
        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO events (event_type, description, data)
            VALUES (?, ?, ?)
        """, (event_type, description, data))
        self.connection.commit()
    
    def get_daily_stats_history(self, days: int = 30) -> List[Dict]:
        """Получить историю дневной статистики"""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM daily_stats
            ORDER BY date DESC
            LIMIT ?
        """, (days,))
        return [dict(row) for row in cursor.fetchall()]
    
    def close(self):
        """Закрыть соединение с БД"""
        if self.connection:
            self.connection.close()
            logger.info("🔒 Соединение с БД закрыто")
