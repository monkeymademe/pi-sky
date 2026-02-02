#!/usr/bin/env python3
"""
Analyze ADS-B receiver performance and suggest range improvements
"""

import json
import requests
import sys
from datetime import datetime, timedelta

def load_config():
    """Load configuration"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

def get_dump1090_stats():
    """Get stats from dump1090"""
    try:
        with open('/run/dump1090-fa/stats.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading stats: {e}")
        return None

def get_aircraft_data():
    """Get current aircraft data"""
    try:
        with open('/run/dump1090-fa/aircraft.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading aircraft data: {e}")
        return None

def calculate_snr(signal_db, noise_db):
    """Calculate Signal-to-Noise Ratio"""
    if signal_db is None or noise_db is None:
        return None
    return signal_db - noise_db

def analyze_performance(stats, aircraft_data):
    """Analyze receiver performance"""
    print("=" * 80)
    print("ADS-B RECEIVER RANGE ANALYSIS")
    print("=" * 80)
    print()
    
    if not stats:
        print("❌ Could not read dump1090 stats")
        return
    
    last1min = stats.get('last1min', {})
    last5min = stats.get('last5min', {})
    last15min = stats.get('last15min', {})
    local = last1min.get('local', {})
    
    # Signal metrics
    signal_db = local.get('signal')
    noise_db = local.get('noise')
    peak_signal = local.get('peak_signal')
    gain_db = local.get('gain_db')
    
    print("📡 SIGNAL QUALITY METRICS")
    print("-" * 80)
    print(f"  Signal Level:      {signal_db:.1f} dBFS" if signal_db else "  Signal Level:      N/A")
    print(f"  Noise Floor:        {noise_db:.1f} dBFS" if noise_db else "  Noise Floor:        N/A")
    print(f"  Peak Signal:        {peak_signal:.1f} dBFS" if peak_signal else "  Peak Signal:        N/A")
    
    if signal_db and noise_db:
        snr = calculate_snr(signal_db, noise_db)
        print(f"  Signal-to-Noise:    {snr:.1f} dB" if snr else "  Signal-to-Noise:    N/A")
    
    print(f"  Current Gain:       {gain_db:.1f} dB" if gain_db else "  Current Gain:       N/A")
    print()
    
    # Message statistics
    print("📊 MESSAGE STATISTICS")
    print("-" * 80)
    print(f"  Messages (1 min):   {last1min.get('messages', 0)}")
    print(f"  Messages (5 min):   {last5min.get('messages', 0)}")
    print(f"  Messages (15 min):  {last15min.get('messages', 0)}")
    print()
    
    # Track statistics
    tracks_1min = last1min.get('tracks', {})
    tracks_5min = last5min.get('tracks', {})
    tracks_15min = last15min.get('tracks', {})
    
    print("✈️  AIRCRAFT TRACKING")
    print("-" * 80)
    print(f"  Tracks (1 min):     {tracks_1min.get('all', 0)}")
    print(f"  Tracks (5 min):     {tracks_5min.get('all', 0)}")
    print(f"  Tracks (15 min):    {tracks_15min.get('all', 0)}")
    print(f"  Single message:     {tracks_1min.get('single_message', 0)}")
    print(f"  Unreliable:         {tracks_1min.get('unreliable', 0)}")
    print()
    
    # Current aircraft
    if aircraft_data:
        aircraft_count = len(aircraft_data.get('aircraft', []))
        print(f"  Currently tracking: {aircraft_count} aircraft")
        if aircraft_count > 0:
            print()
            print("  Current aircraft:")
            for ac in aircraft_data.get('aircraft', [])[:5]:  # Show first 5
                hex_code = ac.get('hex', 'Unknown')
                callsign = ac.get('flight', 'N/A')
                seen = ac.get('seen', 0)
                rssi = ac.get('rssi', 0)
                print(f"    {callsign:12} ({hex_code}) - Seen: {seen:.1f}s ago, RSSI: {rssi:.1f} dB")
        print()
    
    # Message quality
    accepted = local.get('accepted', [0, 0])
    bad = local.get('bad', 0)
    modes = local.get('modes', 0)
    
    if modes > 0:
        bad_percent = (bad / modes) * 100
        print("🔍 MESSAGE QUALITY")
        print("-" * 80)
        print(f"  Total messages:     {modes:,}")
        print(f"  Bad messages:       {bad:,} ({bad_percent:.1f}%)")
        print(f"  Accepted (DF11):    {accepted[0]}")
        print(f"  Accepted (DF17):   {accepted[1]}")
        print()
    
    # Range recommendations
    print("=" * 80)
    print("💡 RANGE IMPROVEMENT RECOMMENDATIONS")
    print("=" * 80)
    print()
    
    recommendations = []
    
    # Signal strength analysis
    if signal_db and signal_db > -10:
        recommendations.append(("⚠️  Signal may be too strong (saturation risk)", 
                                "Consider reducing gain or adding attenuation"))
    elif signal_db and signal_db < -20:
        recommendations.append(("📡 Weak signal detected", 
                                "Improve antenna placement or use higher gain antenna"))
    
    # SNR analysis
    if signal_db and noise_db:
        snr = calculate_snr(signal_db, noise_db)
        if snr and snr < 10:
            recommendations.append(("🔇 Low Signal-to-Noise Ratio", 
                                    "Consider: 1) Better antenna location, 2) 1090 MHz bandpass filter, 3) Lower loss cable"))
        elif snr and snr > 20:
            recommendations.append(("✅ Excellent SNR", 
                                    "Signal quality is good - focus on antenna height for range"))
    
    # Message quality
    if modes > 0:
        bad_percent = (bad / modes) * 100
        if bad_percent > 20:
            recommendations.append(("⚠️  High message error rate", 
                                    "Check: 1) Cable connections, 2) Interference sources, 3) Antenna mounting"))
    
    # Track reliability
    if tracks_1min.get('unreliable', 0) > tracks_1min.get('all', 0) * 0.5:
        recommendations.append(("⚠️  Many unreliable tracks", 
                                "Improve signal quality - consider antenna upgrade or better location"))
    
    # General recommendations
    recommendations.append(("📡 Antenna Height", 
                            "Raise antenna as high as possible - each meter adds ~2-3 km range"))
    recommendations.append(("🔌 Cable Quality", 
                            "Use low-loss cable (LMR-400) and minimize length - every 3dB loss halves range"))
    recommendations.append(("🎯 1090 MHz Filter", 
                            "Add bandpass filter to reduce interference and improve sensitivity"))
    recommendations.append(("📍 Location", 
                            "Place antenna with clear line of sight, away from obstructions"))
    
    if recommendations:
        for i, (title, desc) in enumerate(recommendations, 1):
            print(f"{i}. {title}")
            print(f"   {desc}")
            print()
    else:
        print("✅ Receiver performance looks good!")
        print("   Focus on antenna height and location for maximum range.")
        print()
    
    # Estimated range
    print("=" * 80)
    print("📏 ESTIMATED RANGE")
    print("=" * 80)
    print()
    
    # Rough range estimation based on signal quality
    if signal_db and noise_db:
        snr = calculate_snr(signal_db, noise_db)
        if snr:
            # Very rough estimate: good SNR = better range
            if snr > 20:
                est_range = "200-400 km (excellent conditions)"
            elif snr > 15:
                est_range = "150-300 km (good conditions)"
            elif snr > 10:
                est_range = "100-200 km (moderate conditions)"
            else:
                est_range = "50-150 km (limited by SNR)"
            
            print(f"  Estimated Range:    {est_range}")
            print(f"  (Based on SNR: {snr:.1f} dB)")
            print()
            print("  Note: Actual range depends heavily on:")
            print("    - Antenna height above ground")
            print("    - Terrain and obstructions")
            print("    - Aircraft altitude")
            print("    - Atmospheric conditions")
            print()

def main():
    """Main function"""
    print()
    stats = get_dump1090_stats()
    aircraft_data = get_aircraft_data()
    
    analyze_performance(stats, aircraft_data)
    
    print("=" * 80)
    print(f"Analysis completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

if __name__ == '__main__':
    main()
