"""Scan the webOS filesystem for ABL-related configs, calibration data, and hardware interfaces."""

from ssh_client import TVSSHClient


class FilesystemScanner:
    """Search the rooted TV filesystem for ABL attack surfaces."""

    # Directories likely to contain relevant configs
    SEARCH_DIRS = [
        "/etc",
        "/var/luna",
        "/var/palm",
        "/mnt/lg",
        "/usr/share",
        "/usr/lib",
        "/usr/local",
        "/opt",
        "/tmp",
        "/sys/class",
        "/sys/devices",
        "/proc",
        "/dev",
    ]

    # File patterns related to ABL/display
    ABL_PATTERNS = [
        "*abl*", "*brightness*", "*luminance*", "*dimming*",
        "*peak*", "*current*limit*", "*power*limit*",
    ]

    # Broader display patterns
    DISPLAY_PATTERNS = [
        "*oled*", "*panel*", "*tcon*", "*t-con*", "*tpc*", "*gsr*",
        "*display*", "*backlight*", "*gamma*", "*calibrat*",
    ]

    def __init__(self, ssh: TVSSHClient):
        self.ssh = ssh

    def find_abl_configs(self) -> list[dict]:
        """Search for files containing ABL-related keywords."""
        results = []

        # Grep for ABL keywords in config directories
        keywords = [
            "abl", "ABL", "brightness.limit", "peak.luminance",
            "current.limit", "power.budget", "power.limit",
            "auto.brightness", "dimming.control",
        ]
        for kw in keywords:
            output = self.ssh.exec(
                f"grep -rl '{kw}' /etc/ /var/luna/ /mnt/lg/ /usr/share/ 2>/dev/null | head -30"
            )
            if output.strip():
                files = output.strip().split("\n")
                for f in files:
                    content = self.ssh.read_file(f)[:2000]
                    results.append({
                        "keyword": kw,
                        "file": f,
                        "content_preview": content,
                    })

        return results

    def find_calibration_data(self) -> list[dict]:
        """Find OLED panel calibration and characterization data."""
        results = []

        # Common locations for calibration data
        cal_paths = [
            "/mnt/lg/cmn_data",
            "/mnt/lg/model",
            "/mnt/lg/lgsvc",
            "/mnt/lg/res",
            "/mnt/lg/ciplus",
            "/usr/share/panel",
            "/etc/panel",
        ]

        for path in cal_paths:
            if self.ssh.file_exists(path):
                listing = self.ssh.list_dir(path)
                results.append({"path": path, "listing": listing})

                # Look for binary calibration files
                files = self.ssh.find_files(path, "*", max_depth=3)
                for f in files[:20]:
                    size = self.ssh.exec(f"stat -c '%s' '{f}' 2>/dev/null || stat -f '%z' '{f}' 2>/dev/null").strip()
                    file_type = self.ssh.exec(f"file '{f}' 2>/dev/null").strip()
                    results.append({
                        "file": f,
                        "size": size,
                        "type": file_type,
                    })

        return results

    def find_tcon_files(self) -> list[dict]:
        """Find T-CON firmware, configs, and communication interfaces."""
        results = []

        # Search for T-CON related files
        tcon_patterns = ["*tcon*", "*t_con*", "*tpc*", "*gsr*", "*panel*fw*", "*panel*firm*"]
        for pattern in tcon_patterns:
            files = self.ssh.exec(
                f"find / -name '{pattern}' -not -path '/proc/*' 2>/dev/null | head -20"
            )
            if files.strip():
                for f in files.strip().split("\n"):
                    results.append({"pattern": pattern, "file": f.strip()})

        # Check for T-CON update/flash utilities
        flash_patterns = ["*flash*", "*upgrade*", "*update*"]
        for pattern in flash_patterns:
            files = self.ssh.exec(
                f"find /usr/ /mnt/lg/ -name '{pattern}' 2>/dev/null | head -20"
            )
            if files.strip():
                for f in files.strip().split("\n"):
                    file_info = self.ssh.exec(f"file '{f}' 2>/dev/null").strip()
                    if any(kw in file_info.lower() for kw in ["elf", "script", "executable"]):
                        results.append({
                            "pattern": pattern,
                            "file": f.strip(),
                            "type": file_info,
                        })

        # Check for any panel-related kernel modules
        modules = self.ssh.exec("lsmod 2>/dev/null || cat /proc/modules 2>/dev/null")
        panel_modules = [
            line for line in modules.split("\n")
            if any(kw in line.lower() for kw in ["panel", "oled", "tcon", "display", "drm"])
        ]
        if panel_modules:
            results.append({"source": "kernel_modules", "modules": panel_modules})

        # Check /sys for panel-related sysfs entries
        sysfs = self.ssh.exec(
            "find /sys -name '*oled*' -o -name '*panel*' -o -name '*tcon*' "
            "-o -name '*brightness*' -o -name '*backlight*' 2>/dev/null | head -30"
        )
        if sysfs.strip():
            for entry in sysfs.strip().split("\n"):
                value = self.ssh.exec(f"cat '{entry}' 2>/dev/null").strip()[:500]
                results.append({"sysfs_entry": entry.strip(), "value": value})

        return results

    def dump_service_menu_storage(self) -> list[dict]:
        """Find where service menu settings are persisted."""
        results = []

        # Common locations for service menu config persistence
        storage_paths = [
            "/var/luna/preferences",
            "/mnt/lg/cmn_data/config",
            "/mnt/lg/model",
            "/tmp/luna",
        ]

        for path in storage_paths:
            if self.ssh.file_exists(path):
                listing = self.ssh.list_dir(path)
                results.append({"path": path, "listing": listing})

                # Read JSON config files
                json_files = self.ssh.find_files(path, "*.json", max_depth=3)
                for f in json_files[:15]:
                    content = self.ssh.read_file(f)[:3000]
                    results.append({"file": f, "content": content})

                # Read other config files
                conf_files = self.ssh.find_files(path, "*.conf", max_depth=3)
                for f in conf_files[:15]:
                    content = self.ssh.read_file(f)[:3000]
                    results.append({"file": f, "content": content})

        return results

    def find_hardware_interfaces(self) -> list[dict]:
        """Find I2C, SPI, UART, and other hardware communication interfaces."""
        results = []

        # I2C buses
        i2c_buses = self.ssh.exec("ls /dev/i2c-* 2>/dev/null")
        if i2c_buses.strip():
            results.append({"interface": "i2c", "devices": i2c_buses.strip().split("\n")})

            # Try to detect devices on each I2C bus
            for bus in i2c_buses.strip().split("\n"):
                bus_num = bus.replace("/dev/i2c-", "")
                scan = self.ssh.exec(f"i2cdetect -y {bus_num} 2>/dev/null")
                if scan.strip():
                    results.append({"interface": f"i2c-{bus_num}_scan", "data": scan})

        # SPI devices
        spi_devs = self.ssh.exec("ls /dev/spi* 2>/dev/null")
        if spi_devs.strip():
            results.append({"interface": "spi", "devices": spi_devs.strip().split("\n")})

        # UART/serial devices
        uart_devs = self.ssh.exec("ls /dev/ttyS* /dev/ttyUSB* /dev/ttyAMA* 2>/dev/null")
        if uart_devs.strip():
            results.append({"interface": "uart", "devices": uart_devs.strip().split("\n")})

        # GPIO
        gpio = self.ssh.exec("ls /sys/class/gpio/ 2>/dev/null")
        if gpio.strip():
            results.append({"interface": "gpio", "entries": gpio.strip().split("\n")})

        # DRM/display
        drm = self.ssh.exec("ls /sys/class/drm/ 2>/dev/null")
        if drm.strip():
            results.append({"interface": "drm", "entries": drm.strip().split("\n")})
            # Read DRM device info
            for entry in drm.strip().split("\n")[:5]:
                status = self.ssh.exec(f"cat /sys/class/drm/{entry}/status 2>/dev/null").strip()
                modes = self.ssh.exec(f"cat /sys/class/drm/{entry}/modes 2>/dev/null").strip()
                if status or modes:
                    results.append({
                        "interface": f"drm/{entry}",
                        "status": status,
                        "modes": modes,
                    })

        # Framebuffer devices
        fb = self.ssh.exec("ls /dev/fb* 2>/dev/null")
        if fb.strip():
            results.append({"interface": "framebuffer", "devices": fb.strip().split("\n")})

        return results
