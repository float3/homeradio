# HomeRadio

Localhost web UI for assigning internet radio streams to PulseAudio sinks and playing them with `mpv`.

## Features

- Enumerates audio output devices with `pactl`
- Maps arbitrary stream URLs (`mp3`, `m3u8`, playlists, etc.) to devices
- Runs each stream in its own supervised `mpv` process
- Automatically restarts streams when playback exits unexpectedly
- Persists state to JSON and restores enabled streams on next launch

## Requirements

- Python 3.9+
- `pactl` available on `PATH`
- `mpv` available on `PATH`

## Run

### Linux target machine

```bash
chmod +x setup-and-run.sh
./setup-and-run.sh
```

The script will:

- check for `python3`, `pactl`, and `mpv`
- create `.venv` if needed
- install Python dependencies
- create `data/`
- start the app on port `5000` bound to all network interfaces

From another device on the same network, open:

```bash
http://YOUR-LAN-IP:5000
```

### Manual run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Then open `http://127.0.0.1:5000`.

To change bind address or port:

```bash
HOMERADIO_HOST=0.0.0.0 HOMERADIO_PORT=5000 python run.py
```

## Notes

- Device routing uses the PulseAudio sink name returned by `pactl list short sinks`.
- The app stores its config in `data/config.json`.
