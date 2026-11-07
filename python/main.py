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
state = {"image": None, "status": "Waiting for the MCU", "pending": True}
last_error_print = 0.0

figure = Figure(figsize=(5.8, 5.5), dpi=100, layout="constrained")
axes = figure.subplots()
image = axes.imshow(np.zeros((5, 5)), vmin=0, vmax=534, cmap="inferno")
labels = [[axes.text(c, r, "0", ha="center", va="center", color="white")
           for c in range(5)] for r in range(5)]
axes.set(xticks=range(5), yticks=range(5), xlabel="Column", ylabel="Row")
figure.colorbar(image, ax=axes, label="Sensor output (not calibrated units)")


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


ui.expose_api("GET", "/sensor/frame", get_frame)
ui.expose_api("POST", "/sensor/mode", request_mode)


def loop():
    global last_error_print
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

        raw = Bridge.call("sensx_snapshot")
        if isinstance(raw, bytes):
            raw = raw.decode("ascii")
        values = [int(part) for part in raw.split(",")]
        if len(values) != 31:
            raise ValueError("Unexpected MCU snapshot size")

        sequence, age, mode, pending, error, crc_errors = values[:6]
        grid = np.array(values[6:]).reshape(5, 5)
        mode_name = {0: "ADC", 1: "pressure"}.get(mode, "unknown")
        stale = age > 1500
        limit = 3945 if mode == 0 else 534

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
            image.set_data(grid)
            for r in range(5):
                for c in range(5):
                    labels[r][c].set_text(str(grid[r, c]))
                    labels[r][c].set_color("black" if grid[r, c] > limit * 0.6 else "white")
            title = f"SensX25 | {mode_name}\nTotal {grid.sum()} | peak {grid.max()}"

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
