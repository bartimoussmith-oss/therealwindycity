"""Portability: get this runtime onto *any* device, and keep it movable.

The runtime itself is stdlib-only Python, so "installing" is three things:
  1. python3 present,
  2. this repo (or just `agent/`) present,
  3. a launcher plus a way to keep `serve` running.

Nothing here needs a package manager, a container, or a build step — and when a
device can't do one of the three, `WORKAROUNDS` names the path that still works.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from . import config as cfg

INSTALL_DIR = Path(__file__).resolve().parent / "install"

SCRIPTS = {
    "termux": "termux.sh",
    "linux": "linux.sh",
    "macos": "macos.sh",
    "windows": "windows.ps1",
    "chromebook": "chromebook.md",
}

WORKAROUNDS = {
    "android-termux": [
        "Termux from F-Droid is the supported route (Play Store builds are stale).",
        "pip wheels: if a package won't build, don't install it — this runtime needs none.",
        "Keep it alive in the background: `termux-wake-lock` and the Termux notification.",
        "Storage access: run `termux-setup-storage` once to reach /sdcard, or keep the repo "
        "in Termux's own home.",
        "Battery optimizations kill long runs: Android Settings → Apps → Termux → Unrestricted.",
        "No model on the phone? Point it at a PC: `agent config set base_url "
        "http://<pc-ip>:11434/v1` + `agent config set provider ollama`, or use --provider paste.",
    ],
    "windows": [
        "No admin rights? Install Python for the current user and use `py -m agent serve`.",
        "Firewall: allow Python once, or `New-NetFirewallRule` in the generated script.",
        "WSL2 is optional; native Windows works. If you do use WSL, the LAN IP is the Windows one.",
    ],
    "chromebook": [
        "No Crostini? Use the Play Store Termux/Android app on your phone and point Chrome at it, "
        "or run the host on your PC and install this console as a PWA. Chromebook is a client.",
        "With Crostini: `sudo apt install python3` is enough; no pip needed.",
    ],
    "linux": [
        "User service (no root): `systemctl --user enable --now wyagent` after running linux.sh.",
        "Headless box: keep `agent serve` on 0.0.0.0 and put it behind Tailscale for remote access.",
    ],
    "macos": [
        "launchd plist is written by macos.sh if you want it to start at login.",
        "Gatekeeper is a non-issue: nothing here is a downloaded binary.",
    ],
}


def detect_target() -> str:
    env = os.environ
    if env.get("TERMUX_VERSION") or env.get("PREFIX", "").startswith("/data/data/com.termux"):
        return "termux"
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "macos"
    if system == "linux":
        try:
            if "chromeos" in Path("/etc/os-release").read_text(errors="replace").lower():
                return "chromebook"
        except OSError:
            pass
        return "linux"
    return "linux"


def python_ok() -> tuple[bool, str]:
    if sys.version_info < (3, 9):
        return False, f"python {platform.python_version()} is too old (need 3.9+)"
    return True, f"python {platform.python_version()}"


def install(target: str = "auto") -> int:
    target = detect_target() if target in ("auto", None) else target
    script = SCRIPTS.get(target)
    print(f"windycity-agent installer — target: {target}")
    ok, note = python_ok()
    print(f"  python check : {'ok' if ok else 'FAIL'} ({note})")
    print(f"  repo         : {cfg.REPO_ROOT}")
    print(f"  state dir    : {cfg.home_dir()}")
    if not script or not (INSTALL_DIR / script).exists():
        print(f"\n  no script for {target!r}; available: {', '.join(sorted(SCRIPTS))}")
        return 1

    path = INSTALL_DIR / script
    print(f"\n  script: {path}\n")
    if target == "windows":
        print("  run it in PowerShell (no admin needed for a user install):")
        print(f"    powershell -ExecutionPolicy Bypass -File \"{path}\"")
    elif script.endswith(".md"):
        print((path).read_text(encoding="utf-8"))
    else:
        print("  run it:")
        print(f"    bash {path}")

    tips = WORKAROUNDS.get(target) or []
    if tips:
        print(f"\n  if something blocks you on {target}:")
        for t in tips:
            print(f"    • {t}")

    print("\n  then, from anywhere:")
    print("    wyagent doctor          # probe this device")
    print("    wyagent serve           # console for your phone/tablet/other devices")
    print("    wyagent run \"<task>\"    # one-shot task")
    return 0


def doctor_lines() -> list[str]:
    """Extra environment facts the doctor prints (kept here to avoid clutter)."""
    lines = []
    lines.append(f"install target : {detect_target()}")
    for tool in ("wyagent", "ollama", "claude", "tailscale", "termux-wake-lock", "node"):
        lines.append(f"  {'✓' if shutil.which(tool) else '·'} {tool}")
    disk = shutil.disk_usage(str(cfg.home_dir().parent if cfg.home_dir().parent.exists() else "/"))
    lines.append(f"disk free      : {disk.free / 1e9:.1f} GB")
    return lines


def maybe_run(script: Path, assume_yes: bool = False) -> int:
    if not assume_yes:
        print(f"(not executed automatically — run: bash {script})")
        return 0
    return subprocess.call(["bash", str(script)])
