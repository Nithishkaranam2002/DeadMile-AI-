"""
Validates that all required environment variables are set before starting.
Run: python scripts/validate_env.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REQUIRED = [
    ("OPENAI_API_KEY", "Get from https://platform.openai.com/api-keys"),
]

MAP_REQUIRED_ONE_OF = [
    ("NEXT_PUBLIC_MAPBOX_TOKEN", "Get from https://mapbox.com — free tier works"),
    ("NEXT_PUBLIC_MAPTILER_KEY", "Get from https://maptiler.com — alternative to Mapbox"),
]

OPTIONAL = [
    ("TAVILY_API_KEY", "Get from https://app.tavily.com — falls back to default fuel prices ($3.90/gal)"),
    ("LANGFUSE_PUBLIC_KEY", "Langfuse tracing — optional"),
    ("LANGFUSE_SECRET_KEY", "Langfuse tracing — optional"),
    ("GROQ_API_KEY", "Only if using Groq as LLM provider via LLM_MODEL"),
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


def _is_placeholder(val: str) -> bool:
    if not val:
        return True
    placeholders = ("your_", "sk-your", "tvly-your", "pk.your", "xxx", "change_me")
    return any(val.startswith(p) or p in val for p in placeholders)


def validate() -> None:
    root = Path(__file__).resolve().parents[1]
    _load_dotenv(root / ".env")

    missing_required = []
    missing_optional = []

    for var, help_text in REQUIRED:
        val = os.getenv(var, "")
        if _is_placeholder(val):
            missing_required.append((var, help_text))

    has_map = any(not _is_placeholder(os.getenv(var, "")) for var, _ in MAP_REQUIRED_ONE_OF)
    if not has_map:
        missing_required.append(
            ("NEXT_PUBLIC_MAPBOX_TOKEN or NEXT_PUBLIC_MAPTILER_KEY", "Set one map provider key")
        )

    for var, help_text in OPTIONAL:
        val = os.getenv(var, "")
        if _is_placeholder(val):
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
