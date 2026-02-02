#!/usr/bin/env python3
"""
View raw dump1090-fa output - monitors the JSON files it writes directly
"""

import json
import os
import sys
import time
from datetime import datetime

def clear_screen():
    """Clear the terminal screen"""
    os.system('clear' if os.name != 'nt' else 'cls')

def read_aircraft_json(path):
    """Read aircraft.json file"""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None

def main():
    """Main function"""
    # dump1090-fa writes to /run/dump1090-fa/aircraft.json
    json_path = '/run/dump1090-fa/aircraft.json'
    
    print(f"Monitoring dump1090-fa raw output from: {json_path}")
    print("Press Ctrl+C to stop")
    print("=" * 80)
    time.sleep(2)
    
    try:
        while True:
            data = read_aircraft_json(json_path)
            
            # Clear screen for fresh output
            clear_screen()
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"Timestamp: {timestamp}")
            print(f"File: {json_path}")
            
            # Check if file exists
            if os.path.exists(json_path):
                file_size = os.path.getsize(json_path)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(json_path)).strftime('%H:%M:%S')
                print(f"File size: {file_size} bytes | Last modified: {file_mtime}")
            else:
                print("File does not exist!")
            
            print("=" * 80)
            print()
            
            if data is None:
                print("ERROR: Could not read aircraft.json")
                print("(File may not exist or may be invalid JSON)")
            else:
                # Print raw JSON
                print(json.dumps(data, indent=2))
            
            print()
            print("=" * 80)
            print("Updating every second... (Ctrl+C to stop)")
            
            time.sleep(1)  # Update every second
            
    except KeyboardInterrupt:
        clear_screen()
        print("\nStopped by user")
        sys.exit(0)

if __name__ == '__main__':
    main()
