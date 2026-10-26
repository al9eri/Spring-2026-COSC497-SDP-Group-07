"""the PC's own hotspot, from Python: read it, switch it on, keep it on.

the boards join the PC's own hotspot -- it sits next to them, so range stops
being a problem, and its network is one the fleet already scans. this module is
how the rest of the project talks to it, on either OS, through whatever the
Settings app itself drives (nothing to install):

    config()      ssid, passphrase, band, on/off, clients
    ensure_on()   switch it on if it is off
    subnet()      the /24 it hands out, live

    python -m anomaly.hotspot            # status (never shows the password)
    python -m anomaly.hotspot --on       # switch it on

the passphrase comes back to the caller through a pipe and is never printed or
written anywhere -- it goes straight down the USB cable to the board.

**Windows** -- the Mobile Hotspot, through the same WinRT API the Settings page
uses, driven from PowerShell. two of its habits matter here:
  - it will only start while the PC has a connection to share (Ethernet or
    WiFi with internet). no internet in the demo room = no hotspot.
  - by default it switches itself OFF after a few minutes with nobody
    connected, and a board that rebooted then has nothing to rejoin. turn that
    off: Settings > Network & internet > Mobile hotspot > Power saving.
    `anomaly.fleet --hotspot` also switches it back on whenever it drops.

**macOS** -- Internet Sharing, read from the same preference file the Sharing
pane writes and started through its launch daemon. two differences from
Windows, both because macOS keeps this behind an admin wall:
  - it must be *configured* once by hand (which connection to share, and the
    WiFi name and password): System Settings > General > Sharing > Internet
    Sharing. no script can choose those for you. after that this module can
    switch it on and off.
  - switching it on needs root, so we only ever try `sudo -n` (no password
    prompt, which would hang the control panel). passwordless sudo is unusual,
    so in practice `--on` prints the one command to paste, or you flip the
    switch in Settings. once it is on, everything else here just works.
  - the password lives in the System keychain, which also needs root to read.
    when we cannot, `anomaly.device_wifi --hotspot` asks you to type it once
    instead of reading it off the OS.

Linux is not supported: it has no single hotspot API to drive.
"""
from __future__ import annotations

import argparse
import base64
import json
import plistlib
import re
import subprocess
import sys
import time


class HotspotError(RuntimeError):
    pass


# ============================================================ Windows backend

# Windows' Internet Connection Sharing always hands the hotspot this /24 unless
# someone has edited the registry to change it.
WIN_SUBNET = "192.168.137"

_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # else "preparing modules" lands on stderr as CLIXML
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType=WindowsRuntime]
$null = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType=WindowsRuntime]
$cp = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if ($null -eq $cp) { @{ error = 'no internet connection to share -- Windows will not start a hotspot without one' } | ConvertTo-Json -Compress; exit 0 }
$tm = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($cp)
function Await($op, [Type]$t) {
  $m = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
  $task = $m.MakeGenericMethod($t).Invoke($null, @($op))
  $null = $task.Wait(20000)
  $task.Result
}
function State {
  $c = $tm.GetCurrentAccessPointConfiguration()
  @{ ssid = $c.Ssid; passphrase = $c.Passphrase; band = [string]$c.Band;
     state = [string]$tm.TetheringOperationalState; clients = $tm.ClientCount;
     max_clients = $tm.MaxClientCount; shared_from = $cp.ProfileName }
}
"""

_STATUS = _PRELUDE + r"""
State | ConvertTo-Json -Compress
"""

_START = _PRELUDE + r"""
$out = State
if ($out.state -ne 'On') {
  $r = Await ($tm.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
  $out = State
  $out.start_status = [string]$r.Status
  $out.start_message = [string]$r.AdditionalErrorMessage
}
$out | ConvertTo-Json -Compress
"""


def _win_run(script: str, timeout: float = 40.0) -> dict:
    # -EncodedCommand, NOT the script on stdin: `-Command -` parses stdin like an
    # interactive console, so after a multi-line `if { }` it waits for a
    # possible `else` and silently swallows the line that prints the result --
    # the hotspot started (or not) and the caller heard nothing at all.
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                            "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
                           capture_output=True, text=True, timeout=timeout,
                           # no console flashing up when a windowed app (the
                           # control panel) asks for the hotspot's state
                           creationflags=0x08000000)    # CREATE_NO_WINDOW
    except FileNotFoundError:
        raise HotspotError("powershell.exe not found")
    except subprocess.TimeoutExpired:
        raise HotspotError("Windows did not answer within %d s" % timeout)
    lines = [l for l in r.stdout.splitlines() if l.strip().startswith("{")]
    if not lines:
        # stderr can carry a stack trace, never the passphrase: it is only
        # ever emitted inside the JSON on stdout
        msg = (r.stderr or r.stdout or "").strip().splitlines()
        raise HotspotError("could not read the hotspot: %s" % (msg[-1] if msg else "no output"))
    out = json.loads(lines[-1])
    if out.get("error"):
        raise HotspotError(out["error"])
    return out


def _win_config() -> dict:
    out = _win_run(_STATUS)
    out["configured"] = True          # Windows always has an AP configuration
    return out


def _win_ensure_on() -> dict:
    out = _win_run(_START)
    if out.get("state") != "On":
        why = out.get("start_message") or out.get("start_status") or "unknown"
        raise HotspotError("Windows would not start the hotspot (%s)" % why)
    out["configured"] = True
    return out


def _win_subnet() -> str:
    return WIN_SUBNET


def _win_band_problem(cfg: dict) -> str | None:
    b = (cfg.get("band") or "").lower()
    if "five" in b or b.startswith("5"):
        return ("the hotspot is set to 5 GHz, which the ESP32 cannot join. "
                "Settings > Network & internet > Mobile hotspot > Properties > "
                "Edit > Network band: 2.4 GHz")
    return None


# ============================================================== macOS backend

# Internet Sharing's own NAT, on bridge100. Apple has used this /24 for every
# version that matters here, but we read the live address first and only fall
# back to the constant.
MAC_SUBNET = "192.168.2"

_NAT_PLIST = "/Library/Preferences/SystemConfiguration/com.apple.nat.plist"
_SHARE_IFACE = "bridge100"
_LEASES = "/var/db/dhcpd_leases"
_DAEMON = "system/com.apple.NetworkSharing"

_SETTINGS_PATH = ("System Settings > General > Sharing > Internet Sharing "
                  "(share from your Ethernet or iPhone connection, to Wi-Fi; "
                  "set the network name and a WPA2 password under Wi-Fi Options)")


def _mac_nat() -> dict:
    """the Sharing pane's own preference file, or {} if it was never configured.

    root owns it but it is world-readable, so this needs no privileges. the
    AirPort sub-dictionary has been renamed across releases, so every key is
    looked up case-insensitively rather than spelled out.
    """
    try:
        with open(_NAT_PLIST, "rb") as f:
            return plistlib.load(f).get("NAT", {}) or {}
    except (FileNotFoundError, PermissionError):
        return {}
    except Exception:
        return {}


def _pick(d: dict, *names) -> object:
    """d[name], case- and underscore-insensitively, for the first name present."""
    if not isinstance(d, dict):
        return None
    flat = {re.sub(r"[^a-z0-9]", "", k.lower()): v for k, v in d.items()}
    for n in names:
        v = flat.get(re.sub(r"[^a-z0-9]", "", n.lower()))
        if v is not None:
            return v
    return None


def _mac_iface_ip(iface: str = _SHARE_IFACE) -> str | None:
    """the interface's IPv4 address, or None when it has none (= sharing is off).

    bridge100 only exists and only gets 192.168.2.1 while Internet Sharing is
    actually up and serving, which makes this the honest 'is it on?' test --
    the preference file only says whether it is *meant* to be on.
    """
    try:
        r = subprocess.run(["/usr/sbin/ipconfig", "getifaddr", iface],
                           capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    ip = r.stdout.strip()
    return ip or None


def _mac_clients() -> int | None:
    """how many devices bootpd has handed a lease to, or None if we cannot tell."""
    try:
        with open(_LEASES, encoding="utf-8", errors="replace") as f:
            return f.read().count("{")
    except (FileNotFoundError, PermissionError):
        return None


def _mac_passphrase(ssid: str) -> str | None:
    """the shared network's WPA2 password, if the keychain will give it up.

    Internet Sharing keeps it in the *System* keychain, which needs root -- so
    this is a best effort and None is the normal answer. `sudo -n` never
    prompts: an interactive prompt here would hang the control panel, which
    reads the hotspot on a timer with no terminal attached.
    """
    if not ssid:
        return None
    attempts = [
        ["security", "find-generic-password", "-w", "-s", ssid],
        ["sudo", "-n", "security", "find-generic-password", "-w", "-s", ssid,
         "/Library/Keychains/System.keychain"],
    ]
    for cmd in attempts:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                               stdin=subprocess.DEVNULL)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        pw = r.stdout.strip()
        if r.returncode == 0 and pw:
            return pw
    return None


def _mac_band(air: dict) -> str:
    """2.4 GHz / 5 GHz, read off the configured channel. 0 = the Mac chooses."""
    try:
        ch = int(_pick(air, "Channel") or 0)
    except (TypeError, ValueError):
        ch = 0
    if ch == 0:
        return "auto"
    return "2.4 GHz" if ch <= 14 else "5 GHz"


def _mac_config() -> dict:
    nat = _mac_nat()
    air = _pick(nat, "AirPort") or {}
    ssid = _pick(air, "NetworkName", "networkname", "SSID") or ""
    ip = _mac_iface_ip()
    shared_from = _pick(_pick(nat, "PrimaryInterface") or {}, "Device") or "?"
    # "configured" is the distinction that does not exist on Windows: macOS has
    # no hotspot at all until somebody has picked what to share, in the pane.
    configured = bool(nat) and bool(ssid)
    return {
        "ssid": ssid,
        "passphrase": _mac_passphrase(ssid),
        "band": _mac_band(air),
        "state": "On" if ip else "Off",
        "clients": _mac_clients(),
        "max_clients": None,
        "shared_from": shared_from,
        "configured": configured,
        "ip": ip,
    }


def _mac_ensure_on(timeout: float = 20.0) -> dict:
    cfg = _mac_config()
    if cfg["state"] == "On":
        return cfg
    if not cfg["configured"]:
        raise HotspotError(
            "Internet Sharing has never been set up on this Mac, and no script can "
            "choose which connection to share or name the network. Do it once by hand: "
            + _SETTINGS_PATH)
    # configured but down. starting it is root's job; -n so we never block on a
    # password prompt nobody is there to answer.
    try:
        r = subprocess.run(["sudo", "-n", "launchctl", "kickstart", "-k", _DAEMON],
                           capture_output=True, text=True, timeout=25,
                           stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        r = None
    except subprocess.TimeoutExpired:
        r = None
    if r is None or r.returncode != 0:
        raise HotspotError(
            "macOS will not let a script switch Internet Sharing on without root. "
            "Either flip it on in " + _SETTINGS_PATH + ", or run this once in a "
            "terminal:  sudo launchctl kickstart -k " + _DAEMON)
    deadline = time.time() + timeout
    while time.time() < deadline:                 # bridge100 takes a moment to appear
        time.sleep(1.0)
        cfg = _mac_config()
        if cfg["state"] == "On":
            return cfg
    raise HotspotError("the Internet Sharing daemon was started but %s never got an "
                       "address -- is there a connection to share?" % _SHARE_IFACE)


def _mac_subnet() -> str:
    ip = _mac_iface_ip()
    return ".".join(ip.split(".")[:3]) if ip else MAC_SUBNET


def _mac_band_problem(cfg: dict) -> str | None:
    if cfg.get("band") == "5 GHz":
        return ("Internet Sharing is on a 5 GHz channel, which the ESP32 cannot join. "
                "Set the channel to 11 or lower: " + _SETTINGS_PATH)
    return None


# ================================================================== dispatch

if sys.platform == "win32":
    NAME = "Mobile Hotspot"
    SUBNET = WIN_SUBNET
    _config, _ensure_on, _subnet, _band_problem = (
        _win_config, _win_ensure_on, _win_subnet, _win_band_problem)
elif sys.platform == "darwin":
    NAME = "Internet Sharing"
    SUBNET = MAC_SUBNET
    _config, _ensure_on, _subnet, _band_problem = (
        _mac_config, _mac_ensure_on, _mac_subnet, _mac_band_problem)
else:
    NAME = "hotspot"
    SUBNET = ""

    def _unsupported(*_a, **_k):
        raise HotspotError("the hotspot helpers only support Windows and macOS; "
                           "put the board and this machine on the same WiFi instead "
                           "and run the fleet without --hotspot")

    def _subnet() -> str:
        return ""

    _config = _ensure_on = _band_problem = _unsupported


def config() -> dict:
    """the hotspot as the OS has it configured, passphrase included when readable."""
    return _config()


def ensure_on() -> dict:
    """switch it on if it is off; the result says whether that worked."""
    return _ensure_on()


def subnet() -> str:
    """the /24 the hotspot hands out, read live where the OS can tell us."""
    return _subnet() or SUBNET


def band_problem(cfg: dict) -> str | None:
    """the ESP32 is 2.4 GHz only."""
    return _band_problem(cfg)


def describe(cfg: dict) -> str:
    """one line, safe to print: no passphrase.

    the control panel scrapes the `hotspot 'name': State` prefix off this, so
    both backends print the same shape -- keep it. the one exception is a Mac
    where Internet Sharing was never configured: there is no name and no state
    to report, and saying "Off" would send someone hunting for a switch that
    is not the problem.
    """
    if cfg.get("configured") is False:
        return "%s is not set up on this Mac -- %s" % (NAME, _SETTINGS_PATH)
    return "hotspot %r: %s, %s, %s/%s clients, sharing %s" % (
        cfg.get("ssid"), cfg.get("state"), cfg.get("band"),
        "?" if cfg.get("clients") is None else cfg.get("clients"),
        cfg.get("max_clients") or "?", cfg.get("shared_from"))


def main() -> int:
    ap = argparse.ArgumentParser(description="this machine's %s: read it, switch it on" % NAME)
    ap.add_argument("--on", action="store_true", help="switch it on if it is off")
    a = ap.parse_args()
    try:
        cfg = ensure_on() if a.on else config()
    except HotspotError as e:
        print("  %s" % e)
        return 1
    print("  " + describe(cfg))
    if sys.platform == "darwin" and cfg.get("state") == "On" and not cfg.get("passphrase"):
        print("  (the password is in the System keychain, which needs root -- "
              "device_wifi will ask you to type it)")
    bad = band_problem(cfg)
    if bad:
        print("  WARNING: " + bad)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
