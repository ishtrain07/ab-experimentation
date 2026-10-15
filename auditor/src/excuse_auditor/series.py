import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class SeriesComponent:
    key: str
    name: str
    source: str
    unit: str
    start: Decimal
    end: Decimal
    requires_claim: tuple[str, ...]

    @property
    def change(self) -> Decimal:
        return (self.end - self.start) / self.start


def series_label(path: Path) -> str:
    payload = json.loads(path.read_text())
    return str(payload["label"])


def lookup_component(path: Path, key: str, start: date, end: date) -> SeriesComponent | None:
    payload = json.loads(path.read_text())
    body = payload.get(key)
    if not isinstance(body, dict):
        return None
    points = {date.fromisoformat(item["date"]): Decimal(item["value"]) for item in body["points"]}
    if start not in points or end not in points:
        return None
    return SeriesComponent(
        key=key,
        name=body["name"],
        source=body["source"],
        unit=body["unit"],
        start=points[start],
        end=points[end],
        requires_claim=tuple(body.get("requires_claim") or []),
    )
