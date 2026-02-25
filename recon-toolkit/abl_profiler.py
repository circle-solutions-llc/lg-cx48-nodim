"""Profile ABL behavior by displaying test patterns and measuring brightness response."""

import json
import time

from ssh_client import TVSSHClient


class ABLProfiler:
    """Generate APL test patterns on the TV and characterize the ABL curve."""

    # APL levels to test (percentage of screen at max white)
    APL_TEST_LEVELS = [1, 5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100]

    # Expected peak brightness for 48CX at 1% APL (approximate, nits)
    PEAK_BRIGHTNESS_1PCT = 800  # nits, approximate for CX48

    def __init__(self, ssh: TVSSHClient):
        self.ssh = ssh

    def profile_abl_curve(self) -> dict:
        """Run through APL levels and record brightness measurements.

        Note: This generates test patterns on the TV screen. Actual brightness
        measurement requires an external light meter — the tool will prompt
        the user to enter measurements, or can estimate from power draw.
        """
        results = {
            "model": "OLED48CX",
            "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "methodology": "APL test patterns displayed via framebuffer",
            "measurements": [],
            "instructions": (
                "For each APL level, a test pattern is displayed. "
                "Use a luminance meter pointed at the white area to record nits, "
                "or press Enter to skip (power-based estimation will be used)."
            ),
        }

        # Check if we can write to the framebuffer
        fb_available = self.ssh.file_exists("/dev/fb0")
        if not fb_available:
            results["error"] = "No framebuffer device found. Manual test pattern display required."
            results["manual_instructions"] = self._get_manual_instructions()
            return results

        # Get display resolution
        resolution = self._get_resolution()
        results["resolution"] = resolution

        for apl_pct in self.APL_TEST_LEVELS:
            measurement = self._test_apl_level(apl_pct, resolution)
            results["measurements"].append(measurement)

        # Calculate ABL curve characteristics
        if results["measurements"]:
            results["abl_analysis"] = self._analyze_curve(results["measurements"])

        return results

    def _get_resolution(self) -> dict:
        """Get the current display resolution."""
        # Try multiple methods
        modes = self.ssh.exec("cat /sys/class/drm/*/modes 2>/dev/null | head -5")
        fb_info = self.ssh.exec("cat /sys/class/graphics/fb0/virtual_size 2>/dev/null")
        xres = self.ssh.exec("cat /sys/class/graphics/fb0/stride 2>/dev/null")

        return {
            "drm_modes": modes.strip(),
            "fb_virtual_size": fb_info.strip(),
            "fb_stride": xres.strip(),
            "assumed": "3840x2160",
        }

    def _test_apl_level(self, apl_pct: int, resolution: dict) -> dict:
        """Display a test pattern at a given APL level and measure response."""
        # Generate the test pattern description
        # For a given APL%, we display that percentage of the screen as full white
        # and the rest as full black

        measurement = {
            "apl_pct": apl_pct,
            "pattern": f"{apl_pct}% white, {100 - apl_pct}% black (horizontal split)",
            "measured_nits": None,
            "expected_nits": self._expected_brightness(apl_pct),
            "reduction_pct": None,
            "power_draw_watts": None,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Try to display the pattern using luna capture service (reverse - display)
        # In practice, a dedicated test pattern app would be deployed
        # For now, generate the pattern data for manual use
        measurement["test_pattern_script"] = self._generate_pattern_script(apl_pct)

        return measurement

    def _expected_brightness(self, apl_pct: int) -> float:
        """Calculate expected brightness if ABL were not present."""
        # Without ABL, brightness should be constant regardless of APL
        return self.PEAK_BRIGHTNESS_1PCT

    def _generate_pattern_script(self, apl_pct: int) -> str:
        """Generate a shell script that displays a test pattern at the given APL level."""
        # This creates a simple framebuffer write for the test pattern
        width = 3840
        height = 2160
        white_rows = int(height * apl_pct / 100)

        return f"""#!/bin/sh
# APL {apl_pct}% test pattern - {white_rows} rows white, {height - white_rows} rows black
# Run on the TV via SSH

WIDTH={width}
HEIGHT={height}
WHITE_ROWS={white_rows}
FB=/dev/fb0

# Generate pattern: white rows followed by black rows
# Each pixel is 4 bytes (BGRA)
python3 -c "
import sys
white = b'\\xff\\xff\\xff\\xff' * {width}
black = b'\\x00\\x00\\x00\\xff' * {width}
for row in range({height}):
    if row < {white_rows}:
        sys.stdout.buffer.write(white)
    else:
        sys.stdout.buffer.write(black)
" > $FB 2>/dev/null

echo "Displaying APL {apl_pct}% pattern ({white_rows}/{height} rows white)"
echo "Measure brightness of white area with luminance meter"
"""

    def _analyze_curve(self, measurements: list[dict]) -> dict:
        """Analyze the ABL curve from measurements."""
        analysis = {
            "description": "ABL curve analysis",
            "notes": [
                "Expected brightness should be constant if no ABL",
                "Any reduction from expected indicates ABL activity",
                "The shape of the reduction curve reveals the ABL algorithm",
            ],
        }

        # If we have measured values, compute the curve
        measured = [m for m in measurements if m.get("measured_nits") is not None]
        if measured:
            peak = max(m["measured_nits"] for m in measured)
            analysis["measured_peak_nits"] = peak
            analysis["abl_onset_apl"] = None  # APL where dimming first appears

            for m in measured:
                m["reduction_pct"] = round(
                    (1 - m["measured_nits"] / m["expected_nits"]) * 100, 1
                )
                if analysis["abl_onset_apl"] is None and m["reduction_pct"] > 2:
                    analysis["abl_onset_apl"] = m["apl_pct"]

        return analysis

    def _get_manual_instructions(self) -> str:
        return """
Manual ABL Profiling Instructions:

1. Open an image viewer or web browser on the TV
2. For each APL level, display a test image:
   - APL 10%: Small white rectangle centered on black background
   - APL 25%: White covering top quarter of screen
   - APL 50%: White covering top half of screen
   - APL 75%: White covering top three-quarters
   - APL 100%: Full white screen

3. For each level:
   a. Wait 10 seconds for ABL to stabilize
   b. Measure brightness of the white area with a luminance meter
   c. Record the power consumption from a Kill-A-Watt meter

4. The brightness should theoretically be the same at all APL levels.
   Any reduction at higher APL is ABL in action.

Test pattern images can be generated with the included generate_patterns.py script.
"""
