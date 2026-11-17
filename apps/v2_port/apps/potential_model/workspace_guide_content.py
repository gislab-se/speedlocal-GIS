"""Read presentation-only instructions without importing the app runtime."""
from __future__ import annotations

import json
from pathlib import Path


_TARGETS = frozenset({
    "region", "map", "wind-nature", "wind-grid-apply",
    "scenario", "mix", "social", "results",
})


def load_instruction_steps(path: Path, *, region_id: str) -> list[dict[str, str]]:
    """Read first-visit guide copy separately from recording instructions."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Guide source must be readable UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Guide source must be an object")
    if payload.get("region_id") != region_id:
        raise ValueError("Guide source must match the requested region")
    if payload.get("language") != "sv":
        raise ValueError("Guide source must declare Swedish language")
    steps = payload.get("steps")
    if not isinstance(steps, list) or len(steps) != 10:
        raise ValueError("Guide source must contain exactly ten steps")
    result: list[dict[str, str]] = []
    identifiers: set[str] = set()
    for step in steps:
        if not isinstance(step, dict) or any(
            not isinstance(step.get(key), str) or not step[key].strip()
            for key in ("id", "guide_title", "guide_text", "guide_target")
        ):
            raise ValueError("Guide steps require nonempty text fields")
        if step["id"] in identifiers:
            raise ValueError("Guide steps require unique identifiers")
        if step["guide_target"] not in _TARGETS:
            raise ValueError("Guide steps require supported targets")
        identifiers.add(step["id"])
        result.append({
            "id": step["id"],
            "target": step["guide_target"],
            "title": step["guide_title"],
            "body": step["guide_text"],
        })
    return result
