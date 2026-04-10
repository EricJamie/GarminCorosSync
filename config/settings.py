"""
Configuration settings for Garmin to Coros sync
"""
import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_DIR = DATA_DIR / "db"
FIT_DIR = DATA_DIR / "fit"
LOG_DIR = BASE_DIR / "logs"

# Garmin settings
GARMIN_TOKEN_DIR = os.getenv("GARMIN_TOKEN_DIR", str(Path.home() / ".garminconnect"))
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL", "")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD", "")
# Direct token JSON string (for GitHub Actions / 2FA users)
GARMIN_TOKEN_DATA = os.getenv("GARMIN_TOKEN_DATA", "")

# Coros settings
COROS_EMAIL = os.getenv("COROS_EMAIL", "")
COROS_PASSWORD = os.getenv("COROS_PASSWORD", "")

# Sync settings
SYNC_BATCH_SIZE = 100  # Number of activities to fetch per batch
NEWEST_NUM = int(os.getenv("GARMIN_NEWEST_NUM", "1000"))  # Fetch latest N activities

# Ensure directories exist
for d in [DATA_DIR, DB_DIR, FIT_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)
