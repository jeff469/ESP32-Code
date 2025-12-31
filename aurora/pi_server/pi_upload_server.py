"""Simple Flask server that accepts CSV uploads from the ESP32."""

from flask import Flask, request, abort

app = Flask(__name__)

UPLOAD_DIR = "/home/pi/aurora_uploads"


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        abort(400, "missing file field")
    f = request.files["file"]
    path = f"{UPLOAD_DIR}/{f.filename}"
    f.save(path)
    return "ok"


if __name__ == "__main__":
    import os

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=8000)
