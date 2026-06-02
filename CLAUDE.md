# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Python control scripts for the **HiWonder LeArm** 6-DOF robotic arm (original Bluetooth version, not the LeArm AI).

Reference docs are in `specs/sites.txt`. The user manual PDF is at `specs/LeArm user manual.pdf`.

## Hardware

- **Servos:** PWM-style (LFD-06, LDX-218, LD-1501MG) — position range **500–2500**, center **1500**
- **Controller:** 6-channel Bluetooth servo controller board with a Run button and power switch
- **Servo 1 (gripper):** minimum position is **1500** (not 500) — going below causes stall/buzz
- **Servo layout (base → tip):** 6=waist rotation, 5=shoulder, 4=elbow, 3=wrist pitch, 2=wrist roll, 1=gripper

## Connection

**Use Bluetooth, not USB.** The USB port is for the Windows-only PC software and uses a proprietary protocol — it will not respond to serial commands from Mac.

Control goes through the HM-10 BLE module on the controller board:

| Detail | Value |
|---|---|
| BLE device name | `Hiwonder` |
| BLE address (may change) | `573DF516-1A57-D070-C27D-30CE2297291C` |
| Service UUID | `0000ffe0-0000-1000-8000-00805f9b34fb` |
| Characteristic handle | `32` (UUID `0000ffe1`) |

Install dependencies: `pip install bleak flask`

## Serial Protocol (over BLE)

Packet format for `CMD_SERVO_MOVE` (0x03):

```
0x55 0x55 [data_len] [0x03] [count] [time_low] [time_high] [id] [pos_low] [pos_high] ...
```

- `data_len` = number of parameter bytes + 2
- `count` = number of servos in this packet
- Multiple servos can be moved in one packet
- Position range: 500–2500 (center 1500); clamp servo 1 to 1500–2500

**Example** — move servo 6 to 1700 over 2000 ms:
```
55 55 08 03 01 D0 07 06 A4 06
```

`make_move(positions, duration_ms)` in both scripts builds this packet. It is duplicated — if you change the packet format, update both files.

## Scripts

- **`wave.py`** — standalone sinusoidal wave across all joints. Tune `CENTER`, `AMPLITUDE`, `PERIOD`, and `PHASE_STEP` at the top. Run with `python wave.py`. Ctrl+C returns to center.
- **`server.py`** — Flask web server with real-time parameter control. Run with `python server.py`, then open `http://localhost:5002`. Parameters can be adjusted live while the arm is moving.

## Web Server Architecture (`server.py`)

Flask and Bleak cannot share an event loop, so the BLE wave loop runs in a dedicated daemon thread with its own `asyncio` event loop (`_ble_thread()`). Flask runs in the main thread.

Shared state between threads is a plain `params` dict and a `threading.Event` (`stop_flag`). The GIL makes scalar dict reads/writes safe without a lock.

### API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Serves `templates/index.html` |
| GET | `/api/status` | Returns `{running, connected, error, params}` |
| POST | `/api/params` | Updates `amplitude`, `period`, `phase_step`, `update_hz`, `centers` live |
| POST | `/api/start` | Starts BLE thread and wave loop |
| POST | `/api/stop` | Sets `stop_flag`; arm returns to center before disconnecting |

The frontend (`templates/index.html`) is vanilla JS with no build step. It polls `/api/status` every 800 ms and debounces slider input 60 ms before POSTing to `/api/params`.

## Notes

- The BLE address may differ after power cycle; both scripts auto-discover by name (`Hiwonder`)
- The Run button on the controller runs pre-stored offline action groups (group 100 by default), not a mode switch
- If the gripper (servo 1) buzzes during a wave, its CENTER or AMPLITUDE is pushing it below 1500
- Gripper center differs between scripts: `2500` in `wave.py`, `1500` in `server.py`
