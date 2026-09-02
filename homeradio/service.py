from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from homeradio.config_store import ConfigStore
from homeradio.devices import list_audio_devices, pactl_available
from homeradio.player import MPVSupervisor, mpv_available


class RadioService:
    MAX_RECENT_LINKS = 8

    def __init__(self, store: ConfigStore, player: MPVSupervisor) -> None:
        self.store = store
        self.player = player
        self._lock = threading.Lock()
        self._state = self._normalize_state(self.store.load())

    def load_runtime(self) -> None:
        with self._lock:
            for stream in self._state["streams"]:
                if stream["enabled"]:
                    self.player.ensure_running(
                        stream["id"],
                        stream["url"],
                        stream["device_name"],
                    )

    def get_dashboard(self) -> dict[str, Any]:
        with self._lock:
            streams = [dict(stream) for stream in self._state["streams"]]
            sink_frequencies = dict(self._state["sink_frequencies"])
            recent_links = [dict(link) for link in self._state["recent_links"]]

        statuses = self.player.snapshot()
        for stream in streams:
            stream["runtime"] = statuses.get(
                stream["id"],
                {
                    "running": False,
                    "restart_count": 0,
                    "last_error": None,
                    "last_started_at": None,
                },
            )
            stream["device_frequency"] = sink_frequencies.get(stream["device_name"], "")

        devices: list[dict[str, str]] = []
        device_error = None
        try:
            devices = list_audio_devices()
            for device in devices:
                device["fm_frequency"] = sink_frequencies.get(device["name"], "")
        except Exception as exc:
            device_error = str(exc)

        return {
            "streams": streams,
            "devices": devices,
            "sink_frequencies": sink_frequencies,
            "recent_links": recent_links,
            "device_error": device_error,
            "pactl_available": pactl_available(),
            "mpv_available": mpv_available(),
        }

    def save_stream(self, payload: dict[str, Any]) -> dict[str, Any]:
        stream_id = (payload.get("id") or "").strip()
        record = {
            "id": stream_id,
            "name": (payload.get("name") or "").strip() or "Unnamed stream",
            "url": (payload.get("url") or "").strip(),
            "device_name": (payload.get("device_name") or "").strip(),
            "enabled": bool(payload.get("enabled")),
        }

        if not record["url"]:
            raise ValueError("Stream URL is required")
        if not record["device_name"]:
            raise ValueError("Audio device is required")

        with self._lock:
            streams = self._state["streams"]
            if not record["id"]:
                existing_match = next(
                    (
                        stream
                        for stream in streams
                        if stream["url"] == record["url"]
                        and stream["device_name"] == record["device_name"]
                    ),
                    None,
                )
                if existing_match is not None:
                    record["id"] = existing_match["id"]
                else:
                    record["id"] = str(uuid.uuid4())
            for index, existing in enumerate(streams):
                if existing["id"] == record["id"]:
                    streams[index] = record
                    break
            else:
                streams.append(record)
            self._remember_recent_link(record)
            self._persist_locked()

        self._sync_stream(record)
        return record

    def set_sink_frequency(self, device_name: str, fm_frequency: Any) -> str:
        if not device_name.strip():
            raise ValueError("Audio device is required")

        value = self._parse_fm_frequency(fm_frequency)
        with self._lock:
            if value:
                self._state["sink_frequencies"][device_name] = value
            else:
                self._state["sink_frequencies"].pop(device_name, None)
            self._persist_locked()
        return value

    def delete_stream(self, stream_id: str) -> None:
        with self._lock:
            original_count = len(self._state["streams"])
            self._state["streams"] = [
                stream for stream in self._state["streams"] if stream["id"] != stream_id
            ]
            changed = len(self._state["streams"]) != original_count
            if changed:
                self._persist_locked()

        self.player.stop(stream_id)

    def set_enabled(self, stream_id: str, enabled: bool) -> dict[str, Any]:
        with self._lock:
            target = next(
                (
                    stream
                    for stream in self._state["streams"]
                    if stream["id"] == stream_id
                ),
                None,
            )
            if target is None:
                raise KeyError(stream_id)
            target["enabled"] = enabled
            self._persist_locked()
            record = dict(target)

        self._sync_stream(record)
        return record

    def _sync_stream(self, stream: dict[str, Any]) -> None:
        if stream["enabled"]:
            self.player.ensure_running(
                stream["id"], stream["url"], stream["device_name"]
            )
        else:
            self.player.stop(stream["id"])

    def _persist_locked(self) -> None:
        self.store.save(self._state)

    def _remember_recent_link(self, stream: dict[str, Any]) -> None:
        recent_links = self._state["recent_links"]
        key = (stream["url"], stream["device_name"])
        filtered = [
            link
            for link in recent_links
            if (link.get("url"), link.get("device_name")) != key
        ]
        filtered.insert(
            0,
            {
                "name": stream["name"],
                "url": stream["url"],
                "device_name": stream["device_name"],
                "saved_at": int(time.time()),
            },
        )
        self._state["recent_links"] = filtered[: self.MAX_RECENT_LINKS]

    @staticmethod
    def _normalize_state(data: dict[str, Any]) -> dict[str, Any]:
        streams: list[dict[str, Any]] = []
        sink_frequencies: dict[str, str] = {}
        recent_links: list[dict[str, Any]] = []
        for item in data.get("streams", []):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            device_name = str(item.get("device_name", "")).strip()
            if not url or not device_name:
                continue
            streams.append(
                {
                    "id": str(item.get("id") or uuid.uuid4()),
                    "name": str(item.get("name") or "Unnamed stream").strip()
                    or "Unnamed stream",
                    "url": url,
                    "device_name": device_name,
                    "enabled": bool(item.get("enabled")),
                }
            )
            legacy_frequency = RadioService._parse_fm_frequency(
                item.get("fm_frequency")
            )
            if legacy_frequency and device_name not in sink_frequencies:
                sink_frequencies[device_name] = legacy_frequency

        raw_sink_frequencies = data.get("sink_frequencies", {})
        if isinstance(raw_sink_frequencies, dict):
            for device_name, value in raw_sink_frequencies.items():
                parsed_value = RadioService._parse_fm_frequency(value)
                if parsed_value:
                    sink_frequencies[str(device_name)] = parsed_value
        for item in data.get("recent_links", []):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            device_name = str(item.get("device_name", "")).strip()
            if not url or not device_name:
                continue
            recent_links.append(
                {
                    "name": str(item.get("name") or "Unnamed stream").strip()
                    or "Unnamed stream",
                    "url": url,
                    "device_name": device_name,
                    "saved_at": int(item.get("saved_at") or 0),
                }
            )
        return {
            "streams": streams,
            "sink_frequencies": sink_frequencies,
            "recent_links": recent_links[: RadioService.MAX_RECENT_LINKS],
        }

    @staticmethod
    def _parse_fm_frequency(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""

        try:
            frequency = float(text)
        except ValueError as exc:
            raise ValueError(
                "FM frequency must be a number between 87.5 and 108.0"
            ) from exc

        if frequency < 87.5 or frequency > 108.0:
            raise ValueError("FM frequency must be between 87.5 and 108.0")

        return f"{frequency:.2f}"
