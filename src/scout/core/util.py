"""Pure helper functions ported from the GEE prototype's utility layer.

These have no Earth Engine or Qt dependency and are fully unit-testable.
Ported from AlphaEarth Scout v1.4.16-STRESS (section 2, "DATA HELPERS").
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone

_CODE_SANITIZE_RE = re.compile(r"[^A-Z0-9_-]+")
_HEX_RE = re.compile(r"^[0-9A-F]{6}$")


def safe_code(text: str | None) -> str:
    """Uppercase, trim, and strip anything that isn't A-Z0-9_- .

    Mirrors the JS `safeCode()` used for all project/location/field/sample
    codes so codes stay filesystem- and asset-path-safe.
    """
    if text is None:
        return ""
    cleaned = str(text).strip().upper()
    return _CODE_SANITIZE_RE.sub("-", cleaned)


def safe_text(value) -> str:
    """Normalize optional free text; None/undefined becomes ''."""
    return "" if value is None else str(value)


def safe_number(value, fallback: float = -1.0) -> float:
    """Coerce to a finite float, or fall back (matches JS `safeNumber`)."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return fallback
    if n != n or n in (float("inf"), float("-inf")):  # NaN / inf check
        return fallback
    return n


def pad2(number: int) -> str:
    return f"{int(number):02d}"


def pad3(number: int) -> str:
    return f"{int(number):03d}"


def local_date_stamp() -> str:
    now = datetime.now()
    return f"{now.year:04d}{now.month:02d}{now.day:02d}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def make_uid(prefix: str = "OBJ") -> str:
    """Matches JS `makeUid`: PREFIX-<time base36>-<random base36>."""
    random_part = uuid.uuid4().hex[:8].upper()
    time_part = format(int(time.time() * 1000), "x").upper()
    return f"{str(prefix or 'OBJ').upper()}-{time_part}-{random_part}"


def simple_hash(text: str) -> str:
    """32-bit string hash matching the JS `simpleHash` (avoids relying on
    Math.imul-equivalent semantics; this is a plain Python port using
    wraparound 32-bit arithmetic so fingerprints are stable and short).
    """
    value = str(text or "")
    h = 0
    for ch in value:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF
    return format(h, "08X")


def normalize_hex_color(value: str | None, fallback: str = "FF00FF") -> str:
    clean = str(value or "").strip().replace("#", "").upper()
    if _HEX_RE.match(clean):
        return clean
    return fallback


def hex_to_rgb(hex_value: str) -> tuple[int, int, int]:
    clean = normalize_hex_color(hex_value)
    return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)


def rgb_to_hex(r: float, g: float, b: float) -> str:
    def clamp(v: float) -> int:
        return max(0, min(255, round(v)))

    return f"{clamp(r):02X}{clamp(g):02X}{clamp(b):02X}"


def mix_with_white(hex_value: str, white_fraction: float) -> str:
    r, g, b = hex_to_rgb(hex_value)
    f = max(0.0, min(1.0, white_fraction))
    return rgb_to_hex(r * (1 - f) + 255 * f, g * (1 - f) + 255 * f, b * (1 - f) + 255 * f)


def make_similarity_palette(hex_value: str) -> list[str]:
    """Six-stop ramp from near-white to the full mask colour, matching the
    JS `makeSimilarityPalette` used for the "Similarity ramp" mask style.
    """
    c = normalize_hex_color(hex_value)
    return [
        mix_with_white(c, 0.88),
        mix_with_white(c, 0.68),
        mix_with_white(c, 0.48),
        mix_with_white(c, 0.28),
        mix_with_white(c, 0.12),
        c,
    ]


MASK_COLOR_PRESETS = {
    "Magenta": "FF00FF",
    "Cyan": "00FFFF",
    "Yellow": "FFFF00",
    "Orange": "FF7F00",
    "Red": "FF0000",
    "Lime": "00FF00",
    "Blue": "0066FF",
    "White": "FFFFFF",
    "Black": "000000",
}
