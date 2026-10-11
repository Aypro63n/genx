
import base64
import json
import os
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

HERE = Path(__file__).resolve().parent
HTML_FILE = HERE / "FreeAI-Studio-Local.html"
COLAB_URL = os.environ.get("COLAB_API_URL", "").strip().rstrip("/")
COLAB_KEY = os.environ.get("COLAB_API_KEY", "").strip()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        if self.path != "/api/generate":
            self.send_error(404)
            return

        if not COLAB_URL or not COLAB_KEY:
            self._json(500, {
                "error": "Colab URL or API key missing. Restart with both settings."
            })
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 200_000:
                self._json(400, {"error": "Invalid request size."})
                return

            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            prompt = str(payload.get("prompt", "")).strip()[:1800]

            if not prompt:
                self._json(400, {"error": "Please enter a prompt."})
                return

            forwarded = {"prompt": prompt}
            for key in ("width", "height", "guidance_scale",
                        "negative_prompt", "seed"):
                if key in payload:
                    forwarded[key] = payload[key]

            request = urllib.request.Request(
                COLAB_URL + "/generate",
                data=json.dumps(forwarded).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": COLAB_KEY
                },
                method="POST"
            )

            with urllib.request.urlopen(request, timeout=240) as response:
                result = json.loads(response.read().decode("utf-8"))

            image = result.get("image", "")
            if not image.startswith("data:image/"):
                self._json(502, {
                    "error": result.get("error", "Colab returned no valid image.")
                })
                return

            self._json(200, {"dataUrl": image})

        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
                message = detail.get("error", "Colab request failed.")
            except Exception:
                message = "Colab request failed."

            print("[COLAB ERROR]", exc.code, message, flush=True)
            self._json(502, {"error": message})

        except Exception as exc:
            print("[BRIDGE ERROR]", repr(exc), flush=True)
            self._json(502, {
                "error": "Could not connect to Colab. Check its runtime and ngrok URL."
            })

    def _json(self, status, obj):
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header(
            "Access-Control-Allow-Origin",
            "http://127.0.0.1:8000"
        )
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        print("[local server] " + (fmt % args))


if __name__ == "__main__":
    if not HTML_FILE.exists():
        raise SystemExit("FreeAI-Studio-Local.html not found.")

    if not COLAB_URL or not COLAB_KEY:
        raise SystemExit(
            "COLAB_API_URL or COLAB_API_KEY missing in PowerShell."
        )

    print("FreeAI Studio: http://127.0.0.1:8000/FreeAI-Studio-Local.html")
    print("Colab API configured. Keep this window open.")
    print("Press Ctrl+C to stop.")

    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
