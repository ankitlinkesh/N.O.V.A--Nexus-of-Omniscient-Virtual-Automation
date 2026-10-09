from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib


@dataclass(frozen=True)
class ServerSettings:
    # Localhost by default. LAN access (e.g. phone control) is an explicit
    # opt-in via [server] host = "0.0.0.0" in config/eva.toml.
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass(frozen=True)
class SecuritySettings:
    pairing_token: str = "eva-local"


@dataclass(frozen=True)
class ModelSettings:
    provider: str = "hybrid"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:1.5b"
    fast_model: str = "qwen2.5:1.5b"
    deep_model: str = "mistral:7b"
    smart_enabled: bool = False
    smart_provider: str = "gemini"
    smart_model: str = "gemini-2.5-flash"


@dataclass(frozen=True)
class FeatureSettings:
    screen_capture: bool = True
    voice_enabled: bool = False
    camera_always_on: bool = False


@dataclass(frozen=True)
class Settings:
    server: ServerSettings
    security: SecuritySettings
    models: ModelSettings
    features: FeatureSettings


# Flags that let NOVA act on the real machine. .env.local overrides the process
# environment (it must beat stale shell exports), which also meant nothing could
# force these OFF from outside: a verifier run with EVA_ENABLE_REAL_INPUT=0 still got
# real input from the operator's .env.local. A process that explicitly turns one of
# these off now wins -- only in the off direction, so it can only add friction.
CAPABILITY_FLAGS = (
    "EVA_ENABLE_REAL_INPUT",
    "EVA_GUI_GROUNDING_ENABLED",
    "EVA_MCP_ENABLED",
    "EVA_V2_PLAYWRIGHT_ENABLED",
    "EVA_V2_PYAUTOGUI_ENABLED",
    "EVA_V2_RUNTIME_ENABLED",
    "EVA_VOICE_ENABLED",
    "EVA_VOICE_INPUT_ENABLED",
    "EVA_PERCEPTION_ENABLED",
    "EVA_PROACTIVITY_ENABLED",
    "EVA_BACKGROUND_WORKER_ENABLED",
    "EVA_DURABLE_QUEUE_ENABLED",
    "EVA_SELF_IMPROVEMENT_ENABLED",
)
_EXPLICIT_OFF = {"0", "false", "no", "off"}
# Captured once, from the environment this process was started with.
_PROCESS_DENIED = frozenset(flag for flag in CAPABILITY_FLAGS if os.environ.get(flag, "").strip().lower() in _EXPLICIT_OFF)


def process_denied_flags() -> frozenset[str]:
    return _PROCESS_DENIED


def load_local_env(path: Path, *, override: bool = False) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in _PROCESS_DENIED and value.strip().lower() not in _EXPLICIT_OFF:
            continue  # the launching process turned this capability off; a file cannot turn it back on
        if key and (override or key not in os.environ):
            os.environ[key] = value


def load_project_env(root: Path) -> None:
    load_local_env(root / ".env")
    load_local_env(root / ".env.local", override=True)


def _section(data: dict, name: str) -> dict:
    value = data.get(name, {})
    return value if isinstance(value, dict) else {}


def load_settings(path: Path) -> Settings:
    raw: dict = {}
    if path.exists():
        raw = tomllib.loads(path.read_text(encoding="utf-8-sig"))

    server = _section(raw, "server")
    security = _section(raw, "security")
    models = _section(raw, "models")
    features = _section(raw, "features")

    fast_model = str(models.get("fast_model", models.get("ollama_model", "qwen2.5:1.5b")))
    deep_model = str(models.get("deep_model", "mistral:7b"))

    return Settings(
        server=ServerSettings(
            host=str(server.get("host", "127.0.0.1")),
            port=int(server.get("port", 8765)),
        ),
        security=SecuritySettings(
            pairing_token=str(security.get("pairing_token", "eva-local")),
        ),
        models=ModelSettings(
            provider=str(models.get("provider", "hybrid")),
            ollama_url=str(models.get("ollama_url", "http://127.0.0.1:11434")),
            ollama_model=str(models.get("ollama_model", fast_model)),
            fast_model=fast_model,
            deep_model=deep_model,
            smart_enabled=bool(models.get("smart_enabled", False)),
            smart_provider=str(models.get("smart_provider", "gemini")),
            smart_model=str(models.get("smart_model", "gemini-2.5-flash")),
        ),
        features=FeatureSettings(
            screen_capture=bool(features.get("screen_capture", True)),
            voice_enabled=bool(features.get("voice_enabled", False)),
            camera_always_on=bool(features.get("camera_always_on", False)),
        ),
    )
