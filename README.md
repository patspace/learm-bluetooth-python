# LeArm BLE Control

Python scripts for controlling the **HiWonder LeArm** 6-DOF robotic arm (original Bluetooth version) from macOS.

## Requirements

```
pip install bleak flask
```

## Usage

### Standalone wave (`wave.py`)

Runs a sinusoidal reed-in-the-breeze motion across all joints. Tune `AMPLITUDE`, `PERIOD`, `PHASE_STEP`, and `CENTER` at the top of the file.

```
python wave.py
```

Ctrl+C stops the wave and returns the arm to center.

### Web UI (`server.py`)

A local Flask server with sliders for live parameter editing while the arm is moving.

```
python server.py
```

Open [http://localhost:5001](http://localhost:5001) in your browser.

## Hardware

- **Arm:** HiWonder LeArm (6-DOF, original BLE version — not LeArm AI)
- **Servos:** PWM-style, position range 500–2500 (center 1500)
- **Gripper (servo 1):** minimum position 1500 — going lower causes stall/buzz
- **Servo layout:** 6=waist · 5=shoulder · 4=elbow · 3=wrist pitch · 2=wrist roll · 1=gripper

## Connection

Connects over Bluetooth LE by scanning for a device named `Hiwonder`. Make sure Bluetooth is enabled and the arm is powered on before running either script. The BLE address may change after a power cycle — auto-discovery handles this.

> **Note:** The USB port on the controller is for the Windows PC software only and won't work from Mac.
