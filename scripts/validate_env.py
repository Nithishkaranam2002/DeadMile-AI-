"""
Validates that all required environment variables are set before starting.
Run: python scripts/validate_env.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REQUIRED = [
    ("FEATHERLESS_API_KEY", "Get from https://featherless.ai — use promo BUILDATHON26"),
    ("NEXT_PUBLIC_MAPBOX_TOKEN", "Get from https://mapbox.com — free tier is fine"),
]

OPTIONAL = [
    ("TAVILY_API_KEY", "Get from https://app.tavily.com — falls back to default fuel prices"),
    ("LANGFUSE_PUBLIC_KEY", "Get from Langfuse — tracing is optional"),
    ("LANGFUSE_SECRET_KEY", "Get from Langfuse — tracing is optional"),
    ("OPENAI_API_KEY", "Optional fallback LLM — not required if Featherless works"),
]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def validate() -> None:
    root = Path(__file__).resolve().parents[1]
    _load_dotenv(root / ".env")

    missing_required = []
    missing_optional = []

    for var, help_text in REQUIRED:
        val = os.getenv(var, "")
        if not val or val.startswith("your_"):
            missing_required.append((var, help_text))

    for var, help_text in OPTIONAL:
        val = os.getenv(var, "")
        if not val or val.startswith("your_"):
            missing_optional.append((var, help_text))

    if missing_required:
        print("❌ MISSING REQUIRED ENVIRONMENT VARIABLES:")
        for var, help_text in missing_required:
            print(f"   {var} — {help_text}")
        print()

    if missing_optional:
        print("⚠️  OPTIONAL (will use defaults):")
        for var, help_text in missing_optional:
            print(f"   {var} — {help_text}")
        print()

    if missing_required:
        print("Fix the required variables in .env and try again.")
        sys.exit(1)

    print("✅ All required environment variables are set!")
    sys.exit(0)


if __name__ == "__main__":
    validate()
