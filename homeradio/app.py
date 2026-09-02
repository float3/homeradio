from __future__ import annotations

import atexit
import logging
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

from homeradio.config_store import ConfigStore
from homeradio.player import MPVSupervisor
from homeradio.service import RadioService


def create_app() -> Flask:
    logging.basicConfig(level=logging.INFO)

    root_dir = Path(__file__).resolve().parent.parent
    data_dir = root_dir / "data"
    store = ConfigStore(data_dir / "config.json")
    player = MPVSupervisor()
    service = RadioService(store, player)
    service.load_runtime()

    app = Flask(
        __name__,
        template_folder=str(root_dir / "templates"),
        static_folder=str(root_dir / "static"),
    )
    app.config["SERVICE"] = service

    @app.get("/")
    def index():
        dashboard = service.get_dashboard()
        return render_template("index.html", **dashboard)

    @app.post("/streams")
    def save_stream():
        payload = _get_request_data()
        try:
            service.save_stream(payload)
        except ValueError as exc:
            if _wants_json():
                return jsonify({"error": str(exc)}), 400
            return _redirect_with_error(str(exc))

        if _wants_json():
            return jsonify(service.get_dashboard())
        return redirect(url_for("index"))

    @app.post("/streams/<stream_id>/toggle")
    def toggle_stream(stream_id: str):
        payload = _get_request_data()
        enabled = _bool_value(payload.get("enabled"))
        try:
            service.set_enabled(stream_id, enabled)
        except KeyError:
            return jsonify({"error": "Stream not found"}), 404

        if _wants_json():
            return jsonify(service.get_dashboard())
        return redirect(url_for("index"))

    @app.post("/streams/<stream_id>/delete")
    def delete_stream(stream_id: str):
        service.delete_stream(stream_id)
        if _wants_json():
            return jsonify(service.get_dashboard())
        return redirect(url_for("index"))

    @app.post("/devices/frequency")
    def set_device_frequency():
        payload = _get_request_data()
        try:
            service.set_sink_frequency(
                str(payload.get("device_name") or ""),
                payload.get("fm_frequency"),
            )
        except ValueError as exc:
            if _wants_json():
                return jsonify({"error": str(exc)}), 400
            return _redirect_with_error(str(exc))

        if _wants_json():
            return jsonify(service.get_dashboard())
        return redirect(url_for("index"))

    @app.get("/api/state")
    def api_state():
        return jsonify(service.get_dashboard())

    atexit.register(player.stop_all)
    return app


def _get_request_data():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


def _wants_json() -> bool:
    if request.is_json:
        return True
    accepted = request.accept_mimetypes
    return (
        accepted.best == "application/json"
        and accepted[accepted.best] > accepted["text/html"]
    )


def _redirect_with_error(message: str):
    return redirect(url_for("index", error=message))


def _bool_value(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
