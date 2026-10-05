from __future__ import annotations

from enum import StrEnum


class ActionType(StrEnum):
    SAFE_LOCAL_READ = "SAFE_LOCAL_READ"
    SAFE_LOCAL_UI = "SAFE_LOCAL_UI"
    PRIVACY_SCREEN_READ = "PRIVACY_SCREEN_READ"
    PRIVACY_FILE_READ = "PRIVACY_FILE_READ"
    PRIVACY_CHAT_READ = "PRIVACY_CHAT_READ"
    EXTERNAL_MESSAGE_SEND = "EXTERNAL_MESSAGE_SEND"
    EXTERNAL_POST = "EXTERNAL_POST"
    DESTRUCTIVE_FILE_ACTION = "DESTRUCTIVE_FILE_ACTION"
    SYSTEM_CHANGE = "SYSTEM_CHANGE"
    POWER_ACTION = "POWER_ACTION"
    NETWORK_ACTION = "NETWORK_ACTION"
    SHELL_ACTION = "SHELL_ACTION"
    # Phase 130: a command inside NOVA's isolated WSL box. NOT SHELL_ACTION (which
    # stays hard-blocked): this never runs on the Windows host.
    SANDBOX_COMMAND = "SANDBOX_COMMAND"
    # Phase 134: a file crossing the sandbox boundary (share.to_box / share.from_box).
    # Confirm-class in BOTH gates: the box has internet, and box-made content lands
    # in the user's folders.
    SANDBOX_TRANSFER = "SANDBOX_TRANSFER"
    CREDENTIAL_ACCESS = "CREDENTIAL_ACCESS"
    THIRD_PARTY_SPYING = "THIRD_PARTY_SPYING"
    MALWARE_LIKE = "MALWARE_LIKE"
    ILLEGAL_HARMFUL = "ILLEGAL_HARMFUL"
    UNKNOWN_RISK = "UNKNOWN_RISK"
