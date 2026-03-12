from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class UniverseSnapshotRequest:
    symbols: list[str]
    regime: str = "NORMAL"


@dataclass(frozen=True)
class OptionsChainRequest:
    symbol: str
    expiry: str | None = None


@dataclass(frozen=True)
class IndexSnapshotRequest:
    symbols: list[str]


class MarketDataProvider(Protocol):
    provider_name: str
    feed_mode: str  # realtime|delayed

    def get_universe_snapshot(self, req: UniverseSnapshotRequest) -> dict[str, Any]:
        ...

    def get_options_chain(self, req: OptionsChainRequest) -> dict[str, Any]:
        ...

    def get_index_snapshot(self, req: IndexSnapshotRequest) -> dict[str, Any]:
        ...
