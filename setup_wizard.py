#!/usr/bin/env python3
"""
BatteryHub Setup Wizard
Auto-detects BMS type and configures config.json
"""

import json
import asyncio
import sys
from bleak import BleakScanner, BleakClient

BANNER = """
═══════════════════════════════════════════════════════════════
  🔋 BATTERYHUB SETUP WIZARD
  Automatic BMS Detection & Configuration
═══════════════════════════════════════════════════════════════
"""

print(BANNER)

# Load config
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print("❌ config.json not found!")
    print("Please run this from the BatteryHub directory.")
    sys.exit(1)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 1: Scan for BLE devices
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("\n━━━ Step 1: Scanning for BLE Devices ━━━\n")
print("Scanning for 10 seconds...\n")

async def scan_devices():
    return await BleakScanner.discover(timeout=10.0)

try:
    devices = asyncio.run(scan_devices())
except Exception as e:
    print(f"❌ Scan failed: {e}")
    print("\nTroubleshooting:")
    print("  • Check Bluetooth is enabled")
    print("  • Run as administrator (Windows)")
    print("  • Install bluez (Linux)")
    sys.exit(1)

if not devices:
    print("❌ No BLE devices found!")
    print("\nTroubleshooting:")
    print("  • Check BMS is powered on")
    print("  • Ensure battery has load connected")
    print("  • Move closer to BMS (< 3 meters)")
    sys.exit(1)

print(f"Found {len(devices)} BLE devices:\n")
for i, device in enumerate(devices, 1):
    name = device.name if device.name else "Unknown"
    rssi = f" (RSSI: {device.rssi})" if hasattr(device, 'rssi') else ""
    print(f"  [{i}] {device.address} - {name}{rssi}")

# Select device
print("\n")
while True:
    try:
        choice = input("Enter device number to configure (or 'q' to quit): ")
        if choice.lower() == 'q':
            sys.exit(0)
        selected_idx = int(choice) - 1
        if 0 <= selected_idx < len(devices):
            break
        print("Invalid selection, try again.")
    except ValueError:
        print("Please enter a number.")

selected_device = devices[selected_idx]
print(f"\n✓ Selected: {selected_device.address} ({selected_device.name})\n")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 2: Auto-detect BMS type
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("━━━ Step 2: Detecting BMS Type ━━━\n")

async def test_profile(address, profile):
    """Test a single BMS profile"""
    try:
        async with BleakClient(address, timeout=5.0) as client:
            # Test notification-based
            if profile['protocol'] == 'notification':
                data_received = None
                
                def handler(sender, data):
                    nonlocal data_received
                    data_received = data
                
                try:
                    await client.start_notify(profile['characteristic_uuid'], handler)
                    await client.write_gatt_char(
                        profile['characteristic_uuid'],
                        bytes.fromhex(profile['command'])
                    )
                    await asyncio.sleep(1)
                    await client.stop_notify(profile['characteristic_uuid'])
                    
                    if data_received and len(data_received) >= profile['response_length']:
                        return True, len(data_received), data_received.hex()
                except:
                    pass
            
            # Test read-based
            elif profile['protocol'] == 'read':
                try:
                    await client.write_gatt_char(
                        profile['characteristic_uuid'],
                        bytes.fromhex(profile['command'])
                    )
                    await asyncio.sleep(0.5)
                    response = await client.read_gatt_char(profile['characteristic_uuid'])
                    
                    if len(response) >= profile['response_length']:
                        return True, len(response), response.hex()
                except:
                    pass
                    
    except Exception:
        pass
    
    return False, 0, ""

# Test each profile
results = {}
for profile_name, profile in config['bms_profiles'].items():
    print(f"Testing {profile['name']}... ", end='', flush=True)
    success, length, data = asyncio.run(test_profile(selected_device.address, profile))
    
    if success:
        print(f"✓ WORKS! ({length} bytes)")
        results[profile_name] = {'length': length, 'data': data}
    else:
        print("✗ No response")

if not results:
    print("\n❌ Could not detect BMS type automatically!")
    print("\nYou can manually configure config.json:")
    print(f"  - Set mac_address to: {selected_device.address}")
    print(f"  - Try different profiles or add your own")
    sys.exit(1)

# Select best match
best_profile = list(results.keys())[0]
print(f"\n✓ Detected: {config['bms_profiles'][best_profile]['name']}\n")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 3: Save configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("━━━ Step 3: Save Configuration ━━━\n")

config['user_config']['mac_address'] = selected_device.address
config['user_config']['device_name'] = selected_device.name if selected_device.name else "Unknown BMS"
config['user_config']['selected_profile'] = best_profile

with open('config.json', 'w') as f:
    json.dump(config, f, indent=2)

print("✓ Configuration saved to config.json\n")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Summary
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("═══════════════════════════════════════════════════════════════")
print("  ✅ SETUP COMPLETE!")
print("═══════════════════════════════════════════════════════════════\n")
print(f"BMS Type:    {config['bms_profiles'][best_profile]['name']}")
print(f"MAC Address: {selected_device.address}")
print(f"Device Name: {selected_device.name}\n")
print("Next steps:")
print("  1. Review config.json if needed")
print("  2. Run: python monitor.py")
print("  3. Open: http://localhost:5000\n")
