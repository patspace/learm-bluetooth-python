#!/usr/bin/env python3
"""
Gentle wave motion for LeArm via Bluetooth LE.
Drives joints 2-6 in a sinusoidal cascade (base leads, tip lags)
to produce a reed-in-the-breeze effect.

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

# ── Tunable parameters ────────────────────────────────────────────────────────
# CENTER: resting position per joint (500–2500, center = 1500).
# Servo IDs from base to tip: 6=waist, 5=shoulder, 4=elbow, 3=wrist, 2=wrist roll
# ID 1 is the gripper — left at rest.
JOINTS  = [6,    5,    4,    3,    2,    1   ]
CENTER  = [1500, 1500, 1500, 1000, 1500, 1500]  # tune if arm slouches
AMPLITUDE  = 120    # ±120 position units ≈ ±14° of swing
PERIOD     = 5.0    # seconds per full sway cycle (longer = lazier)
PHASE_STEP = 0.40   # radians of lag added per joint toward the tip
UPDATE_HZ  = 20     # command updates per second
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


async def main():
    address = await find_arm()
    if not address:
        address = input("Enter BLE address manually: ").strip()

    move_duration = int(1000 / UPDATE_HZ * 1.4)
    tick = 1.0 / UPDATE_HZ

    async with BleakClient(address) as client:
        print(f"Connected. Moving to center positions...")

        cmd = make_move(list(zip(JOINTS, CENTER)), 2000)
        await client.write_gatt_char(CHAR_HANDLE, cmd, response=False)
        await asyncio.sleep(2.5)

        print(f"Waving. Period={PERIOD}s  Amplitude={AMPLITUDE}  Ctrl+C to stop.\n")
        start = time.time()
        omega = 2 * math.pi / PERIOD

        try:
            while True:
                t = time.time() - start
                positions = []
                for i, (sid, center) in enumerate(zip(JOINTS, CENTER)):
                    pos = center + AMPLITUDE * math.sin(omega * t + i * PHASE_STEP)
                    positions.append((sid, pos))

                cmd = make_move(positions, move_duration)
                await client.write_gatt_char(CHAR_HANDLE, cmd, response=False)
                await asyncio.sleep(tick)

        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nStopping — returning to center...")
            cmd = make_move(list(zip(JOINTS, CENTER)), 2000)
            await client.write_gatt_char(CHAR_HANDLE, cmd, response=False)
            await asyncio.sleep(2.5)


if __name__ == "__main__":
    asyncio.run(main())
