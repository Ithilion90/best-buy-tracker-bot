import sqlite3
import os
from typing import List, Dict, Optional, Any, Tuple
from contextlib import contextmanager
from datetime import datetime, timedelta

try:
    from .config import config
    from .logger import logger
    from .resilience import circuit_breakers
except ImportError:
    from config import config
    from logger import logger
    from resilience import circuit_breakers

def get_db_path() -> str:
    if hasattr(config, 'frozen') and config.frozen:
        return os.path.join(os.path.dirname(config.executable_path), "tracker.db")
    return config.database_path

@contextmanager
def get_db_connection():
    """Get database connection with circuit breaker protection"""
    try:
        conn = circuit_breakers['database'].call(sqlite3.connect, get_db_path())
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")  # Better performance
        yield conn
    except Exception as e:
        logger.error("Database connection failed", error=str(e))
        raise
    finally:
        if 'conn' in locals():
            conn.close()

def init_db() -> None:
    """Initialize database with improved schema and indices"""
    with get_db_connection() as conn:
        # Check if this is a fresh database
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        is_fresh_db = len(tables) == 0
        
        if is_fresh_db:
            # Fresh database - create new schema
            _create_fresh_schema(conn)
        else:
            # Existing database - migrate if needed
            _migrate_existing_schema(conn)
        
        # Create indices (safe to run multiple times)
        _create_indices(conn)
        
        conn.commit()
        logger.info("Database initialized successfully", fresh_db=is_fresh_db)

def _create_fresh_schema(conn):
    """Create fresh database schema"""
    # Users table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            settings TEXT DEFAULT '{}'
        )
    """)
    
    # Items table with enhanced fields
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            asin TEXT,
            title TEXT,
            currency TEXT DEFAULT 'EUR',
            last_price REAL,
            min_price REAL,
            max_price REAL,
            target_price REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_checked TIMESTAMP,
            check_count INTEGER DEFAULT 0,
            notification_sent_at TIMESTAMP,
            category TEXT,
            priority INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)
    
    # Price history with more details
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            price REAL NOT NULL,
            currency TEXT DEFAULT 'EUR',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'scraping',
            availability TEXT,
            FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE CASCADE
        )
    """)
    
    # User statistics table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            items_tracked INTEGER DEFAULT 0,
            total_savings REAL DEFAULT 0.0,
            notifications_sent INTEGER DEFAULT 0,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_checks INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)
    
    # System metrics table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS system_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT
        )
    """)

def _migrate_existing_schema(conn):
    """Migrate existing database schema"""
    # Get existing columns for items table
    cursor = conn.execute("PRAGMA table_info(items)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    # Add new columns if they don't exist
    new_columns = {
        'last_checked': 'TIMESTAMP',
        'check_count': 'INTEGER DEFAULT 0',
        'notification_sent_at': 'TIMESTAMP',
        'category': 'TEXT',
        'priority': 'INTEGER DEFAULT 1',
        'is_active': 'BOOLEAN DEFAULT 1'
    }
    
    for column_name, column_def in new_columns.items():
        if column_name not in existing_columns:
            try:
                conn.execute(f"ALTER TABLE items ADD COLUMN {column_name} {column_def}")
                logger.info("Added column to items table", column=column_name)
            except Exception as e:
                logger.warning("Failed to add column", column=column_name, error=str(e))
    
    # Create new tables if they don't exist
    _create_fresh_schema(conn)  # This will only create missing tables

def _create_indices(conn):
    """Create database indices (safe to run multiple times)"""
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_items_user_id ON items(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_items_asin ON items(asin)",
        "CREATE INDEX IF NOT EXISTS idx_price_history_item_id ON price_history(item_id)",
        "CREATE INDEX IF NOT EXISTS idx_price_history_timestamp ON price_history(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)"
    ]
    
    # Only add indices for columns that exist
    cursor = conn.execute("PRAGMA table_info(items)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    if 'is_active' in existing_columns:
        indices.append("CREATE INDEX IF NOT EXISTS idx_items_active ON items(is_active)")
    if 'last_checked' in existing_columns:
        indices.append("CREATE INDEX IF NOT EXISTS idx_items_last_checked ON items(last_checked)")
    
    # System metrics indices
    try:
        conn.execute("SELECT 1 FROM system_metrics LIMIT 1")
        indices.append("CREATE INDEX IF NOT EXISTS idx_system_metrics_name_time ON system_metrics(metric_name, timestamp)")
    except:
        pass  # Table doesn't exist yet
    
    for index_sql in indices:
        try:
            conn.execute(index_sql)
        except Exception as e:
            logger.warning("Failed to create index", sql=index_sql, error=str(e))

def ensure_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> None:
    """Ensure user exists with enhanced tracking"""
    with get_db_connection() as conn:
        # Check if user exists
        existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        
        if not existing:
            conn.execute("""
                INSERT INTO users (id, username, first_name, last_name, created_at, last_active)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (user_id, username, first_name, last_name))
            
            # Initialize user stats
            conn.execute("""
                INSERT INTO user_stats (user_id, items_tracked, total_savings, notifications_sent, last_activity, total_checks)
                VALUES (?, 0, 0.0, 0, CURRENT_TIMESTAMP, 0)
            """, (user_id,))
            
            logger.info("New user created", user_id=user_id, username=username)
        else:
            # Update last active time
            conn.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
            conn.execute("UPDATE user_stats SET last_activity = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        
        conn.commit()

def add_item(user_id: int, url: str, asin: str, title: str, currency: str, price: Optional[float], target_price: Optional[float] = None, category: str = None, priority: int = 1) -> int:
    """Add item with enhanced tracking"""
    with get_db_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO items (user_id, url, asin, title, currency, last_price, min_price, max_price, target_price, category, priority, last_checked, check_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
        """, (user_id, url, asin, title, currency, price, price, price, target_price, category, priority))
        
        item_id = cursor.lastrowid
        
        # Add to price history if price is available
        if price is not None:
            conn.execute("""
                INSERT INTO price_history (item_id, price, currency, source, availability)
                VALUES (?, ?, ?, 'scraping', 'in_stock')
            """, (item_id, price, currency))
        
        # Update user stats
        conn.execute("""
            UPDATE user_stats 
            SET items_tracked = items_tracked + 1, last_activity = CURRENT_TIMESTAMP 
            WHERE user_id = ?
        """, (user_id,))
        
        conn.commit()
        logger.info("Item added", user_id=user_id, item_id=item_id, asin=asin, price=price)
        return item_id

def list_items(user_id: int, include_inactive: bool = False) -> List[Dict[str, Any]]:
    """List user items with enhanced filtering"""
    with get_db_connection() as conn:
        where_clause = "WHERE user_id = ?"
        params = [user_id]
        
        if not include_inactive:
            where_clause += " AND is_active = 1"
        
        rows = conn.execute(f"""
            SELECT * FROM items 
            {where_clause}
            ORDER BY priority DESC, created_at ASC
        """, params).fetchall()
        
        return [dict(row) for row in rows]

def update_price(item_id: int, new_price: Optional[float], new_currency: str = None, new_title: str = None, availability: str = 'in_stock') -> None:
    """Update item price with enhanced tracking"""
    with get_db_connection() as conn:
        # Get current item data
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            return
        
        # Calculate new min/max
        current_min = item['min_price']
        current_max = item['max_price']
        savings = 0.0
        
        if new_price is not None:
            new_min = min(current_min, new_price) if current_min is not None else new_price
            new_max = max(current_max, new_price) if current_max is not None else new_price
            
            # Calculate savings if price dropped
            old_price = item['last_price']
            if old_price is not None and new_price < old_price:
                savings = old_price - new_price
                
                # Update user stats
                conn.execute("""
                    UPDATE user_stats 
                    SET total_savings = total_savings + ?, last_activity = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (savings, item['user_id']))
        else:
            new_min = current_min
            new_max = current_max
        
        # Update item
        update_fields = ["last_checked = CURRENT_TIMESTAMP", "check_count = check_count + 1"]
        update_values = []
        
        if new_price is not None:
            update_fields.extend(["last_price = ?", "min_price = ?", "max_price = ?"])
            update_values.extend([new_price, new_min, new_max])
        
        if new_currency:
            update_fields.append("currency = ?")
            update_values.append(new_currency)
        
        if new_title:
            update_fields.append("title = ?")
            update_values.append(new_title)
        
        update_values.append(item_id)
        
        conn.execute(f"""
            UPDATE items 
            SET {', '.join(update_fields)}
            WHERE id = ?
        """, update_values)
        
        # Add to price history
        if new_price is not None:
            conn.execute("""
                INSERT INTO price_history (item_id, price, currency, source, availability)
                VALUES (?, ?, ?, 'scraping', ?)
            """, (item_id, new_price, new_currency or item['currency'], availability))
        
        # Update system metrics
        conn.execute("""
            INSERT INTO system_metrics (metric_name, metric_value, metadata)
            VALUES ('price_check', 1, '{"item_id": ' || ? || '}')
        """, (item_id,))
        
        conn.commit()
        logger.info("Price updated", item_id=item_id, old_price=item['last_price'], new_price=new_price, savings=savings)

def remove_item(user_id: int, item_id: int) -> bool:
    """Remove item with stats update"""
    with get_db_connection() as conn:
        cursor = conn.execute("DELETE FROM items WHERE id = ? AND user_id = ?", (item_id, user_id))
        success = cursor.rowcount > 0
        
        if success:
            # Update user stats
            conn.execute("""
                UPDATE user_stats 
                SET items_tracked = items_tracked - 1, last_activity = CURRENT_TIMESTAMP 
                WHERE user_id = ?
            """, (user_id,))
            logger.info("Item removed", user_id=user_id, item_id=item_id)
        
        conn.commit()
        return success

def all_items() -> List[Dict[str, Any]]:
    """Get all active items for processing"""
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM items 
            WHERE is_active = 1 
            ORDER BY last_checked ASC
        """).fetchall()
        return [dict(row) for row in rows]

def get_all_items() -> List[Dict[str, Any]]:
    """Get all tracked items across all users"""
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM items 
            WHERE is_active = 1 
            ORDER BY last_checked ASC
        """).fetchall()
        return [dict(row) for row in rows]

def update_item_price(item_id: int, new_price: float) -> None:
    """Update item price"""
    with get_db_connection() as conn:
        conn.execute("""
            UPDATE items 
            SET last_price = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_price, item_id))
        conn.commit()

def update_price_bounds(item_id: int, new_min: float, new_max: float) -> None:
    """Update only min and max prices without changing current price"""
    with get_db_connection() as conn:
        conn.execute("""
            UPDATE items 
            SET min_price = ?, max_price = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_min, new_max, item_id))
        conn.commit()

def get_user_stats(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user statistics"""
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

def record_notification(user_id: int, item_id: int) -> None:
    """Record that a notification was sent"""
    with get_db_connection() as conn:
        # Update item
        conn.execute("""
            UPDATE items 
            SET notification_sent_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (item_id,))
        
        # Update user stats
        conn.execute("""
            UPDATE user_stats 
            SET notifications_sent = notifications_sent + 1, last_activity = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (user_id,))
        
        conn.commit()

def get_system_metrics(metric_name: str, hours: int = 24) -> List[Dict[str, Any]]:
    """Get system metrics for the last N hours"""
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM system_metrics 
            WHERE metric_name = ? AND timestamp > datetime('now', '-' || ? || ' hours')
            ORDER BY timestamp DESC
        """, (metric_name, hours)).fetchall()
        return [dict(row) for row in rows]
