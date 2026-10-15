import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

_META_KEYS = frozenset({"label", "scope"})

_DEFAULT_LIMITATIONS = (
    "Series file has no explicit scope metadata; treat values as non-live until configured.",
    "Explained move is the sum of selected component percentage changes, not a mill cost model.",
)


@dataclass(frozen=True)
class SeriesScope:
    demo: bool
    live_feed: bool
    materials: tuple[str, ...]
    limitations: tuple[str, ...]


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
        if self.start == 0:
            raise ValueError(f"Series '{self.key}' starts at zero on the invoice date.")
        return (self.end - self.start) / self.start


@dataclass(frozen=True)
class MarketSeries:
    label: str
    scope: SeriesScope
    component_keys: tuple[str, ...]
    path: Path
    _payload: dict

    def lookup(self, key: str, start: date, end: date) -> SeriesComponent | None:
        body = self._payload.get(key)
        if not isinstance(body, dict):
            return None
        points = {date.fromisoformat(item["date"]): Decimal(str(item["value"])) for item in body["points"]}
        if start not in points or end not in points:
            return None
        start_value = points[start]
        end_value = points[end]
        if start_value == 0:
            return None
        return SeriesComponent(
            key=key,
            name=str(body["name"]),
            source=str(body["source"]),
            unit=str(body["unit"]),
            start=start_value,
            end=end_value,
            requires_claim=tuple(str(token) for token in (body.get("requires_claim") or [])),
        )


def load_series(path: Path) -> MarketSeries:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Series file must be a JSON object.")
    label = str(payload.get("label") or "Untitled series")
    scope = _parse_scope(payload.get("scope"))
    keys = tuple(
        key
        for key, body in payload.items()
        if key not in _META_KEYS and isinstance(body, dict) and "points" in body
    )
    if not keys:
        raise ValueError("Series file has no components with points.")
    return MarketSeries(label=label, scope=scope, component_keys=keys, path=path, _payload=payload)


def series_label(path: Path) -> str:
    return load_series(path).label


def lookup_component(path: Path, key: str, start: date, end: date) -> SeriesComponent | None:
    return load_series(path).lookup(key, start, end)


def _parse_scope(raw: object) -> SeriesScope:
    if not isinstance(raw, dict):
        return SeriesScope(
            demo=True,
            live_feed=False,
            materials=("unspecified",),
            limitations=_DEFAULT_LIMITATIONS,
        )
    materials_raw = raw.get("materials") or ["unspecified"]
    limitations_raw = raw.get("limitations") or list(_DEFAULT_LIMITATIONS)
    return SeriesScope(
        demo=bool(raw.get("demo", True)),
        live_feed=bool(raw.get("live_feed", False)),
        materials=tuple(str(item) for item in materials_raw),
        limitations=tuple(str(item) for item in limitations_raw),
    )
