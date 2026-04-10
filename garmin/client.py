"""
Garmin Connect client for downloading activities
"""
import logging
from pathlib import Path
from typing import List, Optional

from config.settings import GARMIN_TOKEN_DIR, GARMIN_EMAIL, GARMIN_PASSWORD, GARMIN_TOKEN_DATA

logger = logging.getLogger(__name__)


class GarminClient:
    """Garmin Connect API client"""

    def __init__(self, email: str = None, password: str = None,
                 token_dir: str = None, token_data: str = None):
        from garminconnect import Garmin
        self.Garmin = Garmin
        self.email = email if email is not None else GARMIN_EMAIL
        self.password = password if password is not None else GARMIN_PASSWORD
        self.token_dir = token_dir or GARMIN_TOKEN_DIR
        self.token_data = token_data or GARMIN_TOKEN_DATA
        self.client = None
        self._connect()

    def _connect(self):
        """Connect to Garmin - token string > token dir > email+password"""
        from garminconnect import Garmin

        self.client = Garmin()

        # Strategy 1: Direct token data string (best for GitHub Actions / 2FA users)
        # If token_data is a long string (>512 chars), it's treated as token JSON content
        if self.token_data and len(self.token_data) > 512:
            logger.info("Logging in to Garmin with token data (direct string)")
            self.client.login(self.token_data)
            logger.info("Garmin login successful (token data)")
            return

        # Strategy 2: Token store directory
        if self.token_dir:
            token_path = Path(self.token_dir)
            if token_path.exists():
                subdirs = [d for d in token_path.iterdir() if d.is_dir() and d.name.isdigit()]
                if subdirs:
                    token_path = subdirs[0]
                    logger.info(f"Logging in to Garmin with token: {token_path}")
                    self.client.login(str(token_path))
                    logger.info("Garmin login successful (token dir)")
                    return

        # Strategy 3: Email + password (for non-2FA users)
        if self.email and self.password:
            logger.info(f"Logging in to Garmin with email: {self.email}")
            self.client.login(self.email, self.password)
            logger.info("Garmin login successful (email/password)")
            return

        raise ValueError(
            "Garmin login failed. Set one of:\n"
            "  - GARMIN_TOKEN_DATA: entire token JSON as a string (for GitHub Actions)\n"
            "  - GARMIN_TOKEN_DIR: path to ~/.garminconnect directory\n"
            "  - GARMIN_EMAIL + GARMIN_PASSWORD: for non-2FA accounts"
        )

        profile = self.client.get_user_profile()
        logger.info(f"Connected to Garmin: {profile.get('displayName', 'unknown')}")

    def get_activities(self, start: int = 0, limit: int = 100) -> List[dict]:
        """Get activities list"""
        try:
            activities = self.client.get_activities(start, limit)
            return activities or []
        except Exception as e:
            logger.error(f"Error fetching activities: {e}")
            return []

    def get_all_activities(self, newest_num: int = 1000) -> List[dict]:
        """Get all activities (paginated)"""
        all_activities = []
        start = 0
        limit = 100

        while len(all_activities) < newest_num:
            activities = self.get_activities(start, limit)
            if not activities:
                break
            all_activities.extend(activities)
            start += limit
            logger.debug(f"Fetched {len(all_activities)} activities so far")

            # If we got less than limit, we're done
            if len(activities) < limit:
                break

        # Trim to newest_num
        return all_activities[:newest_num]

    def download_fit(self, activity_id: int) -> Optional[bytes]:
        """Download FIT file for an activity"""
        try:
            # The FIT download URL is /download-service/files/activity/{activity_id}
            url = f"{self.client.garmin_connect_fit_download}/{activity_id}"
            fit_data = self.client.download(url)
            return fit_data
        except Exception as e:
            logger.error(f"Error downloading FIT for activity {activity_id}: {e}")
            return None

    def get_activity_info(self, activity_id: int) -> Optional[dict]:
        """Get activity details"""
        try:
            return self.client.get_activity_details(activity_id)
        except Exception as e:
            logger.error(f"Error getting activity details for {activity_id}: {e}")
            return None
