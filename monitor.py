import asyncio
from bleak import BleakClient
import struct
from datetime import datetime
import csv
import os
from pathlib import Path
from flask import Flask, render_template_string, jsonify
import threading
import pandas as pd

# === Configuration ===
DEVICE_NAME = "JBD BMS DP04S007"
MAC_ADDRESS = "A5:C2:37:3D:2D:93"
LOG_FILE = "battery_log.csv"
INTERVAL = 60
CAPACITY_AH = 100

app = Flask(__name__)
latest_data = {
    'voltage': '0.00',
    'current': '0.00',
    'soc': '0',
    'cycles': '0',
    'capacity': '0.0',
    'timestamp': 'Waiting for data...'
}
running = True

# Load last reading from CSV if exists
def load_last_reading():
    global latest_data
    if os.path.exists(LOG_FILE):
        try:
            df = pd.read_csv(LOG_FILE)
            if len(df) > 0:
                last = df.iloc[-1]
                latest_data = {
                    'voltage': f"{last['Voltage']:.2f}",
                    'current': f"{last['Current']:+.2f}",
                    'soc': str(int(last['SOC'])),
                    'cycles': str(int(last['Cycles'])),
                    'capacity': f"{last['Remaining_Ah']:.1f}",
                    'timestamp': last['Timestamp']
                }
                print(f"📊 Loaded last reading: {latest_data['timestamp']}")
        except Exception as e:
            print(f"⚠️  Could not load last reading: {e}")

# === HTML Template ===
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>DC House Battery Monitor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            text-align: center;
        }
        h1 { font-size: 2em; margin-bottom: 10px; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: rgba(255,255,255,0.15);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        .stat-value { font-size: 2.2em; font-weight: bold; margin: 10px 0; }
        .stat-label { font-size: 0.9em; opacity: 0.9; text-transform: uppercase; }
        
        .time-controls {
            background: rgba(255,255,255,0.15);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 20px;
            text-align: center;
        }
        .time-controls h3 { margin-bottom: 10px; font-size: 1.1em; }
        .btn-group {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            justify-content: center;
        }
        .time-btn {
            background: rgba(255,255,255,0.2);
            border: 2px solid rgba(255,255,255,0.3);
            color: white;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        .time-btn:hover {
            background: rgba(255,255,255,0.3);
            transform: translateY(-2px);
        }
        .time-btn.active {
            background: rgba(255,255,255,0.4);
            border-color: rgba(255,255,255,0.6);
            box-shadow: 0 4px 15px rgba(255,255,255,0.3);
        }
        
        .chart-container {
            background: rgba(255,255,255,0.15);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .chart-title { font-size: 1.2em; margin-bottom: 15px; text-align: center; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔋 DC House Battery Monitor</h1>
            <div id="timestamp"></div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Voltage</div>
                <div class="stat-value" id="voltage">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Current</div>
                <div class="stat-value" id="current">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">State of Charge</div>
                <div class="stat-value" id="soc">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Capacity</div>
                <div class="stat-value" id="capacity">--</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Cycles</div>
                <div class="stat-value" id="cycles">--</div>
            </div>
        </div>

        <div class="time-controls">
            <h3>📊 Time Range</h3>
            <div class="btn-group">
                <button class="time-btn" onclick="changeTimeRange(1)">1 Hour</button>
                <button class="time-btn" onclick="changeTimeRange(6)">6 Hours</button>
                <button class="time-btn" onclick="changeTimeRange(12)">12 Hours</button>
                <button class="time-btn active" onclick="changeTimeRange(24)">24 Hours</button>
                <button class="time-btn" onclick="changeTimeRange(168)">1 Week</button>
                <button class="time-btn" onclick="changeTimeRange(720)">1 Month</button>
                <button class="time-btn" onclick="changeTimeRange(8760)">1 Year</button>
                <button class="time-btn" onclick="changeTimeRange(0)">All Time</button>
            </div>
        </div>
        
        <div class="chart-container">
            <div class="chart-title">Voltage Over Time</div>
            <div id="voltage-chart"></div>
        </div>
        
        <div class="chart-container">
            <div class="chart-title">Current Over Time</div>
            <div id="current-chart"></div>
        </div>
        
        <div class="chart-container">
            <div class="chart-title">State of Charge</div>
            <div id="soc-chart"></div>
        </div>
    </div>

    <script>
        let currentRange = 24;
        
        function changeTimeRange(hours) {
            currentRange = hours;
            document.querySelectorAll('.time-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            updateCharts();
        }
        
        function updateCharts() {
            fetch('/api/data?hours=' + currentRange)
                .then(response => response.json())
                .then(data => {
                    if (data.timestamps && data.timestamps.length > 0) {
                        Plotly.newPlot('voltage-chart', [{
                            x: data.timestamps,
                            y: data.voltage,
                            type: 'scatter',
                            mode: 'lines',
                            line: { color: '#4ade80', width: 3 },
                            fill: 'tozeroy',
                            fillcolor: 'rgba(74, 222, 128, 0.2)'
                        }], {
                            paper_bgcolor: 'rgba(0,0,0,0)',
                            plot_bgcolor: 'rgba(0,0,0,0)',
                            font: { color: '#fff' },
                            xaxis: { gridcolor: 'rgba(255,255,255,0.1)' },
                            yaxis: { gridcolor: 'rgba(255,255,255,0.1)', title: 'Voltage (V)' },
                            margin: { t: 10, r: 20, b: 40, l: 50 }
                        }, {responsive: true});
                        
                        Plotly.newPlot('current-chart', [{
                            x: data.timestamps,
                            y: data.current,
                            type: 'scatter',
                            mode: 'lines',
                            line: { color: '#fbbf24', width: 3 },
                            fill: 'tozeroy',
                            fillcolor: 'rgba(251, 191, 36, 0.2)'
                        }], {
                            paper_bgcolor: 'rgba(0,0,0,0)',
                            plot_bgcolor: 'rgba(0,0,0,0)',
                            font: { color: '#fff' },
                            xaxis: { gridcolor: 'rgba(255,255,255,0.1)' },
                            yaxis: { gridcolor: 'rgba(255,255,255,0.1)', title: 'Current (A)' },
                            margin: { t: 10, r: 20, b: 40, l: 50 }
                        }, {responsive: true});
                        
                        Plotly.newPlot('soc-chart', [{
                            x: data.timestamps,
                            y: data.soc,
                            type: 'scatter',
                            mode: 'lines',
                            line: { color: '#60a5fa', width: 3 },
                            fill: 'tozeroy',
                            fillcolor: 'rgba(96, 165, 250, 0.2)'
                        }], {
                            paper_bgcolor: 'rgba(0,0,0,0)',
                            plot_bgcolor: 'rgba(0,0,0,0)',
                            font: { color: '#fff' },
                            xaxis: { gridcolor: 'rgba(255,255,255,0.1)' },
                            yaxis: { gridcolor: 'rgba(255,255,255,0.1)', title: 'SOC (%)', range: [0, 100] },
                            margin: { t: 10, r: 20, b: 40, l: 50 }
                        }, {responsive: true});
                    }
                });
        }
        
        function updateLiveData() {
            fetch('/api/latest')
                .then(response => response.json())
                .then(data => {
                    if (data && data.voltage) {
                        document.getElementById('voltage').textContent = data.voltage + 'V';
                        document.getElementById('current').textContent = data.current + 'A';
                        document.getElementById('soc').textContent = data.soc + '%';
                        document.getElementById('capacity').textContent = data.capacity + 'Ah';
                        document.getElementById('cycles').textContent = data.cycles;
                        document.getElementById('timestamp').textContent = '📅 ' + data.timestamp;
                    }
                });
        }
        
        updateCharts();
        updateLiveData();
        setInterval(() => {
            updateCharts();
            updateLiveData();
        }, 60000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/latest')
def api_latest():
    return jsonify(latest_data)

@app.route('/api/data')
def api_data():
    from flask import request
    hours = request.args.get('hours', type=int, default=24)
    
    if not os.path.exists(LOG_FILE):
        return jsonify({'timestamps': [], 'voltage': [], 'current': [], 'soc': []})
    
    df = pd.read_csv(LOG_FILE)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    
    if hours > 0:
        cutoff = datetime.now() - pd.Timedelta(hours=hours)
        df = df[df['Timestamp'] >= cutoff]
    
    return jsonify({
        'timestamps': df['Timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist(),
        'voltage': df['Voltage'].tolist(),
        'current': df['Current'].tolist(),
        'soc': df['SOC'].tolist()
    })

async def read_battery_data(client):
    CHARACTERISTIC_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
    COMMAND = bytes.fromhex("DD A5 03 00 FF FD 77")
    
    await client.write_gatt_char(CHARACTERISTIC_UUID, COMMAND)
    await asyncio.sleep(0.5)
    response = await client.read_gatt_char(CHARACTERISTIC_UUID)
    
    if len(response) >= 27:
        voltage = struct.unpack('>H', response[4:6])[0] / 100
        current_raw = struct.unpack('>H', response[6:8])[0]
        current = (current_raw - 30000) / 100 if current_raw > 30000 else current_raw / 100
        soc = response[23]
        cycles = struct.unpack('>H', response[12:14])[0]
        capacity = struct.unpack('>H', response[8:10])[0] / 100
        
        return {
            'voltage': f"{voltage:.2f}",
            'current': f"{current:+.2f}",
            'soc': str(soc),
            'cycles': str(cycles),
            'capacity': f"{capacity:.1f}",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    return None

async def monitor_loop():
    global latest_data, running
    
    print(f"🔌 Connecting to {DEVICE_NAME}...")
    print(f"   MAC: {MAC_ADDRESS}\n")
    
    async with BleakClient(MAC_ADDRESS, timeout=30.0) as client:
        print("✅ Connected!\n")
        
        while running:
            data = await read_battery_data(client)
            if data:
                latest_data = data
                print(f"[{data['timestamp']}] V:{data['voltage']}V I:{data['current']}A SOC:{data['soc']}% Cycles:{data['cycles']}")
            
            await asyncio.sleep(INTERVAL)

def run_ble():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(monitor_loop())
    except KeyboardInterrupt:
        print("\n⏹️  Stopped")

if __name__ == '__main__':
    load_last_reading()
    
    ble_thread = threading.Thread(target=run_ble, daemon=True)
    ble_thread.start()
    
    print("\n🌐 Web dashboard: http://localhost:5000\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
