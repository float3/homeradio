from __future__ import annotations

import shutil
import subprocess


def pactl_available() -> bool:
    return shutil.which("pactl") is not None


def list_audio_devices() -> list[dict[str, str]]:
    if not pactl_available():
        raise RuntimeError("pactl is not available on PATH")

    result = subprocess.run(
        ["pactl", "list", "short", "sinks"],
        check=True,
        capture_output=True,
        text=True,
    )

    devices: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        devices.append(
            {
                "id": parts[0],
                "name": parts[1],
                "label": parts[1],
                "driver": parts[2] if len(parts) > 2 else "",
                "state": parts[4] if len(parts) > 4 else "",
            }
        )

    return devices
