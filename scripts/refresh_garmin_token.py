#!/usr/bin/env python3
"""Refresh or acquire a Garmin tokenstore for local/GitHub Actions use."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from garmin.client import GarminClient


def _prompt_mfa() -> str:
    return input("Enter Garmin MFA code: ").strip()


def main():
    parser = argparse.ArgumentParser(description="Refresh or acquire Garmin token data")
    parser.add_argument("--garmin-email", default=None, help="Garmin email")
    parser.add_argument("--garmin-password", default=None, help="Garmin password")
    parser.add_argument("--garmin-token-data", default=None, help="Existing Garmin token JSON")
    parser.add_argument("--garmin-tokenstore", default=None, help="Target Garmin tokenstore path")
    parser.add_argument("--print-token-data", action="store_true", help="Print token JSON to stdout after login")
    args = parser.parse_args()

    client = GarminClient(
        email=args.garmin_email,
        password=args.garmin_password,
        token_data=args.garmin_token_data,
        tokenstore=args.garmin_tokenstore,
        prompt_mfa=_prompt_mfa,
    )
    saved_path = client.refresh_tokenstore(args.garmin_tokenstore)
    print(f"Saved Garmin tokenstore: {saved_path}")

    if args.print_token_data:
        print(client.export_token_data())


if __name__ == "__main__":
    main()
