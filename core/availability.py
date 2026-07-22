"""Shared constants and helpers for farm visit availability and horse periods.

Kept dependency-free (no models/schemas imports) so both the ORM models and the
Pydantic schemas can import from here without creating an import cycle.
"""

# The three visit periods, in canonical order.
PERIOD_KEYS = ["morning", "afternoon", "evening"]

# Fixed time windows each period's start/end must fall within (24h "HH:MM").
PERIOD_WINDOWS = {
    "morning": ("08:00", "12:00"),
    "afternoon": ("12:00", "16:00"),
    "evening": ("16:00", "18:00"),
}


def to_minutes(value: str) -> int:
    """Parse a strict 24h "HH:MM" string into minutes since midnight.

    Raises ValueError on any malformed value (used by validators -> 422).
    """
    if not isinstance(value, str):
        raise ValueError("time must be a string in HH:MM format")
    parts = value.split(":")
    if len(parts) != 2 or len(parts[0]) != 2 or len(parts[1]) != 2:
        raise ValueError(f"invalid time '{value}', expected HH:MM")
    hh, mm = parts
    if not (hh.isdigit() and mm.isdigit()):
        raise ValueError(f"invalid time '{value}', expected HH:MM")
    h, m = int(hh), int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"invalid time '{value}', hours 00-23 and minutes 00-59")
    return h * 60 + m


def default_farm_availability() -> dict:
    """Fresh default availability: enabled, all 7 weekdays, morning+afternoon open."""
    return {
        "enabled": True,
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "periods": {
            "morning": {"open": True, "start": "08:00", "end": "12:00"},
            "afternoon": {"open": True, "start": "12:00", "end": "16:00"},
            "evening": {"open": False, "start": "16:00", "end": "18:00"},
        },
    }


def default_horse_periods() -> list:
    """Fresh default horse periods: all three, canonical order."""
    return list(PERIOD_KEYS)


def normalize_periods(values) -> list:
    """Dedupe and reorder a list of period names into canonical order."""
    return [k for k in PERIOD_KEYS if k in values]
