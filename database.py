import os
import pymysql
from typing import Optional, List, Dict
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "gateway01.us-east-1.prod.aws.tidbcloud.com"),
    "port": int(os.getenv("DB_PORT", 4000)),
    "user": os.getenv("DB_USER", "mcYMx9cHCtp3c25.root"),
    "password": os.getenv("DB_PASSWORD", "khqmZDEiJ4DwqDVV"),
    "database": os.getenv("DB_NAME", "kaontystore"),
    "charset": "utf8mb4",
    "ssl": {"ca": None, "verify_cert": False},
    "cursorclass": pymysql.cursors.DictCursor,
}

# All bot tables prefixed with bot_ to avoid conflicts with existing tables
T_USERS = "bot_users"
T_ORDERS = "bot_orders"
T_TOPUPS = "bot_topup_requests"
T_RATELIMITS = "bot_rate_limits"
T_STOCK = "bot_stock_tracker"


def get_db():
    return pymysql.connect(**DB_CONFIG)


def init_db():
    # Create tables
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {T_USERS} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    balance DECIMAL(12,2) DEFAULT 0.00,
                    is_banned TINYINT DEFAULT 0,
                    is_admin TINYINT DEFAULT 0,
                    language VARCHAR(5) DEFAULT 'en',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {T_ORDERS} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    product_id INT NOT NULL,
                    product_name VARCHAR(255) NOT NULL,
                    quantity INT DEFAULT 1,
                    total_cost DECIMAL(12,2) NOT NULL,
                    `keys` TEXT,
                    order_id_api INT,
                    status VARCHAR(50) DEFAULT 'completed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {T_TOPUPS} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    amount DECIMAL(12,2) NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    txid VARCHAR(500),
                    binance_id VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP NULL
                )
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {T_RATELIMITS} (
                    user_id BIGINT NOT NULL,
                    action VARCHAR(100) NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, action, timestamp)
                )
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {T_STOCK} (
                    product_id INT PRIMARY KEY,
                    product_name VARCHAR(255),
                    category_name VARCHAR(255),
                    last_stock INT DEFAULT 0,
                    last_in_stock TINYINT DEFAULT 0,
                    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()
    finally:
        conn.close()

    # Add language column to existing tables if missing
    try:
        conn2 = get_db()
        with conn2.cursor() as cur:
            cur.execute(f"ALTER TABLE {T_USERS} ADD COLUMN language VARCHAR(5) DEFAULT 'en'")
        conn2.commit()
        conn2.close()
    except Exception:
        pass


# ==================== User Functions ====================

def create_user(telegram_id: int, username: str = None, first_name: str = None) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT IGNORE INTO {T_USERS} (telegram_id, username, first_name) VALUES (%s, %s, %s)",
                (telegram_id, username, first_name)
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_user(telegram_id: int) -> Optional[Dict]:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {T_USERS} WHERE telegram_id = %s", (telegram_id,))
            return cur.fetchone()
    finally:
        conn.close()


def set_language(telegram_id: int, lang: str) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {T_USERS} SET language = %s WHERE telegram_id = %s",
                (lang, telegram_id)
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_language(telegram_id: int) -> str:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT language FROM {T_USERS} WHERE telegram_id = %s", (telegram_id,))
            row = cur.fetchone()
            return row["language"] if row and row["language"] else "en"
    except Exception:
        return "en"
    finally:
        conn.close()


def update_user_activity(telegram_id: int):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {T_USERS} SET last_active = CURRENT_TIMESTAMP WHERE telegram_id = %s",
                (telegram_id,)
            )
        conn.commit()
    finally:
        conn.close()


def get_balance(telegram_id: int) -> float:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT balance FROM {T_USERS} WHERE telegram_id = %s", (telegram_id,))
            row = cur.fetchone()
            return float(row["balance"]) if row else 0.0
    finally:
        conn.close()


def update_balance(telegram_id: int, amount: float) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {T_USERS} SET balance = balance + %s WHERE telegram_id = %s AND (balance + %s) >= 0",
                (amount, telegram_id, amount)
            )
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        return False
    finally:
        conn.close()


def set_balance(telegram_id: int, amount: float) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {T_USERS} SET balance = %s WHERE telegram_id = %s",
                (amount, telegram_id)
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def ban_user(telegram_id: int) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE {T_USERS} SET is_banned = 1 WHERE telegram_id = %s", (telegram_id,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def unban_user(telegram_id: int) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE {T_USERS} SET is_banned = 0 WHERE telegram_id = %s", (telegram_id,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_all_users() -> List[Dict]:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {T_USERS} ORDER BY created_at DESC")
            return cur.fetchall()
    finally:
        conn.close()


def get_user_count() -> int:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) as count FROM {T_USERS}")
            return cur.fetchone()["count"]
    finally:
        conn.close()


def is_banned(telegram_id: int) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT is_banned FROM {T_USERS} WHERE telegram_id = %s", (telegram_id,))
            row = cur.fetchone()
            return row["is_banned"] == 1 if row else False
    finally:
        conn.close()


# ==================== Order Functions ====================

def create_order(telegram_id: int, product_id: int, product_name: str,
                 quantity: int, total_cost: float, keys: List[str],
                 order_id_api: int = None) -> bool:
    conn = get_db()
    try:
        keys_str = "\n".join(keys) if keys else ""
        with conn.cursor() as cur:
            cur.execute(
                f"""INSERT INTO {T_ORDERS} (user_id, product_id, product_name, quantity,
                   total_cost, `keys`, order_id_api) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (telegram_id, product_id, product_name, quantity, total_cost,
                 keys_str, order_id_api)
            )
        conn.commit()
        return True
    except Exception as e:
        import sys
        print(f"[DB ERROR] create_order failed: {e}", file=sys.stderr)
        return False
    finally:
        conn.close()


def get_user_orders(telegram_id: int, limit: int = 10) -> List[Dict]:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {T_ORDERS} WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                (telegram_id, limit)
            )
            return cur.fetchall()
    finally:
        conn.close()


def get_order_by_id(order_id: int) -> Optional[Dict]:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {T_ORDERS} WHERE id = %s", (order_id,))
            return cur.fetchone()
    finally:
        conn.close()


def get_all_orders(limit: int = 50) -> List[Dict]:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {T_ORDERS} ORDER BY created_at DESC LIMIT %s", (limit,))
            return cur.fetchall()
    finally:
        conn.close()


# ==================== Topup Functions ====================

def create_topup_request(telegram_id: int, amount: float, txid: str = None, binance_id: str = None) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""INSERT INTO {T_TOPUPS} (user_id, amount, txid, binance_id)
                   VALUES (%s, %s, %s, %s)""",
                (telegram_id, amount, txid, binance_id)
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_pending_topups() -> List[Dict]:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT t.*, u.username, u.first_name
                   FROM {T_TOPUPS} t
                   JOIN {T_USERS} u ON t.user_id = u.telegram_id
                   WHERE t.status = 'pending'
                   ORDER BY t.created_at ASC"""
            )
            return cur.fetchall()
    finally:
        conn.close()


def approve_topup(topup_id: int) -> Optional[Dict]:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {T_TOPUPS} WHERE id = %s AND status = 'pending'",
                (topup_id,)
            )
            topup = cur.fetchone()
            if not topup:
                return None

            cur.execute(
                f"UPDATE {T_USERS} SET balance = balance + %s WHERE telegram_id = %s",
                (topup["amount"], topup["user_id"])
            )
            cur.execute(
                f"""UPDATE {T_TOPUPS} SET status = 'approved',
                   processed_at = CURRENT_TIMESTAMP WHERE id = %s""",
                (topup_id,)
            )
        conn.commit()
        return topup
    except Exception:
        return None
    finally:
        conn.close()


def reject_topup(topup_id: int) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""UPDATE {T_TOPUPS} SET status = 'rejected',
                   processed_at = CURRENT_TIMESTAMP WHERE id = %s""",
                (topup_id,)
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


# ==================== Rate Limiting ====================

def check_rate_limit(user_id: int, action: str, limit: int = 10, window: int = 60) -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT COUNT(*) as count FROM {T_RATELIMITS}
                   WHERE user_id = %s AND action = %s
                   AND timestamp > DATE_SUB(NOW(), INTERVAL %s SECOND)""",
                (user_id, action, window)
            )
            row = cur.fetchone()
            if row["count"] >= limit:
                return False

            cur.execute(
                f"INSERT INTO {T_RATELIMITS} (user_id, action) VALUES (%s, %s)",
                (user_id, action)
            )
        conn.commit()
        return True
    except Exception:
        return True
    finally:
        conn.close()


def cleanup_old_rate_limits():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {T_RATELIMITS} WHERE timestamp < DATE_SUB(NOW(), INTERVAL 1 HOUR)")
        conn.commit()
    finally:
        conn.close()


# ==================== Stock Tracker ====================


def upsert_stock(product_id: int, product_name: str, category_name: str, stock: int, in_stock: bool) -> bool:
    """Insert or update stock tracker. Returns True if stock changed from 0 to >0 (restock)."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT last_stock, last_in_stock FROM {T_STOCK} WHERE product_id = %s",
                (product_id,)
            )
            old = cur.fetchone()

            was_out = (not old) or (old["last_stock"] == 0) or (old["last_in_stock"] == 0)
            now_available = stock > 0 and in_stock
            restocked = was_out and now_available

            sql = (
                f"INSERT INTO {T_STOCK} (product_id, product_name, category_name, last_stock, last_in_stock, checked_at)"
                f" VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)"
                f" ON DUPLICATE KEY UPDATE"
                f" last_stock = VALUES(last_stock), last_in_stock = VALUES(last_in_stock),"
                f" product_name = VALUES(product_name), category_name = VALUES(category_name),"
                f" checked_at = CURRENT_TIMESTAMP"
            )
            cur.execute(sql, (product_id, product_name, category_name, stock, 1 if in_stock else 0))
        conn.commit()
        return restocked
    except Exception:
        return False
    finally:
        conn.close()


# Initialize database on import
init_db()
