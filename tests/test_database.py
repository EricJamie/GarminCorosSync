import sqlite3
import unittest
from uuid import uuid4

from db.database import STATUS_DUPLICATE, STATUS_SYNCED, SyncDB
from utils.platforms import (
    PLATFORM_COROS,
    PLATFORM_GARMIN_INTL,
    make_direction,
)


class SyncDBTestCase(unittest.TestCase):
    def setUp(self):
        self.db_uri = f"file:test_db_{uuid4().hex}?mode=memory&cache=shared"
        self.db = SyncDB(db_path=self.db_uri, db_uri=True)

    def test_save_only_counts_new_rows(self):
        self.assertTrue(self.db.save_garmin_activity(1001, "Morning Run", "2026-01-01 08:00:00", "running"))
        self.assertFalse(self.db.save_garmin_activity(1001, "Morning Run", "2026-01-01 08:00:00", "running"))

        stats = self.db.get_garmin_stats()
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["pending"], 1)

    def test_duplicate_and_failed_statuses_are_reported(self):
        self.db.save_coros_activity("abc", "Lunch Run", "2026-01-02 12:00:00", 1)
        self.db.save_coros_activity("def", "Evening Run", "2026-01-03 18:00:00", 1)
        self.db.save_coros_activity("ghi", "Trail Run", "2026-01-04 09:00:00", 1)

        self.assertTrue(self.db.mark_coros_duplicate("abc"))
        self.assertTrue(self.db.mark_coros_synced("def"))
        self.assertTrue(self.db.mark_coros_sync_failed("ghi", -2))

        stats = self.db.get_coros_stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["synced"], 2)
        self.assertEqual(stats["duplicate"], 1)
        self.assertEqual(stats["failed_retryable"], 1)
        self.assertEqual(stats["pending"], 0)

    def test_status_codes_are_written_for_duplicate_and_success(self):
        self.db.save_garmin_activity(2002, "Ride", "2026-01-05 07:30:00", "cycling")
        self.db.save_garmin_activity(2003, "Walk", "2026-01-06 07:30:00", "walking")

        self.assertTrue(self.db.mark_garmin_synced(2002))
        self.assertTrue(self.db.mark_garmin_duplicate(2003))

        with sqlite3.connect(self.db_uri, uri=True) as conn:
            rows = dict(
                conn.execute(
                    "SELECT activity_id, coros_import_status FROM garmin_activity ORDER BY activity_id"
                ).fetchall()
            )

        self.assertEqual(rows[2002], STATUS_SYNCED)
        self.assertEqual(rows[2003], STATUS_DUPLICATE)

    def test_generic_sync_mapping_can_be_upserted_and_queried(self):
        self.assertTrue(
            self.db.upsert_sync_mapping(
                PLATFORM_GARMIN_INTL,
                PLATFORM_COROS,
                "9001",
                "coros-42",
                "synced",
            )
        )

        mapping = self.db.get_sync_mapping(PLATFORM_GARMIN_INTL, PLATFORM_COROS, "9001")
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping["target_activity_id"], "coros-42")
        self.assertEqual(mapping["mapping_status"], "synced")

        self.assertTrue(
            self.db.upsert_sync_mapping(
                PLATFORM_GARMIN_INTL,
                PLATFORM_COROS,
                "9001",
                "coros-99",
                "duplicate",
            )
        )

        updated = self.db.get_sync_mapping(PLATFORM_GARMIN_INTL, PLATFORM_COROS, "9001")
        self.assertEqual(updated["target_activity_id"], "coros-99")
        self.assertEqual(updated["mapping_status"], "duplicate")

        reverse_hits = self.db.get_target_mapping(PLATFORM_COROS, "coros-99")
        self.assertEqual(len(reverse_hits), 1)
        self.assertEqual(reverse_hits[0]["source_platform"], PLATFORM_GARMIN_INTL)

    def test_direction_helper_is_normalized(self):
        self.assertEqual(
            make_direction(PLATFORM_COROS, PLATFORM_GARMIN_INTL),
            "coros->garmin_intl",
        )


if __name__ == "__main__":
    unittest.main()
