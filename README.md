# BatteryHub 🔋

**Universal Battery Management System (BMS) Monitor** - One app to monitor ALL your batteries.

Real-time monitoring for JBD, Daly, Victron, and other Bluetooth BMS devices with beautiful web dashboard.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-production-brightgreen.svg)

---

## ✨ Features

- 🔌 **Real-time Bluetooth monitoring** - Connect to your BMS wirelessly
- 📊 **Beautiful web dashboard** - View data from any device on your network
- 📈 **Historical data logging** - CSV export with customizable time ranges
- 📱 **Mobile friendly** - Access from phone, tablet, or computer
- ⚡ **Live updates** - Auto-refresh every 60 seconds
- 🎨 **Interactive charts** - Voltage, current, SOC trending with Plotly

---

## 🚀 Quick Start

### 1. **Clone the Repository**
```bash
git clone https://github.com/driller442/BatteryHub.git
cd BatteryHub
2. Install Dependencies
bash
pip install -r requirements.txt
Required packages:

bleak - Bluetooth Low Energy communication

Flask - Web server

plotly - Interactive charts

pandas - Data handling

3. Configure Your BMS
Edit monitor.py and update your BMS MAC address:

python
# Line 13 - Change this to YOUR BMS Bluetooth MAC address
MAC_ADDRESS = "A5:C2:37:3D:2D:93"  # ← Replace with your BMS MAC
How to find your BMS MAC address:

Windows:

Open Settings → Bluetooth & devices

Find your BMS device (e.g., "JBD BMS DP04S007")

Click "More Bluetooth options" → Look for MAC address

Linux:

bash
sudo bluetoothctl
scan on
# Look for your BMS device and note the MAC address
Android: Use "BLE Scanner" app from Play Store

4. Run BatteryHub
bash
python monitor.py
5. Open Dashboard
Open your browser and go to:

Local: http://localhost:5000

Network: http://YOUR_IP:5000 (shown in console on startup)

📱 What You'll See
text
🌐 Web dashboard: http://localhost:5000

🔌 Connecting to JBD BMS DP04S007...
   MAC: A5:C2:37:3D:2D:93

✅ Connected!

 * Running on http://127.0.0.1:5000
 * Running on http://192.168.1.96:5000
Dashboard displays:

⚡ Voltage (V)

🔋 Current (A) - charging/discharging

📊 State of Charge (%)

🔢 Remaining Capacity (Ah)

🔁 Cycle Count

📈 Historical charts (1 hour to 1 year)

🔧 Supported BMS Types
Currently tested and working:

✅ JBD BMS (Smart BMS, Xiaoxiang BMS)

⚙️ Daly BMS (coming soon)

⚙️ Victron SmartShunt (coming soon)

Protocol: Notification-based async/await Bluetooth LE

📂 Project Structure
text
BatteryHub/
├── monitor.py          # Main application
├── requirements.txt    # Python dependencies
├── README.md          # This file
├── .gitignore         # Git ignore rules
└── battery_log.csv    # Generated data log (auto-created)
⚙️ Configuration
Edit these constants in monitor.py:

python
DEVICE_NAME = "JBD BMS DP04S007"  # Your BMS device name
MAC_ADDRESS = "A5:C2:37:3D:2D:93" # Your BMS MAC address
LOG_FILE = "battery_log.csv"      # Data log filename
INTERVAL = 60                      # Update interval (seconds)
CAPACITY_AH = 100                  # Battery capacity (Ah)
🛠️ Troubleshooting
"Cannot connect to BMS"
✅ Check BMS is powered on and Bluetooth enabled

✅ Verify MAC address is correct in monitor.py

✅ Ensure no other app is connected to BMS

✅ Try running as administrator (Windows)

"Module not found" errors
bash
# Reinstall dependencies
pip install -r requirements.txt --upgrade
"Port 5000 already in use"
✅ Another app is using port 5000

✅ Stop other Flask apps or change port in monitor.py

📊 Data Logging
Battery data is automatically saved to battery_log.csv:

text
Timestamp,Voltage,Current,SOC,Cycles,Remaining_Ah
2026-02-03 22:11:35,13.2,-5.4,85,42,85.0
Use this data for:

Long-term battery health analysis

Capacity degradation tracking

Charge/discharge pattern analysis

Excel/LibreOffice import

🤝 Contributing
Contributions welcome! Please:

Fork the repository

Create a feature branch

Test your changes

Submit a pull request

📜 License
MIT License - See LICENSE file for details

🙏 Acknowledgments
Built with Bleak - Bluetooth LE library

UI powered by Flask

Charts by Plotly

📬 Support
🐛 Issues: https://github.com/driller442/BatteryHub/issues

💬 Discussions: https://github.com/driller442/BatteryHub/discussions

Made with ❤️ for the battery monitoring community
