#!/usr/bin/env python3
"""
LeArm animations via Bluetooth LE.

Modes
-----
  wave      — gentle sinusoidal reed-in-the-breeze across all joints
  spin_clap — condense → rise → clap ×2 → condense, repeat

Usage:
    pip install bleak
    python wave.py
"""

import asyncio
import math
import time
from bleak import BleakClient, BleakScanner

# Hiwonder BLE UART characteristic (handle 32, service 0xFFE0)
CHAR_HANDLE = 32

# ── Select animation ──────────────────────────────────────────────────────────
MODE = "wave"    # "wave" | "spin_clap"
# ─────────────────────────────────────────────────────────────────────────────

# ── Wave parameters ───────────────────────────────────────────────────────────
# Servo IDs from base to tip: 6=waist, 5=shoulder, 4=elbow, 3=wrist, 2=wrist roll, 1=gripper
JOINTS     = [6,    5,    4,    3,    2,    1   ]
CENTER     = [1500, 1500, 1500, 1000, 1500, 2500]
AMPLITUDE  = 800    # ±position units of swing
PERIOD     = 15.0   # seconds per full sway cycle
PHASE_STEP = 0.40   # radians of lag added per joint toward the tip
UPDATE_HZ  = 20
# ─────────────────────────────────────────────────────────────────────────────

# ── Spin-and-clap keyframes ───────────────────────────────────────────────────
SC_CONDENSED = [(6, 1500), (5, 1200), (4, 2200), (3, 1800), (2, 1500), (1, 1500)]
SC_RAISED    = [(6, 1500), (5, 1900), (4, 1300), (3, 1000), (2, 1500), (1, 1500)]
SC_OPEN      = [(1, 2500)]
SC_CLOSED    = [(1, 1500)]
# ─────────────────────────────────────────────────────────────────────────────


def make_move(positions, duration_ms):
    """Build a CMD_SERVO_MOVE packet: 0x55 0x55 [len] 0x03 [count] [t_lo] [t_hi] [id] [p_lo] [p_hi] ..."""
    count = len(positions)
    params = [count, duration_ms & 0xFF, (duration_ms >> 8) & 0xFF]
    for sid, pos in positions:
        pos = max(500, min(2500, int(pos)))
        params += [sid, pos & 0xFF, (pos >> 8) & 0xFF]
    data_len = len(params) + 2
    return bytes([0x55, 0x55, data_len, 0x03] + params)


async def find_arm():
    print("Scanning for Hiwonder arm...")
    devices = await BleakScanner.discover(timeout=5.0)
    for d in devices:
        if d.name and "hiwonder" in d.name.lower():
            print(f"  Found: {d.name}  {d.address}")
            return d.address
    print("  Not found — available devices:")
    for d in devices:
        if d.name:
            print(f"    {d.address}  {d.name}")
    return None


async def run_wave(client):
    print(f"Waving. Period={PERIOD}s  Amplitude={AMPLITUDE}  Ctrl+C to stop.\n")
    start = time.time()
    omega = 2 * math.pi / PERIOD
    tick  = 1.0 / UPDATE_HZ
    move_duration = int(1000 / UPDATE_HZ * 1.4)

    while True:
        t = time.time() - start
        positions = [
            (sid, center + AMPLITUDE * math.sin(omega * t + i * PHASE_STEP))
            for i, (sid, center) in enumerate(zip(JOINTS, CENTER))
        ]
        await client.write_gatt_char(CHAR_HANDLE, make_move(positions, move_duration), response=False)
        await asyncio.sleep(tick)


async def run_spin_clap(client):
    print("Spin & clap. Ctrl+C to stop.\n")

    async def send(pos, dur, pause):
        await client.write_gatt_char(CHAR_HANDLE, make_move(pos, dur), response=False)
        await asyncio.sleep(pause)

    while True:
        await send(SC_CONDENSED, 1500, 1.8)
        await send(SC_RAISED,    2000, 2.3)
        for _ in range(2):
            await send(SC_OPEN,   350, 0.45)
            await send(SC_CLOSED, 350, 0.45)
        await send(SC_CONDENSED, 2000, 2.3)


async def main():
    address = await find_arm()
    if not address:
        address = input("Enter BLE address manually: ").strip()

    async with BleakClient(address) as client:
        print(f"Connected.")

        if MODE == "spin_clap":
            home = SC_CONDENSED
        else:
            home = list(zip(JOINTS, CENTER))

        print("Moving to start position...")
        await client.write_gatt_char(CHAR_HANDLE, make_move(home, 2000), response=False)
        await asyncio.sleep(2.5)

        try:
            if MODE == "spin_clap":
                await run_spin_clap(client)
            else:
                await run_wave(client)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nStopping — returning to start position...")
            await client.write_gatt_char(CHAR_HANDLE, make_move(home, 2000), response=False)
            await asyncio.sleep(2.5)


if __name__ == "__main__":
    asyncio.run(main())
