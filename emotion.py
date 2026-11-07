"""Turn a SensX 5x5 stream into one finished press, then a named emotion.

Tune the constants after a real touch. The page shows total and peak for
the press you just made.
"""

from __future__ import annotations

# Ignore cells this small. Raise it if the pad jitters when nobody is touching.
NOISE_FLOOR = 20
# A press is over after this much silence.
QUIET_SECONDS = 0.30
# Below this average load, the touch counts as light.
LIGHT_MEAN = 500
# A single cell at or above this peak counts as a heavy press.
HEAVY_PEAK = 1400
# Used in the evidence string Gemini reads. Not a cutoff by itself.
FAST_RISE = 0.18
ANXIOUS_TAPS = 3
# This many lit cells means a palm, not a fingertip.
BROAD_CELLS = 8
FIRM_MEAN = 1500
# Variance above this, plus more than one tap, reads as shaky.
SHAKY_VARIANCE = 200_000
SAMPLE_DT = 0.05

EMOTIONS = ("shy", "calm", "hesitant", "angry", "anxious", "confident")


def features(grid):
    total = sum(sum(row) for row in grid)
    pixels_on = sum(1 for row in grid for v in row if v > 0)
    peak = max(max(row) for row in grid) if grid else 0
    if total > 0:
        cop_row = sum(grid[r][c] * r for r in range(5) for c in range(5)) / total
        cop_col = sum(grid[r][c] * c for r in range(5) for c in range(5)) / total
    else:
        cop_row = cop_col = None
    return total, peak, pixels_on, cop_row, cop_col


def press(value, cells):
    grid = [[0] * 5 for _ in range(5)]
    for r, c in cells:
        grid[r][c] = value
    return grid


def block(value, size=4):
    return press(value, [(r, c) for r in range(size) for c in range(size)])


ZEROS = [[0] * 5 for _ in range(5)]

# Each entry is a list of (grid, seconds). The trailing silence closes the press.
DEMOS = {
    "shy": [(press(80, [(2, 2)]), 0.60), (ZEROS, 0.40)],
    "hesitant": [
        (press(90, [(2, 2)]), 0.12),
        (ZEROS, 0.14),
        (press(70, [(2, 1)]), 0.12),
        (ZEROS, 0.14),
        (press(85, [(2, 2)]), 0.12),
        (ZEROS, 0.40),
    ],
    "calm": [(press(180, [(1, 2), (2, 1), (2, 2), (2, 3)]), 0.80), (ZEROS, 0.40)],
    "confident": [(block(220, 4), 0.70), (ZEROS, 0.40)],
    "angry": [(press(2200, [(2, 2), (2, 3)]), 0.10), (ZEROS, 0.40)],
    "anxious": [
        (press(1900, [(1, 1), (2, 2)]), 0.10),
        (ZEROS, 0.12),
        (press(2100, [(3, 3)]), 0.10),
        (ZEROS, 0.12),
        (press(1800, [(2, 1)]), 0.10),
        (ZEROS, 0.12),
        (press(2000, [(1, 3), (2, 2)]), 0.10),
        (ZEROS, 0.12),
        (press(1950, [(2, 2)]), 0.10),
        (ZEROS, 0.40),
    ],
}


def _variance(values):
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _taps(samples):
    taps = 0
    down = False
    for sample in samples:
        touching = sample["total"] >= NOISE_FLOOR
        if touching and not down:
            taps += 1
            down = True
        elif not touching:
            down = False
    return taps


def guess_emotion(gesture):
    """Return (emotion, evidence) from one finished press."""
    light = gesture["mean_total"] < LIGHT_MEAN and gesture["max_peak"] < HEAVY_PEAK
    heavy = gesture["max_peak"] >= HEAVY_PEAK
    broad = gesture["mean_pixels"] >= BROAD_CELLS
    shaky = gesture["variance"] >= SHAKY_VARIANCE and gesture["taps"] >= 2
    evidence = (
        f"total {gesture['mean_total']:.0f}, peak {gesture['max_peak']:.0f}, "
        f"cells {gesture['mean_pixels']:.1f}, rise {gesture['rise']:.2f}s, "
        f"taps {gesture['taps']}, {gesture['duration']:.2f}s"
    )
    if heavy and (gesture["taps"] >= ANXIOUS_TAPS or shaky):
        return "anxious", evidence
    if heavy and not broad:
        return "angry", evidence
    if broad and gesture["mean_total"] >= FIRM_MEAN and gesture["variance"] < SHAKY_VARIANCE:
        return "confident", evidence
    if light and (gesture["duration"] < 0.40 or gesture["taps"] >= 2):
        return "hesitant", evidence
    if light and gesture["duration"] >= 0.40:
        return "shy", evidence
    if light:
        return "hesitant", evidence
    return "calm", evidence


def summarize(samples):
    totals = [sample["total"] for sample in samples]
    max_total = max(totals)
    target = 0.7 * max_total
    rise = 0.0
    for sample in samples:
        if max_total > 0 and sample["total"] >= target:
            rise = sample["t"] - samples[0]["t"]
            break
    gesture = {
        "duration": max(0.0, samples[-1]["t"] - samples[0]["t"]),
        "mean_total": sum(totals) / len(totals),
        "max_peak": max(sample["peak"] for sample in samples),
        "mean_pixels": sum(sample["pixels"] for sample in samples) / len(samples),
        "variance": _variance(totals),
        "rise": rise,
        "taps": _taps(samples),
    }
    emotion, evidence = guess_emotion(gesture)
    gesture["emotion"] = emotion
    gesture["evidence"] = evidence
    return gesture


class Tracker:
    """Collect frames until the pad has been quiet long enough to call it one press."""

    def __init__(self):
        self.samples = []
        self.quiet_for = 0.0
        self.active = False
        self.last_t = None

    def clear(self):
        self.samples = []
        self.quiet_for = 0.0
        self.active = False
        self.last_t = None

    def note(self, grid, now):
        total, peak, pixels, cop_row, cop_col = features(grid)
        touching = total >= NOISE_FLOOR
        dt = SAMPLE_DT if self.last_t is None else max(0.0, min(0.5, now - self.last_t))
        self.last_t = now
        finished = None
        if touching:
            self.quiet_for = 0.0
            self.active = True
            self.samples.append(
                {
                    "t": now,
                    "total": total,
                    "peak": peak,
                    "pixels": pixels,
                    "cop_row": cop_row,
                    "cop_col": cop_col,
                }
            )
        elif self.active:
            self.quiet_for += dt
            if self.quiet_for < QUIET_SECONDS:
                self.samples.append(
                    {
                        "t": now,
                        "total": 0,
                        "peak": 0,
                        "pixels": 0,
                        "cop_row": None,
                        "cop_col": None,
                    }
                )
            else:
                while self.samples and self.samples[-1]["total"] < NOISE_FLOOR:
                    self.samples.pop()
                if self.samples:
                    finished = summarize(self.samples)
                self.samples = []
                self.active = False
                self.quiet_for = 0.0
        return {
            "touching": touching,
            "total": total,
            "peak": peak,
            "pixels_on": pixels,
            "cop_row": cop_row,
            "cop_col": cop_col,
            "gesture": finished,
        }


def play(script, dt=SAMPLE_DT):
    """Replay a scripted press through a fresh tracker. Used by tests and practice."""
    tracker = Tracker()
    clock = 0.0
    finished = None
    seen = []
    for grid, hold in script:
        steps = max(1, int(round(hold / dt)))
        for _ in range(steps):
            clock += dt
            result = tracker.note(grid, clock)
            seen.append(result)
            if result["gesture"] is not None:
                finished = result["gesture"]
    return finished, seen
