from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
PROFILE_PATH = ROOT / "data" / "user_profile.md"


def load_profile() -> Optional[str]:
    if not PROFILE_PATH.exists():
        return None
    try:
        text = PROFILE_PATH.read_text(encoding="utf-8").strip()
        return text if text else None
    except Exception as exc:
        log.warning("user_profile.md load failed: %s — answering without profile", exc)
        return None


def format_profile_block(profile_text: Optional[str]) -> str:
    if not profile_text:
        return ""
    return f"PROFIL UŻYTKOWNIKA (uwzględnij w odpowiedzi — dostosuj ją do tej konkretnej sytuacji):\n{profile_text}"
