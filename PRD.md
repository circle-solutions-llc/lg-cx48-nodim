# PRD: LG CX48 ABL Defeat Project

## Problem Statement

The LG OLED48CX (CX48) aggressively dims the screen via **ABL (Auto Brightness Limiter)** when large portions of the screen are bright. ABL monitors the Average Picture Level (APL) and reduces panel luminance as the bright area increases, to stay within the power supply's delivery capacity (~205W max, ~89W typical).

Unlike TPC/GSR/ASBL (which are software burn-in protections easily disabled via service menu), **ABL is considered a hardware limitation** — the power supply physically cannot deliver enough current for all pixels at full brightness simultaneously. The community consensus is "ABL cannot be disabled."

**This project aims to prove that wrong.**

## Technical Background

### How ABL Works

1. The **T-CON (Timing Controller)** board manages the ABL algorithm
2. It calculates APL (Average Picture Level) — the average brightness across all pixels
3. When APL exceeds thresholds, the T-CON reduces current delivery to the OLED panel
4. This is a graduated curve: small bright areas = full brightness; large bright areas = dimmed
5. The power supply is rated for ~205W max but typical consumption is ~89W

### CX48 Hardware Architecture

| Component | Role in ABL |
|-----------|-------------|
| **Power Supply (SMPS)** | Delivers DC power to panel; has fixed current/wattage limits |
| **Main Board (SoC)** | Runs webOS, processes video signal, sends to T-CON |
| **T-CON Board** | Implements ABL algorithm, controls source/gate driver ICs on panel |
| **OLED Panel** | Contains source driver ICs that regulate per-pixel current |

### Key Specifications

- Model: OLED48CXPUB
- Panel: 48" LG WOLED (WRGB subpixel)
- webOS version: 5.x
- Max power consumption: 205W
- Typical power consumption: 89W
- Resolution: 3840x2160
- Power supply input: 100-120V AC, 50-60Hz

## Attack Vectors

### Vector 1: Power Supply Upgrade (Hardware)

**Theory:** If ABL exists because the PSU can't deliver enough power, give it a bigger PSU.

**Approach:**
- Tear down the CX48 and identify the SMPS board (likely EAY-series part number)
- Map the power rails and current sense/limit circuitry
- Options:
  a. Modify current-sense resistors to raise the limit threshold
  b. Replace the PSU board with a higher-wattage compatible unit
  c. Supplement with an external bench power supply on the panel power rail
- Measure actual panel current draw at various APL levels to understand headroom

**Risk:** Medium-High. Could damage panel if current limit is set too high. Panel organic layers may degrade faster. Fire risk if PSU is undersized for actual load.

**Feasibility:** Medium. Requires electronics skills and test equipment.

### Vector 2: T-CON Firmware Dump & Modification

**Theory:** The ABL algorithm runs in firmware on the T-CON. If we can dump it, reverse-engineer the ABL curve, and flash a modified version, we can relax or eliminate ABL.

**Approach:**
- Identify the T-CON board and its main IC (likely has SPI/JTAG/UART debug interfaces)
- Dump the firmware from the T-CON's flash memory
- Reverse-engineer the ABL algorithm (look for APL calculation and brightness scaling)
- Modify the ABL curve to be less aggressive or disabled
- Flash modified firmware back to T-CON

**Risk:** High. Bricking the T-CON would require replacement board ($$$).

**Feasibility:** Low-Medium. T-CON firmware is rarely documented. Would need significant RE effort.

### Vector 3: webOS Root + Luna Service Exploration

**Theory:** With root SSH access to the TV, explore undocumented luna services and config files that may expose ABL parameters the service menu doesn't show.

**Approach:**
- Root the TV using faultmanager-autoroot or dejavuln-autoroot
- Get SSH access via Homebrew Channel
- Enumerate all luna services related to display/picture settings
- Search the filesystem for ABL-related config files, calibration data, and parameters
- Probe `com.webos.app.factorywin` (service menu) internals
- Check for undocumented service menu pages or hidden parameters
- Examine how the main board communicates ABL parameters to the T-CON

**Risk:** Low. Rooting is well-documented and reversible. Won't damage hardware.

**Feasibility:** High. Strong community tooling exists. Best starting point.

### Vector 4: Real-Time Content-Side ABL Mitigation

**Theory:** Since ABL is APL-dependent, modify the video signal to reduce effective APL without visible impact.

**Approach:**
- Create an HDMI signal processor or software solution that:
  a. Analyzes incoming frame APL in real-time
  b. Applies subtle darkening to less-important screen regions to keep total APL below ABL threshold
  c. Uses temporal dithering or zone-based brightness management
- Alternative: Custom shader/LUT that compresses the top end of brightness to avoid ABL triggers
- Could be implemented as a Raspberry Pi HDMI passthrough or PC-side software

**Risk:** Low. Non-invasive, doesn't modify the TV.

**Feasibility:** Medium. Real-time HDMI processing is complex. PC-side software is more feasible.

### Vector 5: Service Menu Deep Dive + Current Sense Bypass

**Theory:** The service menu may have hidden/undocumented parameters, and the current sensing may be done partially on the main board where firmware can influence it.

**Approach:**
- Access service menu via ColorControl (Windows), Logitech Harmony remote, or service remote
- Document ALL service menu parameters (not just the commonly discussed ones)
- Look for parameters related to: peak luminance, current limit, power budget, panel drive level
- Use root access to trace how service menu settings are communicated to T-CON
- Map the communication protocol between SoC and T-CON (likely MIPI/LVDS + I2C/SPI sideband)

**Risk:** Low-Medium. Service menu changes are reversible.

**Feasibility:** Medium. Requires systematic exploration.

## Project Phases

### Phase 1: Reconnaissance (Weeks 1-2)
1. Root the TV (faultmanager-autoroot)
2. Get SSH access, map the filesystem
3. Enumerate all luna services related to display
4. Document all service menu parameters
5. Identify T-CON board, main ICs, and debug interfaces
6. Measure current power delivery at various APL levels

### Phase 2: Software Vectors (Weeks 3-4)
7. Deep dive into luna services and config files for ABL parameters
8. Probe main board → T-CON communication protocol
9. Build tools to read/write T-CON registers from webOS
10. Prototype content-side APL reduction software
11. Test if any discovered parameters affect ABL behavior

### Phase 3: Hardware Analysis (Weeks 5-6)
12. Tear down and photograph PSU board
13. Map power rails, current sense resistors, and feedback loops
14. Identify T-CON flash memory and debug interfaces
15. Attempt T-CON firmware dump
16. Measure ABL curve with precision (brightness vs APL at various levels)

### Phase 4: Exploit Development (Weeks 7-8)
17. Based on findings, develop the most promising attack:
    - Modified PSU current limits, OR
    - T-CON firmware patch, OR
    - Luna service ABL parameter override, OR
    - Content-side APL mitigation tool
18. Test extensively with brightness meter
19. Verify panel thermal safety (IR thermometer)

### Phase 5: Packaging & Documentation (Week 9)
20. Package working solution as reproducible toolkit
21. Document the full process with photos/diagrams
22. Create safety guidelines and warnings
23. Publish findings

## Deliverables

1. **recon-toolkit/** — Scripts for rooted webOS TV: enumerate luna services, dump configs, probe T-CON
2. **psu-analysis/** — Documentation of PSU teardown, schematics, current sense circuitry
3. **tcon-research/** — T-CON firmware dump tools, RE notes, any discovered ABL parameters
4. **apl-mitigator/** — Content-side APL reduction tool (software fallback solution)
5. **docs/** — Full teardown photos, wiring diagrams, safety notes, and how-to guides

## Success Criteria

- **Full Success:** ABL disabled or reduced to imperceptible levels on 100% APL white screen
- **Partial Success:** ABL curve relaxed significantly (e.g., 50%+ more brightness at high APL)
- **Workaround Success:** Content-side tool that keeps brightness perceptually constant
- **Knowledge Success:** Full documentation of ABL implementation even if not bypassed

## Safety Considerations

- OLED panels can overheat if driven beyond thermal limits — always monitor panel temperature
- Modifying PSU current limits could create fire hazard — use appropriate fusing
- T-CON firmware bricking would require replacement board (~$150-300)
- Increased brightness will accelerate OLED degradation and burn-in risk
- All hardware modifications void warranty
- Never leave a modified TV unattended during initial testing

## Equipment Needed

- USB-to-UART adapter (for serial debug)
- Logic analyzer or oscilloscope (for T-CON communication)
- SPI flash programmer (for T-CON firmware dump)
- Multimeter and bench power supply
- IR thermometer or thermal camera
- Kill-A-Watt or similar power meter
- Brightness/luminance meter
- Service remote or Logitech Harmony remote (backup access)
- Windows PC with ColorControl installed
- Soldering station with fine-tip capability
