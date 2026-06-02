from __future__ import annotations

import os


def get_release_channel() -> str:
    channel = os.environ.get("EVA_RELEASE_CHANNEL", "development").strip().lower()
    if channel in {"community", "public", "development", "private"}:
        return channel
    return "development"


def is_public_mode() -> bool:
    explicit = os.environ.get("EVA_PUBLIC_MODE", "").strip().lower()
    if explicit in {"1", "true", "yes", "on", "community", "public"}:
        return True
    if explicit in {"0", "false", "no", "off"}:
        return False
    return get_release_channel() == "community"
