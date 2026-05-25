#!/usr/bin/env python3
"""
Build script for creating a premium macOS desktop launcher (.app bundle)
for the Household Budgeting application.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Paths
PROJECT_DIR = Path("/Users/carson/Documents/R_Projects/budgeting_tool").resolve()
SOURCE_ICON_PNG = PROJECT_DIR / "resources" / "app_icon_white_circle.png"
APP_BUNDLE_NAME = "Household Budgeting.app"
APP_BUNDLE_PATH = PROJECT_DIR / APP_BUNDLE_NAME
DESKTOP_PATH = Path("/Users/carson/Desktop") / APP_BUNDLE_NAME


def print_step(msg: str):
    print(f"\n==> \033[1;34m{msg}\033[0m")


def print_success(msg: str):
    print(f"\033[1;32m✓ {msg}\033[0m")


def print_error(msg: str):
    print(f"\033[1;31m✗ {msg}\033[0m", file=sys.stderr)


def create_directory_structure():
    print_step("Creating application bundle directory structure...")
    
    # If the old bundle exists, remove it
    if APP_BUNDLE_PATH.exists():
        shutil.rmtree(APP_BUNDLE_PATH)
        
    # Create structure
    macos_dir = APP_BUNDLE_PATH / "Contents" / "MacOS"
    resources_dir = APP_BUNDLE_PATH / "Contents" / "Resources"
    
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)
    
    print_success("Created directory structure:")
    print(f"  {APP_BUNDLE_PATH}")


def generate_icns():
    print_step("Generating Retina-compatible AppIcon.icns...")
    
    if not SOURCE_ICON_PNG.exists():
        print_error(f"Source PNG not found at {SOURCE_ICON_PNG}")
        sys.exit(1)
        
    iconset_dir = PROJECT_DIR / "AppIcon.iconset"
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir(parents=True)
    
    # Define sizes and filenames for the iconset
    icon_sizes = [
        ("16x16", 16),
        ("16x16@2x", 32),
        ("32x32", 32),
        ("32x32@2x", 64),
        ("128x128", 128),
        ("128x128@2x", 256),
        ("256x256", 256),
        ("256x256@2x", 512),
        ("512x512", 512),
        ("512x512@2x", 1024)
    ]
    
    # Use macOS sips tool to resize the source PNG and ensure true PNG format
    for name, size in icon_sizes:
        dest_png = iconset_dir / f"icon_{name}.png"
        cmd = [
            "sips",
            "-s", "format", "png",
            "-z", str(size), str(size),
            str(SOURCE_ICON_PNG),
            "--out", str(dest_png)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print_error(f"sips failed for {name}: {result.stderr}")
        
    # Compile iconset using macOS iconutil directly into the app bundle resources
    icns_dest = APP_BUNDLE_PATH / "Contents" / "Resources" / "AppIcon.icns"
    result = subprocess.run([
        "iconutil",
        "--convert", "icns",
        "--output", str(icns_dest),
        str(iconset_dir)
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print_error(f"iconutil failed: {result.stderr}")
    
    # Clean up iconset directory only if successful
    if icns_dest.exists():
        shutil.rmtree(iconset_dir)
        print_success(f"Successfully compiled AppIcon.icns ({icns_dest.stat().st_size} bytes)")
    else:
        print_error("Failed to generate AppIcon.icns. Leaving AppIcon.iconset for debugging.")
        sys.exit(1)


def write_info_plist():
    print_step("Writing Info.plist configuration...")
    
    plist_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>English</string>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.budgeting.household</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Household Budgeting</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>2.0.0</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleVersion</key>
    <string>2.0.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13.0</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>LSBackgroundOnly</key>
    <false/>
</dict>
</plist>
"""
    plist_path = APP_BUNDLE_PATH / "Contents" / "Info.plist"
    plist_path.write_text(plist_content, encoding="utf-8")
    print_success("Wrote Contents/Info.plist")


def write_launcher_script():
    print_step("Creating robust launcher script...")
    
    launcher_content = f"""#!/bin/bash

# Define project path
PROJECT_DIR="{PROJECT_DIR}"

# Launch the python script inside the native macOS Terminal application.
# This bypasses all Finder/Launch Services sandboxing restrictions and inherits
# Terminal's standard directory access permissions (Files and Folders).
osascript -e "tell application \\"Terminal\\"
    activate
    do script \\"cd '$PROJECT_DIR' && .venv/bin/python desktop_app.py; exit\\"
end tell"
"""
    
    launcher_path = APP_BUNDLE_PATH / "Contents" / "MacOS" / "launcher"
    launcher_path.write_text(launcher_content, encoding="utf-8")
    
    # Make launcher executable
    launcher_path.chmod(0o755)
    print_success("Wrote and permissioned Contents/MacOS/launcher")


def deploy_to_desktop():
    print_step("Deploying Application to Desktop...")
    
    if DESKTOP_PATH.exists():
        shutil.rmtree(DESKTOP_PATH)
        
    shutil.copytree(APP_BUNDLE_PATH, DESKTOP_PATH)
    
    # Touch, register with Launch Services, and perform rename cycle to force Finder cache reload on both copies
    try:
        lsregister_path = "/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"
        
        for path in [APP_BUNDLE_PATH, DESKTOP_PATH]:
            if path.exists():
                subprocess.run(["touch", str(path)], check=True)
                if os.path.exists(lsregister_path):
                    subprocess.run([lsregister_path, "-f", str(path)], check=True)
                    
                # Rename cycle to trigger Finder's directory observer to refresh the bundle icon
                temp_path = path.parent / f"{path.name} Temp"
                os.rename(path, temp_path)
                import time
                time.sleep(0.5)
                os.rename(temp_path, path)
                
        subprocess.run(["killall", "Finder"], stderr=subprocess.DEVNULL)
    except Exception:
        pass
        
    print_success(f"Successfully copied launcher to Desktop: {DESKTOP_PATH}")


def main():
    print_step("Starting macOS App Bundle compilation...")
    create_directory_structure()
    generate_icns()
    write_info_plist()
    write_launcher_script()
    deploy_to_desktop()
    print_success("Application Bundle generated successfully! Double-click 'Household Budgeting' on your Desktop to run.")


if __name__ == "__main__":
    main()
