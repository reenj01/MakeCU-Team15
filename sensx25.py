# SensX25 -> Arduino App Lab (UNO Q)
# Linux side: receives frames from the MCU, rotates them upright,
# watches for a finished press, guesses an emotion, and lets Mote say it.
#
# The browser page is served from this same process. On the board, frames
# arrive through the bridge. On a laptop, use the practice buttons.

from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections import deque
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import emotion

try:
    from arduino.app_utils import App, Bridge

    ON_DEVICE = True
except ImportError:
    ON_DEVICE = False

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(ROOT, "static", "index.html")

WAITING = "Put your hand on the pad. I'll tell you what I feel."
FALLBACKS = {
    "shy": "That was barely a touch. You can stay. I won't make it a big deal.",
    "calm": "You're steady. I can rest in that.",
    "hesitant": "You keep arriving and leaving. I'm still here either way.",
    "angry": "That landed hard. I'm not going anywhere.",
    "anxious": "Your hand won't settle. I'm listening anyway.",
    "confident": "A full, even press. You mean that.",
}

latest = None
frames_received = 0
demo_active = False
tracker = emotion.Tracker()
sensor = threading.Lock()
pending_gesture = None
# Every bridge frame, not just the newest. A short press used to be overwritten
# by the next empty frame before the screen ever saw it.
pending_frames = deque(maxlen=400)
last_frame_at = 0.0

state = {
    "connected": False,
    "mode": "board" if ON_DEVICE else "practice",
    "frames": 0,
    "grid": [[0] * 5 for _ in range(5)],
    "touching": False,
    "total": 0,
    "peak": 0,
    "pixels_on": 0,
    "emotion": None,
    "line": WAITING,
    "line_id": 1,
    "source": None,
    "evidence": "",
    "thinking": False,
    "demo": None,
}
version = 0
condition = threading.Condition()


def to_upright(values):
    """Sensor sends its grid turned a quarter turn CCW.
    Upright (sensing face up, connector at bottom): row r, col c = p[5*(4-c) + r]."""
    return [[values[5 * (4 - c) + r] for c in range(5)] for r in range(5)]


def on_frame(msg):
    """Called by the MCU via Bridge.notify("sensx_frame", "p0,...,p24")."""
    global latest, frames_received, last_frame_at
    try:
        values = [int(part) for part in str(msg).split(",")]
    except ValueError:
        return
    if len(values) != 25:
        return
    grid = to_upright(values)
    total, peak, pixels, _cop_row, _cop_col = emotion.features(grid)
    with sensor:
        if demo_active:
            return
        latest = [row[:] for row in grid]
        frames_received += 1
        count = frames_received
        last_frame_at = time.time()
        pending_frames.append((last_frame_at, latest))
    publish_reading(
        grid,
        {
            "touching": total >= emotion.NOISE_FLOOR,
            "total": total,
            "peak": peak,
            "pixels_on": pixels,
        },
        count,
    )


def _publish(snapshot):
    global version
    with condition:
        version += 1
        for key, value in snapshot.items():
            state[key] = value
        condition.notify_all()


def publish_reading(grid, result, frames):
    _publish(
        {
            "connected": True,
            "frames": frames,
            "grid": [row[:] for row in grid],
            "touching": result["touching"],
            "total": result["total"],
            "peak": result["peak"],
            "pixels_on": result["pixels_on"],
        }
    )


def speak(name, evidence):
    """Ask Gemini for Mote's line. Any failure returns the offline sentence."""
    fallback = FALLBACKS[name]
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return fallback, "offline"
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    prompt = (
        "You are Mote, a small creature who lives in a pressure pad. "
        "You feel how a person touches you. Speak one or two short sentences "
        "in your own voice, reacting to this reading. Do not mention numbers, "
        "sensors, or that you are an AI. No markdown.\n"
        f"Reading: {name}. Evidence: {evidence}."
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": 160},
        }
    ).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode())
        parts = payload["candidates"][0]["content"]["parts"]
        text = " ".join(
            part["text"].strip()
            for part in parts
            if part.get("text") and not part.get("thought")
        ).strip()
        if len(text) >= 2 and text[0] == text[-1] == '"':
            text = text[1:-1].strip()
        if not text:
            return fallback, "offline"
        return text, "gemini"
    except Exception as exc:
        print(f"Gemini request failed ({type(exc).__name__})")
        return fallback, "offline"


def _finish_speech(gesture):
    global pending_gesture
    line, source = speak(gesture["emotion"], gesture["evidence"])
    print(f"{gesture['emotion']}: {line} ({source})")
    _publish(
        {
            "line": line,
            "line_id": state["line_id"] + 1,
            "source": source,
            "emotion": gesture["emotion"],
            "evidence": gesture["evidence"],
            "thinking": False,
        }
    )
    follow = None
    with sensor:
        follow = pending_gesture
        pending_gesture = None
    if follow is not None:
        begin_speech(follow)


def begin_speech(gesture):
    global pending_gesture
    print(f"gesture {gesture['emotion']}  {gesture['evidence']}")
    with sensor:
        if state["thinking"]:
            pending_gesture = gesture
            return
    _publish(
        {
            "thinking": True,
            "emotion": gesture["emotion"],
            "evidence": gesture["evidence"],
        }
    )
    threading.Thread(target=_finish_speech, args=(gesture,), daemon=True).start()


def ingest(grid, now, frames):
    with sensor:
        result = tracker.note(grid, now)
    publish_reading(grid, result, frames)
    if result["gesture"] is not None:
        begin_speech(result["gesture"])


def loop():
    time.sleep(0.02)
    with sensor:
        if demo_active:
            return
        batch = list(pending_frames)
        pending_frames.clear()
        frames = frames_received
        active = tracker.active
        quiet_for = time.time() - last_frame_at if last_frame_at else 0.0
    for arrived, grid in batch:
        ingest(grid, arrived, frames)
    # Frames stopped. Feed silence so a finished press can close, but not
    # between the 20 Hz readings while a finger is still down.
    if not batch and active and quiet_for >= 0.08:
        ingest([[0] * 5 for _ in range(5)], time.time(), frames)


def run_demo(kind):
    global demo_active
    script = emotion.DEMOS[kind]
    try:
        with sensor:
            tracker.clear()
            pending_frames.clear()
        clock_frames = frames_received
        for grid, hold in script:
            steps = max(1, int(round(hold / emotion.SAMPLE_DT)))
            for _ in range(steps):
                ingest([row[:] for row in grid], time.time(), clock_frames)
                time.sleep(emotion.SAMPLE_DT)
    finally:
        with sensor:
            demo_active = False
        _publish({"demo": None, "touching": False})


def start_demo(kind):
    global demo_active
    if kind not in emotion.DEMOS:
        return False
    with sensor:
        if demo_active:
            return False
        demo_active = True
    _publish({"demo": kind})
    threading.Thread(target=run_demo, args=(kind,), daemon=True).start()
    return True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def _send(self, code, body, content_type):
        payload = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, code, payload):
        self._send(code, json.dumps(payload), "application/json")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            with open(INDEX, "rb") as handle:
                self._send(200, handle.read(), "text/html; charset=utf-8")
            return
        if path == "/state":
            with condition:
                self._json(200, dict(state))
            return
        if path == "/events":
            self._events()
            return
        self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/demo":
            self._send(404, "not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            kind = json.loads(raw.decode() or "{}").get("kind", "")
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "bad json"})
            return
        if not start_demo(str(kind)):
            self._json(409, {"ok": False, "error": "busy or unknown press"})
            return
        self._json(202, {"ok": True, "kind": kind})

    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        last = -1
        try:
            while True:
                with condition:
                    if version == last:
                        condition.wait(timeout=5)
                    current = version
                    payload = json.dumps(state)
                if current == last:
                    self.wfile.write(b": keepalive\n\n")
                else:
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    last = current
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            return


def start_server(host, port):
    httpd = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main():
    global latest
    port = int(os.environ.get("PORT", "8741"))
    if not ON_DEVICE:
        latest = [[0] * 5 for _ in range(5)]
        _publish({"connected": True, "mode": "practice"})
    httpd = start_server("0.0.0.0", port)
    bound = httpd.server_address[1]
    print(f"Mote is at http://127.0.0.1:{bound}")
    if ON_DEVICE:
        Bridge.provide("sensx_frame", on_frame)
        App.run(user_loop=loop)
    else:
        try:
            while True:
                loop()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
