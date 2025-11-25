import os
import time
import hmac
import hashlib
import base64
import requests
import json
import pandas as pd
import numpy as np
import math
from flask import Flask, jsonify, request
from datetime import datetime
from zoneinfo import ZoneInfo
import threading

app = Flask(__name__)

# Configuration
class Config:
    def __init__(self):
        self.api_key = os.environ.get('COINCATCH_API_KEY', '')
        self.api_secret = os.environ.get('COINCATCH_API_SECRET', '') 
        self.passphrase = os.environ.get('COINCATCH_PASSPHRASE', '')
        self.base_url = "https://api.coincatch.com"
        self.is_configured = bool(self.api_key and self.api_secret and self.passphrase)
        
        # Timezone setting - New York (EST/EDT)
        self.timezone = ZoneInfo('America/New_York')
        
        # Trading parameters - SOLANA
        self.trade_type = 'percentage' # 'percentage' or 'fixed'
        self.trade_percentage = 50 # Default: 50% of available balance
        self.sol_trade_amount = 0.1  # Default: Buy/Sell 0.1 SOL each time (used if trade_type is 'fixed')
        self.check_interval = 900  # Check every 15 minutes
        self.indicator_interval = '15m'
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9

config = Config()

def get_ny_time():
    """Get current time in New York timezone"""
    return datetime.now(config.timezone)

# Trading state
class TradingState:
    def __init__(self):
        self.is_running = False
        self.last_position = None
        self.last_trade_time = None
        self.last_signals = {}
        self.trade_history = []
        self.current_sol_balance = 0.0
        self.current_usdt_balance = 0.0
        
trading_state = TradingState()

def make_api_request(method, endpoint, data=None):
    """Make authenticated API request"""
    if not config.is_configured:
        return {'error': 'API credentials not configured'}
    
    try:
        if not trading_state.is_running and endpoint not in ['/api/spot/v1/account/assets']:
            return {'error': 'Bot stopped'}
            
        timestamp = str(int(time.time() * 1000))
        body_string = json.dumps(data) if data else ''
        message = f"{timestamp}{method.upper()}{endpoint}{body_string}"
        
        signature = base64.b64encode(
            hmac.new(
                config.api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode()

        headers = {
            'ACCESS-KEY': config.api_key,
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-PASSPHRASE': config.passphrase,
            'Content-Type': 'application/json'
        }

        url = config.base_url + endpoint
        timeout = 10  # Increased timeout for production
        
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, timeout=timeout)
        else:
            response = requests.post(url, headers=headers, json=data, timeout=timeout)
        
        if response.headers.get('content-type', '').startswith('application/json'):
            response_data = response.json()
        else:
            return {'error': f'HTTP {response.status_code}', 'message': 'Server returned non-JSON response'}
        
        if response.status_code == 200:
            return response_data
        else:
            return {'error': f'HTTP {response.status_code}', 'message': response_data.get('msg', str(response_data))}
            
    except Exception as e:
        return {'error': f'Request failed: {str(e)}'}

# ... (keep all your existing functions: get_klines, calculate_macd, get_current_balances, etc.)
# Just copy all the existing functions from your previous file here

@app.route('/')
def index():
    # Serve the HTML directly
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SOL Trading Bot</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #00ffbd 0%, #00a8ff 100%); min-height: 100vh; padding: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            .header { background: white; padding: 30px; border-radius: 15px; text-align: center; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
            .header h1 { color: #00a8ff; font-size: 2.5em; margin-bottom: 10px; }
            .card { background: white; padding: 25px; border-radius: 15px; margin-bottom: 20px; box-shadow: 0 5px 20px rgba(0,0,0,0.1); }
            .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
            .status-item { padding: 15px; background: #f8f9fa; border-radius: 10px; }
            .status-item label { display: block; color: #666; font-size: 0.9em; margin-bottom: 5px; }
            .status-item .value { font-size: 1.3em; font-weight: bold; color: #333; }
            .status-running { color: #28a745 !important; }
            .status-stopped { color: #dc3545 !important; }
            button { padding: 15px 30px; font-size: 1.1em; border: none; border-radius: 8px; cursor: pointer; transition: all 0.3s; font-weight: 600; margin: 5px; }
            .start-button { background: #28a745; color: white; }
            .stop-button { background: #dc3545; color: white; }
            .refresh-button { background: #6c757d; color: white; }
            button:hover { transform: translateY(-2px); }
            button:disabled { opacity: 0.5; cursor: not-allowed; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🪙 SOL Trading Bot</h1>
                <p>MACD Only Strategy - Status: <span id="status">Loading...</span></p>
            </div>
            
            <div class="card">
                <h2>Bot Status</h2>
                <div class="status-grid">
                    <div class="status-item">
                        <label>Status:</label>
                        <div class="value" id="botStatus">LOADING</div>
                    </div>
                    <div class="status-item">
                        <label>Position:</label>
                        <div class="value" id="position">--</div>
                    </div>
                    <div class="status-item">
                        <label>Last Trade:</label>
                        <div class="value" id="lastTrade">--</div>
                    </div>
                </div>
                
                <div style="text-align: center; margin-top: 20px;">
                    <button onclick="startBot()" id="startButton" class="start-button">▶ START BOT</button>
                    <button onclick="stopBot()" id="stopButton" class="stop-button" disabled>■ STOP BOT</button>
                    <button onclick="refreshData()" class="refresh-button">🔄 Refresh</button>
                </div>
            </div>
            
            <div class="card">
                <h2>Account Balance</h2>
                <div class="status-grid">
                    <div class="status-item">
                        <label>SOL Balance:</label>
                        <div class="value" id="solBalance">-- SOL</div>
                    </div>
                    <div class="status-item">
                        <label>USDT Balance:</label>
                        <div class="value" id="usdtBalance">$--</div>
                    </div>
                    <div class="status-item">
                        <label>SOL Price:</label>
                        <div class="value" id="solPrice">$--</div>
                    </div>
                </div>
            </div>
            
            <div id="result" style="margin-top: 20px; padding: 15px; border-radius: 8px; text-align: center;"></div>
        </div>

        <script>
            async function apiCall(endpoint, method = 'GET') {
                try {
                    const response = await fetch(endpoint, { method: method });
                    return await response.json();
                } catch (error) {
                    console.error('API call failed:', error);
                    return { status: 'error', message: 'Network error' };
                }
            }

            async function startBot() {
                const result = document.getElementById('result');
                result.innerHTML = '<div style="color: blue">Starting SOL Bot...</div>';
                
                const data = await apiCall('/api/start_bot', 'POST');
                
                if (data.status === 'success') {
                    result.innerHTML = '<div style="color: green">✅ ' + data.message + '</div>';
                    setTimeout(refreshData, 1000);
                } else {
                    result.innerHTML = '<div style="color: red">❌ ' + data.message + '</div>';
                }
            }

            async function stopBot() {
                const result = document.getElementById('result');
                result.innerHTML = '<div style="color: blue">Stopping Bot...</div>';
                
                const data = await apiCall('/api/stop_bot', 'POST');
                
                if (data.status === 'success') {
                    result.innerHTML = '<div style="color: orange">■ ' + data.message + '</div>';
                    setTimeout(refreshData, 1000);
                } else {
                    result.innerHTML = '<div style="color: red">❌ ' + data.message + '</div>';
                }
            }

            async function refreshData() {
                const data = await apiCall('/api/status');
                
                if (data.status === 'success') {
                    document.getElementById('botStatus').textContent = data.is_running ? 'RUNNING' : 'STOPPED';
                    document.getElementById('botStatus').className = 'value ' + (data.is_running ? 'status-running' : 'status-stopped');
                    
                    document.getElementById('position').textContent = data.last_position || 'NONE';
                    document.getElementById('lastTrade').textContent = data.last_trade_time ? 
                        new Date(data.last_trade_time).toLocaleString() : 'Never';
                    
                    document.getElementById('solBalance').textContent = data.sol_balance ? data.sol_balance.toFixed(4) + ' SOL' : '-- SOL';
                    document.getElementById('usdtBalance').textContent = data.usdt_balance ? '$' + data.usdt_balance.toFixed(2) : '$--';
                    
                    if (data.signals && data.signals.price) {
                        document.getElementById('solPrice').textContent = '$' + data.signals.price.toFixed(2);
                    }
                    
                    if (data.is_running) {
                        document.getElementById('startButton').disabled = true;
                        document.getElementById('stopButton').disabled = false;
                    } else {
                        document.getElementById('startButton').disabled = false;
                        document.getElementById('stopButton').disabled = true;
                    }
                }
            }

            // Refresh data every 5 seconds
            setInterval(refreshData, 5000);
            refreshData();
        </script>
    </body>
    </html>
    """
    return html_content

# ... (keep all your existing API routes: /api/start_bot, /api/stop_bot, /api/status, etc.)
# Just copy all the existing API routes from your previous file here

@app.route('/api/start_bot',methods=['POST'])
def start_bot():
    if trading_state.is_running:
        return jsonify({'status':'error','message':'Bot already running'})
    
    if not config.is_configured:
        return jsonify({'status':'error','message':'API not configured'})
    
    trading_state.is_running=True
    trading_thread=threading.Thread(target=trading_loop,daemon=True)
    trading_thread.start()
    
    return jsonify({'status':'success','message':f'Bot started - MACD Only Strategy'})

@app.route('/api/stop_bot',methods=['POST'])
def stop_bot():
    if not trading_state.is_running:
        return jsonify({'status':'error','message':'Bot not running'})
    
    trading_state.is_running=False
    return jsonify({'status':'success','message':'Bot stopped'})

@app.route('/api/status')
def get_status():
    return jsonify({
        'status':'success',
        'is_running':trading_state.is_running,
        'last_position':trading_state.last_position,
        'last_trade_time':trading_state.last_trade_time.isoformat() if trading_state.last_trade_time else None,
        'signals':trading_state.last_signals,
        'trade_history':trading_state.trade_history,
        'trade_type': config.trade_type,
        'trade_percentage': config.trade_percentage,
        'sol_trade_amount':config.sol_trade_amount,
        'check_interval':config.check_interval,
        'indicator_interval':config.indicator_interval,
        'sol_balance':trading_state.current_sol_balance,
        'usdt_balance':trading_state.current_usdt_balance
    })

# Add other API routes as needed...

if __name__=='__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n"+"="*60)
    print("SOLANA TRADING BOT - MACD ONLY STRATEGY")
    print("="*60)
    if config.trade_type == 'percentage':
        print(f"\nTrade Amount: {config.trade_percentage}% of balance per trade")
    else:
        print(f"\nTrade Amount: {config.sol_trade_amount} SOL per trade")
    print("Strategy: MACD Only (Strong crossovers only)")
    print(f"MACD Settings: Fast={config.macd_fast}, Slow={config.macd_slow}, Signal={config.macd_signal}")
    print(f"Interval: {config.indicator_interval}")
    print(f"Check: {config.check_interval} seconds")
    print("\nAPI Configuration Check:")
    print(f"- COINCATCH_API_KEY: {'✅ SET' if config.api_key else '❌ MISSING'}")
    print(f"- COINCATCH_API_SECRET: {'✅ SET' if config.api_secret else '❌ MISSING'}") 
    print(f"- COINCATCH_PASSPHRASE: {'✅ SET' if config.passphrase else '❌ MISSING'}")
    print(f"- API Configured: {'✅ YES' if config.is_configured else '❌ NO'}")
    print(f"\nStarting server on port {port}...")
    print("="*60+"\n")
    
    app.run(debug=False, host='0.0.0.0', port=port)
