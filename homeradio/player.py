from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)


def mpv_available() -> bool:
    return shutil.which("mpv") is not None


@dataclass
class StreamProcess:
    stream_id: str
    url: str
    device_name: str
    process: subprocess.Popen[str] | None = None
    stop_event: threading.Event | None = None
    thread: threading.Thread | None = None
    restart_count: int = 0
    last_error: str | None = None
    last_started_at: float | None = None


class MPVSupervisor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._streams: dict[str, StreamProcess] = {}

    def ensure_running(self, stream_id: str, url: str, device_name: str) -> None:
        with self._lock:
            current = self._streams.get(stream_id)
            if (
                current
                and current.url == url
                and current.device_name == device_name
                and current.thread
                and current.thread.is_alive()
            ):
                return
            self._stop_locked(stream_id)
            stop_event = threading.Event()
            state = StreamProcess(
                stream_id=stream_id,
                url=url,
                device_name=device_name,
                stop_event=stop_event,
            )
            thread = threading.Thread(
                target=self._worker,
                args=(state,),
                name=f"stream-{stream_id}",
                daemon=True,
            )
            state.thread = thread
            self._streams[stream_id] = state
            thread.start()

    def stop(self, stream_id: str) -> None:
        with self._lock:
            self._stop_locked(stream_id)

    def stop_all(self) -> None:
        with self._lock:
            stream_ids = list(self._streams)
        for stream_id in stream_ids:
            self.stop(stream_id)

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self._lock:
            result: dict[str, dict[str, object]] = {}
            for stream_id, state in self._streams.items():
                running = state.process is not None and state.process.poll() is None
                result[stream_id] = {
                    "running": running,
                    "restart_count": state.restart_count,
                    "last_error": state.last_error,
                    "last_started_at": state.last_started_at,
                }
            return result

    def _stop_locked(self, stream_id: str) -> None:
        state = self._streams.pop(stream_id, None)
        if not state:
            return
        if state.stop_event:
            state.stop_event.set()
        if state.process and state.process.poll() is None:
            state.process.terminate()

    def _worker(self, state: StreamProcess) -> None:
        if not mpv_available():
            state.last_error = "mpv is not available on PATH"
            LOGGER.error(
                "mpv is not available; cannot start stream %s", state.stream_id
            )
            return

        while state.stop_event and not state.stop_event.is_set():
            command = [
                "mpv",
                "--no-video",
                "--really-quiet",
                "--cache=yes",
                f"--audio-device=pulse/{state.device_name}",
                state.url,
            ]

            try:
                LOGGER.info(
                    "Starting stream %s on %s",
                    state.stream_id,
                    state.device_name,
                )
                state.last_started_at = time.time()
                state.process = subprocess.Popen(command)
                exit_code = state.process.wait()
            except Exception as exc:  # pragma: no cover
                state.last_error = str(exc)
                exit_code = -1
            finally:
                state.process = None

            if state.stop_event.is_set():
                break

            state.restart_count += 1
            if exit_code != 0:
                state.last_error = f"mpv exited with code {exit_code}"
            time.sleep(3)
