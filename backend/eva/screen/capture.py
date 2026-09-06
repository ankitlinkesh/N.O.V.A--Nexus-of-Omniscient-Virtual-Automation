from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from mss import mss
from PIL import Image

from .dpi import ensure_dpi_aware


@dataclass(frozen=True)
class CaptureRegion:
    """Where on the desktop an image came from, in the coordinates clicks use.

    Travels WITH the image. The only reason anything needs a screenshot's size is
    to turn a position inside it back into a position on screen, and that needs
    the origin too -- so a size without an origin is an invitation to get it
    wrong. Phase 107 clicked 1800px away because one function measured the screen
    and a different one captured it.
    """

    left: int
    top: int
    width: int
    height: int

    @property
    def valid(self) -> bool:
        return self.width > 0 and self.height > 0

    def to_screen(self, x_in_image: float, y_in_image: float) -> tuple[int, int]:
        """Image coordinates -> screen coordinates."""
        return int(self.left + x_in_image), int(self.top + y_in_image)

    def as_dict(self) -> dict[str, int]:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, raw: object) -> "CaptureRegion | None":
        if not isinstance(raw, dict):
            return None
        try:
            region = cls(int(raw["left"]), int(raw["top"]), int(raw["width"]), int(raw["height"]))
        except (KeyError, TypeError, ValueError):
            return None
        return region if region.valid else None


def virtual_desktop_region() -> CaptureRegion:
    """The union of every display, in click coordinates."""
    ensure_dpi_aware()
    with mss() as screen:
        monitor = screen.monitors[0]
    return CaptureRegion(
        int(monitor["left"]), int(monitor["top"]), int(monitor["width"]), int(monitor["height"])
    )


def clamp_to_desktop(region: CaptureRegion) -> CaptureRegion | None:
    """Trim a rect to the part of it that is actually on a display.

    A window rect can hang off the edge of the desktop. Grabbing an off-screen
    rect either fails or silently returns a differently-sized image, and then the
    origin arithmetic is wrong again in exactly the case the origin exists for --
    so the CLAMPED rect is what gets reported, never the requested one.
    """
    desktop = virtual_desktop_region()
    left = max(region.left, desktop.left)
    top = max(region.top, desktop.top)
    right = min(region.left + region.width, desktop.left + desktop.width)
    bottom = min(region.top + region.height, desktop.top + desktop.height)
    if right <= left or bottom <= top:
        return None
    return CaptureRegion(left, top, right - left, bottom - top)


def foreground_window_region() -> CaptureRegion | None:
    """The rect of the window in front, clamped to the desktop, or None.

    This is how a vision call stays scoped to the app being automated instead of
    photographing every display. None means "I could not establish a window",
    and callers are expected to REFUSE rather than quietly widen to the whole
    desktop -- silently sending more than the task needs is the failure this
    exists to prevent.
    """
    ensure_dpi_aware()
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        rect = wintypes.RECT()
        if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            return None
    except Exception:
        return None

    region = CaptureRegion(
        int(rect.left), int(rect.top), int(rect.right - rect.left), int(rect.bottom - rect.top)
    )
    return clamp_to_desktop(region) if region.valid else None


def capture_screen_jpeg(
    quality: int = 74, region: CaptureRegion | None = None
) -> tuple[bytes, CaptureRegion]:
    """Capture `region` (default: the whole desktop) and say which region it was.

    **Callers choose their own scope, deliberately.** "What is on my screen" and
    "where in this window is that button" are different questions, and answering
    the second by photographing every display sends far more away than the task
    needs -- during Phase 108's own validation a full-desktop grab put an
    unrelated video call into a cloud request. So the vision-click path passes the
    foreground window's rect and the general screenshot paths keep the desktop.

    On the monitor indices: `monitors[0]` is the union of every display.
    `monitors[1]` is NOT reliably the primary one -- mss enumerates in
    EnumDisplayMonitors order, and on the machine this was measured on
    `monitors[1]` reports `is_primary: False` while the real primary is
    `monitors[2]`. The function this replaced grabbed `monitors[1]` and called it
    "the primary screen".
    """
    ensure_dpi_aware()
    wanted = region or virtual_desktop_region()
    clamped = clamp_to_desktop(wanted)
    if clamped is None:
        raise ValueError(f"Capture region {wanted.as_dict()} is entirely off-screen.")

    with mss() as screen:
        shot = screen.grab(
            {"left": clamped.left, "top": clamped.top, "width": clamped.width, "height": clamped.height}
        )
        image = Image.frombytes("RGB", shot.size, shot.rgb)

    out = BytesIO()
    image.save(out, format="JPEG", quality=quality, optimize=True)
    # Width and height come from the IMAGE, not the requested rect: the grid the
    # model answers on is laid over the pixels it was actually shown.
    return out.getvalue(), CaptureRegion(clamped.left, clamped.top, int(image.width), int(image.height))
