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
        
        # Trading parameters
        self.symbol = 'SOLUSDT_UMCBL'
        self.margin_coin = 'USDT'
        self.base_asset = 'SOL'
        self.quote_asset = 'USDT'
        
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
        self.product_type = 'umcbl'

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
    """Make authenticated API request"""
    if not config.is_configured:
        return {'error': 'API credentials not configured'}
    
    try:
        timestamp = str(int(time.time() * 1000))
        
        # Build query string for GET requests
        query_string = ""
        if params and method.upper() == 'GET':
            query_string = '?' + '&'.join([f"{k}={v}" for k, v in params.items()])
            full_endpoint = endpoint + query_string
        else:
            full_endpoint = endpoint
            
        body_string = json.dumps(data) if data else ''
        message = f"{timestamp}{method.upper()}{full_endpoint}{body_string}"
        
        print(f"DEBUG: Signing message: {message}")
        
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
        timeout = 10
        
        print(f"DEBUG: Making {method} request to: {url}")
        
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, timeout=timeout)
        else:
            response = requests.post(url, headers=headers, json=data, timeout=timeout)
        
        print(f"DEBUG: Response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"DEBUG: Non-200 response: {response.text}")
            
        if response.headers.get('content-type', '').startswith('application/json'):
            response_data = response.json()
        else:
            return {'error': f'HTTP {response.status_code}', 'message': response.text}
        
        print(f"DEBUG: Full API response: {response_data}")
        
        if response.status_code == 200:
            return response_data
        else:
            error_msg = response_data.get('msg', response_data.get('message', str(response_data)))
            return {'error': f'HTTP {response.status_code}', 'message': error_msg}
            
    except Exception as e:
        print(f"Request failed: {str(e)}")
        return {'error': f'Request failed: {str(e)}'}

def test_api_connection():
    """Test API connection with current credentials"""
    print("Testing API connection...")
    
    # Test with a simple public endpoint first
    result = make_api_request('GET', '/api/mix/v1/market/contracts', {'productType': 'umcbl'})
    
    if 'error' in result:
        print(f"❌ API connection failed: {result.get('message')}")
        return False
    else:
        print("✅ API connection successful!")
        return True

def get_klines(symbol=None, interval=None, limit=100):
    """Fetch candlestick data"""
    if symbol is None:
        symbol = config.symbol
        
    if interval is None:
        interval = config.indicator_interval
        
    try:
        interval_map = {'1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m', '1H': '1H', '4H': '4H', '1D': '1D'}
        granularity = interval_map.get(interval, '15m')
        
        params = {
            'symbol': symbol,
            'granularity': granularity,
            'limit': str(limit)
        }
        
        print(f"Getting {interval} candles for {symbol}...")
        result = make_api_request('GET', '/api/mix/v1/market/candles', params=params)
        
        if 'error' in result:
            print(f"ERROR in klines: {result.get('error')} - {result.get('message')}")
            return None
            
        if isinstance(result, dict) and 'data' in result:
            data = result['data']
        else:
            print(f"ERROR: Unexpected klines format: {result}")
            return None
            
        if not data or len(data) == 0:
            print("ERROR: Empty klines data")
            return None
            
        print(f"Got {len(data)} {interval} candles")
            
        df = pd.DataFrame(data)
        if df.empty:
            return None
            
        # Map columns based on CoinCatch response format
        if len(df.columns) >= 6:
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'quote_volume'][:len(df.columns)]
        else:
            return None
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp').reset_index(drop=True)
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        return df
    except Exception as e:
        print(f"Error fetching klines: {e}")
        return None

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
        
        # Strong buy signal: MACD crosses above signal line
        if current_macd > current_signal and prev_macd <= prev_signal:
            return 1
        # Strong sell signal: MACD crosses below signal line
        elif current_macd < current_signal and prev_macd >= prev_signal:
            return -1
        # Weak buy: MACD above signal line
        elif current_macd > current_signal:
            return 0.5
        # Weak sell: MACD below signal line
        elif current_macd < current_signal:
            return -0.5
        else:
            return 0
            
    except Exception as e:
        print(f"Error calculating MACD: {e}")
        return 0

def get_current_balances():
    """Get current account balances"""
    try:
        # Get account information
        result = make_api_request('GET', '/api/mix/v1/account/account', {
            'symbol': config.symbol,
            'marginCoin': config.margin_coin
        })
        
        if 'error' in result:
            print(f"Failed to get balances: {result.get('message')}")
            return 0.0, 0.0
        
        usdt_balance = 0.0
        sol_balance = 0.0
        
        if result and 'data' in result:
            account_data = result['data']
            usdt_balance = float(account_data.get('available', 0))
            
            # Get positions to determine SOL balance
            positions_result = make_api_request('GET', '/api/mix/v1/position/all-position', {
                'productType': config.product_type
            })
            
            if 'error' not in positions_result and 'data' in positions_result:
                positions = positions_result['data']
                if positions:
                    for position in positions:
                        if position.get('symbol') == config.symbol and position.get('holdSide') == 'long':
                            sol_balance = float(position.get('total', 0))
                            break
        
        trading_state.current_sol_balance = sol_balance
        trading_state.current_usdt_balance = usdt_balance
        
        print(f"DEBUG: Balances - SOL: {sol_balance}, USDT: {usdt_balance}")
        return sol_balance, usdt_balance
        
    except Exception as e:
        print(f"Error getting balances: {e}")
        return 0.0, 0.0

def get_trading_signals():
    """Get signals from MACD indicator only"""
    required_candles = 100
    
    df = get_klines(interval=config.indicator_interval, limit=required_candles)
    if df is None or len(df) < 50:
        print("Failed to get klines data")
        return None
    
    macd_signal = calculate_macd(df, config.macd_fast, config.macd_slow, config.macd_signal)
    
    signals = {
        'macd': macd_signal,
        'timestamp': get_ny_time().isoformat(),
        'price': float(df['close'].iloc[-1]),
        'interval': config.indicator_interval
    }
    
    # Determine consensus based on MACD signal strength
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

def get_current_price():
    """Get the current price of the trading pair"""
    try:
        result = make_api_request('GET', '/api/mix/v1/market/ticker', {
            'symbol': config.symbol
        })
        
        if 'error' in result:
            print(f"Failed to get price: {result.get('message')}")
            return None
        
        current_price = None
        if isinstance(result, dict) and 'data' in result:
            data = result['data']
            if isinstance(data, dict):
                current_price = data.get('last') or data.get('close') or data.get('lastPr')
            elif isinstance(data, list) and len(data) > 0:
                current_price = data[0].get('last') or data[0].get('close')
        
        if not current_price:
            print(f"Could not parse price from response: {result}")
            return None
        
        price_float = float(current_price)
        print(f"DEBUG: Current price: {price_float}")
        return price_float
        
    except Exception as e:
        print(f"Error getting current price: {e}")
        return None

def execute_buy_order():
    """Execute buy order (Open Long)"""
    try:
        if not trading_state.is_running:
            return False
            
        sol_balance, usdt_balance = get_current_balances()
        current_price = get_current_price()
        
        if current_price is None:
            print("Cannot execute buy: No current price")
            return False
        
        quantity = config.trade_amount
        
        order_data = {
            "symbol": config.symbol,
            "marginCoin": config.margin_coin,
            "side": "open_long",
            "orderType": "market",
            "size": str(quantity),
            "productType": config.product_type
        }
        
        print(f"\n{'='*60}")
        print(f"EXECUTING BUY ORDER (OPEN LONG)")
        print(f"SOL Quantity: {quantity:.6f}")
        print(f"Current Price: ${current_price:.2f}")
        print(f"{'='*60}\n")
        
        result = make_api_request('POST', '/api/mix/v1/order/placeOrder', data=order_data)
        
        if not trading_state.is_running:
            return False
            
        if 'error' in result:
            print(f"Buy order failed: {result.get('message')}")
            return False
        
        print(f"✅ BUY ORDER SUCCESSFUL")
        time.sleep(2)
        get_current_balances()
        
        return quantity, quantity * current_price, current_price
        
    except Exception as e:
        print(f"Error executing buy order: {e}")
        return False

def execute_sell_order():
    """Execute sell order (Close Long)"""
    try:
        if not trading_state.is_running:
            return False
            
        sol_balance, usdt_balance = get_current_balances()
        current_price = get_current_price()
        
        if current_price is None:
            print("Cannot execute sell: No current price")
            return False
        
        quantity = min(config.trade_amount, sol_balance)
        
        if quantity < config.min_trade_amount:
            print(f"Sell quantity too small: {quantity}")
            return False
        
        order_data = {
            "symbol": config.symbol,
            "marginCoin": config.margin_coin,
            "side": "close_long",
            "orderType": "market",
            "size": str(quantity),
            "productType": config.product_type
        }
        
        print(f"\n{'='*60}")
        print(f"EXECUTING SELL ORDER (CLOSE LONG)")
        print(f"Closing: {quantity:.6f} SOL")
        print(f"Current Price: ${current_price:.2f}")
        print(f"{'='*60}\n")
        
        result = make_api_request('POST', '/api/mix/v1/order/placeOrder', data=order_data)
        
        if not trading_state.is_running:
            return False
            
        if 'error' in result:
            print(f"Sell order failed: {result.get('message')}")
            return False
        
        print(f"✅ SELL ORDER SUCCESSFUL")
        time.sleep(2)
        get_current_balances()
        
        return quantity, quantity * current_price, current_price
        
    except Exception as e:
        print(f"Error executing sell order: {e}")
        return False

def trading_loop():
    """Main trading loop"""
    print("\n🤖 COINCATCH SOL BOT STARTED 🤖")
    print(f"Trading Pair: {config.symbol}")
    print(f"Trade Amount: {config.trade_amount} SOL")
    print(f"Check Interval: {config.check_interval} seconds")
    
    while trading_state.is_running:
        try:
            if not trading_state.is_running:
                break
                
            signals = get_trading_signals()
            
            if signals is None:
                print("Failed to get signals, waiting...")
                time.sleep(60)
                continue
            
            trading_state.last_signals = signals
            sol_balance, usdt_balance = get_current_balances()
            
            print(f"\n--- Check at {signals['timestamp']} ---")
            print(f"Price: ${signals['price']:.2f}")
            print(f"SOL Position: {sol_balance:.6f} | USDT: ${usdt_balance:.2f}")
            print(f"Signal: {signals['consensus']} (MACD: {signals['macd']})")
            
            # Determine current position
            if sol_balance > config.trade_amount * 0.5:
                current_position = 'SOL'
            else:
                current_position = 'USDT'
                
            trading_state.last_position = current_position
            
            # Trading Logic
            if signals['consensus'] in ['BUY', 'WEAK_BUY'] and current_position == 'USDT':
                print("BUY signal - Executing Buy...")
                trade_result = execute_buy_order()
                if trade_result:
                    amount_traded, cost, price = trade_result
                    trading_state.trade_history.append({
                        'time': get_ny_time().isoformat(),
                        'action': 'BUY',
                        'amount_sol': amount_traded,
                        'cost_usdt': cost,
                        'price_sol': price,
                        'signal': signals['consensus']
                    })
                    trading_state.last_trade_time = get_ny_time().isoformat()
                    
            elif signals['consensus'] in ['SELL', 'WEAK_SELL'] and current_position == 'SOL':
                print("SELL signal - Executing Sell...")
                trade_result = execute_sell_order()
                if trade_result:
                    amount_traded, proceeds, price = trade_result
                    trading_state.trade_history.append({
                        'time': get_ny_time().isoformat(),
                        'action': 'SELL',
                        'amount_sol': amount_traded,
                        'proceeds_usdt': proceeds,
                        'price_sol': price,
                        'signal': signals['consensus']
                    })
                    trading_state.last_trade_time = get_ny_time().isoformat()
                    
            else:
                print(f"No trade - Signal: {signals['consensus']}, Position: {current_position}")
                
            # Wait for next check
            for i in range(config.check_interval):
                if not trading_state.is_running:
                    break
                time.sleep(1)
                
        except Exception as e:
            print(f"Error in trading loop: {e}")
            time.sleep(60)

# Flask Routes
@app.route('/')
def index():
    sol_balance, usdt_balance = get_current_balances()
    sol_price = get_current_price()
    
    if sol_price:
        sol_value = sol_balance * sol_price
        total_value = usdt_balance + sol_value
    else:
        sol_value = 0.0
        total_value = usdt_balance
        
    return render_template('index.html', 
        is_running=trading_state.is_running,
        sol_balance=f"{sol_balance:.6f}",
        usdt_balance=f"{usdt_balance:.2f}",
        sol_price=f"{sol_price:.2f}" if sol_price else "N/A",
        sol_value=f"{sol_value:.2f}",
        total_value=f"{total_value:.2f}",
        last_trade_time=trading_state.last_trade_time or "N/A",
        last_signals=trading_state.last_signals,
        trade_history=trading_state.trade_history[-10:],  # Last 10 trades
        trade_amount=f"{config.trade_amount} SOL",
        check_interval=config.check_interval,
        indicator_interval=config.indicator_interval
    )

@app.route('/start', methods=['POST'])
def start_bot():
    if not config.is_configured:
        return jsonify({'status': 'error', 'message': 'API credentials not configured'})
    
    if not test_api_connection():
        return jsonify({'status': 'error', 'message': 'API connection test failed'})
        
    if not trading_state.is_running:
        trading_state.is_running = True
        threading.Thread(target=trading_loop, daemon=True).start()
        return jsonify({'status': 'success', 'message': 'Bot started'})
    return jsonify({'status': 'info', 'message': 'Bot already running'})

@app.route('/stop', methods=['POST'])
def stop_bot():
    if trading_state.is_running:
        trading_state.is_running = False
        return jsonify({'status': 'success', 'message': 'Bot stopped'})
    return jsonify({'status': 'info', 'message': 'Bot not running'})

@app.route('/api/test_connection', methods=['GET'])
def api_test_connection():
    success = test_api_connection()
    return jsonify({'status': 'success' if success else 'error', 'message': 'Connection test completed'})

@app.route('/api/balances', methods=['GET'])
def api_balances():
    sol_balance, usdt_balance = get_current_balances()
    sol_price = get_current_price()
    return jsonify({
        'sol_balance': sol_balance,
        'usdt_balance': usdt_balance,
        'sol_price': sol_price,
        'sol_value': sol_balance * sol_price if sol_price else 0
    })

@app.route('/api/manual_buy', methods=['POST'])
def manual_buy():
    if not trading_state.is_running:
        return jsonify({'status': 'error', 'message': 'Bot not running'})
    
    result = execute_buy_order()
    if result:
        return jsonify({'status': 'success', 'message': 'Manual buy executed'})
    return jsonify({'status': 'error', 'message': 'Manual buy failed'})

@app.route('/api/manual_sell', methods=['POST'])
def manual_sell():
    if not trading_state.is_running:
        return jsonify({'status': 'error', 'message': 'Bot not running'})
    
    result = execute_sell_order()
    if result:
        return jsonify({'status': 'success', 'message': 'Manual sell executed'})
    return jsonify({'status': 'error', 'message': 'Manual sell failed'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
