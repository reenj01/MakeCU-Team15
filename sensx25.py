# SensX25 -> Arduino App Lab (UNO Q)
# Linux side: receives frames from the MCU, rotates them upright,
# and prints the grid plus total load, center of pressure and contact area.
 
import time
from arduino.app_utils import App, Bridge
 
latest = None          # latest upright 5x5 grid (list of lists)
frames_received = 0
 
 
def to_upright(p):
    """Sensor sends its grid turned a quarter turn CCW.
    Upright (sensing face up, connector at bottom): row r, col c = p[5*(4-c) + r]."""
    return [[p[5 * (4 - c) + r] for c in range(5)] for r in range(5)]
 
 
def on_frame(msg):
    """Called by the MCU via Bridge.notify("sensx_frame", "p0,...,p24")."""
    global latest, frames_received
    try:
        p = [int(v) for v in str(msg).split(",")]
        if len(p) == 25:
            latest = to_upright(p)
            frames_received += 1
    except ValueError:
        pass
 
 
Bridge.provide("sensx_frame", on_frame)
 
 
def features(grid):
    total = sum(sum(row) for row in grid)
    pixels_on = sum(1 for row in grid for v in row if v > 0)
    peak = max(max(row) for row in grid)
    if total > 0:
        cop_row = sum(grid[r][c] * r for r in range(5) for c in range(5)) / total
        cop_col = sum(grid[r][c] * c for r in range(5) for c in range(5)) / total
    else:
        cop_row = cop_col = None
    return total, peak, pixels_on, cop_row, cop_col
 
 
def loop():
    time.sleep(0.25)   # print 4x per second
    if latest is None:
        print("Waiting for frames from the sensor...")
        return
 
    grid = latest
    total, peak, pixels_on, cop_row, cop_col = features(grid)
 
    print(f"frames: {frames_received}")
    for row in grid:
        print(" ".join(f"{v:4d}" for v in row))
    if cop_row is None:
        print("no touch")
    else:
        print(f"total={total}  peak={peak}  pixels_on={pixels_on}  "
              f"CoP=(row {cop_row:.2f}, col {cop_col:.2f})")
    print("-" * 26)
 
 
App.run(user_loop=loop)
