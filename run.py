import os

from homeradio.app import create_app

app = create_app()


if __name__ == "__main__":
    host = os.getenv("HOMERADIO_HOST", "0.0.0.0")
    port = int(os.getenv("HOMERADIO_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
