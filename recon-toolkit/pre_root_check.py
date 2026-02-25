#!/usr/bin/env python3
"""
Pre-root checker for LG webOS TVs.

Discovers LG TVs on the local network via SSDP, queries their firmware
version, and checks rootability before any SSH access is needed.
"""

import argparse
import json
import socket
import struct
import sys
import time
from urllib.request import urlopen, Request
from urllib.error import URLError

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SSDP_MX = 3
SSDP_ST = "urn:lge-com:service:webos-second-screen:1"

# Known rootable firmware ranges for CX (OLED48CX) — webOS 5.x
# Source: community reports + CanI.RootMy.TV
# Format: (min_version, max_version, exploit, notes)
CX_ROOTABLE_INFO = {
    "webos5": {
        "faultmanager": "webOS 5 latest firmware is patched as of 2025. "
                        "If your firmware is older (pre-2024 update), it may still be vulnerable. "
                        "Check CanI.RootMy.TV with your exact firmware version.",
        "dejavuln": "DejaVuln works on webOS 3.5+. May work if faultmanager is patched.",
        "downgrade": "CX (2020) supports firmware downgrade via USB. "
                     "Download a rootable firmware from community sources.",
    }
}


def discover_lg_tvs(timeout: int = 5) -> list[dict]:
    """Discover LG TVs on the local network via SSDP."""
    msg = (
        f"M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
        f"MAN: \"ssdp:discover\"\r\n"
        f"MX: {SSDP_MX}\r\n"
        f"ST: {SSDP_ST}\r\n"
        f"\r\n"
    ).encode()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout)

    # Send SSDP discovery
    sock.sendto(msg, (SSDP_ADDR, SSDP_PORT))

    # Also try the general SSDP target
    general_msg = msg.replace(SSDP_ST.encode(), b"ssdp:all")
    sock.sendto(general_msg, (SSDP_ADDR, SSDP_PORT))

    tvs = []
    seen_ips = set()
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(4096)
            ip = addr[0]
            if ip in seen_ips:
                continue

            response = data.decode("utf-8", errors="replace")

            # Check if this is an LG TV
            if "LG" in response or "webos" in response.lower():
                seen_ips.add(ip)
                tv = {"ip": ip, "ssdp_response": response}

                # Extract LOCATION header for device description
                for line in response.split("\r\n"):
                    if line.lower().startswith("location:"):
                        tv["location"] = line.split(":", 1)[1].strip()
                    elif line.lower().startswith("server:"):
                        tv["server"] = line.split(":", 1)[1].strip()

                tvs.append(tv)
        except socket.timeout:
            break

    sock.close()
    return tvs


def query_tv_info(ip: str) -> dict:
    """Query TV info via the webOS HTTP API (no auth required for basic info)."""
    info = {"ip": ip}

    # Try the common webOS info endpoints
    endpoints = [
        (f"http://{ip}:3000/api/system", "system_api"),
        (f"http://{ip}:1925/system/info", "system_info"),
        (f"http://{ip}:3000/", "root"),
    ]

    for url, key in endpoints:
        try:
            req = Request(url, headers={"User-Agent": "lg-cx48-nodim/1.0"})
            resp = urlopen(req, timeout=3)
            data = resp.read().decode("utf-8", errors="replace")
            try:
                info[key] = json.loads(data)
            except json.JSONDecodeError:
                info[key] = data[:1000]
        except (URLError, OSError):
            pass

    # Try SSAP WebSocket handshake to get device info
    try:
        req = Request(
            f"http://{ip}:3000/api/v2/",
            headers={"User-Agent": "lg-cx48-nodim/1.0"}
        )
        resp = urlopen(req, timeout=3)
        data = resp.read().decode("utf-8", errors="replace")
        try:
            info["ssap_info"] = json.loads(data)
        except json.JSONDecodeError:
            info["ssap_info"] = data[:1000]
    except (URLError, OSError):
        pass

    return info


def check_developer_mode_port(ip: str) -> bool:
    """Check if the Developer Mode SSH port (9922) is open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((ip, 9922))
        sock.close()
        return result == 0
    except OSError:
        return False


def check_homebrew_ssh(ip: str) -> bool:
    """Check if Homebrew Channel SSH (port 22) is already available."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((ip, 22))
        sock.close()
        return result == 0
    except OSError:
        return False


def print_rooting_guide(tv_info: dict):
    """Print a rooting guide based on what we know about the TV."""
    ip = tv_info["ip"]

    print("\n" + "=" * 60)
    print("ROOTING GUIDE FOR YOUR LG CX48")
    print("=" * 60)

    # Check if already rooted
    if check_homebrew_ssh(ip):
        print("\n[!] SSH port 22 is OPEN — your TV may already be rooted!")
        print(f"    Try: ssh root@{ip} (password: alpine)")
        return

    print(f"""
STEP 1: CHECK YOUR FIRMWARE VERSION
------------------------------------
On the TV: Settings > All Settings > General > About This TV
Note down the "Software Version" (e.g., 04.30.60)

Then check: https://cani.rootmy.tv
Enter your model (OLED48CX) and firmware version.

STEP 2: CHOOSE YOUR METHOD
---------------------------

Option A: faultmanager-autoroot (if firmware is vulnerable)
  1. On the TV, install "Developer Mode" app from the LG Content Store
  2. Sign in with your LG developer account (create one at webostv.developer.lge.com)
  3. Enable Developer Mode in the app, then restart the TV
  4. On your Mac, install webOS SDK or use Dev Manager:
     - Download: https://webostv.developer.lge.com/develop/tools/cli-installation
     - Or use ares-setup-device + ares-shell from the CLI tools
  5. Connect to the TV:
     ares-setup-device (add your TV's IP, port 9922)
     ares-shell -d <device_name>
  6. On the TV shell:
     cd /tmp
     curl -L -o autoroot.sh https://github.com/throwaway96/faultmanager-autoroot/raw/main/autoroot.sh
     sh autoroot.sh
  7. Wait for "Payload complete"
  8. BEFORE rebooting: uninstall Developer Mode app
  9. Reboot the TV

Option B: Firmware downgrade first (if current firmware is patched)
  1. Find a rootable firmware version:
     - Check community sources for OLED48CX firmware files
     - Look for older firmware (pre-2024) .epk files
  2. Prepare a USB drive (FAT32):
     - Create a folder called "LG_DTV" at the root
     - Copy the .epk firmware file into LG_DTV/
  3. Open TV browser and go to: https://webosapp.club/downgrade/
     - This enables firmware downgrade (normally blocked)
  4. Insert USB drive into TV
  5. Go to Settings > All Settings > General > About This TV > Check for Updates
  6. TV should find the older firmware on USB and offer to install
  7. After downgrade, proceed with Option A above

Option C: dejavuln-autoroot (alternative exploit)
  Same process as Option A but use:
  curl -L -o autoroot.sh https://github.com/throwaway96/dejavuln-autoroot/raw/main/autoroot.sh

STEP 3: VERIFY ROOT
--------------------
After reboot, Homebrew Channel should appear in your app list.
Open it and enable SSH in settings.
Then from your Mac:
  ssh root@{ip}
  Password: alpine

STEP 4: SECURE SSH
------------------
  ssh root@{ip} 'mkdir -p /home/root/.ssh && cat >> /home/root/.ssh/authorized_keys' < ~/.ssh/id_rsa.pub
""")


def main():
    parser = argparse.ArgumentParser(description="Pre-root check for LG webOS TVs")
    parser.add_argument("--tv-ip", help="IP address of TV (skip discovery)")
    parser.add_argument("--discover", action="store_true", help="Discover LG TVs on network")
    args = parser.parse_args()

    if args.discover or not args.tv_ip:
        print("Searching for LG TVs on your network...")
        tvs = discover_lg_tvs(timeout=5)

        if not tvs:
            print("No LG TVs found via SSDP discovery.")
            if not args.tv_ip:
                print("Use --tv-ip <IP> to specify the TV address directly.")
                return
        else:
            print(f"\nFound {len(tvs)} LG TV(s):")
            for tv in tvs:
                print(f"  - {tv['ip']}")
                if "server" in tv:
                    print(f"    Server: {tv['server']}")

            if not args.tv_ip:
                args.tv_ip = tvs[0]["ip"]
                print(f"\nUsing first discovered TV: {args.tv_ip}")

    ip = args.tv_ip
    print(f"\nChecking TV at {ip}...")

    # Port checks
    print(f"\n  Port 22  (Homebrew SSH): ", end="")
    if check_homebrew_ssh(ip):
        print("OPEN — TV appears to already be rooted!")
    else:
        print("closed")

    print(f"  Port 9922 (Dev Mode SSH): ", end="")
    if check_developer_mode_port(ip):
        print("OPEN — Developer Mode is enabled")
    else:
        print("closed")

    # Query TV info
    print(f"\n  Querying TV info...")
    tv_info = query_tv_info(ip)

    for key in ["system_api", "system_info", "ssap_info"]:
        if key in tv_info and tv_info[key]:
            print(f"  {key}: {json.dumps(tv_info[key], indent=2)[:500]}")

    # Print rooting guide
    print_rooting_guide(tv_info)


if __name__ == "__main__":
    main()
