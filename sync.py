#!/usr/bin/env python3
"""
Garmin ⇄ Coros Bidirectional Sync Tool

Syncs activities between Garmin International and Coros:
  - Garmin → Coros: download FIT from Garmin, upload to Coros
  - Coros → Garmin: download FIT from Coros, import to Garmin
"""
import argparse
import logging
import os
import sys
import time
import tempfile
from datetime import datetime
from pathlib import Path

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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


# ─── Garmin → Coros ──────────────────────────────────────────────────────────

def fetch_garmin_activities(garmin_client: GarminClient, db: SyncDB,
                            newest_num: int = 1000) -> int:
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

            if db.save_garmin_activity(activity_id, activity_name, start_time, sport_type):
                saved_count += 1

        except Exception as e:
            logger.error(f"Error saving Garmin activity: {e}")

    logger.info(f"Saved {saved_count} new Garmin activities to database")
    return saved_count


def sync_garmin_to_coros(garmin_client: GarminClient, coros_client: CorosClient,
                          db: SyncDB, dry_run: bool = False) -> dict:
    """Sync unsynced activities from Garmin to Coros"""
    results = {"synced": 0, "failed": 0, "skipped": 0}

    unsynced = db.get_unsynced_garmin_activities(limit=100)
    logger.info(f"Found {len(unsynced)} Garmin activities to sync to Coros")

    if not unsynced:
        logger.info("No Garmin activities to sync")
        return results

    for activity_id, activity_name, start_time, sport_type in unsynced:
        logger.info(f"[Garmin→Coros] {activity_id} - {activity_name or 'Unknown'}")

        try:
            fit_data = garmin_client.download_fit(activity_id)
            if not fit_data:
                logger.warning(f"Failed to download FIT for {activity_id}")
                db.mark_garmin_sync_failed(activity_id, -1)
                results["failed"] += 1
                continue

            if dry_run:
                logger.info(f"[DRY RUN] Would upload Garmin activity {activity_id} to Coros")
                results["skipped"] += 1
                continue

            success = coros_client.upload_activity(activity_id, fit_data)

            if success:
                db.mark_garmin_synced(activity_id)
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

def fetch_coros_activities(coros_client: CorosClient, db: SyncDB) -> int:
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

            if db.save_coros_activity(label_id, activity_name, start_time, sport_type):
                saved_count += 1

        except Exception as e:
            logger.error(f"Error saving Coros activity: {e}")

    logger.info(f"Saved {saved_count} new Coros activities to database")
    return saved_count


def sync_coros_to_garmin(coros_client: CorosClient, garmin_client: GarminClient,
                          db: SyncDB, dry_run: bool = False) -> dict:
    """Sync unsynced activities from Coros to Garmin"""
    results = {"synced": 0, "failed": 0, "skipped": 0}

    unsynced = db.get_unsynced_coros_activities(limit=100)
    logger.info(f"Found {len(unsynced)} Coros activities to sync to Garmin")

    if not unsynced:
        logger.info("No Coros activities to sync")
        return results

    # Ensure FIT_DIR exists for temp files
    FIT_DIR.mkdir(parents=True, exist_ok=True)

    for label_id, activity_name, start_time, sport_type in unsynced:
        logger.info(f"[Coros→Garmin] {label_id} - {activity_name or 'Unknown'}")

        try:
            fit_data = coros_client.download_activity(label_id, sport_type or 0)
            if not fit_data:
                logger.warning(f"Failed to download FIT for Coros activity {label_id}")
                db.mark_coros_sync_failed(label_id, -1)
                results["failed"] += 1
                continue

            if dry_run:
                logger.info(f"[DRY RUN] Would upload Coros activity {label_id} to Garmin")
                results["skipped"] += 1
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
                        results["synced"] += 1
                        logger.info(f"[Coros→Garmin] Successfully synced {label_id}")
                    else:
                        # Check for duplicate - this is OK, means already in Garmin
                        if failures and any('DUPLICATE' in str(f) for f in failures):
                            db.mark_coros_synced(label_id)
                            results["synced"] += 1
                            logger.info(f"[Coros→Garmin] Duplicate activity {label_id} - already in Garmin")
                        else:
                            db.mark_coros_sync_failed(label_id, -2)
                            logger.warning(f"[Coros→Garmin] Import failed for {label_id}: {failures}")
                            results["failed"] += 1
                else:
                    db.mark_coros_synced(label_id)
                    results["synced"] += 1
            finally:
                # Clean up temp file
                if temp_fit.exists():
                    temp_fit.unlink()

        except Exception as e:
            error_str = str(e)
            # Handle duplicate activity error (HTTP 409)
            if 'Duplicate' in error_str or 'duplicate' in error_str:
                db.mark_coros_synced(label_id)
                results["synced"] += 1
                logger.info(f"[Coros→Garmin] Duplicate activity {label_id} - already in Garmin")
            else:
                logger.error(f"[Coros→Garmin] Error syncing {label_id}: {e}")
                db.mark_coros_sync_failed(label_id, -3)
                results["failed"] += 1

        time.sleep(2)

    return results


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Garmin ⇄ Coros Bidirectional Sync Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full bidirectional sync
  python sync.py --coros-email "..." --coros-password "..."

  # With Garmin token directory (for 2FA users)
  python sync.py --coros-email "..." --coros-password "..." --garmin-email "..."

  # Only Garmin → Coros
  python sync.py --coros-email "..." --coros-password "..." --garmin-only

  # Only Coros → Garmin
  python sync.py --coros-email "..." --coros-password "..." --coros-only

  # Dry run first
  python sync.py --coros-email "..." --coros-password "..." --dry-run
        """
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be synced without uploading")
    parser.add_argument("--newest", type=int, default=NEWEST_NUM,
                        help=f"Number of latest Garmin activities to fetch (default: {NEWEST_NUM})")
    parser.add_argument("--coros-email", default=COROS_EMAIL,
                        help="Coros account email")
    parser.add_argument("--coros-password", default=COROS_PASSWORD,
                        help="Coros account password")
    parser.add_argument("--garmin-token-data", default=GARMIN_TOKEN_DATA,
                        help="Full garmin_tokens.json content as string (for GitHub Actions / 2FA users)")
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
                           help="Only sync Garmin → Coros")
    dir_group.add_argument("--coros-only", action="store_true",
                           help="Only sync Coros → Garmin")

    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("Garmin ⇄ Coros Sync Tool")
    logger.info("=" * 50)

    # Validate Coros credentials
    if not args.coros_email or not args.coros_password:
        logger.error("Coros email and password are required")
        logger.error("Set COROS_EMAIL and COROS_PASSWORD environment variables")
        logger.error("Or use --coros-email and --coros-password arguments")
        sys.exit(1)

    # Validate Garmin credentials
    has_token_data = bool(args.garmin_token_data and len(args.garmin_token_data) > 512)
    has_email_password = bool(args.garmin_email and args.garmin_password)
    has_garmin_auth = has_token_data or has_email_password
    if not has_garmin_auth:
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
            token_data=args.garmin_token_data
        )

        # Connect to Coros
        logger.info("Connecting to Coros...")
        coros_client = CorosClient(args.coros_email, args.coros_password)

        # ─── Garmin → Coros ────────────────────────────────────────────────
        if not args.coros_only:
            if args.force_fetch_garmin:
                fetch_garmin_activities(garmin_client, db, args.newest)

            garmin_stats = db.get_garmin_stats()
            logger.info(f"Garmin DB: {garmin_stats['total']} total, "
                        f"{garmin_stats['synced']} synced, {garmin_stats['unsynced']} unsynced")

            if not args.dry_run:
                results = sync_garmin_to_coros(garmin_client, coros_client, db, args.dry_run)
                logger.info(f"[Garmin→Coros] {results}")
            else:
                results = sync_garmin_to_coros(garmin_client, coros_client, db, dry_run=True)
                logger.info(f"[Garmin→Coros] DRY RUN: {results}")

        # ─── Coros → Garmin ────────────────────────────────────────────────
        if not args.garmin_only:
            if args.force_fetch_coros:
                fetch_coros_activities(coros_client, db)

            coros_stats = db.get_coros_stats()
            logger.info(f"Coros DB: {coros_stats['total']} total, "
                        f"{coros_stats['synced']} synced, {coros_stats['unsynced']} unsynced")

            if not args.dry_run:
                results = sync_coros_to_garmin(coros_client, garmin_client, db, args.dry_run)
                logger.info(f"[Coros→Garmin] {results}")
            else:
                results = sync_coros_to_garmin(coros_client, garmin_client, db, dry_run=True)
                logger.info(f"[Coros→Garmin] DRY RUN: {results}")

        # Final stats
        logger.info("=" * 50)
        logger.info(f"Garmin stats: {db.get_garmin_stats()}")
        logger.info(f"Coros stats:  {db.get_coros_stats()}")
        logger.info("Sync complete!")

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
