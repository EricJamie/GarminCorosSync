"""Platform and sync-direction constants shared across sync flows."""

PLATFORM_GARMIN_INTL = "garmin_intl"
PLATFORM_COROS = "coros"

DIRECTION_GARMIN_INTL_TO_COROS = f"{PLATFORM_GARMIN_INTL}->{PLATFORM_COROS}"
DIRECTION_COROS_TO_GARMIN_INTL = f"{PLATFORM_COROS}->{PLATFORM_GARMIN_INTL}"


def make_direction(source_platform: str, target_platform: str) -> str:
    """Create a normalized direction key for logging and mapping."""
    return f"{source_platform}->{target_platform}"
