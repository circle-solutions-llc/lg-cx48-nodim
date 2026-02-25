#!/usr/bin/env python3
"""
LG CX48 ABL Recon Toolkit

Connects to a rooted LG webOS TV via SSH and enumerates all luna services,
display-related configurations, service menu parameters, and T-CON
communication interfaces to find ABL-related attack surfaces.
"""

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ssh_client import TVSSHClient
from luna_explorer import LunaExplorer
from filesystem_scanner import FilesystemScanner
from service_menu_dumper import ServiceMenuDumper
from abl_profiler import ABLProfiler

console = Console()


def parse_args():
    parser = argparse.ArgumentParser(
        description="LG CX48 ABL Recon Toolkit — enumerate attack surfaces on rooted webOS TV"
    )
    parser.add_argument("--tv-ip", required=True, help="IP address of the rooted LG TV")
    parser.add_argument("--tv-port", type=int, default=22, help="SSH port (default: 22)")
    parser.add_argument("--tv-user", default="root", help="SSH user (default: root)")
    parser.add_argument("--tv-password", default="alpine", help="SSH password (default: alpine)")
    parser.add_argument("--ssh-key", help="Path to SSH private key (preferred over password)")
    parser.add_argument("--output-dir", default="./recon-output", help="Directory for output files")
    parser.add_argument(
        "--modules",
        nargs="+",
        default=["all"],
        choices=["all", "luna", "filesystem", "service-menu", "abl-profile"],
        help="Which recon modules to run",
    )
    return parser.parse_args()


def run_luna_recon(ssh: TVSSHClient, output_dir: Path):
    """Enumerate all luna services related to display, picture, and power."""
    console.rule("[bold blue]Luna Service Exploration")

    explorer = LunaExplorer(ssh)

    # Enumerate display-related luna services
    console.print("[bold]Enumerating display-related luna services...")
    services = explorer.enumerate_display_services()
    _save_json(output_dir / "luna-display-services.json", services)
    console.print(f"  Found {len(services)} display-related services")

    # Dump all picture settings
    console.print("[bold]Dumping picture settings...")
    picture_settings = explorer.dump_picture_settings()
    _save_json(output_dir / "luna-picture-settings.json", picture_settings)

    # Dump all system settings
    console.print("[bold]Dumping system settings...")
    system_settings = explorer.dump_system_settings()
    _save_json(output_dir / "luna-system-settings.json", system_settings)

    # Probe for ABL-specific parameters
    console.print("[bold]Probing for ABL-related parameters...")
    abl_params = explorer.probe_abl_parameters()
    _save_json(output_dir / "luna-abl-params.json", abl_params)

    # Dump OLED-specific settings
    console.print("[bold]Dumping OLED-specific settings...")
    oled_settings = explorer.dump_oled_settings()
    _save_json(output_dir / "luna-oled-settings.json", oled_settings)

    return {
        "services": services,
        "picture_settings": picture_settings,
        "abl_params": abl_params,
        "oled_settings": oled_settings,
    }


def run_filesystem_recon(ssh: TVSSHClient, output_dir: Path):
    """Scan the filesystem for ABL-related configs, calibration data, and binaries."""
    console.rule("[bold blue]Filesystem Scan")

    scanner = FilesystemScanner(ssh)

    # Search for ABL/brightness/dimming related files
    console.print("[bold]Searching for ABL-related configuration files...")
    abl_files = scanner.find_abl_configs()
    _save_json(output_dir / "fs-abl-configs.json", abl_files)
    console.print(f"  Found {len(abl_files)} potentially relevant files")

    # Dump OLED calibration data
    console.print("[bold]Searching for OLED calibration/panel data...")
    cal_files = scanner.find_calibration_data()
    _save_json(output_dir / "fs-calibration-data.json", cal_files)

    # Find T-CON related binaries and configs
    console.print("[bold]Searching for T-CON related files...")
    tcon_files = scanner.find_tcon_files()
    _save_json(output_dir / "fs-tcon-files.json", tcon_files)

    # Dump service menu configuration storage
    console.print("[bold]Dumping service menu config storage...")
    svc_configs = scanner.dump_service_menu_storage()
    _save_json(output_dir / "fs-service-menu-storage.json", svc_configs)

    # Find all I2C/SPI device interfaces
    console.print("[bold]Enumerating hardware interfaces (I2C/SPI/UART)...")
    hw_interfaces = scanner.find_hardware_interfaces()
    _save_json(output_dir / "fs-hardware-interfaces.json", hw_interfaces)

    return {
        "abl_files": abl_files,
        "calibration": cal_files,
        "tcon_files": tcon_files,
        "hw_interfaces": hw_interfaces,
    }


def run_service_menu_recon(ssh: TVSSHClient, output_dir: Path):
    """Dump all service menu parameters via luna service calls."""
    console.rule("[bold blue]Service Menu Parameter Dump")

    dumper = ServiceMenuDumper(ssh)

    console.print("[bold]Enumerating all service menu categories...")
    categories = dumper.enumerate_categories()
    _save_json(output_dir / "svc-menu-categories.json", categories)
    console.print(f"  Found {len(categories)} categories")

    console.print("[bold]Dumping all OLED service menu parameters...")
    oled_params = dumper.dump_oled_parameters()
    _save_json(output_dir / "svc-menu-oled-params.json", oled_params)
    console.print(f"  Found {len(oled_params)} OLED parameters")

    console.print("[bold]Searching for undocumented/hidden parameters...")
    hidden_params = dumper.find_hidden_parameters()
    _save_json(output_dir / "svc-menu-hidden-params.json", hidden_params)
    console.print(f"  Found {len(hidden_params)} potentially hidden parameters")

    return {
        "categories": categories,
        "oled_params": oled_params,
        "hidden_params": hidden_params,
    }


def run_abl_profile(ssh: TVSSHClient, output_dir: Path):
    """Profile ABL behavior by measuring brightness response at various APL levels."""
    console.rule("[bold blue]ABL Behavior Profiling")

    profiler = ABLProfiler(ssh)

    console.print("[bold]Generating APL test patterns and measuring response...")
    console.print("  (This will display test patterns on the TV)")
    profile = profiler.profile_abl_curve()
    _save_json(output_dir / "abl-profile.json", profile)

    # Display summary table
    table = Table(title="ABL Profile (Brightness vs APL)")
    table.add_column("APL %", justify="right")
    table.add_column("Measured Brightness", justify="right")
    table.add_column("Expected (No ABL)", justify="right")
    table.add_column("ABL Reduction", justify="right")

    for point in profile.get("measurements", []):
        reduction = point.get("reduction_pct", "N/A")
        table.add_row(
            f"{point['apl_pct']}%",
            f"{point['measured_nits']} nits",
            f"{point['expected_nits']} nits",
            f"{reduction}%",
        )

    console.print(table)
    return profile


def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    console.print(f"  [dim]Saved to {path}[/dim]")


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(Panel.fit(
        "[bold red]LG CX48 ABL Recon Toolkit[/bold red]\n"
        f"Target: {args.tv_ip}:{args.tv_port}\n"
        f"Output: {output_dir}",
        title="lg-cx48-nodim",
    ))

    # Connect to TV
    console.print(f"\n[bold]Connecting to TV at {args.tv_ip}...")
    ssh = TVSSHClient(
        host=args.tv_ip,
        port=args.tv_port,
        username=args.tv_user,
        password=args.tv_password,
        key_path=args.ssh_key,
    )
    ssh.connect()
    console.print("[green]Connected![/green]")

    # Get basic TV info
    info = ssh.get_tv_info()
    _save_json(output_dir / "tv-info.json", info)
    console.print(f"  Model: {info.get('model', 'unknown')}")
    console.print(f"  webOS: {info.get('webos_version', 'unknown')}")
    console.print(f"  Firmware: {info.get('firmware', 'unknown')}")

    modules = args.modules
    run_all = "all" in modules

    results = {}

    if run_all or "luna" in modules:
        results["luna"] = run_luna_recon(ssh, output_dir)

    if run_all or "filesystem" in modules:
        results["filesystem"] = run_filesystem_recon(ssh, output_dir)

    if run_all or "service-menu" in modules:
        results["service_menu"] = run_service_menu_recon(ssh, output_dir)

    if run_all or "abl-profile" in modules:
        results["abl_profile"] = run_abl_profile(ssh, output_dir)

    # Summary
    console.rule("[bold green]Recon Complete")
    _save_json(output_dir / "recon-summary.json", results)
    console.print(f"\nAll results saved to [bold]{output_dir}[/bold]")
    console.print("Review the JSON files and look for ABL-related parameters.")
    console.print("\nKey files to examine first:")
    console.print("  - luna-abl-params.json (any ABL parameters found in luna services)")
    console.print("  - svc-menu-hidden-params.json (undocumented service menu entries)")
    console.print("  - fs-tcon-files.json (T-CON firmware and config files)")
    console.print("  - fs-hardware-interfaces.json (I2C/SPI interfaces to T-CON)")

    ssh.close()


if __name__ == "__main__":
    main()
