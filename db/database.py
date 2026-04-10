"""
SQLite database for tracking sync status
"""
import sqlite3
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime

from config.settings import DB_DIR


class SyncDB:
    """Database for tracking synced activities"""

    def __init__(self, db_name: str = "sync_garmin_coros.db"):
        self.db_path = DB_DIR / db_name
        self._init_db()

    def _init_db(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            # Garmin activities table (Garmin -> Coros sync)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS garmin_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activity_id INTEGER NOT NULL UNIQUE,
                    activity_name TEXT,
                    start_time TEXT,
                    sport_type TEXT,
                    is_synced_coros INTEGER DEFAULT 0,
                    coros_import_status INTEGER DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_garmin_activity_id
                ON garmin_activity(activity_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_garmin_is_synced
                ON garmin_activity(is_synced_coros)
            """)

            # Coros activities table (Coros -> Garmin sync)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS coros_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label_id TEXT NOT NULL UNIQUE,
                    activity_name TEXT,
                    start_time TEXT,
                    sport_type INTEGER,
                    is_synced_garmin INTEGER DEFAULT 0,
                    garmin_import_status INTEGER DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_coros_label_id
                ON coros_activity(label_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_coros_is_synced
                ON coros_activity(is_synced_garmin)
            """)

    # ─── Garmin activities (Garmin → Coros) ─────────────────────────────────

    def save_garmin_activity(self, activity_id: int, activity_name: str = None,
                             start_time: str = None, sport_type: str = None) -> bool:
        """Save Garmin activity if not exists"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO garmin_activity
                    (activity_id, activity_name, start_time, sport_type)
                    VALUES (?, ?, ?, ?)
                """, (activity_id, activity_name, start_time, sport_type))
                return True
        except Exception as e:
            print(f"Error saving Garmin activity {activity_id}: {e}")
            return False

    def get_unsynced_garmin_activities(self, limit: int = 100) -> List[Tuple]:
        """Get Garmin activities not yet synced to Coros"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT activity_id, activity_name, start_time, sport_type
                FROM garmin_activity
                WHERE is_synced_coros = 0
                ORDER BY start_time DESC
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()

    def mark_garmin_synced(self, activity_id: int) -> bool:
        """Mark Garmin activity as synced to Coros"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE garmin_activity
                    SET is_synced_coros = 1, coros_import_status = 1, updated_at = ?
                    WHERE activity_id = ?
                """, (datetime.now().isoformat(), activity_id))
                return True
        except Exception as e:
            print(f"Error marking Garmin activity {activity_id} as synced: {e}")
            return False

    def mark_garmin_sync_failed(self, activity_id: int, status: int) -> bool:
        """Mark Garmin activity sync as failed"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE garmin_activity
                    SET coros_import_status = ?, updated_at = ?
                    WHERE activity_id = ?
                """, (status, datetime.now().isoformat(), activity_id))
                return True
        except Exception as e:
            print(f"Error marking Garmin activity {activity_id} sync failed: {e}")
            return False

    # ─── Coros activities (Coros → Garmin) ──────────────────────────────────

    def save_coros_activity(self, label_id: str, activity_name: str = None,
                            start_time: str = None, sport_type: int = None) -> bool:
        """Save Coros activity if not exists"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO coros_activity
                    (label_id, activity_name, start_time, sport_type)
                    VALUES (?, ?, ?, ?)
                """, (label_id, activity_name, start_time, sport_type))
                return True
        except Exception as e:
            print(f"Error saving Coros activity {label_id}: {e}")
            return False

    def get_unsynced_coros_activities(self, limit: int = 100) -> List[Tuple]:
        """Get Coros activities not yet synced to Garmin"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT label_id, activity_name, start_time, sport_type
                FROM coros_activity
                WHERE is_synced_garmin = 0
                ORDER BY start_time DESC
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()

    def mark_coros_synced(self, label_id: str) -> bool:
        """Mark Coros activity as synced to Garmin"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE coros_activity
                    SET is_synced_garmin = 1, garmin_import_status = 1, updated_at = ?
                    WHERE label_id = ?
                """, (datetime.now().isoformat(), label_id))
                return True
        except Exception as e:
            print(f"Error marking Coros activity {label_id} as synced: {e}")
            return False

    def mark_coros_sync_failed(self, label_id: str, status: int) -> bool:
        """Mark Coros activity sync as failed"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE coros_activity
                    SET garmin_import_status = ?, updated_at = ?
                    WHERE label_id = ?
                """, (status, datetime.now().isoformat(), label_id))
                return True
        except Exception as e:
            print(f"Error marking Coros activity {label_id} sync failed: {e}")
            return False

    # ─── Stats ────────────────────────────────────────────────────────────────

    def get_garmin_stats(self) -> dict:
        """Get Garmin activity sync stats"""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM garmin_activity").fetchone()[0]
            synced = conn.execute(
                "SELECT COUNT(*) FROM garmin_activity WHERE is_synced_coros = 1"
            ).fetchone()[0]
            unsynced = conn.execute(
                "SELECT COUNT(*) FROM garmin_activity WHERE is_synced_coros = 0"
            ).fetchone()[0]
            return {"total": total, "synced": synced, "unsynced": unsynced}

    def get_coros_stats(self) -> dict:
        """Get Coros activity sync stats"""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM coros_activity").fetchone()[0]
            synced = conn.execute(
                "SELECT COUNT(*) FROM coros_activity WHERE is_synced_garmin = 1"
            ).fetchone()[0]
            unsynced = conn.execute(
                "SELECT COUNT(*) FROM coros_activity WHERE is_synced_garmin = 0"
            ).fetchone()[0]
            return {"total": total, "synced": synced, "unsynced": unsynced}

    # ─── Legacy compatibility ────────────────────────────────────────────────

    # Keep old methods for backward compatibility
    def save_activity(self, activity_id: int, activity_name: str = None,
                      start_time: str = None, sport_type: str = None) -> bool:
        return self.save_garmin_activity(activity_id, activity_name, start_time, sport_type)

    def get_unsynced_activities(self, limit: int = 100) -> List[Tuple]:
        return self.get_unsynced_garmin_activities(limit)

    def mark_synced(self, activity_id: int, target: str = "coros") -> bool:
        if target == "coros":
            return self.mark_garmin_synced(activity_id)
        return False

    def mark_sync_failed(self, activity_id: int, target: str = "coros",
                         status: int = None) -> bool:
        if target == "coros":
            return self.mark_garmin_sync_failed(activity_id, status or -1)
        return False

    def get_activity_count(self) -> dict:
        """Legacy method - returns Garmin stats"""
        return self.get_garmin_stats()
