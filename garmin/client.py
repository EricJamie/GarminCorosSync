"""
Garmin Connect client for downloading activities
"""
import logging
from pathlib import Path
from typing import List, Optional

from config.settings import GARMIN_EMAIL, GARMIN_PASSWORD, GARMIN_TOKEN_DATA, GARMIN_TOKENSTORE

logger = logging.getLogger(__name__)


class GarminTokenExpiredError(RuntimeError):
    """Raised when saved Garmin tokens are no longer usable."""


class GarminClient:
    """Garmin Connect API client"""

    def __init__(self, email: str = None, password: str = None,
                 token_data: str = None, tokenstore: str = None, prompt_mfa=None):
        from garminconnect import Garmin
        self.Garmin = Garmin
        self.email = email if email is not None else GARMIN_EMAIL
        self.password = password if password is not None else GARMIN_PASSWORD
        self.token_data = token_data or GARMIN_TOKEN_DATA
        self.tokenstore = tokenstore or GARMIN_TOKENSTORE
        self.prompt_mfa = prompt_mfa
        self.client = None
        self._connect()

    def _new_garmin(self, *args):
        prompt_mfa = getattr(self, "prompt_mfa", None)
        if prompt_mfa:
            return self.Garmin(*args, prompt_mfa=prompt_mfa)
        return self.Garmin(*args)

    def _login_with_token_data(self) -> None:
        logger.info("Logging in to Garmin with token data")
        self.client = self._new_garmin()
        self.client.login(self.token_data)
        logger.info("Garmin login successful (token)")

    def _login_with_tokenstore(self, tokenstore_path: str) -> None:
        logger.info(f"Logging in to Garmin with tokenstore: {tokenstore_path}")
        self.client = self._new_garmin(self.email or None, self.password or None)
        self.client.login(tokenstore_path)
        logger.info("Garmin login successful (tokenstore)")

    def _login_with_password(self) -> None:
        logger.info(f"Logging in to Garmin with email: {self.email}")
        self.client = self._new_garmin(self.email, self.password)
        tokenstore_write_path = self._resolve_tokenstore_write_path()
        logger.info(f"Garmin tokenstore will be saved to: {tokenstore_write_path}")
        self.client.login(tokenstore_write_path)
        logger.info("Garmin login successful (email/password)")

    def dump_tokenstore(self, path: str = None) -> str:
        """Persist the current Garmin token state to disk."""
        if not self.client or not hasattr(self.client, "client"):
            raise RuntimeError("Garmin client is not connected")
        target_path = path or self._resolve_tokenstore_write_path()
        self.client.client.dump(target_path)
        return target_path

    def export_token_data(self) -> str:
        """Export current Garmin token JSON."""
        if not self.client or not hasattr(self.client, "client"):
            raise RuntimeError("Garmin client is not connected")
        return self.client.client.dumps()

    def refresh_tokenstore(self, path: str = None) -> str:
        """Refresh persisted Garmin tokens when the underlying client supports it."""
        if not self.client or not hasattr(self.client, "client"):
            raise RuntimeError("Garmin client is not connected")

        inner_client = self.client.client
        target_path = path or self._resolve_tokenstore_write_path()

        if hasattr(inner_client, "_refresh_session"):
            logger.info("Refreshing Garmin tokenstore")
            inner_client._refresh_session()
            inner_client.dump(target_path)
            logger.info("Garmin tokenstore refreshed")
            return target_path

        logger.info("Underlying Garmin client has no explicit refresh API; dumping current tokenstore")
        inner_client.dump(target_path)
        return target_path

    def _discover_tokenstore(self) -> Optional[str]:
        """Find the most recent local Garmin tokenstore if present."""
        configured = Path(self.tokenstore).expanduser() if self.tokenstore else None
        if configured and configured.exists():
            return str(configured)

        home = Path.home()
        candidates = sorted(
            home.glob(".garminconnect/*/garmin_tokens.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return str(candidates[0])
        return None

    def _resolve_tokenstore_write_path(self) -> str:
        """Choose where a first successful login should persist tokens."""
        if self.tokenstore:
            path = Path(self.tokenstore).expanduser()
        else:
            path = Path.home() / ".garminconnect" / "default" / "garmin_tokens.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    @staticmethod
    def _is_token_error(exc: Exception) -> bool:
        message = str(exc).lower()
        token_markers = (
            "token",
            "expired",
            "invalid",
            "unauthorized",
            "401",
            "social profile",
        )
        return any(marker in message for marker in token_markers)

    @classmethod
    def _wrap_token_error(cls, exc: Exception, source: str) -> GarminTokenExpiredError:
        if cls._is_token_error(exc):
            return GarminTokenExpiredError(f"Garmin {source} is expired or invalid: {exc}")
        return GarminTokenExpiredError(f"Garmin {source} login failed: {exc}")

    def _connect(self):
        """Connect to Garmin with token reuse first, then credentials fallback."""
        if not hasattr(self, "Garmin"):
            from garminconnect import Garmin
            self.Garmin = Garmin

        if self.token_data and len(self.token_data) > 512:
            try:
                self._login_with_token_data()
                return
            except Exception as exc:
                if self.email and self.password:
                    logger.warning(
                        "%s Falling back to email/password and refreshing tokenstore.",
                        self._wrap_token_error(exc, "token"),
                    )
                else:
                    raise self._wrap_token_error(exc, "token") from exc

        tokenstore_path = self._discover_tokenstore()
        if tokenstore_path:
            try:
                self._login_with_tokenstore(tokenstore_path)
                return
            except Exception as exc:
                if self.email and self.password:
                    logger.warning(
                        "%s Falling back to email/password and refreshing tokenstore.",
                        self._wrap_token_error(exc, "tokenstore"),
                    )
                else:
                    raise self._wrap_token_error(exc, "tokenstore") from exc

        if self.email and self.password:
            self._login_with_password()
            return

        raise ValueError(
            "Garmin login failed. Set one of:\n"
            "  - GARMIN_TOKEN_DATA: token JSON as string (for 2FA users)\n"
            "  - GARMIN_EMAIL + GARMIN_PASSWORD: for non-2FA users"
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
