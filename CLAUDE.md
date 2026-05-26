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

Install dependency: `pip install bleak`

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

## Scripts

- **`wave.py`** — gentle sinusoidal reed-in-the-breeze wave across all joints. Tune `CENTER`, `AMPLITUDE`, `PERIOD`, and `PHASE_STEP` at the top. Run with `python wave.py`.

## Notes

- The BLE address may differ after power cycle; `wave.py` auto-discovers by name (`Hiwonder`)
- The Run button on the controller runs pre-stored offline action groups (group 100 by default), not a mode switch
- If the gripper (servo 1) buzzes during a wave, its CENTER or AMPLITUDE is pushing it below 1500
