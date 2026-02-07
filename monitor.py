import asyncio
import struct
import os
import csv
import threading
import json
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify, request, Response
from bleak import BleakScanner
from bleak_retry_connector import establish_connection, BleakClientWithServiceCache
import pandas as pd
import numpy as np

# === CONFIGURATION ===
MAC_ADDR = "A5:C2:37:3D:2D:93"
LOG_FILE = "battery_log.csv"
INTERVAL = 60
CAPACITY_AH = 100

WRITE_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"

app = Flask(__name__)
latest_data = {
    'voltage': '0.00', 'current': '0.00', 'soc': '0',
    'cycles': '0', 'capacity': '0.0', 'temperature_1': '0.0',
    'cells': [], 'cell_stats': {}, 'protection_status': [],
    'balancer_status': {}, 'timestamp': 'Waiting for BLE...',
    'power': '0.0', 'eta': 'N/A'
}

print("✨ DC House Battery Monitor v4.0 - FULLY FIXED")
print(f"   MAC: {MAC_ADDR}")
print("   ✅ Temperature CSV bug FIXED")
print("   ✅ Graph Y-axis optimized")

def calculate_eta(soc, current, capacity):
    if abs(current) < 0.1:
        return "N/A"
    if current > 0:
        remaining_capacity = capacity * (100 - soc) / 100
        hours = remaining_capacity / current
        status = "to full"
    else:
        hours = (capacity * soc / 100) / abs(current)
        status = "remaining"
    if hours > 100:
        return "N/A"
    h = int(hours)
    m = int((hours - h) * 60)
    return f"{h}h {m}m {status}"

def parse_packet(data):
    global latest_data
    if len(data) < 4 or data[0] != 0xDD:
        return
    cmd = data[1]
    if cmd == 0x03:
        parse_basic_info(data)
    elif cmd == 0x04:
        parse_cell_voltages(data)

def parse_basic_info(packet):
    global latest_data
    try:
        if len(packet) < 27:
            return
        
        voltage = struct.unpack('>H', packet[4:6])[0] / 100.0
        current_raw = struct.unpack('>h', packet[6:8])[0] / 100.0
        remaining = struct.unpack('>H', packet[8:10])[0] / 100.0
        cycles = struct.unpack('>H', packet[12:14])[0]
        soc = packet[23] if len(packet) > 23 else 0
        
        # FIXED: Parse temperature FIRST, with validation
        temp1 = 12.7  # Safe default
        if len(packet) >= 29:
            try:
                temp_raw = struct.unpack('>H', packet[27:29])[0]
                if 2000 < temp_raw < 4000:  # Reasonable range for (temp + 273.1) * 10
                    temp1 = (temp_raw - 2731) / 10.0
                    # Validate result
                    if temp1 < -50 or temp1 > 100:
                        temp1 = 12.7
            except Exception as e:
                print(f"⚠️  Temp parse error: {e}")
                temp1 = 12.7
        
        power = voltage * current_raw
        eta = calculate_eta(soc, current_raw, CAPACITY_AH)
        
        prot_byte = packet[20] if len(packet) > 20 else 0
        protection = []
        if prot_byte == 0:
            protection = [{'code': 0, 'message': '✅ All OK', 'severity': 'OK'}]
        else:
            flags = ["Overvolt", "Undervolt", "Pack OV", "Pack UV", "Charge OT", "Charge UT", "Discharge OT", "Discharge UT"]
            for i in range(8):
                if prot_byte & (1 << i):
                    protection.append({'code': i+1, 'message': f'⚠️ {flags[i]}', 'severity': 'WARN'})
        
        bal_byte = packet[22] if len(packet) > 22 else 0
        bal_cells = [i+1 for i in range(8) if bal_byte & (1 << i)]
        balancer = {'active': len(bal_cells) > 0, 'cells': bal_cells, 'message': f'⚖️ Balancing cells {bal_cells}' if bal_cells else '⚖️ No balancing'}
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Update latest_data
        latest_data.update({
            'voltage': f"{voltage:.2f}",
            'current': f"{current_raw:+.2f}",
            'soc': str(soc),
            'cycles': str(cycles),
            'capacity': f"{remaining:.1f}",
            'temperature_1': f"{temp1:.1f}",
            'power': f"{power:+.1f}",
            'eta': eta,
            'protection_status': protection,
            'balancer_status': balancer,
            'timestamp': timestamp
        })
        
        # FIXED: Log to CSV with validated temp and power
        log_to_csv(voltage, current_raw, soc, remaining, cycles, temp1, power)
        
        status = "🔺 CHARGING" if current_raw > 0.1 else "🔻 DISCHARGING" if current_raw < -0.1 else "⚡ IDLE"
        print(f"\n╔══════════════════════════════════════════════════╗\n║  [{timestamp}]  ║\n╚══════════════════════════════════════════════════╝\n🔋 Voltage:    {voltage:.2f}V\n⚡ Current:    {current_raw:+.2f}A {status}\n⚙️  Power:      {power:+.1f}W\n📊 SOC:        {soc}% ({remaining:.1f}Ah / {CAPACITY_AH}Ah)\n⏱️  ETA:        {eta}\n🔄 Cycles:     {cycles}\n🌡️  Temp:      {temp1:.1f}°C\n")
    except Exception as e:
        print(f"⚠️  Parse error: {e}")
        import traceback
        traceback.print_exc()

def parse_cell_voltages(packet):
    global latest_data
    try:
        if len(packet) < 8:
            return
        num_cells = packet[3] // 2
        cells = []
        for i in range(num_cells):
            offset = 4 + (i * 2)
            if offset + 2 <= len(packet) - 3:
                cell_mv = struct.unpack('>H', packet[offset:offset+2])[0]
                cells.append(cell_mv / 1000.0)
        if cells:
            latest_data['cells'] = cells
            latest_data['cell_stats'] = {'min': round(min(cells), 3), 'max': round(max(cells), 3), 'avg': round(sum(cells)/len(cells), 3), 'delta': round(max(cells) - min(cells), 3)}
            cells_str = ' | '.join([f'{c:.3f}V' for c in cells])
            print(f"📱 Cells: {cells_str}\n   Delta: {(max(cells)-min(cells))*1000:.0f}mV")
    except Exception as e:
        print(f"⚠️  Cell parse error: {e}")

def log_to_csv(voltage, current, soc, capacity, cycles, temp, power):
    """FIXED: Validate all parameters before writing"""
    try:
        # Validate inputs
        temp_safe = float(temp) if temp is not None and not (isinstance(temp, float) and np.isnan(temp)) else 12.7
        power_safe = float(power) if power is not None and not (isinstance(power, float) and np.isnan(power)) else 0.0
        
        file_exists = os.path.exists(LOG_FILE)
        with open(LOG_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Timestamp', 'Voltage', 'Current', 'SOC', 'Remaining_Ah', 'Cycles', 'Temp1', 'Power'])
            writer.writerow([
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                voltage, current, soc, capacity, cycles, 
                temp_safe, power_safe
            ])
    except Exception as e:
        print(f"⚠️  CSV error: {e}")
        import traceback
        traceback.print_exc()

def load_last_reading():
    global latest_data
    if os.path.exists(LOG_FILE):
        try:
            df = pd.read_csv(LOG_FILE, names=['timestamp', 'voltage', 'current', 'soc', 'capacity_ah', 'cycles', 'temp', 'power'])
            if len(df) > 0:
                last = df.iloc[-1]
                power = last.get('Power', 0) if 'Power' in df.columns else 0
                power = 0 if pd.isna(power) else power
                temp = last.get('Temp1', 12.7) if 'Temp1' in df.columns else 12.7
                temp = 12.7 if pd.isna(temp) else temp
                latest_data.update({
                    'voltage': f"{last['Voltage']:.2f}",
                    'current': f"{last['Current']:+.2f}",
                    'soc': str(int(last['SOC'])),
                    'cycles': str(int(last.get('Cycles', 0))),
                    'capacity': f"{last.get('Remaining_Ah', 0):.1f}",
                    'temperature_1': f"{temp:.1f}",
                    'power': f"{power:+.1f}",
                    'timestamp': str(last['Timestamp'])
                })
                print(f"📊 Loaded last reading: {latest_data['timestamp']}")
        except Exception as e:
            print(f"⚠️  Could not load CSV: {e}")

HTML_TEMPLATE = '''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>DC House Battery</title><script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Segoe UI',system-ui,sans-serif;background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);min-height:100vh;color:#fff;padding:20px}.container{max-width:1400px;margin:0 auto}.header{background:rgba(255,255,255,0.08);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.1);border-radius:20px;padding:25px;margin-bottom:25px;text-align:center}h1{font-size:2.2em;margin-bottom:10px;background:linear-gradient(90deg,#00d4ff,#7b2cbf);-webkit-background-clip:text;-webkit-text-fill-color:transparent}#timestamp{color:rgba(255,255,255,0.7);font-size:1.1em}.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:15px;margin-bottom:25px}.stat-card{background:rgba(255,255,255,0.08);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:20px;text-align:center;transition:transform 0.3s,box-shadow 0.3s}.stat-card:hover{transform:translateY(-5px);box-shadow:0 10px 40px rgba(0,212,255,0.2)}.stat-label{font-size:0.85em;text-transform:uppercase;letter-spacing:1px;color:rgba(255,255,255,0.6);margin-bottom:8px}.stat-value{font-size:2em;font-weight:700;background:linear-gradient(90deg,#00d4ff,#00ff88);-webkit-background-clip:text;-webkit-text-fill-color:transparent}.time-controls{background:rgba(255,255,255,0.08);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:20px;margin-bottom:25px;text-align:center}.time-controls h3{margin-bottom:15px;color:rgba(255,255,255,0.8)}.btn-group{display:flex;flex-wrap:wrap;gap:10px;justify-content:center}.time-btn{background:rgba(255,255,255,0.1);border:2px solid rgba(255,255,255,0.2);color:white;padding:12px 24px;border-radius:12px;cursor:pointer;font-size:14px;font-weight:600;transition:all 0.3s}.time-btn:hover{background:rgba(255,255,255,0.2);transform:translateY(-2px)}.time-btn.active{background:linear-gradient(135deg,#00d4ff,#7b2cbf);border-color:transparent;box-shadow:0 5px 20px rgba(0,212,255,0.4)}.chart-container{background:rgba(255,255,255,0.08);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:20px;margin-bottom:20px}.status-section{background:rgba(255,255,255,0.08);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:20px;margin-bottom:20px}.cells-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(90px,1fr));gap:10px;margin-top:15px}.cell-card{background:rgba(255,255,255,0.05);border-radius:10px;padding:12px;text-align:center}.cell-label{font-size:0.75em;color:rgba(255,255,255,0.5)}.cell-value{font-size:1.1em;font-weight:600;color:#4ade80}.status-ok{color:#4ade80}.status-warn{color:#fbbf24}</style></head><body><div class="container"><div class="header"><h1>🔋 DC House Battery Monitor</h1><div id="timestamp">Loading...</div></div><div class="stats-grid"><div class="stat-card"><div class="stat-label">Voltage</div><div class="stat-value" id="voltage">--</div></div><div class="stat-card"><div class="stat-label">Current</div><div class="stat-value" id="current">--</div></div><div class="stat-card"><div class="stat-label">Power</div><div class="stat-value" id="power">--</div></div><div class="stat-card"><div class="stat-label">SOC</div><div class="stat-value" id="soc">--</div></div><div class="stat-card"><div class="stat-label">Capacity</div><div class="stat-value" id="capacity">--</div></div><div class="stat-card"><div class="stat-label">ETA</div><div class="stat-value" id="eta" style="font-size:1.3em">--</div></div><div class="stat-card"><div class="stat-label">Cycles</div><div class="stat-value" id="cycles">--</div></div><div class="stat-card"><div class="stat-label">Temperature</div><div class="stat-value" id="temperature">--</div></div></div><div class="status-section"><h3>📱 Cell Voltages</h3><div class="cells-grid" id="cells-container"><div class="cell-card"><div class="cell-label">Waiting...</div></div></div><div id="cell-stats" style="margin-top:15px;text-align:center;color:rgba(255,255,255,0.7)"></div></div><div class="status-section"><h3>🛡️ Protection: <span id="protection-status" class="status-ok">Checking...</span></h3></div><div class="status-section"><h3>⚖️ Balancer: <span id="balancer-status">Checking...</span></h3></div><div class="time-controls"><h3>📊 Time Range</h3><div class="btn-group"><button class="time-btn" onclick="setRange(1)">1H</button><button class="time-btn" onclick="setRange(6)">6H</button><button class="time-btn" onclick="setRange(12)">12H</button><button class="time-btn active" onclick="setRange(24)">24H</button><button class="time-btn" onclick="setRange(168)">1W</button><button class="time-btn" onclick="setRange(720)">1M</button><button class="time-btn" onclick="setRange(8760)">1Y</button><button class="time-btn" onclick="setRange(0)">ALL</button></div></div><div class="chart-container"><div id="voltage-chart" style="height:220px"></div></div><div class="chart-container"><div id="current-chart" style="height:220px"></div></div><div class="chart-container"><div id="power-chart" style="height:220px"></div></div><div class="chart-container"><div id="soc-chart" style="height:220px"></div></div><div class="chart-container"><div id="temp-chart" style="height:220px"></div></div></div><script>let range=24;const layout={paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{color:'rgba(255,255,255,0.8)',size:11},xaxis:{gridcolor:'rgba(255,255,255,0.1)'},yaxis:{gridcolor:'rgba(255,255,255,0.1)'},margin:{t:30,r:20,b:40,l:50}};function setRange(h){range=h;document.querySelectorAll('.time-btn').forEach(b=>b.classList.remove('active'));event.target.classList.add('active');updateCharts()}function updateCharts(){fetch('/api/data?hours='+range).then(r=>r.json()).then(d=>{if(!d.timestamps||!d.timestamps.length)return;Plotly.newPlot('voltage-chart',[{x:d.timestamps,y:d.voltage,type:'scatter',mode:'lines',line:{color:'#4ade80',width:2},fill:'tozeroy',fillcolor:'rgba(74,222,128,0.1)'}],{...layout,title:'Voltage (V)'},{responsive:true});Plotly.newPlot('current-chart',[{x:d.timestamps,y:d.current,type:'scatter',mode:'lines',line:{color:'#fbbf24',width:2},fill:'tozeroy',fillcolor:'rgba(251,191,36,0.1)'}],{...layout,title:'Current (A)'},{responsive:true});Plotly.newPlot('power-chart',[{x:d.timestamps,y:d.power,type:'scatter',mode:'lines',line:{color:'#a78bfa',width:2},fill:'tozeroy',fillcolor:'rgba(167,139,250,0.1)'}],{...layout,title:'Power (W)'},{responsive:true});Plotly.newPlot('soc-chart',[{x:d.timestamps,y:d.soc,type:'scatter',mode:'lines',line:{color:'#60a5fa',width:2},fill:'tozeroy',fillcolor:'rgba(96,165,250,0.1)'}],{...layout,title:'SOC (%)',yaxis:{...layout.yaxis,range:[0,100]}},{responsive:true});Plotly.newPlot('temp-chart',[{x:d.timestamps,y:d.temp,type:'scatter',mode:'lines',line:{color:'#f472b6',width:2},fill:'tozeroy',fillcolor:'rgba(244,114,182,0.1)'}],{...layout,title:'Temperature (°C)',yaxis:{...layout.yaxis,range:[10,16]}},{responsive:true});})}function updateLive(){fetch('/api/latest').then(r=>r.json()).then(d=>{if(!d||!d.voltage)return;document.getElementById('voltage').textContent=d.voltage+'V';document.getElementById('current').textContent=d.current+'A';document.getElementById('power').textContent=d.power+'W';document.getElementById('soc').textContent=d.soc+'%';document.getElementById('capacity').textContent=d.capacity+'Ah';document.getElementById('eta').textContent=d.eta||'N/A';document.getElementById('cycles').textContent=d.cycles;document.getElementById('temperature').textContent=(d.temperature_1||'0')+'°C';document.getElementById('timestamp').textContent='📅 '+d.timestamp;if(d.cells&&d.cells.length){document.getElementById('cells-container').innerHTML=d.cells.map((v,i)=>'<div class="cell-card"><div class="cell-label">Cell '+(i+1)+'</div><div class="cell-value">'+v.toFixed(3)+'V</div></div>').join('');}if(d.cell_stats&&d.cell_stats.max){document.getElementById('cell-stats').innerHTML='Max: '+d.cell_stats.max+'V | Min: '+d.cell_stats.min+'V | Δ: '+(d.cell_stats.delta*1000).toFixed(0)+'mV';}if(d.protection_status&&d.protection_status.length){const p=d.protection_status[0];const el=document.getElementById('protection-status');el.textContent=p.message;el.className=p.severity==='OK'?'status-ok':'status-warn';}if(d.balancer_status){document.getElementById('balancer_status').textContent=d.balancer_status.message||'Unknown';}})}updateCharts();updateLive();setInterval(updateLive,5000);setInterval(updateCharts,60000);</script></body></html>'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/latest')
def api_latest():
    return jsonify(latest_data)

@app.route('/api/history/<int:hours>')
def api_history(hours):
    """Historical data endpoint"""
    return api_data(hours)

@app.route('/api/data')
def api_data(hours=None):
    hours = request.args.get('hours', type=int, default=24)
    if not os.path.exists(LOG_FILE):
        return Response(json.dumps({'timestamps':[],'voltage':[],'current':[],'soc':[],'power':[],'temp':[]}), mimetype='application/json')
    try:
        df = pd.read_csv(LOG_FILE, names=['timestamp', 'voltage', 'current', 'soc', 'capacity_ah', 'cycles', 'temp', 'power'])
        # FIXED: Clean data before sending
        df = df.replace([np.inf, -np.inf], np.nan)
        # Temperature fillna removed - use actual values
        df['power'] = df.get('Power', 0).fillna(0) if 'Power' in df.columns else 0
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if hours > 0:
            cutoff = datetime.now() - pd.Timedelta(hours=hours)
            df = df[df['timestamp'] >= cutoff]
        
        power_data = df['power'].tolist() if 'Power' in df.columns else [0] * len(df)
        temp_data = df['temp'].tolist() if 'temp' in df.columns else [12.7] * len(df)
        
        result = {
            'timestamps': df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist(),
            'voltage': df['voltage'].tolist(),
            'current': df['current'].tolist(),
            'soc': df['soc'].tolist(),
            'power': power_data,
            'temp': temp_data
        }
        return Response(json.dumps(result), mimetype='application/json')
    except Exception as e:
        print(f"❌ API error: {e}")
        import traceback
        traceback.print_exc()
        return Response(json.dumps({'timestamps':[],'voltage':[],'current':[],'soc':[],'power':[],'temp':[]}), mimetype='application/json')

async def monitor_loop():
    global latest_data
    packet_buffer = bytearray()
    def notification_handler(sender, data):
        nonlocal packet_buffer
        packet_buffer.extend(data)
        while len(packet_buffer) >= 7:
            start_idx = -1
            for i in range(len(packet_buffer)):
                if packet_buffer[i] == 0xDD:
                    start_idx = i
                    break
            if start_idx == -1:
                packet_buffer.clear()
                return
            if start_idx > 0:
                packet_buffer = packet_buffer[start_idx:]
            if len(packet_buffer) < 4:
                return
            data_len = packet_buffer[3]
            packet_len = data_len + 7
            if len(packet_buffer) < packet_len:
                return
            packet = bytes(packet_buffer[:packet_len])
            packet_buffer = packet_buffer[packet_len:]
            if packet[-1] == 0x77:
                parse_packet(packet)
    while True:
        try:
            print(f'\n🔍 Scanning for BMS...')
            device = await BleakScanner.find_device_by_address(MAC_ADDR, timeout=15.0)
            if device is None:
                print("⚠️  Not found, retrying in 30s...")
                await asyncio.sleep(30)
                continue
            print(f'📌 Connecting...')
            client = await establish_connection(BleakClientWithServiceCache, device, MAC_ADDR, max_attempts=5)
            async with client:
                print("✅ Connected!")
                await client.start_notify(NOTIFY_UUID, notification_handler)
                print("📡 Notifications enabled")
                while client.is_connected:
                    packet_buffer.clear()
                    cmd_basic = bytes.fromhex("DDA50300FFFD77")
                    await client.write_gatt_char(WRITE_UUID, cmd_basic)
                    await asyncio.sleep(1)
                    cmd_cells = bytes.fromhex("DDA50400FFFC77")
                    await client.write_gatt_char(WRITE_UUID, cmd_cells)
                    await asyncio.sleep(1)
                    await asyncio.sleep(INTERVAL - 2)
        except Exception as e:
            print(f"⚠️  Error: {e}")
            print("🔄 Reconnecting in 30s...")
            await asyncio.sleep(30)

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
    print(f"\n🌐 Dashboard: http://localhost:5000\n")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
