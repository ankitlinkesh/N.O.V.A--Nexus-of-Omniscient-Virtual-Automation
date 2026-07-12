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
