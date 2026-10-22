# Water Quality Monitor

ESP32 DevKit V1 + DWS-MH-02 water sensor (flow, temperature, TDS) → home server → phone app.

```
[sensor] --> [ESP32: firmware/] --WiFi, HTTP POST--> [home server: server/app.py + SQLite] <-- [phone app]
```

## 1. Parts

| Part | Use |
|---|---|
| ESP32 DevKit V1 | reads the sensor, sends over WiFi |
| 4.7 kΩ resistor | TDS reference |
| 10 kΩ resistor | temperature divider |
| 10 kΩ + 20 kΩ resistors | drop the 5 V flow pulse to ~3.3 V |
| 100 nF capacitor (optional) | smooths the temperature reading |

No ADC or TDS board needed: the ESP32 has analog inputs, and it drives the TDS electrodes
itself with alternating polarity (plain DC would corrode them).

## 2. Identify the wires first

Colors vary between batches. Check with a multimeter before wiring:

- **TDS pair**: open circuit when dry, some resistance when both are in water.
- **Temperature**: about 10 kΩ to the − wire at room temperature (NTC thermistor).
  If yours differs, change `NTC_R25` in [firmware/src/main.cpp](firmware/src/main.cpp).
- **Pulse**: power the sensor (+5 V / GND), measure the pulse wire while you blow through it.
  - Switches 0 V ↔ ~5 V: use the divider below.
  - Stays at 0 V: it's open-collector. Skip the divider, wire it straight to GPIO27, and change
    `pinMode(PIN_FLOW, INPUT)` to `INPUT_PULLUP`.

Typical colors: red = +5 V, black = GND, yellow = pulse, green = temperature, blue + other wire = TDS.

## 3. Wiring

Full schematic: https://claude.ai/artifact/Ly4EsdJo9hSQuPKV1TVnU7

```
Sensor +5V (red)    -> ESP32 VIN   (5 V from USB)
Sensor GND (black)  -> ESP32 GND

Pulse (yellow) --[10k]--+-- GPIO27 (D27)
                        |
                      [20k]
                        |
                       GND

3V3 --[10k]--+-- GPIO34 (D34)
             |
      Temperature (green)        (thermistor's other end is sensor GND)
             |
          [100nF] to GND (optional)

GPIO25 (D25) --[4.7k]--+-- GPIO35 (D35)
                       |
                 TDS electrode 1

GPIO26 (D26) ---------- TDS electrode 2
```

Never connect a 5 V signal straight to an ESP32 pin.

## 4. Home server

Any always-on machine on your network. Your Pi 3 works well for this.

```bash
cd server
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
WATER_API_KEY=pick-a-long-random-string uvicorn app:app --host 0.0.0.0 --port 8000
```

Run at boot on a Pi: edit the key in `water-server.service`, then

```bash
sudo cp water-server.service /etc/systemd/system/
sudo systemctl enable --now water-server
```

Open `http://<server-ip>:8000/docs` to try the API.

| Endpoint | Returns |
|---|---|
| `POST /api/readings` | stores a list of readings (used by the ESP32) |
| `GET /api/readings/latest` | newest reading |
| `GET /api/readings?hours=24` | history for charts |
| `GET /api/usage?days=7` | liters per day |
| `GET /api/health` | `{"ok": true}` |

All endpoints except `/api/health` need the header `X-API-Key: <your key>`.

## 5. Flash the ESP32

Install [PlatformIO](https://platformio.org) (the VS Code extension is easiest), then:

1. Copy `firmware/include/secrets.example.h` to `secrets.h` and fill in WiFi, server URL, API key
   and an `OTA_PASS` of your choice.
2. Plug in the board and run `pio run -e esp32dev -t upload` in `firmware/`
   (some DevKit V1 boards need the **BOOT** button held when "Connecting..." appears).
3. Run `pio device monitor` to watch readings every 10 s.

### Updates over WiFi

After the first USB flash, the board accepts new firmware over WiFi:

1. Copy `firmware/local.example.ini` to `local.ini`. Set `upload_port` to `<DEVICE_ID>.local`
   (or the board's IP) and `--auth=` to the same `OTA_PASS` as in `secrets.h`.
2. Run `pio run -e ota -t upload` in `firmware/`. It takes about 2–3 minutes, then the board reboots.

If a WiFi update leaves the board unable to reach WiFi (bad credentials, a crash at boot),
flash it once more over USB. Changing `board_build.partitions` also needs a USB flash.

## 6. Calibration (in the serial monitor)

| Command | What to do |
|---|---|
| `flowstart` → pour exactly 1 L → `flowstop` | saves pulses per liter |
| `tds 342` | probe in a 342 ppm calibration solution (or any water you measured with a TDS pen; use that number) |
| `status` | prints temperature, water resistance and TDS now |

Calibration is saved on the ESP32 and survives reboots and reflashing.
For temperature, compare with a thermometer and adjust `NTC_BETA` (3435 and 3950 are common).

TDS accuracy is roughly ±10% after calibration — good for trends and filter-change alerts.
If readings sit near 0 or never change, adjust `TDS_R_REF` to be close to the `water ... ohm`
value `status` prints in your water.

## 7. Phone access

- **At home**: the app calls `http://<server-ip>:8000/api/...`.
- **Away from home**: install [Tailscale](https://tailscale.com) on the server and phone and use the
  server's Tailscale address. Don't port-forward this server to the internet — it has no HTTPS.

If the server is down, the ESP32 keeps up to ~2.7 hours of readings in memory and sends them later.
