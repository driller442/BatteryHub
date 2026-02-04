# BatteryHub 🔋

**Universal Battery Management System Monitor** - Real-time monitoring for multiple BMS types!

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![BMS Support](https://img.shields.io/badge/BMS-JBD%20%7C%20Daly%20%7C%20ANT-green.svg)](https://github.com/driller44/batteryhub)

> 🎯 **Monitor your battery in real-time with a beautiful web dashboard!**

## ✨ Features

- 🔌 **Multi-BMS Support** - JBD, Daly, ANT, Overkill Solar, Xiaoxiang
- 📊 **Real-Time Monitoring** - Voltage, Current, SOC, Temperature, Power
- 📱 **Cell Voltage Tracking** - Individual cell monitoring with delta calculation
- 🌐 **Web Dashboard** - Responsive interface at http://localhost:5000
- 📈 **Historical Graphs** - Interactive 24-hour charts with Chart.js
- 💾 **CSV Data Logging** - Automatic logging for external analysis
- ⚡ **Efficient BLE Protocol** - Notification-based (low power, fast updates)

## 🚀 Quick Start

```bash
git clone https://github.com/driller44/batteryhub.git
cd BatteryHub
pip install -r requirements.txt
python monitor.py
Open http://localhost:5000 in your browser!

📋 Supported BMS Hardware
BrandModelsStatus
JBDDP04S007, SP04S028, etc.✅ Fully Tested
Overkill SolarAll JBD chipset models✅ Compatible
XiaoxiangSmart BMS series✅ Compatible
DalySmart BMS with Bluetooth⚠️ Experimental
ANTLifepo4 BMS⚠️ Experimental
Hardware Tested
✅ JBD BMS DP04S007L4S100A (4S 100A) - Confirmed Working

🔧 Configuration
Edit config.json with your BMS MAC address:

json
{
  "user_config": {
    "mac_address": "A5:C2:37:3D:2D:93",
    "selected_profile": "JBD_Standard"
  }
}
🐛 Troubleshooting
BMS Not Found?

Ensure BMS is powered on

Connect a load to wake from sleep

Check Bluetooth is enabled

Getting Zeros?

BMS in sleep mode - connect load/charger

Power cycle the BMS

🤝 Contributing
Contributions welcome! See CONTRIBUTING.md

Report bugs

Add BMS profiles

Submit pull requests

📄 License
MIT License - see LICENSE file for details.

⭐ Support This Project
If BatteryHub is useful to you:

⭐ Star this repository

📣 Share with the DIY battery community

🐛 Report bugs or suggest features

🤝 Contribute code or documentation

Made with ❤️ for the DIY solar and battery enthusiast community

---

## ?? Platform-Specific Bluetooth Notes

### Docker Deployment

**Windows/macOS:**
- ?? Bluetooth is NOT accessible in Docker containers
- Web interface loads but shows "Disconnected" status  
- **Solution**: Run natively with `python monitor.py` for development

**Linux/Raspberry Pi:**
- ? Full Bluetooth support in Docker
- **Recommended** for 24/7 production monitoring
- Deploy on a Raspberry Pi placed near your battery bank

### Native Python

- ? Full Bluetooth support on all platforms (Windows/Linux/macOS)
- Best for development and local testing
- Run with: `python monitor.py`
