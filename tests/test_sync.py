import unittest
from unittest import mock
from types import SimpleNamespace
from uuid import uuid4

from db.database import SyncDB
from sync import (
    _parse_since_date,
    _requires_coros_credentials,
    _activity_is_on_or_after,
    _select_window,
    get_sync_plans,
    run_sync_plan,
    sync_coros_to_garmin,
    sync_garmin_to_coros,
)
from utils.platforms import (
    DIRECTION_COROS_TO_GARMIN_INTL,
    DIRECTION_GARMIN_INTL_TO_COROS,
    PLATFORM_COROS,
    PLATFORM_GARMIN_INTL,
)


class FakeGarminClient:
    def __init__(self, fit_data=b"fit"):
        self.fit_data = fit_data
        self.download_calls = []

    def download_fit(self, activity_id):
        self.download_calls.append(activity_id)
        return self.fit_data


class FakeCorosClient:
    def __init__(self, fit_data=b"fit", upload_result=True):
        self.fit_data = fit_data
        self.upload_result = upload_result
        self.download_calls = []
        self.upload_calls = []

    def upload_activity(self, activity_id, fit_data):
        self.upload_calls.append((activity_id, fit_data))
        return self.upload_result

    def download_activity(self, label_id, sport_type):
        self.download_calls.append((label_id, sport_type))
        return self.fit_data


class SyncFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.db_uri = f"file:test_sync_{uuid4().hex}?mode=memory&cache=shared"
        self.db = SyncDB(db_path=self.db_uri, db_uri=True)

    def test_garmin_to_coros_dry_run_keeps_activity_pending(self):
        self.db.save_garmin_activity(3001, "Run", "2026-01-01 09:00:00", "running")
        garmin_client = FakeGarminClient()
        coros_client = FakeCorosClient()

        with mock.patch("sync.time.sleep", return_value=None):
            result = sync_garmin_to_coros(garmin_client, coros_client, self.db, dry_run=True)

        self.assertEqual(result, {"synced": 0, "failed": 0, "skipped": 1})
        self.assertEqual(len(garmin_client.download_calls), 0)
        self.assertEqual(len(coros_client.upload_calls), 0)
        self.assertEqual(self.db.get_garmin_stats()["pending"], 1)

    def test_garmin_to_coros_limit_respects_newest_window(self):
        for idx in range(5):
            self.db.save_garmin_activity(4000 + idx, f"Run {idx}", f"2026-01-0{idx + 1} 09:00:00", "running")

        garmin_client = FakeGarminClient()
        coros_client = FakeCorosClient()

        with mock.patch("sync.time.sleep", return_value=None):
            result = sync_garmin_to_coros(garmin_client, coros_client, self.db, dry_run=True, limit=3)

        self.assertEqual(result, {"synced": 0, "failed": 0, "skipped": 3})
        self.assertEqual(len(garmin_client.download_calls), 0)

    def test_coros_to_garmin_download_failure_is_retryable(self):
        self.db.save_coros_activity("c1", "Run", "2026-01-01 09:00:00", 1)
        coros_client = FakeCorosClient(fit_data=None)
        garmin_client = FakeGarminClient()

        with mock.patch("sync.time.sleep", return_value=None):
            result = sync_coros_to_garmin(coros_client, garmin_client, self.db, dry_run=False)

        self.assertEqual(result, {"synced": 0, "failed": 1, "skipped": 0})
        stats = self.db.get_coros_stats()
        self.assertEqual(stats["failed_retryable"], 1)
        self.assertEqual(stats["pending"], 0)

    def test_coros_to_garmin_dry_run_skips_download(self):
        self.db.save_coros_activity("c-dry", "Run", "2026-01-01 09:00:00", 1)
        coros_client = FakeCorosClient(fit_data=b"fit-data")
        garmin_client = FakeGarminClient()

        with mock.patch("sync.time.sleep", return_value=None):
            result = sync_coros_to_garmin(coros_client, garmin_client, self.db, dry_run=True, limit=1)

        self.assertEqual(result, {"synced": 0, "failed": 0, "skipped": 1})
        self.assertEqual(coros_client.download_calls, [])

    def test_garmin_to_coros_since_filter_skips_older_records(self):
        self.db.save_garmin_activity(5001, "Old Run", "2025-03-29 09:00:00", "running")
        self.db.save_garmin_activity(5002, "New Run", "2025-03-30 09:00:00", "running")
        garmin_client = FakeGarminClient()
        coros_client = FakeCorosClient()

        with mock.patch("sync.time.sleep", return_value=None):
            result = sync_garmin_to_coros(
                garmin_client,
                coros_client,
                self.db,
                dry_run=True,
                limit=10,
                since=_parse_since_date("20250330"),
            )

        self.assertEqual(result, {"synced": 0, "failed": 0, "skipped": 1})

    def test_coros_to_garmin_since_filter_skips_older_records(self):
        self.db.save_coros_activity("old", "Old Ride", "2025-03-29 09:00:00", 1)
        self.db.save_coros_activity("new", "New Ride", "2025-03-30 09:00:00", 1)
        coros_client = FakeCorosClient(fit_data=b"fit-data")
        garmin_client = FakeGarminClient()

        with mock.patch("sync.time.sleep", return_value=None):
            result = sync_coros_to_garmin(
                coros_client,
                garmin_client,
                self.db,
                dry_run=True,
                limit=10,
                since=_parse_since_date("2025-03-30"),
            )

        self.assertEqual(result, {"synced": 0, "failed": 0, "skipped": 1})

    def test_coros_to_garmin_success_writes_mapping(self):
        self.db.save_coros_activity("c2", "Run", "2026-01-01 09:00:00", 1)

        class ImportingGarminClient(FakeGarminClient):
            def __init__(self):
                super().__init__()
                self.client = self

            def import_activity(self, _path):
                return {"detailedImportResult": {"successes": ["ok"], "failures": []}}

        coros_client = FakeCorosClient(fit_data=b"fit-data")
        garmin_client = ImportingGarminClient()

        with mock.patch("sync.time.sleep", return_value=None), \
                mock.patch("pathlib.Path.write_bytes", return_value=None), \
                mock.patch("pathlib.Path.exists", return_value=True), \
                mock.patch("pathlib.Path.unlink", return_value=None):
            result = sync_coros_to_garmin(coros_client, garmin_client, self.db, dry_run=False)

        self.assertEqual(result, {"synced": 1, "failed": 0, "skipped": 0})
        mapping = self.db.get_sync_mapping(PLATFORM_COROS, PLATFORM_GARMIN_INTL, "c2")
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping["mapping_status"], "synced")

    def test_sync_plan_selection_respects_direction_flags(self):
        args = type(
            "Args",
            (),
            {
                "coros_only": True,
                "garmin_only": False,
                "force_fetch_garmin": False,
                "force_fetch_coros": False,
                "dry_run": True,
                "newest": 5,
            },
        )()

        plans = [plan for plan in get_sync_plans(args) if plan.should_run(args)]
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].source_platform, PLATFORM_COROS)

    def test_coros_credentials_only_required_when_coros_plans_run(self):
        default_args = type("Args", (), {})()
        self.assertTrue(_requires_coros_credentials(default_args))

    def test_since_date_parser_accepts_both_formats(self):
        self.assertEqual(str(_parse_since_date("20250330")), "2025-03-30")
        self.assertEqual(str(_parse_since_date("2025-03-30")), "2025-03-30")

    def test_activity_since_helper_filters_by_date(self):
        since = _parse_since_date("20250330")
        self.assertTrue(_activity_is_on_or_after("2025-03-30 00:00:00", since))
        self.assertTrue(_activity_is_on_or_after("2025-04-01 10:00:00", since))
        self.assertFalse(_activity_is_on_or_after("2025-03-29 23:59:59", since))

    def test_select_window_can_choose_earliest_after_since(self):
        rows = [
            ("id3", "Run 3", "2025-04-01 09:00:00", "running"),
            ("id2", "Run 2", "2025-03-31 09:00:00", "running"),
            ("id1", "Run 1", "2025-03-30 09:00:00", "running"),
            ("old", "Old Run", "2025-03-29 09:00:00", "running"),
        ]

        selected = _select_window(
            rows,
            since=_parse_since_date("20250330"),
            earliest=2,
        )

        self.assertEqual([row[0] for row in selected], ["id1", "id2"])

    def test_run_sync_plan_returns_direction_summary_payload(self):
        plan = SimpleNamespace(
            direction_key=DIRECTION_GARMIN_INTL_TO_COROS,
            fetch_func=lambda **kwargs: 2,
            fetch_kwargs_factory=lambda runtime: {},
            sync_func=lambda **kwargs: {"synced": 1, "failed": 0, "skipped": 1},
            sync_kwargs_factory=lambda runtime: {},
            stats_func=lambda db: {"total": 2, "synced": 0, "unsynced": 2, "pending": 2, "duplicate": 0, "failed_retryable": 0},
            force_fetch_enabled=lambda args: False,
            stats_label="Garmin DB",
            result_label="[Garmin->Coros]",
        )
        runtime = {
            "args": type("Args", (), {"dry_run": True, "since": None})(),
            "db": self.db,
        }

        result = run_sync_plan(plan, runtime)

        self.assertEqual(result["direction_key"], DIRECTION_GARMIN_INTL_TO_COROS)
        self.assertEqual(result["fetched"], 2)
        self.assertEqual(result["results"]["synced"], 1)


if __name__ == "__main__":
    unittest.main()
