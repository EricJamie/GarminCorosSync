"""
Garmin Connect client wrapper for this sync project.
"""
import logging
from pathlib import Path
from typing import List, Optional

from config.settings import GARMIN_EMAIL, GARMIN_PASSWORD, GARMIN_TOKEN_DATA
from garmin.vendor.garmin_client import ActivityDownloadFormat, GarminClient as VendoredGarminClient
from garmin.vendor.garmin_client.constants import ACTIVITIES_URL

logger = logging.getLogger(__name__)


class GarminTokenExpiredError(RuntimeError):
    """Raised when provided Garmin token data is no longer usable."""


class GarminClient:
    """Project-level compatibility wrapper around the vendored Garmin client."""

    def __init__(
        self,
        email: str = None,
        password: str = None,
        token_data: str = None,
        prompt_mfa=None,
    ):
        self.email = email if email is not None else GARMIN_EMAIL
        self.password = password if password is not None else GARMIN_PASSWORD
        self.token_data = token_data or GARMIN_TOKEN_DATA
        self.prompt_mfa = prompt_mfa

        self._client: Optional[VendoredGarminClient] = None
        self.client = self

        self._connect()

    def _new_client(self) -> VendoredGarminClient:
        return VendoredGarminClient()

    def _login_with_token_data(self) -> None:
        logger.info("Logging in to Garmin with token data")
        self._client = self._new_client()
        self._client.loads(self.token_data)
        self._client._load_profile()
        logger.info("Garmin login successful (token)")

    def _login_with_password(self) -> None:
        logger.info("Logging in to Garmin with email: %s", self.email)
        self._client = self._new_client()
        self._client.login(self.email, self.password, prompt_mfa=self.prompt_mfa)
        logger.info("Garmin login successful (email/password)")

    def export_token_data(self) -> str:
        """Export current Garmin token JSON."""
        if not self._client:
            raise RuntimeError("Garmin client is not connected")
        return self._client.dumps()

    @staticmethod
    def _is_token_error(exc: Exception) -> bool:
        message = str(exc).lower()
        token_markers = (
            "token",
            "expired",
            "invalid",
            "unauthorized",
            "401",
            "refresh",
            "429",
            "too many requests",
        )
        return any(marker in message for marker in token_markers)

    @classmethod
    def _wrap_token_error(cls, exc: Exception, source: str) -> GarminTokenExpiredError:
        if cls._is_token_error(exc):
            return GarminTokenExpiredError(f"Garmin {source} is expired or invalid: {exc}")
        return GarminTokenExpiredError(f"Garmin {source} login failed: {exc}")

    def _connect(self):
        """Connect to Garmin with token reuse first, then credentials fallback."""
        if self.token_data and len(self.token_data) > 32:
            try:
                self._login_with_token_data()
                return
            except Exception as exc:
                if self.email and self.password:
                    logger.warning(
                        "%s Falling back to email/password and reissuing token data.",
                        self._wrap_token_error(exc, "token"),
                    )
                else:
                    raise self._wrap_token_error(exc, "token") from exc

        if self.email and self.password:
            self._login_with_password()
            return

        raise ValueError(
            "Garmin login failed. Set one of:\n"
            "  - GARMIN_TOKEN_DATA: token JSON as string\n"
            "  - GARMIN_EMAIL + GARMIN_PASSWORD"
        )

    def get_activities(self, start: int = 0, limit: int = 100) -> List[dict]:
        """Get activities list using the same endpoint shape as upstream garminconnect."""
        try:
            if not self._client:
                return []
            return self._client._connectapi(
                ACTIVITIES_URL,
                params={"start": str(start), "limit": str(limit)},
            ) or []
        except Exception as e:
            logger.error("Error fetching activities: %s", e)
            return []

    def get_all_activities(self, newest_num: int = 1000) -> List[dict]:
        """Get all activities (paginated)."""
        all_activities = []
        start = 0
        limit = 100

        while len(all_activities) < newest_num:
            activities = self.get_activities(start, limit)
            if not activities:
                break
            all_activities.extend(activities)
            start += limit

            if len(activities) < limit:
                break

        return all_activities[:newest_num]

    def download_fit(self, activity_id: int) -> Optional[bytes]:
        """Download FIT zip for an activity."""
        try:
            if not self._client:
                return None
            return self._client.download_activity(
                activity_id,
                ActivityDownloadFormat.ORIGINAL,
            )
        except Exception as e:
            logger.error("Error downloading FIT for activity %s: %s", activity_id, e)
            return None

    def get_activity_info(self, activity_id: int) -> Optional[dict]:
        """Get activity details when available."""
        try:
            if not self._client:
                return None
            return self._client._connectapi(f"/activity-service/activity/{int(activity_id)}")
        except Exception as e:
            logger.error("Error getting activity details for %s: %s", activity_id, e)
            return None

    def get_user_profile(self) -> Optional[dict]:
        """Return Garmin user settings/profile."""
        if not self._client:
            return None
        return self._client.get_user_profile()

    def upload_activity(self, activity_path: str):
        """Upload an activity file to Garmin Connect."""
        if not self._client:
            raise RuntimeError("Garmin client is not connected")

        activity_file = Path(activity_path)
        if not activity_file.exists():
            raise FileNotFoundError(activity_path)

        with activity_file.open("rb") as handle:
            return self._client._request(
                "POST",
                "/upload-service/upload",
                files={"file": (activity_file.name, handle)},
            ).json()

    def import_activity(self, activity_path: str):
        """Compatibility alias for older call sites."""
        return self.upload_activity(activity_path)
