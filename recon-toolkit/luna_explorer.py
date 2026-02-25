"""Explore luna services on rooted webOS TV for ABL-related parameters."""

from ssh_client import TVSSHClient


class LunaExplorer:
    """Systematically enumerate luna services related to display and brightness."""

    # Luna service URIs known to relate to display/picture/power
    DISPLAY_SERVICES = [
        "luna://com.webos.settingsservice/getSystemSettings",
        "luna://com.webos.service.config/getConfigs",
        "luna://com.webos.service.tvpower/power/getPowerState",
        "luna://com.webos.service.tv2/getSystemInfo",
    ]

    # Settings categories to probe
    SETTINGS_CATEGORIES = [
        "picture", "other", "option", "system", "commercial",
        "broadcast", "network", "sound", "general", "lock",
    ]

    # Config keys that may relate to ABL
    ABL_CONFIG_PREFIXES = [
        "tv.model", "tv.config", "tv.picture", "tv.oled",
        "tv.panel", "tv.display", "tv.power", "tv.brightness",
        "tv.dimming", "tv.abl", "tv.tpc", "tv.gsr",
        "tv.luminance", "tv.current", "com.webos.service.tv2",
    ]

    # Specific config keys to try
    ABL_CONFIG_KEYS = [
        "tv.config.ablMode",
        "tv.config.ablEnable",
        "tv.config.ablLevel",
        "tv.config.tpcEnable",
        "tv.config.gsrEnable",
        "tv.config.peakLuminance",
        "tv.config.maxBrightness",
        "tv.config.panelPowerLimit",
        "tv.config.oledDimming",
        "tv.config.currentLimit",
        "tv.config.powerBudget",
        "tv.picture.ablMode",
        "tv.picture.tpcEnable",
        "tv.picture.gsrEnable",
        "tv.oled.ablCurve",
        "tv.oled.ablThreshold",
        "tv.oled.peakNits",
        "tv.oled.maxCurrent",
        "tv.panel.ablConfig",
        "tv.panel.currentLimit",
        "tv.panel.powerLimit",
    ]

    def __init__(self, ssh: TVSSHClient):
        self.ssh = ssh

    def enumerate_display_services(self) -> list[dict]:
        """Find all luna services related to display/picture/power."""
        results = []

        # List all registered services
        raw = self.ssh.exec("ls-monitor -l 2>/dev/null || luna-send -n 1 -f "
                           "'luna://com.palm.bus/signal/listNames' '{}'")
        if raw:
            results.append({"source": "service_list", "data": raw[:5000]})

        # Try to list services via bus
        for method in ["listNames", "listActiveMethods"]:
            resp = self.ssh.luna_send(
                f"luna://com.palm.bus/signal/{method}", {}
            )
            if resp and "raw_output" not in resp:
                results.append({"source": f"bus_{method}", "data": resp})

        # Check for display-specific service files
        service_files = self.ssh.find_files("/usr/share/luna-service2", "*.service")
        display_services = [
            f for f in service_files
            if any(kw in f.lower() for kw in [
                "display", "picture", "tv2", "panel", "oled",
                "power", "brightness", "setting", "config"
            ])
        ]
        results.append({"source": "service_files", "data": display_services})

        # Read each display service file
        for svc_file in display_services[:20]:
            content = self.ssh.read_file(svc_file)
            results.append({"source": f"service_file:{svc_file}", "data": content[:2000]})

        return results

    def dump_picture_settings(self) -> dict:
        """Dump all picture-related settings."""
        results = {}

        # Get settings for each category
        for category in self.SETTINGS_CATEGORIES:
            resp = self.ssh.luna_send(
                "luna://com.webos.settingsservice/getSystemSettings",
                {"category": category, "keys": ["*"]}
            )
            results[category] = resp

            # Also try without keys filter
            resp2 = self.ssh.luna_send(
                "luna://com.webos.settingsservice/getSystemSettings",
                {"category": category}
            )
            results[f"{category}_full"] = resp2

        return results

    def dump_system_settings(self) -> dict:
        """Dump system configuration settings."""
        results = {}

        # Dump all configs
        resp = self.ssh.luna_send(
            "luna://com.webos.service.config/getConfigs",
            {"configNames": ["*"]}
        )
        results["all_configs"] = resp

        # Try each ABL-related prefix
        for prefix in self.ABL_CONFIG_PREFIXES:
            resp = self.ssh.luna_send(
                "luna://com.webos.service.config/getConfigs",
                {"configNames": [f"{prefix}.*"]}
            )
            results[f"config_{prefix}"] = resp

        return results

    def probe_abl_parameters(self) -> dict:
        """Specifically probe for ABL-related parameters."""
        results = {}

        # Try each known/guessed ABL config key
        for key in self.ABL_CONFIG_KEYS:
            resp = self.ssh.luna_send(
                "luna://com.webos.service.config/getConfigs",
                {"configNames": [key]}
            )
            results[key] = resp

        # Try settings service with ABL-related keys
        abl_setting_keys = [
            "ablMode", "ablEnable", "tpcEnable", "gsrEnable",
            "peakLuminance", "oledDimming", "brightnessLimit",
            "currentLimit", "powerLimit", "panelDrive",
            "energySaving", "eyeComfortMode", "aiPicture",
            "hdrModuleMode", "dynamicContrast",
        ]
        for key in abl_setting_keys:
            resp = self.ssh.luna_send(
                "luna://com.webos.settingsservice/getSystemSettings",
                {"category": "picture", "keys": [key]}
            )
            results[f"picture_{key}"] = resp

        # Check the factory/service menu application's settings
        resp = self.ssh.luna_send(
            "luna://com.webos.service.config/getConfigs",
            {"configNames": ["com.webos.app.factorywin.*"]}
        )
        results["factorywin_config"] = resp

        # Try TV2 service for system info that might include ABL state
        for method in ["getSystemInfo", "getPanelInfo", "getOledInfo"]:
            resp = self.ssh.luna_send(f"luna://com.webos.service.tv2/{method}", {})
            results[f"tv2_{method}"] = resp

        return results

    def dump_oled_settings(self) -> dict:
        """Dump all OLED-specific settings and panel information."""
        results = {}

        # OLED-specific luna calls
        oled_queries = [
            ("luna://com.webos.service.tv2/getPanelInfo", {}),
            ("luna://com.webos.service.tv2/getOledInfo", {}),
            ("luna://com.webos.settingsservice/getSystemSettings",
             {"category": "picture", "keys": ["oledLightControl"]}),
            ("luna://com.webos.settingsservice/getSystemSettings",
             {"category": "picture", "keys": ["backlight"]}),
            ("luna://com.webos.settingsservice/getSystemSettings",
             {"category": "picture", "keys": ["contrast"]}),
            ("luna://com.webos.settingsservice/getSystemSettings",
             {"category": "picture", "keys": ["brightness"]}),
            ("luna://com.webos.settingsservice/getSystemSettings",
             {"category": "other", "keys": ["oledCareMode"]}),
        ]

        for uri, params in oled_queries:
            key = uri.split("/")[-1] + "_" + str(list(params.get("keys", ["default"]))[0] if "keys" in params else "default")
            resp = self.ssh.luna_send(uri, params)
            results[key] = resp

        # Search for OLED-related config files on disk
        oled_configs = self.ssh.exec(
            "grep -rl -i 'abl\\|brightness.*limit\\|peak.*luminance\\|current.*limit\\|power.*budget' "
            "/etc/ /var/luna/ /mnt/lg/ 2>/dev/null | head -50"
        )
        results["oled_config_files"] = oled_configs.strip().split("\n") if oled_configs.strip() else []

        return results
