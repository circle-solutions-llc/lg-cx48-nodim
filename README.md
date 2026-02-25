# lg-cx48-nodim

Toolkit for disabling ABL (Auto Brightness Limiter) on the LG OLED48CX.

> **WARNING:** This project involves hardware modification of a television. It will void your warranty, may damage your TV, and carries fire/electrical risk. Proceed at your own risk.

## Background

The LG CX48 OLED aggressively dims the screen when large areas are bright (high APL). This is ABL — a power supply current limitation enforced by the T-CON. Unlike TPC/GSR (software burn-in protections), ABL is considered a hardware limitation.

This project aims to characterize, reduce, or eliminate ABL through multiple attack vectors.

## Project Structure

```
recon-toolkit/    # Scripts for rooted webOS: enumerate services, dump configs, probe T-CON
psu-analysis/     # PSU teardown docs, schematics, current sense circuitry
tcon-research/    # T-CON firmware tools, RE notes, ABL parameter research
apl-mitigator/    # Content-side APL reduction tool (software fallback)
docs/             # Teardown photos, wiring diagrams, safety notes
```

## Attack Vectors

1. **webOS Root + Luna Service Exploration** — Find undocumented ABL parameters
2. **Service Menu Deep Dive** — Systematically document all hidden settings
3. **T-CON Firmware RE** — Dump and modify the ABL algorithm
4. **Power Supply Modification** — Increase current delivery capacity
5. **Content-Side APL Mitigation** — Reduce effective APL in the video signal

## Getting Started

### Prerequisites

- LG OLED48CX with rootable firmware (check [CanI.RootMy.TV](https://cani.rootmy.tv))
- SSH client
- Python 3.10+
- Windows PC with [ColorControl](https://github.com/Maassoft/ColorControl) (for service menu access)

### Phase 1: Root & Recon

```bash
# After rooting your TV and enabling SSH in Homebrew Channel:
cd recon-toolkit
pip install -r requirements.txt

# Run the full recon suite
python recon.py --tv-ip <YOUR_TV_IP>
```

See [PRD.md](PRD.md) for full project plan.
