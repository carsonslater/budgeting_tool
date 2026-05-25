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
SOURCE_ICON_PNG = Path("/Users/carson/.gemini/antigravity-ide/brain/fa40cd80-b267-4083-917a-ba45ebe76863/budget_icon_white_1779725519009.png")
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
LOG_FILE="$PROJECT_DIR/launcher_error.log"

# Navigate to project directory
cd "$PROJECT_DIR" || {{
  osascript -e 'display dialog "Could not navigate to project folder '$PROJECT_DIR'." buttons {{"OK"}} default button "OK" with icon stop'
  exit 1
}}

# Check if .venv exists
if [ ! -d ".venv" ]; then
  osascript -e 'display dialog "Virtual environment (.venv) not found. Please set up the environment before running." buttons {{"OK"}} default button "OK" with icon stop'
  exit 1
fi

# Check if frontend is built, if not, build it
if [ ! -d "web/dist" ]; then
  osascript -e 'display dialog "Frontend build not found. Building the React interface (this may take a few seconds)..." buttons {{"OK"}} default button "OK" with icon note'
  
  # Set common path variables to locate npm
  export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
  
  if command -v npm &> /dev/null; then
    cd web
    npm install && npm run build
    BUILD_STATUS=$?
    cd ..
    if [ $BUILD_STATUS -ne 0 ]; then
      osascript -e 'display dialog "Failed to build the frontend. Please run npm run build inside the web/ directory manually to inspect the error." buttons {{"OK"}} default button "OK" with icon stop'
      exit 1
    fi
  else
    osascript -e 'display dialog "npm is not installed or not in PATH. Please run npm run build inside the web/ directory manually." buttons {{"OK"}} default button "OK" with icon stop'
    exit 1
  fi
fi

# Launch the desktop app using the virtual environment python interpreter
# Redirect output to launcher_error.log in case of troubleshooting
./.venv/bin/python desktop_app.py > "$LOG_FILE" 2>&1

# Check exit code
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
  osascript -e 'display dialog "Household Budgeting failed to start. Error code: '$EXIT_CODE'.\nCheck logs at: '$LOG_FILE'" buttons {{"OK"}} default button "OK" with icon stop'
  exit $EXIT_CODE
fi
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
