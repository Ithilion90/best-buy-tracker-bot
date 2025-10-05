import sqlite3
import os
from typing import List, Dict, Optional, Any, Tuple, Callable
from contextlib import contextmanager
from datetime import datetime, timedelta
import threading

try:
    import psycopg2  # type: ignore
    import psycopg2.pool  # type: ignore
except Exception:  # pragma: no cover - psycopg2 optional
    psycopg2 = None  # type: ignore

try:
    from .config import config
    from .logger import logger
    from .resilience import circuit_breakers
except ImportError:
    from config import config
    from logger import logger
    from resilience import circuit_breakers

_raw_db_url = getattr(config, 'database_url', '')
_is_postgres = False
if _raw_db_url and _raw_db_url.startswith(('postgres://', 'postgresql://')):
    if psycopg2 is None:
        # Graceful fallback: log and keep using SQLite instead of crashing
        try:
            logger.warning("DATABASE_URL set but psycopg2 not installed; falling back to SQLite", database_url=_raw_db_url)
        except Exception:
            pass
        _is_postgres = False
    else:
        _is_postgres = True

from typing import Any as _Any
_pg_pool: _Any = None  # SimpleConnectionPool instance when PostgreSQL is enabled
_pg_pool_lock = threading.Lock()

def _init_pg_pool():  # lazy init
    global _pg_pool
    if not _is_postgres:
        return
    if psycopg2 is None:  # safety (should already be filtered earlier)
        return
    if _pg_pool is None:
        with _pg_pool_lock:
            if _pg_pool is None:
                minc = 1
                maxc = max(2, getattr(config, 'db_pool_size', 5))
                _pg_pool = psycopg2.pool.SimpleConnectionPool(minc, maxc, getattr(config, 'database_url'))  # type: ignore
                logger.info("PostgreSQL connection pool initialized", min=minc, max=maxc)

def is_postgres() -> bool:
    """Public helper to know if backend is PostgreSQL."""
    return _is_postgres

def get_db_path() -> str:
    # For SQLite only
    if _is_postgres:
        return ''
    if hasattr(config, 'frozen') and getattr(config, 'frozen', False):
        return os.path.join(os.path.dirname(getattr(config, 'executable_path', '.')), "tracker.db")
    return config.database_path

@contextmanager
def get_db_connection():
    """Get database connection (SQLite or PostgreSQL) with circuit breaker protection"""
    if _is_postgres:
        _init_pg_pool()
        conn = None
        try:
            assert _pg_pool is not None
            conn = circuit_breakers['database'].call(_pg_pool.getconn)  # type: ignore
            yield conn
        except Exception as e:  # pragma: no cover
            logger.error("PostgreSQL connection failed", error=str(e))
            raise
        finally:
            if conn is not None and _pg_pool is not None:
                _pg_pool.putconn(conn)
    else:
        try:
            conn = circuit_breakers['database'].call(sqlite3.connect, get_db_path())
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")  # Better performance
            yield conn
        except Exception as e:
            logger.error("SQLite connection failed", error=str(e))
            raise
        finally:
            if 'conn' in locals():
                conn.close()

def init_db() -> None:
    """Initialize database schema (works for SQLite & PostgreSQL)."""
    with get_db_connection() as conn:
        if _is_postgres:
            _init_db_postgres(conn)
        else:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            is_fresh_db = len(tables) == 0
            if is_fresh_db:
                _create_fresh_schema(conn)
            else:
                _migrate_existing_schema(conn)
            _create_indices(conn)
            conn.commit()
            logger.info("SQLite DB initialized", fresh_db=is_fresh_db)

def _init_db_postgres(conn):  # pragma: no cover (not hit in SQLite tests)
    cur = conn.cursor()
    # Detect existing tables
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    existing = {r[0] for r in cur.fetchall()}
    fresh = len(existing) == 0
    # Users
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            last_active TIMESTAMPTZ DEFAULT NOW(),
            settings JSONB DEFAULT '{}'::jsonb
        )
    """)
    # Items
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            asin TEXT,
            domain TEXT,
            title TEXT,
            currency TEXT DEFAULT 'EUR',
            last_price DOUBLE PRECISION,
            min_price DOUBLE PRECISION,
            max_price DOUBLE PRECISION,
            target_price DOUBLE PRECISION,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            last_checked TIMESTAMPTZ,
            check_count INTEGER DEFAULT 0,
            notification_sent_at TIMESTAMPTZ,
            category TEXT,
            priority INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT TRUE,
            new_only BOOLEAN DEFAULT FALSE
        )
    """)
    # Ensure new columns exist (for existing DBs)
    try:
        cur.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS availability TEXT")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS new_only BOOLEAN DEFAULT FALSE")
    except Exception:
        pass
    # Price history
    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id BIGSERIAL PRIMARY KEY,
            item_id BIGINT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            price DOUBLE PRECISION NOT NULL,
            currency TEXT DEFAULT 'EUR',
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            source TEXT DEFAULT 'scraping',
            availability TEXT
        )
    """)
    # User stats
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            items_tracked INTEGER DEFAULT 0,
            total_savings DOUBLE PRECISION DEFAULT 0.0,
            notifications_sent INTEGER DEFAULT 0,
            last_activity TIMESTAMPTZ DEFAULT NOW(),
            total_checks INTEGER DEFAULT 0
        )
    """)
    # System metrics
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_metrics (
            id BIGSERIAL PRIMARY KEY,
            metric_name TEXT NOT NULL,
            metric_value DOUBLE PRECISION NOT NULL,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            metadata TEXT
        )
    """)
    # Indices
    idx_statements = [
        "CREATE INDEX IF NOT EXISTS idx_items_user_id ON items(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_items_asin ON items(asin)",
        "CREATE INDEX IF NOT EXISTS idx_price_history_item_id ON price_history(item_id)",
        "CREATE INDEX IF NOT EXISTS idx_price_history_timestamp ON price_history(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)",
        "CREATE INDEX IF NOT EXISTS idx_items_active ON items(is_active)",
        "CREATE INDEX IF NOT EXISTS idx_items_last_checked ON items(last_checked)",
        "CREATE INDEX IF NOT EXISTS idx_system_metrics_name_time ON system_metrics(metric_name, timestamp)"
    ]
    for stmt in idx_statements:
        try:
            cur.execute(stmt)
        except Exception as e:
            logger.warning("Failed to create PG index", sql=stmt, error=str(e))
    conn.commit()
    logger.info("PostgreSQL DB initialized", fresh_db=fresh)

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
            domain TEXT, -- Amazon domain (e.g. amazon.it, amazon.de) to distinguish regional listings
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
            availability TEXT,
            new_only BOOLEAN DEFAULT 0, -- Track only NEW condition products
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
    'is_active': 'BOOLEAN DEFAULT 1',
    'domain': 'TEXT',
    'availability': 'TEXT',
    'new_only': 'BOOLEAN DEFAULT 0'
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
        if _is_postgres:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            existing = cur.fetchone()
            if not existing:
                cur.execute(
                    "INSERT INTO users (id, username, first_name, last_name) VALUES (%s, %s, %s, %s)",
                    (user_id, username, first_name, last_name)
                )
                cur.execute(
                    "INSERT INTO user_stats (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
                    (user_id,)
                )
                logger.info("New user created", user_id=user_id, username=username)
            else:
                cur.execute("UPDATE users SET last_active = NOW() WHERE id = %s", (user_id,))
                cur.execute("UPDATE user_stats SET last_activity = NOW() WHERE user_id = %s", (user_id,))
            conn.commit()
        else:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not existing:
                conn.execute("""
                    INSERT INTO users (id, username, first_name, last_name, created_at, last_active)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (user_id, username, first_name, last_name))
                conn.execute("""
                    INSERT INTO user_stats (user_id, items_tracked, total_savings, notifications_sent, last_activity, total_checks)
                    VALUES (?, 0, 0.0, 0, CURRENT_TIMESTAMP, 0)
                """, (user_id,))
                logger.info("New user created", user_id=user_id, username=username)
            else:
                conn.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
                conn.execute("UPDATE user_stats SET last_activity = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
            conn.commit()

def add_item(user_id: int, url: str, asin: str, title: str, currency: str, price: Optional[float], target_price: Optional[float] = None, category: str = None, priority: int = 1, domain: Optional[str] = None) -> int:
    """Add item with enhanced tracking (domain-aware)"""
    with get_db_connection() as conn:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO items (user_id, url, asin, domain, title, currency, last_price, min_price, max_price, target_price, category, priority, last_checked, check_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), 1)
                RETURNING id
                """,
                (user_id, url, asin, domain, title, currency, price, price, price, target_price, category, priority)
            )
            item_id = cur.fetchone()[0]
            if price is not None:
                cur.execute(
                    "INSERT INTO price_history (item_id, price, currency, source, availability) VALUES (%s, %s, %s, 'scraping', 'in_stock')",
                    (item_id, price, currency)
                )
            cur.execute("UPDATE user_stats SET items_tracked = items_tracked + 1, last_activity = NOW() WHERE user_id = %s", (user_id,))
            conn.commit()
            logger.info("Item added", user_id=user_id, item_id=item_id, asin=asin, price=price)
            return item_id
        else:
            cursor = conn.execute("""
                INSERT INTO items (user_id, url, asin, domain, title, currency, last_price, min_price, max_price, target_price, category, priority, last_checked, check_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
            """, (user_id, url, asin, domain, title, currency, price, price, price, target_price, category, priority))
            item_id = cursor.lastrowid
            if price is not None:
                conn.execute("""
                    INSERT INTO price_history (item_id, price, currency, source, availability)
                    VALUES (?, ?, ?, 'scraping', 'in_stock')
                """, (item_id, price, currency))
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
        if _is_postgres:
            cur = conn.cursor()
            where_clause = "WHERE user_id = %s"
            if not include_inactive:
                where_clause += " AND is_active = TRUE"
            cur.execute(f"SELECT * FROM items {where_clause} ORDER BY priority DESC, created_at ASC", (user_id,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        else:
            where_clause = "WHERE user_id = ?"
            params = [user_id]
            if not include_inactive:
                where_clause += " AND is_active = 1"
            rows = conn.execute(f"SELECT * FROM items {where_clause} ORDER BY priority DESC, created_at ASC", params).fetchall()
            return [dict(row) for row in rows]

def count_items_for_user(user_id: int) -> int:
    """Return active item count for a user (diagnostic)."""
    with get_db_connection() as conn:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM items WHERE user_id = %s AND is_active = TRUE", (user_id,))
            r = cur.fetchone()
            return int(r[0]) if r else 0
        else:
            row = conn.execute("SELECT COUNT(*) FROM items WHERE user_id = ? AND is_active = 1", (user_id,)).fetchone()
            return int(row[0]) if row else 0

def get_item_by_user_and_asin(user_id: int, asin: str, domain: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return single active item for a user by ASIN (and domain if provided)"""
    if not asin:
        return None
    with get_db_connection() as conn:
        if _is_postgres:
            cur = conn.cursor()
            if domain:
                cur.execute("SELECT * FROM items WHERE user_id = %s AND asin = %s AND domain = %s AND is_active = TRUE LIMIT 1", (user_id, asin, domain))
            else:
                cur.execute("SELECT * FROM items WHERE user_id = %s AND asin = %s AND is_active = TRUE LIMIT 1", (user_id, asin))
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
        else:
            if domain:
                row = conn.execute("SELECT * FROM items WHERE user_id = ? AND asin = ? AND domain = ? AND is_active = 1 LIMIT 1", (user_id, asin, domain)).fetchone()
            else:
                row = conn.execute("SELECT * FROM items WHERE user_id = ? AND asin = ? AND is_active = 1 LIMIT 1", (user_id, asin)).fetchone()
            return dict(row) if row else None

def update_price(item_id: int, new_price: Optional[float], new_currency: str = None, new_title: str = None, availability: Optional[str] = None) -> None:
    """Update item price with enhanced tracking and availability persistence."""
    with get_db_connection() as conn:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute("SELECT * FROM items WHERE id = %s", (item_id,))
            item = cur.fetchone()
            if not item:
                return
            cols = [d[0] for d in cur.description]
            item_dict = dict(zip(cols, item))
            current_min = item_dict['min_price']
            current_max = item_dict['max_price']
            savings = 0.0
            if new_price is not None:
                new_min = min(current_min, new_price) if current_min is not None else new_price
                new_max = max(current_max, new_price) if current_max is not None else new_price
                old_price = item_dict['last_price']
                if old_price is not None and new_price < old_price:
                    savings = old_price - new_price
                    cur.execute("UPDATE user_stats SET total_savings = total_savings + %s, last_activity = NOW() WHERE user_id = %s", (savings, item_dict['user_id']))
            else:
                new_min = current_min
                new_max = current_max
            set_parts = ["last_checked = NOW()", "check_count = check_count + 1"]
            vals: List = []
            if new_price is not None:
                set_parts.extend(["last_price = %s", "min_price = %s", "max_price = %s"])
                vals.extend([new_price, new_min, new_max])
            if new_currency:
                set_parts.append("currency = %s")
                vals.append(new_currency)
            if new_title:
                set_parts.append("title = %s")
                vals.append(new_title)
            if availability is not None and availability != '':
                set_parts.append("availability = %s")
                vals.append(availability)
            vals.append(item_id)
            cur.execute(f"UPDATE items SET {', '.join(set_parts)} WHERE id = %s", vals)
            if new_price is not None:
                cur.execute("INSERT INTO price_history (item_id, price, currency, source, availability) VALUES (%s, %s, %s, 'scraping', %s)", (item_id, new_price, new_currency or item_dict['currency'], availability))
            cur.execute("INSERT INTO system_metrics (metric_name, metric_value, metadata) VALUES ('price_check', 1, %s)", (f'{{"item_id": {item_id}}}',))
            conn.commit()
            logger.info("Price updated", item_id=item_id, old_price=item_dict['last_price'], new_price=new_price, savings=savings)
        else:
            item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            if not item:
                return
            current_min = item['min_price']
            current_max = item['max_price']
            savings = 0.0
            if new_price is not None:
                new_min = min(current_min, new_price) if current_min is not None else new_price
                new_max = max(current_max, new_price) if current_max is not None else new_price
                old_price = item['last_price']
                if old_price is not None and new_price < old_price:
                    savings = old_price - new_price
                    conn.execute("UPDATE user_stats SET total_savings = total_savings + ?, last_activity = CURRENT_TIMESTAMP WHERE user_id = ?", (savings, item['user_id']))
            else:
                new_min = current_min
                new_max = current_max
            update_fields = ["last_checked = CURRENT_TIMESTAMP", "check_count = check_count + 1"]
            update_values: List = []
            if new_price is not None:
                update_fields.extend(["last_price = ?", "min_price = ?", "max_price = ?"])
                update_values.extend([new_price, new_min, new_max])
            if new_currency:
                update_fields.append("currency = ?")
                update_values.append(new_currency)
            if new_title:
                update_fields.append("title = ?")
                update_values.append(new_title)
            if availability is not None and availability != '':
                update_fields.append("availability = ?")
                update_values.append(availability)
            update_values.append(item_id)
            conn.execute(f"UPDATE items SET {', '.join(update_fields)} WHERE id = ?", update_values)
            if new_price is not None:
                conn.execute("INSERT INTO price_history (item_id, price, currency, source, availability) VALUES (?, ?, ?, 'scraping', ?)", (item_id, new_price, new_currency or item['currency'], availability))
            conn.execute('INSERT INTO system_metrics (metric_name, metric_value, metadata) VALUES ("price_check", 1, "{" || "\"item_id\": " || ? || "}")', (item_id,))
            conn.commit()
            logger.info("Price updated", item_id=item_id, old_price=item['last_price'], new_price=new_price, savings=savings)

def update_item_availability(item_id: int, availability: str) -> None:
    """Update availability field on items table independently of price updates."""
    if not availability:
        return
    with get_db_connection() as conn:
        try:
            if _is_postgres:
                cur = conn.cursor()
                cur.execute("UPDATE items SET availability = %s, updated_at = NOW() WHERE id = %s", (availability, item_id))
                conn.commit()
            else:
                conn.execute("UPDATE items SET availability = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (availability, item_id))
                conn.commit()
        except Exception as e:
            logger.warning("Failed to update item availability", item_id=item_id, availability=availability, error=str(e))

def remove_item(user_id: int, item_id: int) -> bool:
    """Remove item with stats update"""
    with get_db_connection() as conn:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute("DELETE FROM items WHERE id = %s AND user_id = %s", (item_id, user_id))
            success = cur.rowcount > 0
            if success:
                cur.execute("UPDATE user_stats SET items_tracked = items_tracked - 1, last_activity = NOW() WHERE user_id = %s", (user_id,))
                logger.info("Item removed", user_id=user_id, item_id=item_id)
            conn.commit()
            return success
        else:
            cursor = conn.execute("DELETE FROM items WHERE id = ? AND user_id = ?", (item_id, user_id))
            success = cursor.rowcount > 0
            if success:
                conn.execute("UPDATE user_stats SET items_tracked = items_tracked - 1, last_activity = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
                logger.info("Item removed", user_id=user_id, item_id=item_id)
            conn.commit()
            return success

def all_items() -> List[Dict[str, Any]]:
    """Get all active items for processing"""
    with get_db_connection() as conn:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute("SELECT * FROM items WHERE is_active = TRUE ORDER BY last_checked ASC NULLS FIRST")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        else:
            rows = conn.execute("SELECT * FROM items WHERE is_active = 1 ORDER BY last_checked ASC").fetchall()
            return [dict(row) for row in rows]

def get_all_items() -> List[Dict[str, Any]]:
    """Get all tracked items across all users"""
    with get_db_connection() as conn:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute("SELECT * FROM items WHERE is_active = TRUE ORDER BY last_checked ASC NULLS FIRST")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        else:
            rows = conn.execute("SELECT * FROM items WHERE is_active = 1 ORDER BY last_checked ASC").fetchall()
            return [dict(row) for row in rows]

def update_item_price(item_id: int, new_price: float) -> None:
    """Update item price"""
    with get_db_connection() as conn:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute("UPDATE items SET last_price = %s, updated_at = NOW() WHERE id = %s", (new_price, item_id))
            conn.commit()
        else:
            conn.execute("UPDATE items SET last_price = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_price, item_id))
            conn.commit()
    def update_item_availability(item_id: int, availability: str) -> None:
        """Update availability field on items table independently of price updates."""
        if not availability:
            return
        with get_db_connection() as conn:
            try:
                if _is_postgres:
                    cur = conn.cursor()
                    cur.execute("UPDATE items SET availability = %s, updated_at = NOW() WHERE id = %s", (availability, item_id))
                    conn.commit()
                else:
                    conn.execute("UPDATE items SET availability = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (availability, item_id))
                    conn.commit()
            except Exception as e:
                logger.warning("Failed to update item availability", item_id=item_id, availability=availability, error=str(e))

def update_price_bounds(item_id: int, new_min: float, new_max: float) -> None:
    """Update only min and max prices without changing current price"""
    with get_db_connection() as conn:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute("UPDATE items SET min_price = %s, max_price = %s, updated_at = NOW() WHERE id = %s", (new_min, new_max, item_id))
            conn.commit()
        else:
            conn.execute("UPDATE items SET min_price = ?, max_price = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_min, new_max, item_id))
            conn.commit()

def update_item_domain(item_id: int, domain: str) -> None:
    """Persist domain for an existing item if not already set."""
    if not domain:
        return
    with get_db_connection() as conn:
        try:
            if _is_postgres:
                cur = conn.cursor()
                cur.execute("UPDATE items SET domain = %s WHERE id = %s AND (domain IS NULL OR domain = '')", (domain, item_id))
                conn.commit()
            else:
                conn.execute("UPDATE items SET domain = ? WHERE id = ? AND (domain IS NULL OR domain = '')", (domain, item_id))
                conn.commit()
        except Exception as e:
            logger.warning("Failed to update item domain", item_id=item_id, domain=domain, error=str(e))

def get_user_stats(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user statistics"""
    with get_db_connection() as conn:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute("SELECT * FROM user_stats WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
        else:
            row = conn.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

def record_notification(user_id: int, item_id: int) -> None:
    """Record that a notification was sent"""
    with get_db_connection() as conn:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute("UPDATE items SET notification_sent_at = NOW() WHERE id = %s", (item_id,))
            cur.execute("UPDATE user_stats SET notifications_sent = notifications_sent + 1, last_activity = NOW() WHERE user_id = %s", (user_id,))
            conn.commit()
        else:
            conn.execute("UPDATE items SET notification_sent_at = CURRENT_TIMESTAMP WHERE id = ?", (item_id,))
            conn.execute("UPDATE user_stats SET notifications_sent = notifications_sent + 1, last_activity = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
            conn.commit()

def get_system_metrics(metric_name: str, hours: int = 24) -> List[Dict[str, Any]]:
    """Get system metrics for the last N hours"""
    with get_db_connection() as conn:
        if _is_postgres:
            cur = conn.cursor()
            cur.execute("SELECT * FROM system_metrics WHERE metric_name = %s AND timestamp > NOW() - (%s || ' hours')::interval ORDER BY timestamp DESC", (metric_name, hours))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        else:
            rows = conn.execute("SELECT * FROM system_metrics WHERE metric_name = ? AND timestamp > datetime('now', '-' || ? || ' hours') ORDER BY timestamp DESC", (metric_name, hours)).fetchall()
            return [dict(row) for row in rows]

def toggle_new_only(item_id: int, user_id: int) -> bool:
    """Toggle new_only flag for an item. Returns new state (True if now tracking new only)."""
    with get_db_connection() as conn:
        if _is_postgres:
            cur = conn.cursor()
            # Get current state
            cur.execute("SELECT new_only FROM items WHERE id = %s AND user_id = %s", (item_id, user_id))
            row = cur.fetchone()
            if not row:
                return False
            current_state = row[0] if row[0] is not None else False
            new_state = not current_state
            # Update
            cur.execute("UPDATE items SET new_only = %s, updated_at = NOW() WHERE id = %s AND user_id = %s", (new_state, item_id, user_id))
            conn.commit()
            logger.info("Toggled new_only", item_id=item_id, user_id=user_id, new_state=new_state)
            return new_state
        else:
            # Get current state
            row = conn.execute("SELECT new_only FROM items WHERE id = ? AND user_id = ?", (item_id, user_id)).fetchone()
            if not row:
                return False
            current_state = bool(row[0]) if row[0] is not None else False
            new_state = not current_state
            # Update
            conn.execute("UPDATE items SET new_only = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?", (int(new_state), item_id, user_id))
            conn.commit()
            logger.info("Toggled new_only", item_id=item_id, user_id=user_id, new_state=new_state)
            return new_state

