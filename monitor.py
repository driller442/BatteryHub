import asyncio
from bleak import BleakClient, BleakScanner
from bleak_retry_connector import establish_connection, BleakClientWithServiceCache
import struct
from datetime import datetime, timedelta
import csv
import os
from flask import Flask, render_template_string, jsonify, request
import threading
import time

# ============= CONFIGURATION =============
MAC_ADDR = "A5:C2:37:3D:2D:93"
LOG_FILE = "battery_log.csv"
MONITOR_INTERVAL = 60

# BLE UUIDs
WRITE_CHAR = "0000ff02-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR = "0000ff01-0000-1000-8000-00805f9b34fb"

# Command bytes
CMD_READ_BASIC = bytes.fromhex("DDAA0300FFFD77")
CMD_READ_CELLS = bytes.fromhex("DDAA0400FFFC77")

# ============= GLOBAL STATE =============
battery_data = {
    'status': 'Connecting...',
    'voltage': 0,
    'current': 0,
    'soc': 0,
    'remaining_ah': 0,
    'nominal_ah': 100,
    'cycles': 0,
    'cells': [],
    'temperature_1': None,
    'temperature_2': None,
    'power': 0
}

session_stats = {
    'start_time': datetime.now(),
    'readings_count': 0,
    'anomalies_filtered': 0,
    'last_valid_soc': None,
    'last_valid_voltage': None,
    'last_reading_time': datetime.now()
}

app = Flask(__name__)

# ============= DATA PARSING =============
def is_valid_reading(new_data):
    """Validate new readings to filter anomalies"""
    if new_data.get('soc', 0) > 100:
        return False, f"SOC out of range: {new_data['soc']}"
    
    current = new_data.get('current', 0)
    if abs(current) > 20:
        return False, f"Current spike: {current}A"
    
    # Check SOC changes
    if session_stats['last_valid_soc'] is not None:
        last_soc = session_stats['last_valid_soc']
        new_soc = new_data.get('soc', 0)
        soc_change = abs(new_soc - last_soc)
        if soc_change > 25:
            return False, f"Impossible SOC change: {last_soc}% → {new_soc}%"
    
    # Check voltage changes
    if session_stats['last_valid_voltage'] is not None:
        last_v = session_stats['last_valid_voltage']
        new_v = new_data.get('voltage', 0)
        v_change = abs(new_v - last_v)
        if v_change > 2.0:
            return False, f"Impossible voltage change: {last_v}V → {new_v}V"
    
    return True, "Valid"

def parse_basic_info(data):
    """Parse basic battery information"""
    voltage = int.from_bytes(data[4:6], 'big') / 100
    current_raw = int.from_bytes(data[6:8], 'big')
    current = (current_raw - 65536 if current_raw > 32767 else current_raw) / 100
    remaining_cap = int.from_bytes(data[8:10], 'big') / 100
    nominal_cap = int.from_bytes(data[10:12], 'big') / 100
    cycles = int.from_bytes(data[12:14], 'big')
    soc_percent = int((remaining_cap / nominal_cap * 100) if nominal_cap > 0 else 0)
    power = voltage * current
    
    # Try to parse temperature (byte 38 if available)
    temp1 = None
    if len(data) > 38:
        temp1_raw = int.from_bytes(data[38:39], 'big')
        if temp1_raw > 0 and temp1_raw < 100:
            temp1 = (temp1_raw - 40) / 10 + 40  # Adjust from Kelvin offset
    
    new_data = {
        'voltage': voltage,
        'current': current,
        'power': power,
        'soc': soc_percent,
        'remaining_ah': remaining_cap,
        'nominal_ah': nominal_cap,
        'cycles': cycles,
        'temperature_1': temp1
    }
    
    # Validate reading
    is_valid, reason = is_valid_reading(new_data)
    if not is_valid:
        print(f"⚠️  ANOMALY DETECTED: {reason} - SKIPPING")
        session_stats['anomalies_filtered'] += 1
        return
    
    # Update session stats
    now = datetime.now()
    time_since_last = (now - session_stats['last_reading_time']).total_seconds() / 3600
    session_stats['last_reading_time'] = now
    session_stats['readings_count'] += 1
    session_stats['last_valid_soc'] = soc_percent
    session_stats['last_valid_voltage'] = voltage
    
    battery_data.update(new_data)
    battery_data['status'] = 'Connected'

def parse_cell_voltages(data):
    """Parse individual cell voltages"""
    cells = []
    for i in range(4):
        cell_v = int.from_bytes(data[4 + i*2:6 + i*2], 'big') / 1000
        cells.append(cell_v)
    battery_data['cells'] = cells

def log_to_csv():
    """Log data to CSV file"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Create file with headers if it doesn't exist
    try:
        with open(LOG_FILE, 'r') as f:
            pass
    except FileNotFoundError:
        with open(LOG_FILE, 'w') as f:
            f.write("Timestamp,Voltage,Current,Power,SOC,RemainingAh,Cycles,Cell1,Cell2,Cell3,Cell4,Temp1,Temp2\n")
    
    if 'voltage' in battery_data and 'cells' in battery_data:
        with open(LOG_FILE, 'a') as f:
            cells_str = ",".join(f"{c:.3f}" for c in battery_data['cells'])
            temp1 = battery_data.get('temperature_1', '')
            temp2 = battery_data.get('temperature_2', '')
            f.write(f"{timestamp},{battery_data['voltage']:.2f},{battery_data['current']:.2f},"
                   f"{battery_data['power']:.2f},{battery_data['soc']},{battery_data['remaining_ah']:.1f},"
                   f"{battery_data['cycles']},{cells_str},{temp1},{temp2}\n")

# ============= WEB DASHBOARD =============
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>DC House Battery Monitor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #1a1a1a;
            color: #e0e0e0;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { text-align: center; color: #4CAF50; margin-bottom: 30px; }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: #2d2d2d;
            padding: 20px;
            border-radius: 10px;
            border: 1px solid #3d3d3d;
        }
        .stat-label { font-size: 0.9em; color: #888; margin-bottom: 5px; }
        .stat-value { font-size: 2em; font-weight: bold; color: #4CAF50; }
        .stat-unit { font-size: 0.6em; color: #888; margin-left: 5px; }
        .stat-subtitle { font-size: 0.8em; color: #aaa; margin-top: 5px; }
        .chart-container {
            background: #2d2d2d;
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 20px;
            border: 1px solid #3d3d3d;
        }
        .time-selector {
            text-align: center;
            margin-bottom: 20px;
        }
        .time-btn {
            background: #3d3d3d;
            color: #e0e0e0;
            border: 1px solid #555;
            padding: 10px 20px;
            margin: 5px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }
        .time-btn:hover { background: #4d4d4d; }
        .time-btn.active { background: #4CAF50; color: white; }
        .footer { text-align: center; color: #888; margin-top: 20px; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔋 DC House Battery Monitor</h1>
        
        <div class="grid">
            <div class="card">
                <div class="stat-label">Voltage</div>
                <div class="stat-value" id="voltage">--<span class="stat-unit">V</span></div>
                <div class="stat-subtitle">Normal: 12.8-13.6V</div>
            </div>
            <div class="card">
                <div class="stat-label">Current</div>
                <div class="stat-value" id="current">--<span class="stat-unit">A</span></div>
                <div class="stat-subtitle" id="current-status">Waiting...</div>
            </div>
            <div class="card">
                <div class="stat-label">State of Charge</div>
                <div class="stat-value" id="soc">--<span class="stat-unit">%</span></div>
                <div class="stat-subtitle" id="capacity-info">-- / 100Ah</div>
            </div>
            <div class="card">
                <div class="stat-label">Cycles</div>
                <div class="stat-value" id="cycles">--</div>
                <div class="stat-subtitle">Charge/Discharge</div>
            </div>
            <div class="card">
                <div class="stat-label">Temperature</div>
                <div class="stat-value" id="temp">--<span class="stat-unit">°C</span></div>
                <div class="stat-subtitle">BMS Sensor</div>
            </div>
            <div class="card">
                <div class="stat-label">Session Stats</div>
                <div style="margin-top: 10px; font-size: 0.9em;">
                    <div style="margin: 5px 0;"><strong>Valid:</strong> <span id="readings-count" style="color: #4CAF50;">--</span></div>
                    <div style="margin: 5px 0;"><strong>Filtered:</strong> <span id="anomalies" style="color: #ff6b6b;">--</span></div>
                </div>
            </div>
        </div>

        <div class="time-selector">
            <button class="time-btn" onclick="updateCharts(1)">1 Hour</button>
            <button class="time-btn" onclick="updateCharts(6)">6 Hours</button>
            <button class="time-btn" onclick="updateCharts(12)">12 Hours</button>
            <button class="time-btn active" onclick="updateCharts(24)">24 Hours</button>
            <button class="time-btn" onclick="updateCharts(168)">1 Week</button>
            <button class="time-btn" onclick="updateCharts(720)">1 Month</button>
            <button class="time-btn" onclick="updateCharts(8760)">1 Year</button>
            <button class="time-btn" onclick="updateCharts(999999)">All Time</button>
        </div>

        <div class="chart-container">
            <div id="currentChart"></div>
        </div>
        <div class="chart-container">
            <div id="socChart"></div>
        </div>
        <div class="chart-container">
            <div id="voltageChart"></div>
        </div>
        <div class="chart-container">
            <div id="tempChart"></div>
        </div>

        <div class="footer">
            <div>Last updated: <span id="last-update">--</span></div>
            <div id="chart-info" style="margin-top: 5px; color: #666;">--</div>
        </div>
    </div>

    <script>
        let currentHours = 24;
        
        const layout = {
            paper_bgcolor: '#2d2d2d',
            plot_bgcolor: '#1a1a1a',
            font: { color: '#e0e0e0', size: 12 },
            xaxis: { gridcolor: '#3d3d3d', showgrid: true, color: '#e0e0e0' },
            yaxis: { gridcolor: '#3d3d3d', showgrid: true, color: '#e0e0e0' },
            hovermode: 'x unified',
            margin: { l: 60, r: 40, t: 60, b: 60 }
        };

        const config = {
            responsive: true,
            displayModeBar: true,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'],
            displaylogo: false
        };

        function updateCharts(hours) {
            currentHours = hours;
            
            // Update button styles
            document.querySelectorAll('.time-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            fetch(`/api/history?hours=${hours}`)
                .then(response => response.json())
                .then(data => {
                    if (data.timestamps && data.timestamps.length > 0) {
                        const timeRange = hours >= 999999 ? 'All Time' : hours >= 720 ? '1 Month' : 
                                        hours >= 168 ? '1 Week' : `${hours} Hours`;
                        document.getElementById('chart-info').innerHTML = 
                            `Viewing: ${timeRange} | ${data.timestamps.length} points`;
                        
                        // Current chart
                        const currentTrace = {
                            x: data.timestamps,
                            y: data.current,
                            type: 'scatter',
                            mode: 'lines',
                            name: 'Current',
                            line: { color: '#2196F3', width: 2 },
                            hovertemplate: '<b>%{x}</b><br>Current: %{y:.2f}A<extra></extra>'
                        };
                        Plotly.newPlot('currentChart', [currentTrace], {
                            ...layout,
                            title: { text: 'Charge/Discharge Current', font: { color: '#e0e0e0', size: 16 } },
                            yaxis: { ...layout.yaxis, title: 'Current (A)' }
                        }, config);

                        // SOC chart
                        const socTrace = {
                            x: data.timestamps,
                            y: data.soc,
                            type: 'scatter',
                            mode: 'lines',
                            name: 'SOC',
                            fill: 'tozeroy',
                            fillcolor: 'rgba(255, 152, 0, 0.3)',
                            line: { color: '#FF9800', width: 2 },
                            hovertemplate: '<b>%{x}</b><br>SOC: %{y}%<extra></extra>'
                        };
                        Plotly.newPlot('socChart', [socTrace], {
                            ...layout,
                            title: { text: 'State of Charge', font: { color: '#e0e0e0', size: 16 } },
                            yaxis: { ...layout.yaxis, title: 'SOC (%)', range: [0, 100] }
                        }, config);

                        // Voltage chart
                        const voltageTrace = {
                            x: data.timestamps,
                            y: data.voltage,
                            type: 'scatter',
                            mode: 'lines',
                            name: 'Voltage',
                            line: { color: '#4CAF50', width: 2 },
                            hovertemplate: '<b>%{x}</b><br>Voltage: %{y:.2f}V<extra></extra>'
                        };
                        Plotly.newPlot('voltageChart', [voltageTrace], {
                            ...layout,
                            title: { text: 'Battery Voltage', font: { color: '#e0e0e0', size: 16 } },
                            yaxis: { ...layout.yaxis, title: 'Voltage (V)' }
                        }, config);

                        // Temperature chart
                        if (data.temp1 && data.temp1.some(t => t !== null)) {
                            const temp1Trace = {
                                x: data.timestamps,
                                y: data.temp1,
                                type: 'scatter',
                                mode: 'lines',
                                name: 'Temp 1',
                                line: { color: '#FF5722', width: 2 },
                                hovertemplate: '<b>%{x}</b><br>Temp: %{y:.1f}°C<extra></extra>'
                            };
                            Plotly.newPlot('tempChart', [temp1Trace], {
                                ...layout,
                                title: { text: 'Battery Temperature', font: { color: '#e0e0e0', size: 16 } },
                                yaxis: { ...layout.yaxis, title: 'Temperature (°C)' }
                            }, config);
                        }
                    }
                })
                .catch(error => console.error('Chart error:', error));
        }

        function updateData() {
            fetch('/api/battery')
                .then(response => response.json())
                .then(data => {
                    if (data.error) return;
                    
                    document.getElementById('voltage').innerHTML = data.voltage + '<span class="stat-unit">V</span>';
                    document.getElementById('current').innerHTML = Math.abs(data.current).toFixed(2) + '<span class="stat-unit">A</span>';
                    document.getElementById('soc').innerHTML = data.soc + '<span class="stat-unit">%</span>';
                    document.getElementById('cycles').innerHTML = data.cycles;
                    document.getElementById('capacity-info').textContent = `${data.remaining_ah}Ah / 100Ah`;
                    
                    let statusHtml = '';
                    let currentVal = parseFloat(data.current);
                    if (currentVal > 0.1) {
                        statusHtml = '⚡ CHARGING';
                    } else if (currentVal < -0.1) {
                        statusHtml = '🔻 DISCHARGING';
                    } else {
                        statusHtml = '⏸️ IDLE';
                    }
                    document.getElementById('current-status').innerHTML = statusHtml;
                    
                    if (data.temperature_1) {
                        document.getElementById('temp').innerHTML = data.temperature_1.toFixed(1) + '<span class="stat-unit">°C</span>';
                    }
                    
                    document.getElementById('readings-count').textContent = data.stats.readings_count;
                    document.getElementById('anomalies').textContent = data.stats.anomalies_filtered;
                    document.getElementById('last-update').textContent = new Date().toLocaleString();
                })
                .catch(error => console.error('Error:', error));
        }

        // Initial load
        updateData();
        updateCharts(24);
        
        // Auto-refresh
        setInterval(updateData, 5000);
        setInterval(() => updateCharts(currentHours), 30000);
    </script>
</body>
</html>
'''

@app.route('/')
def dashboard():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/battery')
def api_battery():
    if battery_data.get('status') == 'Connecting...':
        return jsonify({'error': 'Connecting to battery...'}), 200
    
    if not battery_data or 'voltage' not in battery_data:
        return jsonify({'error': 'No data available'}), 200
    
    duration = datetime.now() - session_stats['start_time']
    hours = int(duration.total_seconds() // 3600)
    
    stats_data = {
        'readings_count': session_stats['readings_count'],
        'anomalies_filtered': session_stats['anomalies_filtered']
    }
    
    return jsonify({
        'voltage': f"{battery_data.get('voltage', 0):.2f}",
        'current': f"{battery_data.get('current', 0):.2f}",
        'soc': battery_data.get('soc', 0),
        'remaining_ah': f"{battery_data.get('remaining_ah', 0):.1f}",
        'cycles': battery_data.get('cycles', 0),
        'temperature_1': battery_data.get('temperature_1'),
        'stats': stats_data
    })

@app.route('/api/history')
def api_history():
    hours = int(request.args.get('hours', 24))
    
    try:
        with open(LOG_FILE, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        timestamps = []
        voltages = []
        currents = []
        socs = []
        temp1s = []
        
        for row in rows:
            try:
                ts = datetime.strptime(row['Timestamp'], '%Y-%m-%d %H:%M:%S')
                if ts >= cutoff_time:
                    timestamps.append(row['Timestamp'])
                    voltages.append(float(row['Voltage']))
                    currents.append(float(row['Current']))
                    # FIX: Handle SOC as float first
                    socs.append(int(float(row['SOC'])))
                    temp1s.append(float(row['Temp1']) if row.get('Temp1') and row['Temp1'] != '' else None)
            except:
                continue
        
        return jsonify({
            'timestamps': timestamps,
            'voltage': voltages,
            'current': currents,
            'soc': socs,
            'temp1': temp1s
        })
    except:
        return jsonify({'timestamps': [], 'voltage': [], 'current': [], 'soc': [], 'temp1': []})

def run_web_server():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# ============= BLE MONITORING =============
def handle_notification(sender, data):
    """Handle BLE notifications"""
    if data[5:7] == b'\xDD\x03':
        parse_basic_info(data)
    elif data[5:7] == b'\xDD\x04':
        parse_cell_voltages(data)

async def read_once(client):
    """Read battery data once"""
    await client.write_gatt_char(WRITE_CHAR, CMD_READ_BASIC, response=False)
    await asyncio.sleep(1.5)
    await client.write_gatt_char(WRITE_CHAR, CMD_READ_CELLS, response=False)
    await asyncio.sleep(1.5)
    log_to_csv()

async def monitor_continuous(interval=60):
    """Main monitoring loop with retry logic"""
    attempt = 0
    max_attempts = 10
    retry_delay = 10
    
    print("=" * 50)
    print("🔋 DC House Battery Monitor v3.1")
    print("=" * 50)
    print(f"MAC: {MAC_ADDR}")
    print(f"Logging to: {LOG_FILE}")
    print(f"Interval: {interval}s")
    print(f"Web Dashboard: http://localhost:5000")
    print("✅ Anomaly filtering ENABLED")
    print("✅ Temperature tracking ENABLED")
    print("Press Ctrl+C to stop...")
    print("=" * 50)
    
    while attempt < max_attempts:
        attempt += 1
        try:
            print(f"\n🔍 Connecting to DC House Battery (attempt {attempt}/{max_attempts})...")
            battery_data['status'] = 'Connecting...'
            
            device = await BleakScanner.find_device_by_address(MAC_ADDR, timeout=10.0)
            if device is None:
                raise Exception(f"Device {MAC_ADDR} not found")
            
            client = await establish_connection(
                BleakClientWithServiceCache,
                device,
                MAC_ADDR
            )
            
            async with client:
                print("✅ Connected!")
                battery_data['status'] = 'Connected'
                attempt = 0  # Reset on successful connection
                
                await client.start_notify(NOTIFY_CHAR, handle_notification)
                await asyncio.sleep(1)
                
                while client.is_connected:
                    await read_once(client)
                    
                    # Display status
                    print(f"\n{'=' * 50}")
                    print(f"🔋 Voltage: {battery_data.get('voltage', 0):.2f}V")
                    print(f"⚡ Current: {battery_data.get('current', 0):.2f}A")
                    print(f"📊 SOC: {battery_data.get('soc', 0)}%")
                    print(f"🔄 Cycles: {battery_data.get('cycles', 0)}")
                    if battery_data.get('temperature_1'):
                        print(f"🌡️  Temp: {battery_data['temperature_1']:.1f}°C")
                    print(f"✅ Valid readings: {session_stats['readings_count']}")
                    print(f"⚠️  Anomalies filtered: {session_stats['anomalies_filtered']}")
                    
                    await asyncio.sleep(interval)
                    
        except KeyboardInterrupt:
            print("\n🛑 Monitor stopped by user")
            break
        except Exception as e:
            print(f"❌ Connection error: {e}")
            if attempt < max_attempts:
                print(f"⏳ Retrying in {retry_delay} seconds...")
                battery_data['status'] = f'Connection lost - Retrying {attempt}/{max_attempts}...'
                await asyncio.sleep(retry_delay)
            else:
                print("❌ Max retries reached")
                battery_data['status'] = 'Connection failed'
                break

# ============= MAIN =============
if __name__ == "__main__":
    # Start web server in background thread
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    # Run BLE monitor
    try:
        asyncio.run(monitor_continuous(MONITOR_INTERVAL))
    except KeyboardInterrupt:
        print("\n✅ Monitor stopped")
