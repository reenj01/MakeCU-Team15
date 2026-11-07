# MakeCU-Team15

SensX25 on the Arduino UNO Q, plus **Mote**, a small on-screen agent that watches how someone presses the pad and answers in text.

The MCU sketch (`sensx25.ino`) reads sensor frames, checks the CRC, and sends 25 values across the bridge. `sensx25.py` turns each frame upright, waits until a press starts and ends, names the emotion, and serves the page.

## Emotions

The guess uses the whole press, not one frame.

| Press | Reading |
| --- | --- |
| Light, held, small area | shy |
| Light and short, or light repeated taps | hesitant |
| Moderate and steady | calm |
| Many cells, firm, steady | confident |
| Heavy, small area | angry |
| Heavy repeated taps, or a shaky heavy press | anxious |

Light and heavy are cutoffs in `emotion.py` (`LIGHT_MEAN`, `HEAVY_PEAK`). After a real touch, the page shows total, peak, and the evidence line. Edit those two numbers so your feather touch stays under `LIGHT_MEAN` and a hard press clears `HEAVY_PEAK`.

## Run the page on a laptop

```bash
python3 sensx25.py
```

Open http://127.0.0.1:8741. The practice row plays six presses through the same gesture code the pad uses. Keys 1–6 do the same thing.

There is no Gemini key in that mode, so Mote speaks the backup line and the page marks it `offline voice`.

## Gemini

Mote's sentence comes from Gemini. The emotion label stays local, so a bad network does not freeze the reading.

```bash
export GEMINI_API_KEY="your-key"
export GEMINI_MODEL="gemini-2.5-flash"   # optional
python3 sensx25.py
```

The key stays in the Python process. The browser never sees it. If the request fails, the backup line is what Mote says.

## Run it on the UNO Q

Copy this folder into the Linux app and run `sensx25.py` the same way as before. The sketch is unchanged: it still notifies `sensx_frame`. On the board, open `http://<board-ip>:8741` from a laptop on the same network.

`arduino.app_utils` is part of App Lab. A laptop without it starts in practice mode instead of waiting for the bridge.
