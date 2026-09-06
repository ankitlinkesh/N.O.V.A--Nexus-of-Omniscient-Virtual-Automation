from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..screen.capture import capture_screen_jpeg
from .windows import get_active_window, list_open_windows, windows_as_dicts


@dataclass
class DesktopObservation:
    timestamp: str
    active_window_title: str | None
    active_process: str | None
    open_windows: list[dict[str, object]] = field(default_factory=list)
    screen_capture_available: bool = False
    screen_capture_path: str | None = None
    last_tool_result: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_desktop_snapshot(
    *,
    include_windows: bool = True,
    include_screen: bool = False,
    explicit_screen_intent: bool = False,
    last_tool_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active = get_active_window()
    notes: list[str] = []
    if active is None:
        notes.append("Active window is unavailable on this platform or permission context.")
    open_windows = windows_as_dicts(list_open_windows()) if include_windows else []
    screen_path: str | None = None
    screen_available = False
    if include_screen:
        if not explicit_screen_intent:
            notes.append("Screen capture skipped because the request did not explicitly ask to inspect the screen.")
        else:
            try:
                image, _region = capture_screen_jpeg()
                output_dir = Path(__file__).resolve().parents[3] / "data"
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / "desktop_observation_screen.jpg"
                output_path.write_bytes(image)
                screen_path = str(output_path)
                screen_available = True
                notes.append("Captured one screenshot for this explicit request. No continuous watching is active.")
            except Exception as exc:
                notes.append(f"Screen capture failed safely: {exc}")
    observation = DesktopObservation(
        timestamp=datetime.now(timezone.utc).isoformat(),
        active_window_title=active.title if active else None,
        active_process=active.process_name if active else None,
        open_windows=open_windows,
        screen_capture_available=screen_available,
        screen_capture_path=screen_path,
        last_tool_result=last_tool_result,
        notes=notes,
    )
    return {"ok": True, **observation.as_dict()}
