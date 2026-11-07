import base64
import io
import queue
import threading
import time

import matplotlib

# Render on the UNO Q without requiring a desktop display.
matplotlib.use("Agg")

import numpy as np
from matplotlib.figure import Figure
from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI

ui = WebUI()
commands = queue.Queue(maxsize=1)
lock = threading.Lock()
state = {"image": None, "status": "Waiting for the MCU", "pending": True,
         "servo_source": "average"}
last_error_print = 0.0

figure = Figure(figsize=(5.8, 5.5), dpi=100, layout="constrained")
axes = figure.subplots()
image = axes.imshow(np.zeros((5, 5)), vmin=0, vmax=534, cmap="inferno")
labels = [[axes.text(c, r, "0", ha="center", va="center", color="white")
           for c in range(5)] for r in range(5)]
axes.set(xticks=range(5), yticks=range(5), xlabel="Column", ylabel="Row")
figure.colorbar(image, ax=axes, label="Sensor output (not calibrated units)")

# The sketch maps pressure to the servo on every sensor frame; Python only picks the source.
SERVO_SOURCES = {"average": 0, "peak": 1, "nonzero": 2}
sent_servo_source = None


def get_frame():
    with lock:
        return dict(state)


def request_mode(mode: int):
    if mode not in (0, 1):
        return {"accepted": False, "message": "Use 0 for ADC or 1 for pressure"}
    with lock:
        if state["pending"]:
            return {"accepted": False, "message": "A mode request is in progress"}
        state["pending"] = True
        state["status"] = "Mode request queued"
    try:
        commands.put_nowait(mode)
    except queue.Full:
        with lock:
            state["pending"] = False
        return {"accepted": False, "message": "Please retry"}
    return {"accepted": True}


def set_servo_source(source: str):
    if source not in SERVO_SOURCES:
        return {"accepted": False, "message": "Use average, peak or nonzero"}
    with lock:
        state["servo_source"] = source
    return {"accepted": True}


ui.expose_api("GET", "/sensor/frame", get_frame)
ui.expose_api("POST", "/sensor/mode", request_mode)
ui.expose_api("POST", "/servo/source", set_servo_source)


def loop():
    global last_error_print, sent_servo_source
    started = time.monotonic()
    try:
        # Make all MCU calls here to avoid concurrent Bridge requests.
        try:
            mode = commands.get_nowait()
        except queue.Empty:
            mode = None

        if mode is not None:
            if not Bridge.call("sensx_set_mode", mode):
                print("Mode request rejected by the MCU", flush=True)

        with lock:
            source = state["servo_source"]
        if source != sent_servo_source:
            if Bridge.call("set_servo_source", SERVO_SOURCES[source]):
                sent_servo_source = source

        raw = Bridge.call("sensx_snapshot")
        if isinstance(raw, bytes):
            raw = raw.decode("ascii")
        values = [int(part) for part in raw.split(",")]
        if len(values) != 33:
            raise ValueError("Unexpected MCU snapshot size")

        sequence, age, mode, pending, error, crc_errors = values[:6]
        grid = np.array(values[6:31]).reshape(5, 5)
        servo_angle, servo_locked = values[31:]
        mode_name = {0: "ADC", 1: "pressure"}.get(mode, "unknown")
        stale = age > 1500
        limit = 3945 if mode == 0 else 100

        status = f"Mode: {mode_name} | frame: {sequence} | CRC errors: {crc_errors}"
        if pending:
            status += " | Confirming mode..."
        elif error:
            status += " | Mode confirmation failed: check sensor RX / D1"
        if stale:
            status += " | NO RECENT DATA"

        # Do not display old values as if they belonged to a new mode.
        if stale or pending:
            image.set_data(np.zeros((5, 5)))
            for row in labels:
                for label in row:
                    label.set_text("--")
            title = f"SensX25 | {mode_name}\nWaiting for valid data"
        else:
            # Pressure mode shows readings above 100 as 100; the servo still uses raw values.
            shown = np.minimum(grid, limit) if mode == 1 else grid
            image.set_data(shown)
            for r in range(5):
                for c in range(5):
                    labels[r][c].set_text(str(shown[r, c]))
                    labels[r][c].set_color("black" if shown[r, c] > limit * 0.6 else "white")
            title = f"SensX25 | {mode_name}\nTotal {shown.sum()} | peak {shown.max()}"

            if mode == 1:
                status += f" | servo {servo_angle}° ({source})"
                if servo_locked:
                    status += " locked"

        image.set_clim(0, limit)
        axes.set_title(title)
        output = io.BytesIO()
        figure.savefig(output, format="png")
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        with lock:
            state.update(image=encoded, status=status, pending=bool(pending))

    except Exception as exc:
        with lock:
            state.update(status=f"Communication error: {exc}", pending=False)
        if time.monotonic() - last_error_print > 3:
            print(f"SensX25 error: {exc}", flush=True)
            last_error_print = time.monotonic()

    # Target up to five display updates per second; sensor acquisition is separate.
    time.sleep(max(0.01, 0.2 - (time.monotonic() - started)))


App.run(user_loop=loop)
