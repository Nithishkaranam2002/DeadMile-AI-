#!/usr/bin/env python3
"""Cron-friendly script to sync live loads from LIVE_LOAD_API_URL into DeadMile."""

from __future__ import annotations

import os
import sys

import httpx

API_BASE = os.getenv("API_GATEWAY_URL", "http://localhost:8010").rstrip("/")
API_KEY = os.getenv("API_GATEWAY_KEY", "")


def main() -> int:
    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    try:
        resp = httpx.post(f"{API_BASE}/loads/live/sync", headers=headers, timeout=120.0)
        resp.raise_for_status()
        data = resp.json()
        print(f"Synced {data.get('upserted', 0)} loads from {data.get('source', 'api')}")
        return 0
    except Exception as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
