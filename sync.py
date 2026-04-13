#!/usr/bin/env python3
"""
Garmin <-> Coros bidirectional sync tool.
"""
import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import (
    COROS_EMAIL, COROS_PASSWORD,
    GARMIN_EMAIL, GARMIN_PASSWORD, GARMIN_TOKEN_DATA,
    FIT_DIR, NEWEST_NUM
)
from db.database import SyncDB
from garmin.client import GarminClient
from coros.client import CorosClient
from utils.platforms import (
    DIRECTION_COROS_TO_GARMIN_INTL,
    DIRECTION_GARMIN_INTL_TO_COROS,
    PLATFORM_COROS,
    PLATFORM_GARMIN_INTL,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncDirectionPlan:
    """One executable sync direction with fetch + sync steps."""

    direction_key: str
    source_platform: str
    target_platform: str
    fetch_func: Callable[..., int]
    fetch_kwargs_factory: Callable[..., Dict]
    sync_func: Callable[..., dict]
    sync_kwargs_factory: Callable[..., Dict]
    stats_func: Callable[[SyncDB], dict]
    force_fetch_enabled: Callable[[argparse.Namespace], bool]
    should_run: Callable[[argparse.Namespace], bool]
    stats_label: str
    result_label: str


def _has_garmin_auth(args: argparse.Namespace) -> bool:
    has_token_data = bool(args.garmin_token_data and len(args.garmin_token_data) > 32)
    has_email_password = bool(args.garmin_email and args.garmin_password)
    return has_token_data or has_email_password


def _requires_coros_credentials(args: argparse.Namespace) -> bool:
    return True


def _parse_since_date(value: Optional[str]) -> Optional[date]:
    """Parse YYYYMMDD or YYYY-MM-DD into a date object."""
    if not value:
        return None

    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    raise argparse.ArgumentTypeError(
        f"Invalid --since value '{value}'. Use YYYYMMDD or YYYY-MM-DD."
    )


def _activity_is_on_or_after(start_time: str, since: Optional[date]) -> bool:
    """Return True when an activity timestamp is on/after the since date."""
    if since is None:
        return True
    if not start_time:
        return False

    normalized = str(start_time).strip().replace("T", " ")
    date_part = normalized[:10]
    try:
        return datetime.strptime(date_part, "%Y-%m-%d").date() >= since
    except ValueError:
        return False


def _select_window(rows, since: Optional[date], newest: Optional[int] = None, earliest: Optional[int] = None):
    """Filter by since-date, then choose either newest-N or earliest-N rows."""
    filtered = [row for row in rows if _activity_is_on_or_after(row[2], since)]

    if earliest is not None:
        filtered = sorted(filtered, key=lambda row: row[2] or "")
        return filtered[:earliest]

    if newest is not None:
        filtered = sorted(filtered, key=lambda row: row[2] or "", reverse=True)
        return filtered[:newest]

    return filtered


def _log_final_summary(db: SyncDB):
    logger.info("=" * 50)
    logger.info(f"Garmin stats: {db.get_garmin_stats()}")
    logger.info(f"Coros stats:  {db.get_coros_stats()}")
    logger.info("Sync complete!")


def _log_direction_run_summary(plan_runs):
    """Log one compact summary line per executed direction."""
    if not plan_runs:
        return

    logger.info("=" * 50)
    logger.info("Direction summary:")
    for run in plan_runs:
        logger.info(
            "%s fetched=%s synced=%s failed=%s skipped=%s",
            run["direction_key"],
            run["fetched"],
            run["results"].get("synced", 0),
            run["results"].get("failed", 0),
            run["results"].get("skipped", 0),
        )


def _looks_like_duplicate(import_result) -> bool:
    """Best-effort duplicate detection for loosely-defined platform responses."""
    if import_result is None:
        return False

    if isinstance(import_result, dict):
        values_to_check = [
            import_result.get("status"),
            import_result.get("message"),
            import_result.get("error"),
            import_result.get("code"),
        ]
        text = " ".join(str(v) for v in values_to_check if v is not None).lower()
        return "duplicate" in text or "already" in text or "exists" in text

    return "duplicate" in str(import_result).lower()


def _looks_like_success(import_result) -> bool:
    """Best-effort success detection for loosely-defined platform responses."""
    if import_result is None:
        return False

    if isinstance(import_result, dict):
        if import_result.get("success") is True:
            return True
        if str(import_result.get("status", "")).lower() in {"success", "ok", "200"}:
            return True
        if str(import_result.get("code", "")).lower() in {"0", "200"}:
            return True

    return not _looks_like_duplicate(import_result)


# ─── Garmin → Coros ──────────────────────────────────────────────────────────

def fetch_garmin_activities(garmin_client: GarminClient, db: SyncDB,
                            newest_num: int = 1000, since: Optional[date] = None) -> int:
    """Fetch activities from Garmin and save to database"""
    logger.info(f"Fetching latest {newest_num} activities from Garmin...")

    activities = garmin_client.get_all_activities(newest_num=newest_num)
    logger.info(f"Retrieved {len(activities)} activities from Garmin")

    saved_count = 0
    for activity in activities:
        try:
            activity_id = activity.get("activityId")
            activity_name = activity.get("activityName", "")
            start_time = activity.get("startTimeLocal", "")
            sport_type = activity.get("sportTypeKey", "")

            if not _activity_is_on_or_after(start_time, since):
                continue

            if db.save_garmin_activity(activity_id, activity_name, start_time, sport_type):
                saved_count += 1

        except Exception as e:
            logger.error(f"Error saving Garmin activity: {e}")

    logger.info(f"Saved {saved_count} new Garmin activities to database")
    return saved_count


def sync_garmin_to_coros(garmin_client: GarminClient, coros_client: CorosClient,
                          db: SyncDB, dry_run: bool = False, limit: int = 100,
                          since: Optional[date] = None,
                          earliest: Optional[int] = None) -> dict:
    """Sync unsynced activities from Garmin to Coros"""
    results = {"synced": 0, "failed": 0, "skipped": 0}

    unsynced = _select_window(
        db.get_unsynced_garmin_activities(limit=max(limit, earliest or 0)),
        since=since,
        newest=None if earliest is not None else limit,
        earliest=earliest,
    )
    logger.info(f"Found {len(unsynced)} Garmin activities to sync to Coros")

    if not unsynced:
        logger.info("No Garmin activities to sync")
        return results

    for activity_id, activity_name, start_time, sport_type in unsynced:
        logger.info(f"[Garmin→Coros] {activity_id} - {activity_name or 'Unknown'}")

        try:
            if dry_run:
                logger.info(f"[DRY RUN] Would upload Garmin activity {activity_id} to Coros")
                results["skipped"] += 1
                continue

            fit_data = garmin_client.download_fit(activity_id)
            if not fit_data:
                logger.warning(f"Failed to download FIT for {activity_id}")
                db.mark_garmin_sync_failed(activity_id, -1)
                results["failed"] += 1
                continue

            success = coros_client.upload_activity(activity_id, fit_data)

            if success:
                db.mark_garmin_synced(activity_id)
                db.upsert_sync_mapping(
                    PLATFORM_GARMIN_INTL,
                    PLATFORM_COROS,
                    str(activity_id),
                    str(activity_id),
                    "synced",
                )
                logger.info(f"[Garmin→Coros] Successfully synced {activity_id}")
                results["synced"] += 1
            else:
                db.mark_garmin_sync_failed(activity_id, -2)
                logger.warning(f"[Garmin→Coros] Failed to upload {activity_id}")
                results["failed"] += 1

        except Exception as e:
            logger.error(f"[Garmin→Coros] Error syncing {activity_id}: {e}")
            db.mark_garmin_sync_failed(activity_id, -3)
            results["failed"] += 1

        time.sleep(2)

    return results


# ─── Coros → Garmin ──────────────────────────────────────────────────────────

def fetch_coros_activities(coros_client: CorosClient, db: SyncDB, since: Optional[date] = None) -> int:
    """Fetch activities from Coros and save to database"""
    logger.info("Fetching all activities from Coros...")

    activities = coros_client.get_all_activities()
    logger.info(f"Retrieved {len(activities)} activities from Coros")

    saved_count = 0
    for activity in activities:
        try:
            label_id = str(activity.get("labelId", ""))
            activity_name = activity.get("name", "")
            # Convert Unix timestamp to ISO format string
            start_ts = activity.get("startTime", 0)
            if start_ts and start_ts > 1000000000:
                start_time = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S")
            else:
                start_time = str(activity.get("date", ""))
            sport_type = activity.get("sportType", 0)

            if not _activity_is_on_or_after(start_time, since):
                continue

            if db.save_coros_activity(label_id, activity_name, start_time, sport_type):
                saved_count += 1

        except Exception as e:
            logger.error(f"Error saving Coros activity: {e}")

    logger.info(f"Saved {saved_count} new Coros activities to database")
    return saved_count


def sync_coros_to_garmin(coros_client: CorosClient, garmin_client: GarminClient,
                          db: SyncDB, dry_run: bool = False, limit: int = 100,
                          since: Optional[date] = None,
                          earliest: Optional[int] = None) -> dict:
    """Sync unsynced activities from Coros to Garmin"""
    results = {"synced": 0, "failed": 0, "skipped": 0}

    unsynced = _select_window(
        db.get_unsynced_coros_activities(limit=max(limit, earliest or 0)),
        since=since,
        newest=None if earliest is not None else limit,
        earliest=earliest,
    )
    logger.info(f"Found {len(unsynced)} Coros activities to sync to Garmin")

    if not unsynced:
        logger.info("No Coros activities to sync")
        return results

    # Ensure FIT_DIR exists for temp files
    FIT_DIR.mkdir(parents=True, exist_ok=True)

    for label_id, activity_name, start_time, sport_type in unsynced:
        logger.info(f"[Coros→Garmin] {label_id} - {activity_name or 'Unknown'}")

        try:
            if dry_run:
                logger.info(f"[DRY RUN] Would upload Coros activity {label_id} to Garmin")
                results["skipped"] += 1
                continue

            fit_data = coros_client.download_activity(label_id, sport_type or 0)
            if not fit_data:
                logger.warning(f"Failed to download FIT for Coros activity {label_id}")
                db.mark_coros_sync_failed(label_id, -1)
                results["failed"] += 1
                continue

            # Garmin's import_activity needs a file path - write to temp file
            temp_fit = FIT_DIR / f"coros_{label_id}.fit"
            temp_fit.write_bytes(fit_data)

            try:
                # Use Garmin's import_activity for cleaner import (no re-export to Strava)
                import_result = garmin_client.client.import_activity(str(temp_fit))
                logger.info(f"Garmin import result: {import_result}")

                # Check if import was successful or duplicate
                if import_result and import_result.get("detailedImportResult"):
                    successes = import_result["detailedImportResult"].get("successes", [])
                    failures = import_result["detailedImportResult"].get("failures", [])
                    if successes:
                        db.mark_coros_synced(label_id)
                        db.upsert_sync_mapping(
                            PLATFORM_COROS,
                            PLATFORM_GARMIN_INTL,
                            str(label_id),
                            str(label_id),
                            "synced",
                        )
                        results["synced"] += 1
                        logger.info(f"[Coros→Garmin] Successfully synced {label_id}")
                    else:
                        # Check for duplicate - this is OK, means already in Garmin
                        if failures and any('DUPLICATE' in str(f) for f in failures):
                            db.mark_coros_duplicate(label_id)
                            db.upsert_sync_mapping(
                                PLATFORM_COROS,
                                PLATFORM_GARMIN_INTL,
                                str(label_id),
                                str(label_id),
                                "duplicate",
                            )
                            results["synced"] += 1
                            logger.info(f"[Coros→Garmin] Duplicate activity {label_id} - already in Garmin")
                        else:
                            db.mark_coros_sync_failed(label_id, -2)
                            logger.warning(f"[Coros→Garmin] Import failed for {label_id}: {failures}")
                            results["failed"] += 1
                else:
                    db.mark_coros_synced(label_id)
                    db.upsert_sync_mapping(
                        PLATFORM_COROS,
                        PLATFORM_GARMIN_INTL,
                        str(label_id),
                        str(label_id),
                        "synced",
                    )
                    results["synced"] += 1
            finally:
                # Clean up temp file
                if temp_fit.exists():
                    temp_fit.unlink()

        except Exception as e:
            error_str = str(e)
            # Handle duplicate activity error (HTTP 409)
            if 'Duplicate' in error_str or 'duplicate' in error_str:
                db.mark_coros_duplicate(label_id)
                db.upsert_sync_mapping(
                    PLATFORM_COROS,
                    PLATFORM_GARMIN_INTL,
                    str(label_id),
                    str(label_id),
                    "duplicate",
                )
                results["synced"] += 1
                logger.info(f"[Coros→Garmin] Duplicate activity {label_id} - already in Garmin")
            else:
                logger.error(f"[Coros→Garmin] Error syncing {label_id}: {e}")
                db.mark_coros_sync_failed(label_id, -3)
                results["failed"] += 1

        time.sleep(2)

    return results


def get_sync_plans(args: argparse.Namespace):
    """Return enabled direction plans for the current run."""
    plans = [
        SyncDirectionPlan(
            direction_key=DIRECTION_GARMIN_INTL_TO_COROS,
            source_platform=PLATFORM_GARMIN_INTL,
            target_platform=PLATFORM_COROS,
            fetch_func=fetch_garmin_activities,
            fetch_kwargs_factory=lambda runtime: {
                "garmin_client": runtime["garmin_client"],
                "db": runtime["db"],
                "newest_num": runtime["args"].newest,
                "since": runtime["args"].since,
            },
            sync_func=sync_garmin_to_coros,
            sync_kwargs_factory=lambda runtime: {
                "garmin_client": runtime["garmin_client"],
                "coros_client": runtime["coros_client"],
                "db": runtime["db"],
                "dry_run": runtime["args"].dry_run,
                "limit": runtime["args"].newest,
                "since": runtime["args"].since,
                "earliest": runtime["args"].earliest,
            },
            stats_func=lambda db: db.get_garmin_stats(),
            force_fetch_enabled=lambda parsed_args: parsed_args.force_fetch_garmin,
            should_run=lambda parsed_args: not parsed_args.coros_only,
            stats_label="Garmin DB",
            result_label="[Garmin->Coros]",
        ),
        SyncDirectionPlan(
            direction_key=DIRECTION_COROS_TO_GARMIN_INTL,
            source_platform=PLATFORM_COROS,
            target_platform=PLATFORM_GARMIN_INTL,
            fetch_func=fetch_coros_activities,
            fetch_kwargs_factory=lambda runtime: {
                "coros_client": runtime["coros_client"],
                "db": runtime["db"],
                "since": runtime["args"].since,
            },
            sync_func=sync_coros_to_garmin,
            sync_kwargs_factory=lambda runtime: {
                "coros_client": runtime["coros_client"],
                "garmin_client": runtime["garmin_client"],
                "db": runtime["db"],
                "dry_run": runtime["args"].dry_run,
                "limit": runtime["args"].newest,
                "since": runtime["args"].since,
                "earliest": runtime["args"].earliest,
            },
            stats_func=lambda db: db.get_coros_stats(),
            force_fetch_enabled=lambda parsed_args: parsed_args.force_fetch_coros,
            should_run=lambda parsed_args: not parsed_args.garmin_only,
            stats_label="Coros DB",
            result_label="[Coros->Garmin]",
        ),
    ]
    return plans


def run_sync_plan(plan: SyncDirectionPlan, runtime: Dict) -> dict:
    """Execute fetch + sync for one direction plan."""
    args = runtime["args"]

    if plan.force_fetch_enabled(args):
        logger.info(f"Force fetching {plan.source_platform} activities before sync")

    fetched = plan.fetch_func(**plan.fetch_kwargs_factory(runtime))
    stats = plan.stats_func(runtime["db"])
    logger.info(
        f"{plan.stats_label}: {stats['total']} total, "
        f"{stats['synced']} synced, {stats['unsynced']} unsynced, "
        f"{stats['pending']} pending, {stats['duplicate']} duplicate, "
        f"{stats['failed_retryable']} retryable-failed"
    )

    results = plan.sync_func(**plan.sync_kwargs_factory(runtime))
    if args.dry_run:
        logger.info(f"{plan.result_label} DRY RUN: fetched={fetched}, results={results}")
    else:
        logger.info(f"{plan.result_label} fetched={fetched}, results={results}")
    return {
        "direction_key": plan.direction_key,
        "fetched": fetched,
        "results": results,
    }


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Garmin <-> Coros Bidirectional Sync Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full bidirectional sync
  python sync.py --coros-email "..." --coros-password "..."

  # With Garmin token data (for 2FA users)
  python sync.py --coros-email "..." --coros-password "..." --garmin-token-data "..."

  # Only Garmin -> Coros
  python sync.py --coros-email "..." --coros-password "..." --garmin-only

  # Only Coros -> Garmin
  python sync.py --coros-email "..." --coros-password "..." --coros-only

  # Dry run first
  python sync.py --coros-email "..." --coros-password "..." --dry-run
        """
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be synced without uploading")
    window_group = parser.add_mutually_exclusive_group()
    window_group.add_argument("--newest", type=int, default=NEWEST_NUM,
                              help=f"Number of newest activities to sync after filtering (default: {NEWEST_NUM})")
    window_group.add_argument("--earliest", type=int, default=None,
                              help="Number of earliest activities to sync after filtering")
    parser.add_argument("--since", type=_parse_since_date, default=None,
                        help="Only sync activities on or after this date (YYYYMMDD or YYYY-MM-DD)")
    parser.add_argument("--coros-email", default=COROS_EMAIL,
                        help="Coros account email")
    parser.add_argument("--coros-password", default=COROS_PASSWORD,
                        help="Coros account password")
    parser.add_argument("--garmin-token-data", default=GARMIN_TOKEN_DATA,
                        help="Full Garmin token JSON content as string (recommended for GitHub Actions / 2FA users)")
    parser.add_argument("--garmin-email", default=GARMIN_EMAIL,
                        help="Garmin account email (for non-2FA users or as account identifier)")
    parser.add_argument("--garmin-password", default=GARMIN_PASSWORD,
                        help="Garmin account password (for non-2FA users)")
    parser.add_argument("--force-fetch-garmin", action="store_true",
                        help="Force re-fetch activities from Garmin")
    parser.add_argument("--force-fetch-coros", action="store_true",
                        help="Force re-fetch activities from Coros")
    # Sync direction flags
    dir_group = parser.add_mutually_exclusive_group()
    dir_group.add_argument("--garmin-only", action="store_true",
                           help="Only sync Garmin -> Coros")
    dir_group.add_argument("--coros-only", action="store_true",
                           help="Only sync Coros -> Garmin")

    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("Garmin <-> Coros Sync Tool")
    logger.info("=" * 50)

    # Validate Coros credentials only if Coros directions will run.
    if _requires_coros_credentials(args) and (not args.coros_email or not args.coros_password):
        logger.error("Coros email and password are required")
        logger.error("Set COROS_EMAIL and COROS_PASSWORD environment variables")
        logger.error("Or use --coros-email and --coros-password arguments")
        sys.exit(1)

    # Validate Garmin credentials
    if not _has_garmin_auth(args):
        logger.error("Garmin auth required. Set one of:")
        logger.error("  - GARMIN_TOKEN_DATA: token JSON as string (for 2FA users)")
        logger.error("  - GARMIN_EMAIL + GARMIN_PASSWORD: for non-2FA users")
        sys.exit(1)

    try:
        db = SyncDB()

        # Connect to Garmin
        logger.info("Connecting to Garmin...")
        garmin_client = GarminClient(
            email=args.garmin_email if args.garmin_email else None,
            password=args.garmin_password if args.garmin_password else None,
            token_data=args.garmin_token_data,
        )

        logger.info("Connecting to Coros...")
        coros_client = CorosClient(args.coros_email, args.coros_password)

        runtime = {
            "args": args,
            "db": db,
            "garmin_client": garmin_client,
            "coros_client": coros_client,
        }

        plan_runs = []
        for plan in get_sync_plans(args):
            if plan.should_run(args):
                plan_runs.append(run_sync_plan(plan, runtime))

        _log_direction_run_summary(plan_runs)
        _log_final_summary(db)

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
