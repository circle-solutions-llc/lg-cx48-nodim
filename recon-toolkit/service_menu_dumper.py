"""Dump and enumerate all service menu parameters via luna services."""

from ssh_client import TVSSHClient


class ServiceMenuDumper:
    """Systematically extract all service menu parameters from the TV."""

    # Known service menu category IDs (from IN-START menu)
    # These vary by model/firmware but this covers the CX range
    KNOWN_CATEGORIES = {
        1: "ADC",
        2: "White Balance",
        3: "White Balance 2",
        4: "Sound",
        5: "Timer",
        6: "Option",
        7: "Hotel Mode",
        8: "System 1",
        9: "System 2",
        10: "IP",
        11: "Reserved",
        12: "OLED",  # <-- This is the critical one for ABL
        13: "OLED (alt)",  # Some firmware versions use 13
        14: "Module",
        15: "Panel",
    }

    # OLED submenu parameters known from community research
    KNOWN_OLED_PARAMS = [
        "TPC Enable",
        "GSR Enable",
        "HDR Module",
        "OLED Off",
        "Panel Refresh",
        "Pixel Refresher",
        "JB Mode",
        "TPC Temp",
        "OLED Luminance",
    ]

    def __init__(self, ssh: TVSSHClient):
        self.ssh = ssh

    def enumerate_categories(self) -> list[dict]:
        """List all service menu categories accessible via luna."""
        results = []

        # Try to get factory menu structure
        resp = self.ssh.luna_send(
            "luna://com.webos.service.config/getConfigs",
            {"configNames": ["com.webos.app.factorywin.*"]}
        )
        results.append({"source": "factorywin_config", "data": resp})

        # Try to enumerate ezAdjust menu items
        for menu_type in ["ezAdjust", "inStart", "pCheck"]:
            resp = self.ssh.luna_send(
                "luna://com.webos.service.config/getConfigs",
                {"configNames": [f"tv.svcmenu.{menu_type}.*"]}
            )
            results.append({"source": f"svcmenu_{menu_type}", "data": resp})

        # Check for service menu persistence files
        svc_files = self.ssh.exec(
            "find /var/luna/preferences /mnt/lg/ -name '*svc*' -o -name '*service*' "
            "-o -name '*factory*' -o -name '*instart*' -o -name '*ezadj*' 2>/dev/null | head -30"
        )
        if svc_files.strip():
            for f in svc_files.strip().split("\n"):
                content = self.ssh.read_file(f)[:3000]
                results.append({"source": f"file:{f}", "data": content})

        return results

    def dump_oled_parameters(self) -> list[dict]:
        """Extract all parameters from the OLED service menu section."""
        results = []

        # Search for OLED-specific config storage
        oled_configs = self.ssh.exec(
            "grep -rl -i 'tpc\\|gsr\\|oled.*enable\\|peak.*lum\\|panel.*bright' "
            "/var/luna/ /mnt/lg/ /etc/ 2>/dev/null | head -30"
        )
        if oled_configs.strip():
            for f in oled_configs.strip().split("\n"):
                content = self.ssh.read_file(f)[:5000]
                results.append({
                    "file": f.strip(),
                    "content": content,
                })

        # Try known config key patterns for OLED menu
        oled_keys = [
            "tv.config.tpcEnable",
            "tv.config.gsrEnable",
            "tv.config.oledLuminance",
            "tv.config.panelRefresh",
            "tv.config.hdrModule",
            "tv.config.jbMode",
            "tv.config.oledOff",
            "tv.config.oledCare",
            "tv.config.tpcTemp",
            "tv.config.ablMode",
            "tv.config.ablCurve",
            "tv.config.ablThreshold",
            "tv.config.peakBrightness",
            "tv.config.maxPanelCurrent",
            "tv.config.panelPowerBudget",
            "tv.config.oledDriveCurrent",
            "tv.config.pixelBoost",
            "tv.config.dynamicToneMapping",
        ]
        for key in oled_keys:
            resp = self.ssh.luna_send(
                "luna://com.webos.service.config/getConfigs",
                {"configNames": [key]}
            )
            if resp and resp != {"raw_output": ""}:
                results.append({"key": key, "value": resp})

        # Try to read OLED settings from the settings service
        oled_setting_keys = [
            "tpcEnable", "gsrEnable", "oledLuminance", "panelRefresh",
            "hdrModule", "ablMode", "ablCurve", "peakBrightness",
            "oledDriveCurrent", "panelPowerLimit", "currentLimit",
        ]
        for key in oled_setting_keys:
            for category in ["picture", "other", "option"]:
                resp = self.ssh.luna_send(
                    "luna://com.webos.settingsservice/getSystemSettings",
                    {"category": category, "keys": [key]}
                )
                if resp and resp != {"raw_output": ""}:
                    results.append({
                        "category": category,
                        "key": key,
                        "value": resp,
                    })

        return results

    def find_hidden_parameters(self) -> list[dict]:
        """Search for undocumented service menu parameters."""
        results = []

        # Search binary files for strings related to ABL
        binaries_to_search = [
            "/usr/bin/luna-send",
            "/usr/sbin/",
        ]

        # Find the TV service binaries
        tv_bins = self.ssh.exec(
            "find /usr/bin /usr/sbin /usr/lib -name '*tv*' -o -name '*panel*' "
            "-o -name '*oled*' -o -name '*display*' 2>/dev/null | head -30"
        )
        if tv_bins.strip():
            for binary in tv_bins.strip().split("\n")[:10]:
                # Extract strings related to ABL
                strings_output = self.ssh.exec(
                    f"strings '{binary}' 2>/dev/null | "
                    f"grep -i 'abl\\|brightness.*limit\\|current.*limit\\|power.*budget\\|"
                    f"peak.*lum\\|tpc\\|gsr\\|dimming\\|panel.*drive' | head -50"
                )
                if strings_output.strip():
                    results.append({
                        "binary": binary.strip(),
                        "abl_strings": strings_output.strip().split("\n"),
                    })

        # Search shared libraries
        libs = self.ssh.exec(
            "find /usr/lib -name '*.so*' | "
            "xargs -I{} sh -c 'strings {} 2>/dev/null | "
            "grep -il \"abl\\|brightness.limit\\|current.limit\" && echo {}' 2>/dev/null | head -20"
        )
        if libs.strip():
            results.append({"source": "shared_libraries", "matches": libs.strip().split("\n")})

        # Check for any luna service API definitions that mention ABL
        api_files = self.ssh.exec(
            "find /usr/share/luna-service2 /etc/palm -name '*.json' -o -name '*.api' 2>/dev/null | "
            "xargs grep -l -i 'abl\\|brightness.*limit\\|panel.*power' 2>/dev/null | head -20"
        )
        if api_files.strip():
            for f in api_files.strip().split("\n"):
                content = self.ssh.read_file(f)[:3000]
                results.append({"source": f"api_file:{f}", "content": content})

        # Look for display driver configurations
        display_configs = self.ssh.exec(
            "find / -name '*.conf' -o -name '*.cfg' -o -name '*.ini' 2>/dev/null | "
            "xargs grep -l -i 'abl\\|auto.bright\\|current.lim\\|power.lim' 2>/dev/null | head -20"
        )
        if display_configs.strip():
            for f in display_configs.strip().split("\n"):
                content = self.ssh.read_file(f)[:3000]
                results.append({"source": f"config_file:{f}", "content": content})

        return results
