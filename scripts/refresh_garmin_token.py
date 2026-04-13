#!/usr/bin/env python3
"""Acquire Garmin token data for local or GitHub Actions use."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from garmin.client import GarminClient


def _prompt_mfa() -> str:
    return input("Enter Garmin MFA code: ").strip()


def main():
    parser = argparse.ArgumentParser(description="Acquire Garmin token data")
    parser.add_argument("--garmin-email", default=None, help="Garmin email")
    parser.add_argument("--garmin-password", default=None, help="Garmin password")
    parser.add_argument("--garmin-token-data", default=None, help="Existing Garmin token JSON")
    args = parser.parse_args()

    client = GarminClient(
        email=args.garmin_email,
        password=args.garmin_password,
        token_data=args.garmin_token_data,
        prompt_mfa=_prompt_mfa,
    )
    print(client.export_token_data())


if __name__ == "__main__":
    main()
