"""Test configuration.

Integration tests need the real service credentials, and `.env.local` lives at
the repository root. Loading it here means `pytest` behaves the same way whether
it is run by hand or by a script, and without needing the file to be shell-safe —
a connection string containing `&` cannot simply be sourced.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env.local"

if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)
