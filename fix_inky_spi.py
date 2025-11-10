#!/usr/bin/env python3
"""
Helper script to check and fix SPI configuration for Inky displays

This script checks if the SPI configuration is correct for Inky displays
and provides instructions or can automatically add the required overlay.
"""

import sys
import os
import subprocess

CONFIG_FILE = "/boot/firmware/config.txt"
REQUIRED_OVERLAY = "dtoverlay=spi0-0cs"


def check_config():
    """Check if the SPI overlay is configured correctly"""
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Config file not found: {CONFIG_FILE}")
        print("This script is designed for Raspberry Pi OS.")
        return False
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            content = f.read()
        
        # Check if the overlay is already present
        if REQUIRED_OVERLAY in content:
            print("✓ SPI overlay is already configured correctly!")
            print(f"  Found: {REQUIRED_OVERLAY}")
            return True
        else:
            print("✗ SPI overlay is missing!")
            print(f"  Required: {REQUIRED_OVERLAY}")
            return False
            
    except PermissionError:
        print(f"Error: Cannot read {CONFIG_FILE}")
        print("This script needs to be run with sudo to read the config file.")
        return False
    except Exception as e:
        print(f"Error reading config file: {e}")
        return False


def suggest_fix():
    """Print instructions to fix the configuration"""
    print("\n" + "=" * 60)
    print("HOW TO FIX THE SPI CONFIGURATION")
    print("=" * 60)
    print("\n1. Edit the configuration file:")
    print(f"   sudo nano {CONFIG_FILE}")
    print("\n2. Add this line at the end of the file:")
    print(f"   {REQUIRED_OVERLAY}")
    print("\n3. Save and exit (Ctrl+X, then Y, then Enter)")
    print("\n4. Reboot your Raspberry Pi:")
    print("   sudo reboot")
    print("\n5. After reboot, try running display_inky.py again")
    print("=" * 60)


def auto_fix():
    """Automatically add the overlay to the config file"""
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Config file not found: {CONFIG_FILE}")
        return False
    
    try:
        # Read current content
        with open(CONFIG_FILE, 'r') as f:
            lines = f.readlines()
        
        # Check if already present
        if any(REQUIRED_OVERLAY in line for line in lines):
            print("✓ Overlay is already present in config file")
            return True
        
        # Check if there's a comment or blank line at the end
        # Add the overlay after the last non-empty line
        with open(CONFIG_FILE, 'a') as f:
            # Add a blank line if the last line doesn't end with newline
            if lines and not lines[-1].endswith('\n'):
                f.write('\n')
            f.write(f"{REQUIRED_OVERLAY}\n")
        
        print(f"✓ Added {REQUIRED_OVERLAY} to {CONFIG_FILE}")
        print("\n⚠️  IMPORTANT: You must reboot for changes to take effect:")
        print("   sudo reboot")
        return True
        
    except PermissionError:
        print(f"Error: Cannot write to {CONFIG_FILE}")
        print("This script must be run with sudo to modify the config file.")
        print("\nRun it like this:")
        print("  sudo python3 fix_inky_spi.py --fix")
        return False
    except Exception as e:
        print(f"Error modifying config file: {e}")
        return False


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Check and fix SPI configuration for Inky displays',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Automatically add the required overlay to config.txt (requires sudo)'
    )
    
    args = parser.parse_args()
    
    print("Inky SPI Configuration Checker")
    print("=" * 60)
    
    if args.fix:
        print("\nAttempting to automatically fix configuration...")
        if auto_fix():
            return 0
        else:
            suggest_fix()
            return 1
    else:
        is_ok = check_config()
        if not is_ok:
            suggest_fix()
            print("\nTo automatically fix, run:")
            print("  sudo python3 fix_inky_spi.py --fix")
            return 1
        return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

