#!/usr/bin/env python3
"""
Colorwood capture helper.

  python capture.py info              device + screen details
  python capture.py shot [name]       one screenshot
  python capture.py burst 20 0.4      20 frames, 0.4s apart (catches animations)
  python capture.py watch             screenshot on every Enter, q to quit

Frames land in ./captures/ as PNG.
"""

import subprocess, sys, time, os
from datetime import datetime

OUT = "captures"


def adb(args, binary=False):
    """Run adb. exec-out is mandatory for binary data — plain `shell` mangles
    newlines on Windows and produces corrupt PNGs."""
    try:
        r = subprocess.run(["adb"] + args, capture_output=True, timeout=30)
    except FileNotFoundError:
        sys.exit("adb not found. Install platform-tools and put it on PATH.")
    except subprocess.TimeoutExpired:
        sys.exit("adb timed out. Is the screen on and unlocked?")
    if r.returncode != 0:
        sys.exit(f"adb failed: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout if binary else r.stdout.decode(errors="replace").strip()


def check_device():
    out = adb(["devices"])
    lines = [l for l in out.splitlines()[1:] if l.strip()]
    if not lines:
        sys.exit("No device. Check the cable, USB debugging, and that you\n"
                 "accepted the RSA prompt on the phone.")
    if any("unauthorized" in l for l in lines):
        sys.exit("Device unauthorized — accept the debugging prompt on the phone.")
    if len(lines) > 1:
        sys.exit(f"Multiple devices:\n" + "\n".join(lines) + "\nUnplug the others.")
    return lines[0].split()[0]


def info():
    dev = check_device()
    print(f"device      : {dev}")
    print(f"model       : {adb(['shell', 'getprop', 'ro.product.model'])}")
    print(f"android     : {adb(['shell', 'getprop', 'ro.build.version.release'])}")
    print(f"size        : {adb(['shell', 'wm', 'size'])}")
    print(f"density     : {adb(['shell', 'wm', 'density'])}")
    fg = adb(["shell", "dumpsys", "window", "|", "grep", "-E", "mCurrentFocus"])
    print(f"focus       : {fg or '(unavailable)'}")
    print()
    print("If 'size' shows an override, screenshots use the physical size —")
    print("calibrate tile coordinates against a real capture, never against specs.")


def shot(name=None):
    check_device()
    os.makedirs(OUT, exist_ok=True)
    png = adb(["exec-out", "screencap", "-p"], binary=True)
    if not png.startswith(b"\x89PNG"):
        sys.exit("Not a PNG. Some overlays/DRM block screencap — try again "
                 "with the game in the foreground.")
    stamp = datetime.now().strftime("%H%M%S")
    fn = f"{OUT}/{name}_{stamp}.png" if name else f"{OUT}/shot_{stamp}.png"
    with open(fn, "wb") as f:
        f.write(png)
    print(f"{fn}  ({len(png)//1024} KB)")
    return fn


def burst(n, gap):
    check_device()
    os.makedirs(OUT, exist_ok=True)
    tag = datetime.now().strftime("%H%M%S")
    print(f"{n} frames, {gap}s apart — start the action now")
    for i in range(n):
        t = time.time()
        png = adb(["exec-out", "screencap", "-p"], binary=True)
        with open(f"{OUT}/burst{tag}_{i:03d}.png", "wb") as f:
            f.write(png)
        print(f"  {i+1}/{n}", end="\r", flush=True)
        time.sleep(max(0, gap - (time.time() - t)))
    print(f"\ndone -> {OUT}/burst{tag}_*.png")


def watch():
    check_device()
    print("Enter = capture, q = quit")
    i = 0
    while True:
        if input().strip().lower() == "q":
            return
        i += 1
        shot(f"w{i:02d}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "info"
    if cmd == "info":
        info()
    elif cmd == "shot":
        shot(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "burst":
        burst(int(sys.argv[2]) if len(sys.argv) > 2 else 20,
              float(sys.argv[3]) if len(sys.argv) > 3 else 0.4)
    elif cmd == "watch":
        watch()
    else:
        sys.exit(__doc__)
