# Garmin <-> Coros Sync Tool

Garmin International and Coros bidirectional sync utility.

## Supported Directions

- Garmin -> Coros
- Coros -> Garmin
- Bidirectional sync in one run

## Authentication

Garmin uses token JSON:

- `GARMIN_TOKEN_DATA`

Coros uses account credentials:

- `COROS_EMAIL`
- `COROS_PASSWORD`

Optional Garmin bootstrap credentials:

- `GARMIN_EMAIL`
- `GARMIN_PASSWORD`

Config priority:

1. CLI args
2. Environment variables
3. Project-root `.env`

## Install

```bash
pip install -r requirements.txt
```

## Get Garmin Token Data

```bash
python scripts/refresh_garmin_token.py \
  --garmin-email you@example.com \
  --garmin-password your-password
```

The script prints one JSON object. Put that full JSON string into `GARMIN_TOKEN_DATA`.

Example:

```env
GARMIN_TOKEN_DATA={"di_token":"...","di_refresh_token":"...","di_client_id":"..."}
COROS_EMAIL=you@example.com
COROS_PASSWORD=your-password
GARMIN_NEWEST_NUM=1000
```

## Common Commands

Full bidirectional sync:

```bash
python sync.py
```

Garmin only:

```bash
python sync.py --garmin-only
```

Coros only:

```bash
python sync.py --coros-only
```

Dry run:

```bash
python sync.py --dry-run
```

From a date onward:

```bash
python sync.py --garmin-only --since 20250330
```

Newest 3 after a date:

```bash
python sync.py --coros-only --since 20250330 --newest 3
```

Earliest 3 after a date:

```bash
python sync.py --coros-only --since 20250330 --earliest 3
```

## CLI Options

- `--garmin-only`
- `--coros-only`
- `--dry-run`
- `--since YYYYMMDD|YYYY-MM-DD`
- `--newest N`
- `--earliest N`

`--newest` and `--earliest` are mutually exclusive.

## GitHub Actions

Workflow:
[sync.yml](/Users/ms/项目/GarminProject/GarminCorosSync/.github/workflows/sync.yml)

Required GitHub Secrets:

- `GARMIN_TOKEN_DATA`
- `COROS_EMAIL`
- `COROS_PASSWORD`

Manual workflow inputs:

- `direction`
  `both`, `garmin_only`, `coros_only`
- `since`
  optional date lower bound
- `window_mode`
  `default`, `newest`, `earliest`
- `window_size`
  used with `newest` or `earliest`
- `dry_run`

## Notes

- First runs should use `--dry-run`.
- Garmin token refresh is manual: re-run the token script and replace `GARMIN_TOKEN_DATA`.
- Local `.env` and GitHub Secrets are equivalent configuration sources for runtime behavior.

Internal implementation notes live in [private_docs/INTERNAL.md](/Users/ms/项目/GarminProject/GarminCorosSync/private_docs/INTERNAL.md).
