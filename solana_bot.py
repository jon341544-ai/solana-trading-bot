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
from flask import Flask, jsonify, request, render_template
from datetime import datetime
from zoneinfo import ZoneInfo
import threading

app = Flask(__name__)

# Configuration
class Config:
    def __init__(self):
        # CoinCatch Configuration
        self.api_key = os.environ.get('COINCATCH_API_KEY', '')
        self.api_secret = os.environ.get('COINCATCH_API_SECRET', '') 
        self.passphrase = os.environ.get('COINCATCH_PASSPHRASE', '')
        self.base_url = "https://api.coincatch.com"
        self.is_configured = bool(self.api_key and self.api_secret and self.passphrase)
        
        print(f"DEBUG: API Key configured: {bool(self.api_key)}")
        print(f"DEBUG: API Secret configured: {bool(self.api_secret)}")
        print(f"DEBUG: Passphrase configured: {bool(self.passphrase)}")
        
        # Trading parameters
        self.symbol = 'SOLUSDT_UMCBL'
        self.margin_coin = 'USDT'
        self.base_asset = 'SOL'
        self.quote_asset = 'USDT'
        self.product_type = 'umcbl'
        
        # Timezone setting
        self.timezone = ZoneInfo('America/New_York')
        
        # Trading parameters
        self.trade_type = 'fixed'
        self.trade_amount = 0.1
        self.check_interval = 900
        self.indicator_interval = '15m'
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.min_trade_amount = 0.1

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

def make_api_request(method, endpoint, params=None, data=None):
    """Make authenticated API request with detailed debugging"""
    if not config.is_configured:
        print("DEBUG: API not configured")
        return {'error': 'API credentials not configured'}
    
    try:
        timestamp = str(int(time.time() * 1000))
        
        # Build query string for GET requests
        query_string = ""
        if params and method.upper() == 'GET':
            query_string = '?' + '&'.join([f"{k}={v}" for k, v in params.items()])
            
        full_endpoint = endpoint + query_string
        body_string = json.dumps(data) if data else ''
        
        # Create signature message
        message = f"{timestamp}{method.upper()}{full_endpoint}{body_string}"
        
        print(f"DEBUG: Signature message: {message}")
        
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

        url = config.base_url + full_endpoint
        
        print(f"DEBUG: Making {method} request to: {url}")
        print(f"DEBUG: Headers: { {k: v for k, v in headers.items() if k != 'ACCESS-SIGN'} }")
        if data:
            print(f"DEBUG: Request data: {data}")
        if params:
            print(f"DEBUG: Request params: {params}")
        
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, timeout=10)
        else:
            response = requests.post(url, headers=headers, json=data, timeout=10)
        
        print(f"DEBUG: Response status code: {response.status_code}")
        print(f"DEBUG: Response headers: {dict(response.headers)}")
        print(f"DEBUG: Raw response text: {response.text}")
        
        # Try to parse JSON
        try:
            response_data = response.json()
            print(f"DEBUG: Parsed JSON response: {response_data}")
        except json.JSONDecodeError as e:
            print(f"DEBUG: JSON decode error: {e}")
            return {'error': f'JSON decode error: {e}', 'raw_response': response.text}
        
        if response.status_code == 200:
            return response_data
        else:
            error_msg = response_data.get('msg', response_data.get('message', str(response_data)))
            print(f"DEBUG: API error: {error_msg}")
            return {'error': f'HTTP {response.status_code}', 'message': error_msg}
            
    except requests.exceptions.RequestException as e:
        print(f"DEBUG: Request exception: {e}")
        return {'error': f'Request failed: {str(e)}'}
    except Exception as e:
        print(f"DEBUG: General exception: {e}")
        return {'error': f'Request failed: {str(e)}'}

def test_all_endpoints():
    """Test all API endpoints to see which ones work"""
    print("\n=== TESTING ALL API ENDPOINTS ===")
    
    # Test 1: Public contracts endpoint
    print("\n1. Testing public contracts endpoint...")
    result1 = make_api_request('GET', '/api/mix/v1/market/contracts', {'productType': 'umcbl'})
    print(f"Contracts result: {result1}")
    
    # Test 2: Ticker endpoint
    print("\n2. Testing ticker endpoint...")
    result2 = make_api_request('GET', '/api/mix/v1/market/ticker', {'symbol': config.symbol})
    print(f"Ticker result: {result2}")
    
    # Test 3: Account endpoint
    print("\n3. Testing account endpoint...")
    result3 = make_api_request('GET', '/api/mix/v1/account/account', {'symbol': config.symbol, 'marginCoin': config.margin_coin})
    print(f"Account result: {result3}")
    
    # Test 4: Klines endpoint
    print("\n4. Testing klines endpoint...")
    result4 = make_api_request('GET', '/api/mix/v1/market/candles', {
        'symbol': config.symbol,
        'granularity': '15m',
        'limit': '10'
    })
    print(f"Klines result: {result4}")
    
    return {
        'contracts': result1,
        'ticker': result2,
        'account': result3,
        'klines': result4
    }

def get_current_balances():
    """Get current account balances"""
    print("DEBUG: Getting balances...")
    
    # Try account endpoint
    result = make_api_request('GET', '/api/mix/v1/account/account', {
        'symbol': config.symbol,
        'marginCoin': config.margin_coin
    })
    
    if 'error' in result:
        print(f"DEBUG: Account endpoint error: {result.get('message')}")
        # Try alternative endpoint
        result2 = make_api_request('GET', '/api/mix/v1/account/accounts', {
            'symbol': config.symbol,
            'marginCoin': config.margin_coin
        })
        print(f"DEBUG: Alternative accounts endpoint result: {result2}")
        
        if 'error' not in result2 and 'data' in result2:
            account_data = result2['data']
            usdt_balance = float(account_data.get('available', 0))
            sol_balance = 0.0
            print(f"DEBUG: Got balances from accounts - USDT: {usdt_balance}")
            return sol_balance, usdt_balance
        
        return 0.0, 0.0
    
    if 'data' in result:
        account_data = result['data']
        usdt_balance = float(account_data.get('available', 0))
        sol_balance = 0.0
        print(f"DEBUG: Got balances from account - USDT: {usdt_balance}")
        return sol_balance, usdt_balance
    
    print(f"DEBUG: Unexpected account response: {result}")
    return 0.0, 0.0

def get_current_price():
    """Get the current price"""
    print("DEBUG: Getting current price...")
    
    result = make_api_request('GET', '/api/mix/v1/market/ticker', {
        'symbol': config.symbol
    })
    
    if 'error' in result:
        print(f"DEBUG: Ticker endpoint error: {result.get('message')}")
        return None
    
    if 'data' in result:
        data = result['data']
        print(f"DEBUG: Ticker data: {data}")
        
        # Try different possible price fields
        price_fields = ['last', 'lastPr', 'close', 'price']
        for field in price_fields:
            if field in data:
                price = data[field]
                print(f"DEBUG: Found price in field '{field}': {price}")
                try:
                    return float(price)
                except (ValueError, TypeError):
                    continue
        
        print(f"DEBUG: No valid price field found in: {data}")
        return None
    
    print(f"DEBUG: Unexpected ticker response: {result}")
    return None

def get_klines(symbol=None, interval=None, limit=100):
    """Fetch candlestick data"""
    if symbol is None:
        symbol = config.symbol
    if interval is None:
        interval = config.indicator_interval
        
    print(f"DEBUG: Getting klines for {symbol}, interval {interval}")
    
    interval_map = {
        '1m': '1m', '5m': '5m', '15m': '15m', 
        '30m': '30m', '1H': '1H', '4H': '4H', '1D': '1D'
    }
    granularity = interval_map.get(interval, '15m')
    
    result = make_api_request('GET', '/api/mix/v1/market/candles', {
        'symbol': symbol,
        'granularity': granularity,
        'limit': str(limit)
    })
    
    if 'error' in result:
        print(f"DEBUG: Klines error: {result.get('message')}")
        return None
        
    if 'data' in result and result['data']:
        data = result['data']
        print(f"DEBUG: Got {len(data)} klines")
        
        try:
            df = pd.DataFrame(data)
            if len(df.columns) >= 6:
                df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume'] + list(df.columns[6:])
                
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df = df.sort_values('timestamp').reset_index(drop=True)
                
                return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        except Exception as e:
            print(f"DEBUG: Error processing klines: {e}")
            
    print(f"DEBUG: No klines data in response: {result}")
    return None

# Simplified trading functions for now
def calculate_macd(df, fast=12, slow=26, signal=9):
    """Calculate MACD indicator"""
    try:
        close = df['close']
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        
        current_macd = macd_line.iloc[-1]
        current_signal = signal_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        prev_signal = signal_line.iloc[-2]
        
        if current_macd > current_signal and prev_macd <= prev_signal:
            return 1
        elif current_macd < current_signal and prev_macd >= prev_signal:
            return -1
        elif current_macd > current_signal:
            return 0.5
        elif current_macd < current_signal:
            return -0.5
        else:
            return 0
    except Exception as e:
        print(f"DEBUG: MACD calculation error: {e}")
        return 0

def get_trading_signals():
    """Get trading signals"""
    df = get_klines(limit=100)
    if df is None:
        return None
        
    macd_signal = calculate_macd(df)
    current_price = float(df['close'].iloc[-1])
    
    signals = {
        'macd': macd_signal,
        'timestamp': get_ny_time().isoformat(),
        'price': current_price,
        'interval': config.indicator_interval
    }
    
    if macd_signal == 1:
        signals['consensus'] = 'BUY'
    elif macd_signal == -1:
        signals['consensus'] = 'SELL'
    elif macd_signal == 0.5:
        signals['consensus'] = 'WEAK_BUY'
    elif macd_signal == -0.5:
        signals['consensus'] = 'WEAK_SELL'
    else:
        signals['consensus'] = 'NEUTRAL'
    
    return signals

# Flask routes
@app.route('/')
def index():
    return """
    <html>
        <head><title>SOL Bot Debug</title></head>
        <body>
            <h1>SOL Trading Bot - Debug Mode</h1>
            <button onclick="testEndpoints()">Test All Endpoints</button>
            <button onclick="getBalances()">Get Balances</button>
            <button onclick="getPrice()">Get Price</button>
            <div id="results"></div>
            <script>
                function testEndpoints() {
                    fetch('/api/debug/test_endpoints')
                        .then(r => r.json())
                        .then(data => document.getElementById('results').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>');
                }
                function getBalances() {
                    fetch('/api/debug/balances')
                        .then(r => r.json())
                        .then(data => document.getElementById('results').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>');
                }
                function getPrice() {
                    fetch('/api/debug/price')
                        .then(r => r.json())
                        .then(data => document.getElementById('results').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>');
                }
            </script>
        </body>
    </html>
    """

@app.route('/api/debug/test_endpoints')
def debug_test_endpoints():
    results = test_all_endpoints()
    return jsonify(results)

@app.route('/api/debug/balances')
def debug_balances():
    sol, usdt = get_current_balances()
    return jsonify({'sol_balance': sol, 'usdt_balance': usdt})

@app.route('/api/debug/price')
def debug_price():
    price = get_current_price()
    return jsonify({'price': price})

@app.route('/start', methods=['POST'])
def start_bot():
    if not config.is_configured:
        return jsonify({'status': 'error', 'message': 'API not configured'})
    
    # Test endpoints first
    results = test_all_endpoints()
    
    # Check if any endpoint works
    working_endpoints = []
    for endpoint, result in results.items():
        if 'error' not in result:
            working_endpoints.append(endpoint)
    
    if not working_endpoints:
        return jsonify({'status': 'error', 'message': 'No API endpoints working', 'debug': results})
    
    if not trading_state.is_running:
        trading_state.is_running = True
        # Start a simple monitoring loop instead of full trading
        threading.Thread(target=monitoring_loop, daemon=True).start()
        return jsonify({'status': 'success', 'message': 'Bot started in monitoring mode', 'working_endpoints': working_endpoints})
    
    return jsonify({'status': 'info', 'message': 'Bot already running'})

@app.route('/stop', methods=['POST'])
def stop_bot():
    if trading_state.is_running:
        trading_state.is_running = False
        return jsonify({'status': 'success', 'message': 'Bot stopped'})
    return jsonify({'status': 'info', 'message': 'Bot not running'})

def monitoring_loop():
    """Simple monitoring loop that just logs prices and balances"""
    print("DEBUG: Starting monitoring loop")
    while trading_state.is_running:
        try:
            price = get_current_price()
            sol_balance, usdt_balance = get_current_balances()
            
            if price:
                print(f"MONITOR: Price: ${price:.2f}, SOL: {sol_balance:.6f}, USDT: ${usdt_balance:.2f}")
            else:
                print("MONITOR: Failed to get price")
                
            time.sleep(30)  # Check every 30 seconds
            
        except Exception as e:
            print(f"MONITOR: Error: {e}")
            time.sleep(60)

if __name__ == '__main__':
    print("=== SOL BOT DEBUG MODE STARTED ===")
    print("Visit the web interface to test endpoints")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)