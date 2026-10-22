# Carrier board design

A 2-layer carrier board. The ESP32 DevKit V1 plugs into female headers, and the
DWS-MH-02 sensor plugs into a JST socket. JLCPCB assembles the SMT parts; you
hand-solder the headers and the socket.

## Decisions

| Topic | Choice | Why |
|---|---|---|
| Board type | Carrier for DevKit V1 | keeps USB for power and flashing; simple 2-layer board |
| Sensor connection | JST socket matching the sensor plug | sensor plugs straight in |
| Assembly | JLCPCB SMT (0805 parts), THT hand-soldered | 0805 is still easy to rework by hand |
| TDS | auto-range: 4.7k (tap) + 47k (filtered) | each water reads with a reference resistor near its own resistance |
| Flow input | 4.7k pull-up to 5 V + 10k/20k divider | works whether the sensor drives 5 V or only pulls low |

## Connections (nets)

| Net | Connects |
|---|---|
| +5V | DevKit VIN, sensor +, R5 |
| GND | DevKit GND (both sides), sensor −, R2, C1, C2 |
| 3V3 | DevKit 3V3, R3 |
| PULSE_RAW | sensor pulse, R5, R1 |
| FLOW | R1, R2, C1, DevKit D27 |
| TEMP | sensor temp, R3, C2, DevKit D34 |
| TDS_SENSE | sensor TDS 1, R4, R6, DevKit D35 |
| TDS_LO | R4, DevKit D25 |
| TDS_HI | R6, DevKit D33 |
| TDS_B | sensor TDS 2, DevKit D26 |

## Parts

| Ref | Value | Package | Purpose |
|---|---|---|---|
| R1 | 10k | 0805 | pulse divider, series |
| R2 | 20k | 0805 | pulse divider, to GND |
| R3 | 10k | 0805 | thermistor pull-up (match the NTC's 25 °C value) |
| R4 | 4.7k | 0805 | TDS reference, low range |
| R5 | 4.7k | 0805 | pulse pull-up to 5 V |
| R6 | 47k | 0805 | TDS reference, high range |
| C1 | 1 nF | 0805 | pulse noise filter (~7 µs, fine up to tens of kHz) |
| C2 | 100 nF | 0805 | temperature noise filter |
| J1, J2 | 1x15 female header, 2.54 mm | THT | DevKit sockets |
| J3 | 6-pin JST (PH 2.0 or XH 2.5, TBD) | THT | sensor |
| H1–H4 | M3 mounting holes | — | — |

Flow levels at D27: sensor driving 5 V gives 3.33 V. Open-collector with only the
4.7k pull-up gives 5 × 20 / (4.7 + 10 + 20) = 2.88 V, above the ESP32's 2.48 V
logic-high threshold.

## Still to measure

- [ ] Sensor connector pitch (2.0 or 2.5 mm) and wire order
- [ ] DevKit header row spacing (center to center) and pins per side
- [ ] Thermistor resistance at room temperature (sets R3)
