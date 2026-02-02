#!/usr/bin/env python3
"""
Simple script to continuously view raw dump1090 aircraft data output
"""

import requests
import json
import sys
import time
import os
from datetime import datetime

def load_config():
    """Load configuration from config.json"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: config.json not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config.json: {e}")
        sys.exit(1)

def get_dump1090_data(dump1090_url):
    """Fetch data from dump1090"""
    try:
        response = requests.get(dump1090_url, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return None

def clear_screen():
    """Clear the terminal screen"""
    os.system('clear' if os.name != 'nt' else 'cls')

def main():
    """Main function"""
    config = load_config()
    dump1090_url = config.get('dump1090_url', 'http://localhost:8080/data/aircraft.json')
    
    print(f"Monitoring dump1090 at: {dump1090_url}")
    print("Press Ctrl+C to stop")
    print("=" * 80)
    time.sleep(2)
    
    try:
        while True:
            data = get_dump1090_data(dump1090_url)
            
            # Clear screen for fresh output
            clear_screen()
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"Timestamp: {timestamp}")
            print(f"URL: {dump1090_url}")
            print("=" * 80)
            print()
            
            if data is None:
                print("ERROR: Could not fetch data from dump1090")
                print("(dump1090 may not be running or URL is incorrect)")
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
