"""
SQLite database for tracking sync status
"""
import sqlite3
from typing import List, Optional, Tuple
from datetime import datetime

from config.settings import DB_DIR

STATUS_SYNCED = 1
STATUS_DUPLICATE = 2


class SyncDB:
    """Database for tracking synced activities"""

    def __init__(self, db_name: str = "sync_garmin_coros.db", db_path=None, db_uri: bool = False):
        self.db_path = db_path or (DB_DIR / db_name)
        self.db_uri = db_uri
        self._keepalive_conn = None
        if self.db_uri and "mode=memory" in str(self.db_path):
            self._keepalive_conn = self._connect()
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path, uri=self.db_uri)

    def _init_db(self):
        """Initialize database tables"""
        with self._connect() as conn:
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

            # Generic cross-platform mapping table.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_platform TEXT NOT NULL,
                    target_platform TEXT NOT NULL,
                    source_activity_id TEXT NOT NULL,
                    target_activity_id TEXT,
                    mapping_status TEXT NOT NULL DEFAULT 'synced',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source_platform, target_platform, source_activity_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sync_mapping_source
                ON sync_mapping(source_platform, target_platform, source_activity_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sync_mapping_target
                ON sync_mapping(target_platform, target_activity_id)
            """)

    # ─── Garmin activities (Garmin → Coros) ─────────────────────────────────

    def save_garmin_activity(self, activity_id: int, activity_name: str = None,
                             start_time: str = None, sport_type: str = None) -> bool:
        """Save Garmin activity if not exists"""
        try:
            with self._connect() as conn:
                cursor = conn.execute("""
                    INSERT OR IGNORE INTO garmin_activity
                    (activity_id, activity_name, start_time, sport_type)
                    VALUES (?, ?, ?, ?)
                """, (activity_id, activity_name, start_time, sport_type))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error saving Garmin activity {activity_id}: {e}")
            return False

    def get_unsynced_garmin_activities(self, limit: int = 100) -> List[Tuple]:
        """Get Garmin activities not yet synced to Coros"""
        with self._connect() as conn:
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
            with self._connect() as conn:
                conn.execute("""
                    UPDATE garmin_activity
                    SET is_synced_coros = 1, coros_import_status = ?, updated_at = ?
                    WHERE activity_id = ?
                """, (STATUS_SYNCED, datetime.now().isoformat(), activity_id))
                return True
        except Exception as e:
            print(f"Error marking Garmin activity {activity_id} as synced: {e}")
            return False

    def mark_garmin_duplicate(self, activity_id: int) -> bool:
        """Mark Garmin activity as already existing in Coros"""
        try:
            with self._connect() as conn:
                conn.execute("""
                    UPDATE garmin_activity
                    SET is_synced_coros = 1, coros_import_status = ?, updated_at = ?
                    WHERE activity_id = ?
                """, (STATUS_DUPLICATE, datetime.now().isoformat(), activity_id))
                return True
        except Exception as e:
            print(f"Error marking Garmin activity {activity_id} as synced: {e}")
            return False

    def mark_garmin_sync_failed(self, activity_id: int, status: int) -> bool:
        """Mark Garmin activity sync as failed"""
        try:
            with self._connect() as conn:
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
            with self._connect() as conn:
                cursor = conn.execute("""
                    INSERT OR IGNORE INTO coros_activity
                    (label_id, activity_name, start_time, sport_type)
                    VALUES (?, ?, ?, ?)
                """, (label_id, activity_name, start_time, sport_type))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error saving Coros activity {label_id}: {e}")
            return False

    def get_unsynced_coros_activities(self, limit: int = 100) -> List[Tuple]:
        """Get Coros activities not yet synced to Garmin"""
        with self._connect() as conn:
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
            with self._connect() as conn:
                conn.execute("""
                    UPDATE coros_activity
                    SET is_synced_garmin = 1, garmin_import_status = ?, updated_at = ?
                    WHERE label_id = ?
                """, (STATUS_SYNCED, datetime.now().isoformat(), label_id))
                return True
        except Exception as e:
            print(f"Error marking Coros activity {label_id} as synced: {e}")
            return False

    def mark_coros_duplicate(self, label_id: str) -> bool:
        """Mark Coros activity as already existing in Garmin"""
        try:
            with self._connect() as conn:
                conn.execute("""
                    UPDATE coros_activity
                    SET is_synced_garmin = 1, garmin_import_status = ?, updated_at = ?
                    WHERE label_id = ?
                """, (STATUS_DUPLICATE, datetime.now().isoformat(), label_id))
                return True
        except Exception as e:
            print(f"Error marking Coros activity {label_id} as synced: {e}")
            return False

    def mark_coros_sync_failed(self, label_id: str, status: int) -> bool:
        """Mark Coros activity sync as failed"""
        try:
            with self._connect() as conn:
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
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM garmin_activity").fetchone()[0]
            synced = conn.execute(
                "SELECT COUNT(*) FROM garmin_activity WHERE is_synced_coros = 1"
            ).fetchone()[0]
            unsynced = conn.execute(
                "SELECT COUNT(*) FROM garmin_activity WHERE is_synced_coros = 0"
            ).fetchone()[0]
            duplicates = conn.execute(
                "SELECT COUNT(*) FROM garmin_activity WHERE coros_import_status = ?",
                (STATUS_DUPLICATE,)
            ).fetchone()[0]
            retryable_failed = conn.execute(
                "SELECT COUNT(*) FROM garmin_activity WHERE is_synced_coros = 0 AND coros_import_status < 0"
            ).fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM garmin_activity WHERE is_synced_coros = 0 AND coros_import_status IS NULL"
            ).fetchone()[0]
            return {
                "total": total,
                "synced": synced,
                "unsynced": unsynced,
                "duplicate": duplicates,
                "failed_retryable": retryable_failed,
                "pending": pending,
            }

    def get_coros_stats(self) -> dict:
        """Get Coros activity sync stats"""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM coros_activity").fetchone()[0]
            synced = conn.execute(
                "SELECT COUNT(*) FROM coros_activity WHERE is_synced_garmin = 1"
            ).fetchone()[0]
            unsynced = conn.execute(
                "SELECT COUNT(*) FROM coros_activity WHERE is_synced_garmin = 0"
            ).fetchone()[0]
            duplicates = conn.execute(
                "SELECT COUNT(*) FROM coros_activity WHERE garmin_import_status = ?",
                (STATUS_DUPLICATE,)
            ).fetchone()[0]
            retryable_failed = conn.execute(
                "SELECT COUNT(*) FROM coros_activity WHERE is_synced_garmin = 0 AND garmin_import_status < 0"
            ).fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM coros_activity WHERE is_synced_garmin = 0 AND garmin_import_status IS NULL"
            ).fetchone()[0]
            return {
                "total": total,
                "synced": synced,
                "unsynced": unsynced,
                "duplicate": duplicates,
                "failed_retryable": retryable_failed,
                "pending": pending,
            }

    # ─── Generic sync mapping ────────────────────────────────────────────────

    def upsert_sync_mapping(self, source_platform: str, target_platform: str,
                            source_activity_id: str, target_activity_id: Optional[str] = None,
                            mapping_status: str = "synced") -> bool:
        """Create or update a generic source->target activity mapping."""
        try:
            with self._connect() as conn:
                now = datetime.now().isoformat()
                conn.execute("""
                    INSERT INTO sync_mapping
                    (source_platform, target_platform, source_activity_id, target_activity_id, mapping_status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_platform, target_platform, source_activity_id)
                    DO UPDATE SET
                        target_activity_id = excluded.target_activity_id,
                        mapping_status = excluded.mapping_status,
                        updated_at = excluded.updated_at
                """, (
                    source_platform,
                    target_platform,
                    str(source_activity_id),
                    None if target_activity_id is None else str(target_activity_id),
                    mapping_status,
                    now,
                    now,
                ))
                return True
        except Exception as e:
            print(f"Error upserting sync mapping {source_platform}->{target_platform}:{source_activity_id}: {e}")
            return False

    def get_sync_mapping(self, source_platform: str, target_platform: str,
                         source_activity_id: str) -> Optional[dict]:
        """Return a sync mapping for a source activity if it exists."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT source_platform, target_platform, source_activity_id, target_activity_id,
                       mapping_status, created_at, updated_at
                FROM sync_mapping
                WHERE source_platform = ? AND target_platform = ? AND source_activity_id = ?
            """, (source_platform, target_platform, str(source_activity_id))).fetchone()

        if not row:
            return None

        return {
            "source_platform": row[0],
            "target_platform": row[1],
            "source_activity_id": row[2],
            "target_activity_id": row[3],
            "mapping_status": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }

    def get_target_mapping(self, target_platform: str, target_activity_id: str) -> List[dict]:
        """List mappings that already point at a target activity."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT source_platform, target_platform, source_activity_id, target_activity_id, mapping_status
                FROM sync_mapping
                WHERE target_platform = ? AND target_activity_id = ?
                ORDER BY id ASC
            """, (target_platform, str(target_activity_id))).fetchall()

        return [
            {
                "source_platform": row[0],
                "target_platform": row[1],
                "source_activity_id": row[2],
                "target_activity_id": row[3],
                "mapping_status": row[4],
            }
            for row in rows
        ]

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
