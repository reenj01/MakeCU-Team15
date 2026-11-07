# SensX25 Live — UNO Q / Arduino App Lab

An application for direct UART connection, based on the supplied SensX25 Python sample.
It uses matplotlib to render a 5×5 heatmap with numeric values and displays it through WebUI.

The target refresh rate is up to 5 updates per second. Actual performance depends on the UNO Q’s workload.
This application does not guarantee recording every frame or lossless data acquisition.

## Wiring

This application assumes a SensX25 with a 3.3 V UART interface. The supplied sample does not specify the supply voltage, wire colors, or connector pin order. Check your sensor’s documentation before connecting it.

An RS-485 version cannot be connected directly.

| SensX25 | UNO Q |
| --- | --- |
| TX | D0 / RX |
| RX | D1 / TX (required for mode switching and readback) |
| GND | GND |
| VCC | Power supply specified by the sensor manufacturer |

## App Lab Setup

1. Create a new App or duplicate the existing TestServo App.
2. Add **WebUI - HTML** (`arduino:web_ui`) from Bricks.
3. Add `Arduino_RouterBridge` and its dependencies under Sketch libraries. If the previous Bridge-based project compiled successfully, keep those libraries.
4. Copy the following files, preserving the folder structure:

   ```text
   sketch/sketch.ino
   sketch/sketch.yaml
   python/main.py
   python/requirements.txt
   assets/index.html
   ```

5. For a new App, use the included `sketch/sketch.yaml`. It specifies UNO Q core 1.1.0, Bridge 0.4.4, and the dependency versions from the previously supplied successful build log.
6. Click **Run** and open the WebUI link. The default address is `http://<UNO-Q-IP>:7000`. When opening it in your computer’s browser, use the UNO Q’s IP address rather than your computer’s `localhost`.

## Operation

- The MCU reads `Serial1` at 921600 baud, 8N1, and validates frames consisting of `FF FF`, 50 data bytes, and a CRC8 byte.
- Python retrieves the latest 25 readings through Bridge and renders them using matplotlib’s `inferno` colormap.
- The grid is rotated 90 degrees clockwise so the sensor connector is positioned at the bottom.
- The display range is 0–534 in pressure mode and 0–3945 in ADC mode, following the ranges stated in the original sample.
- At startup, the application reads register `0x6005` without changing the saved setting.
- When a mode button is pressed, the application writes the setting using Modbus RTU function `0x06`, then verifies it by reading it back using function `0x03`.
- The sensor retains the selected mode after power-off. Repeated writes to an already confirmed mode are skipped.
- Numeric values are hidden during mode switching and when data becomes stale, preventing old readings from being mistaken for data in the new mode.
- Values are sensor output readings. They are not converted into calibrated pressure units such as Pa.

## Troubleshooting

- **Mode confirmation failed:** Check the sensor RX → D1 connection, signal voltage, and interface type.
- **NO RECENT DATA:** Check the sensor TX → D0 connection, common ground, and sensor power.
- **Communication error:** Check the Python logs, Sketch startup, and Bridge libraries.
- **Increasing CRC errors:** Check cable length, loose connections, electrical noise, and possible UART receive data loss at 921600 baud.
- **Heatmap displayed with mode “unknown”:** Sensor data is being received, but the mode has not been confirmed through readback.

Compilation, UART reception, and mode switching have not yet been verified on physical hardware.