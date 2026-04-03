from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


class ConfigStore:
    DEFAULT_STATE = {"streams": [], "sink_frequencies": {}, "recent_links": []}

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return dict(self.DEFAULT_STATE)
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return dict(self.DEFAULT_STATE)
            streams = data.get("streams", [])
            if not isinstance(streams, list):
                streams = []
            sink_frequencies = data.get("sink_frequencies", {})
            if not isinstance(sink_frequencies, dict):
                sink_frequencies = {}
            recent_links = data.get("recent_links", [])
            if not isinstance(recent_links, list):
                recent_links = []
            return {
                "streams": streams,
                "sink_frequencies": sink_frequencies,
                "recent_links": recent_links,
            }

    def save(self, data: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
