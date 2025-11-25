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
        # CoinCatch Configuration for Mix API
        self.api_key = os.environ.get('COINCATCH_API_KEY', '')
        self.api_secret = os.environ.get('COINCATCH_API_SECRET', '') 
        self.passphrase = os.environ.get('COINCATCH_PASSPHRASE', '')
        self.base_url = "https://api.coincatch.com"
        self.is_configured = bool(self.api_key and self.api_secret and self.passphrase)
        
        # Trading parameters - USING FUTURES SYMBOL
        self.symbol = 'SOLUSDT_UMCBL'  # Using Mix symbol instead of Spot
        self.margin_coin = 'USDT'  # Margin coin for Mix trading
        self.base_asset = 'SOL'
        self.quote_asset = 'USDT'
        
        # Timezone setting - New York (EST/EDT)
        self.timezone = ZoneInfo('America/New_York')
        
        # Trading parameters
        self.trade_type = 'fixed'
        self.trade_amount = 0.1  # Default: 0.1 SOL contracts
        self.check_interval = 900  # Check every 15 minutes
        self.indicator_interval = '15m'
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        
        # Minimum trade amount for SOL/USDT Mix
        self.min_trade_amount = 0.1
        self.product_type = 'umcbl'  # Unified margin contract

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
    """Make authenticated API request for Mix API"""
    if not config.is_configured:
        return {'error': 'API credentials not configured'}
    
    try:
        timestamp = str(int(time.time() * 1000))
        body_string = json.dumps(data) if data else ''
        message = f"{timestamp}{method.upper()}{endpoint}{body_string}"
        
        print(f"Signing message: {message}")
        
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
        timeout = 10
        
        print(f"Making {method} request to: {url}")
        
        if method.upper() == 'GET':
            if data and isinstance(data, dict):
                response = requests.get(url, headers=headers, timeout=timeout, params=data)
            else:
                response = requests.get(url, headers=headers, timeout=timeout)
        else:
            response = requests.post(url, headers=headers, json=data, timeout=timeout)
        
        print(f"Response status: {response.status_code}")
        
        if response.headers.get('content-type', '').startswith('application/json'):
            response_data = response.json()
        else:
            response_text = response.text
            print(f"Non-JSON response: {response_text}")
            return {'error': f'HTTP {response.status_code}', 'message': 'Server returned non-JSON response'}
        
        print(f"API Response: {response_data}")
        
        if response.status_code == 200:
            return response_data
        else:
            error_msg = response_data.get('msg', response_data.get('message', str(response_data)))
            print(f"API error {response.status_code}: {error_msg}")
            return {'error': f'HTTP {response.status_code}', 'message': error_msg}
            
    except requests.exceptions.Timeout:
        print("API request timeout")
        return {'error': 'Timeout', 'message': 'Request timed out'}
    except Exception as e:
        print(f"Request failed: {str(e)}")
        return {'error': f'Request failed: {str(e)}'}

def test_api_connection():
    """Test API connection with current credentials"""
    print("Testing API connection...")
    
    # Test account endpoint
    result = make_api_request('GET', '/api/mix/v1/account/accounts', {
        'symbol': config.symbol,
        'marginCoin': config.margin_coin
    })
    
    if 'error' in result:
        print(f"❌ API connection failed: {result.get('message')}")
        return False
    else:
        print("✅ API connection successful!")
        if 'data' in result:
            print(f"Account data received")
        return True

def get_klines(symbol=None, interval=None, limit=100):
    """Fetch candlestick data using Mix API"""
    if symbol is None:
        symbol = config.symbol
        
    if interval is None:
        interval = config.indicator_interval
        
    try:
        import time
        end_time = int(time.time() * 1000)
        
        interval_map = {'1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m', '1H': '1H', '4H': '4H', '1D': '1D'}
        granularity = interval_map.get(interval, '15m')
        
        # Calculate start time for the required number of candles
        interval_minutes = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1H': 60, '4H': 240, '1D': 1440}
        minutes_per_candle = interval_minutes.get(interval, 15)
        start_time = end_time - (limit * minutes_per_candle * 60 * 1000)
        
        endpoint = f'/api/mix/v1/market/candles?symbol={symbol}&granularity={granularity}&startTime={start_time}&endTime={end_time}'
        
        print(f"Getting {interval} candles for {symbol}...")
        result = make_api_request('GET', endpoint)
        
        if 'error' in result:
            print(f"ERROR in klines: {result.get('error')} - {result.get('message')}")
            return None
            
        if isinstance(result, list):
            data = result
        elif isinstance(result, dict) and 'data' in result:
            data = result['data']
        else:
            print(f"ERROR: Unexpected klines format")
            return None
            
        if not data or len(data) == 0:
            print("ERROR: Empty klines data")
            return None
            
        print(f"Got {len(data)} {interval} candles")
            
        df = pd.DataFrame(data)
        if df.empty:
            return None
            
        # Assuming the same column order as the original BTC bot
        if len(df.columns) >= 6:
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume'] + list(df.columns[6:])
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
        histogram = macd_line - signal_line
        
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
    """Get current account balances using Mix API"""
    try:
        # Use Mix account endpoint
        result = make_api_request('GET', '/api/mix/v1/account/accounts', {
            'symbol': config.symbol,
            'marginCoin': config.margin_coin
        })
        
        if 'error' in result:
            print(f"Failed to get Mix balances: {result.get('message')}")
            return 0.0, 0.0
        
        sol_balance = 0.0
        usdt_balance = 0.0
        
        if result and 'data' in result:
            account_data = result['data']
            # Get available USDT balance
            usdt_balance = float(account_data.get('available', 0))
            
            # Check for open positions to determine SOL "balance"
            positions_result = make_api_request('GET', '/api/mix/v1/position/all-position', {
                'productType': config.product_type
            })
            
            if 'data' in positions_result and positions_result['data']:
                # If we have open positions, calculate equivalent SOL
                for position in positions_result['data']:
                    if position.get('symbol') == config.symbol and position.get('holdSide') == 'long':
                        sol_balance = float(position.get('total', 0))
                        break
        
        trading_state.current_sol_balance = sol_balance
        trading_state.current_usdt_balance = usdt_balance
        
        return sol_balance, usdt_balance
    except Exception as e:
        print(f"Error getting Mix balances: {e}")
        return 0.0, 0.0

def get_trading_signals():
    """Get signals from MACD indicator only"""
    required_candles = 100
    
    df = get_klines(interval=config.indicator_interval, limit=required_candles)
    if df is None or len(df) < 50:
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
        endpoint = f'/api/mix/v1/market/ticker?symbol={config.symbol}'
        ticker_result = make_api_request('GET', endpoint)
        
        if 'error' in ticker_result:
            print(f"Failed to get price: {ticker_result.get('message')}")
            return None
        
        # Handle response format for Mix API
        current_price = None
        if isinstance(ticker_result, dict):
            if 'data' in ticker_result:
                data = ticker_result['data']
                if isinstance(data, dict):
                    current_price = data.get('last') or data.get('close') or data.get('lastPr')
                elif isinstance(data, list) and len(data) > 0:
                    current_price = data[0].get('last') or data[0].get('close')
            else:
                current_price = ticker_result.get('last') or ticker_result.get('close')
        
        if not current_price:
            print(f"Could not parse price from response: {ticker_result}")
            return None
        
        return float(current_price)
        
    except Exception as e:
        print(f"Error getting current price: {e}")
        return None

def execute_buy_order():
    """Execute buy order using Mix API (Open Long)"""
    try:
        if not trading_state.is_running:
            return False
            
        sol_balance, usdt_balance = get_current_balances()
        current_price = get_current_price()
        
        if current_price is None:
            return False
        
        # For Mix trading, we're opening a long position
        quantity = config.trade_amount
        usdt_required = quantity * current_price
        
        print(f"Mix Buy (Open Long): {quantity:.6f} SOL = ${usdt_required:.2f} USDT")
            
        if usdt_balance < usdt_required:
            print(f"Insufficient USDT margin: Need ${usdt_required:.2f}, have ${usdt_balance:.2f}")
            return False
        
        order_data = {
            "symbol": config.symbol,
            "marginCoin": config.margin_coin,
            "side": "open_long",
            "orderType": "market",
            "size": str(quantity),
            "productType": config.product_type
        }
        
        print(f"\n{'='*60}")
        print(f"EXECUTING MIX BUY ORDER (OPEN LONG)")
        print(f"SOL Quantity: {quantity:.6f}")
        print(f"Margin Required: ${usdt_required:.2f}")
        print(f"Current Price: ${current_price:.2f}")
        print(f"{'='*60}\n")
        
        result = make_api_request('POST', '/api/mix/v1/order/placeOrder', order_data)
        
        if not trading_state.is_running:
            return False
            
        if 'error' in result:
            print(f"Mix buy order failed: {result.get('message')}")
            return False
        
        print(f"✅ MIX BUY ORDER SUCCESSFUL")
        time.sleep(1)
        get_current_balances()
        
        return quantity, usdt_required, current_price
        
    except Exception as e:
        print(f"Error executing Mix buy order: {e}")
        return False

def execute_sell_order():
    """Execute sell order using Mix API (Close Long)"""
    try:
        if not trading_state.is_running:
            return False
            
        sol_balance, usdt_balance = get_current_balances()
        current_price = get_current_price()
        
        if current_price is None:
            return False
        
        # For Mix trading, we're closing a long position
        quantity = min(config.trade_amount, sol_balance)
        expected_proceeds = quantity * current_price
            
        if sol_balance < quantity:
            print(f"Insufficient SOL position: Need {quantity:.6f} SOL, have {sol_balance:.6f} SOL")
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
        print(f"EXECUTING MIX SELL ORDER (CLOSE LONG)")
        print(f"Closing: {quantity:.6f} SOL")
        print(f"Current Price: ${current_price:.2f}")
        print(f"Expected Proceeds: ${expected_proceeds:.2f}")
        print(f"{'='*60}\n")
        
        result = make_api_request('POST', '/api/mix/v1/order/placeOrder', order_data)
        
        if not trading_state.is_running:
            return False
            
        if 'error' in result:
            error_msg = result.get('message', 'Unknown error')
            print(f"Mix sell order failed: {error_msg}")
            return False
        
        print(f"✅ MIX SELL ORDER SUCCESSFUL")
        time.sleep(1)
        get_current_balances()
        
        return quantity, expected_proceeds, current_price
        
    except Exception as e:
        print(f"Error executing Mix sell order: {e}")
        return False

# --- Trading Loop and Web Server Endpoints ---

def trading_loop():
    """Main trading loop - MACD Only"""
    print("\n🤖 COINCATCH SOL BOT STARTED - MACD ONLY STRATEGY 🤖")
    print(f"Trading Pair: {config.symbol}")
    print(f"Fixed SOL Amount: {config.trade_amount} SOL")
    print(f"Check Interval: {config.check_interval} seconds")
    print(f"Indicator Interval: {config.indicator_interval}")
    print(f"MACD Settings: Fast={config.macd_fast}, Slow={config.macd_slow}, Signal={config.macd_signal}\n")
    
    while trading_state.is_running:
        try:
            if not trading_state.is_running:
                break
                
            signals = get_trading_signals()
            
            if signals is None:
                print("Failed to get signals, retrying...")
                for _ in range(config.check_interval):
                    if not trading_state.is_running:
                        break
                    time.sleep(1)
                continue
            
            trading_state.last_signals = signals
            sol_balance, usdt_balance = get_current_balances()
            
            print(f"\n--- Check at {signals['timestamp']} ---")
            print(f"Price: ${signals['price']:.2f}")
            print(f"SOL Position: {sol_balance:.6f} | Available USDT: ${usdt_balance:.2f}")
            print(f"Trade Amount: {config.trade_amount} SOL")
            print(f"Signal: {signals['consensus']} (MACD: {signals['macd']})")
            
            # Determine current position
            if sol_balance > config.trade_amount * 0.5:
                current_position = 'SOL'
            else:
                current_position = 'USDT'
                
            trading_state.last_position = current_position
            print(f"Current Position: {current_position}")
            
            # Trading Logic
            if signals['consensus'] in ['BUY', 'WEAK_BUY'] and current_position == 'USDT':
                print("BUY signal detected and currently holding USDT. Executing Buy (Open Long)...")
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
                    trading_state.last_position = 'SOL'
                    
            elif signals['consensus'] in ['SELL', 'WEAK_SELL'] and current_position == 'SOL':
                print("SELL signal detected and currently holding SOL. Executing Sell (Close Long)...")
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
                    trading_state.last_position = 'USDT'
                    
            else:
                print(f"No trade executed. Signal: {signals['consensus']}, Position: {current_position}")
                
            # Wait for the next check interval
            for _ in range(config.check_interval):
                if not trading_state.is_running:
                    break
                time.sleep(1)
                
        except Exception as e:
            print(f"An error occurred in the trading loop: {e}")
            time.sleep(60) # Wait a minute before retrying

# --- Web Server Endpoints ---

@app.route('/')
def index():
    sol_balance, usdt_balance = get_current_balances()
    
    # Get current SOL price for portfolio value calculation
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
        trade_history=trading_state.trade_history,
        trade_amount=f"{config.trade_amount} SOL",
        check_interval=config.check_interval,
        indicator_interval=config.indicator_interval,
        macd_settings=f"Fast={config.macd_fast}, Slow={config.macd_slow}, Signal={config.macd_signal}"
    )

@app.route('/start', methods=['POST'])
def start_bot():
    if not config.is_configured:
        return jsonify({'status': 'error', 'message': 'Configuration missing. Please set COINCATCH_API_KEY, COINCATCH_API_SECRET, and COINCATCH_PASSPHRASE environment variables.'}), 400
    
    # Test connection before starting
    print("Testing API connection before starting bot...")
    if not test_api_connection():
        return jsonify({'status': 'error', 'message': 'API connection test failed. Please check your credentials.'}), 400
        
    if not trading_state.is_running:
        trading_state.is_running = True
        threading.Thread(target=trading_loop).start()
        return jsonify({'status': 'success', 'message': 'CoinCatch SOL trading bot started.'})
    return jsonify({'status': 'info', 'message': 'CoinCatch SOL trading bot is already running.'})

@app.route('/stop', methods=['POST'])
def stop_bot():
    if trading_state.is_running:
        trading_state.is_running = False
        return jsonify({'status': 'success', 'message': 'CoinCatch SOL trading bot stopped.'})
    return jsonify({'status': 'info', 'message': 'CoinCatch SOL trading bot is not running.'})

@app.route('/api/test_connection', methods=['GET'])
def test_connection():
    """Test API connection endpoint"""
    success = test_api_connection()
    if success:
        return jsonify({'status': 'success', 'message': 'API connection test passed'})
    else:
        return jsonify({'status': 'error', 'message': 'API connection test failed'}), 400

@app.route('/api/get_data', methods=['GET'])
def get_data():
    sol_balance, usdt_balance = get_current_balances()
    sol_price = get_current_price()
    
    if sol_price:
        sol_value = sol_balance * sol_price
        total_value = usdt_balance + sol_value
    else:
        sol_value = 0.0
        total_value = usdt_balance
        
    return jsonify({
        'status': 'success',
        'is_running': trading_state.is_running,
        'sol_balance': sol_balance,
        'usdt_balance': usdt_balance,
        'sol_price': sol_price,
        'sol_value': sol_value,
        'total_value': total_value,
        'last_position': trading_state.last_position,
        'last_trade_time': trading_state.last_trade_time,
        'last_signals': trading_state.last_signals,
        'trade_history': trading_state.trade_history,
        'trade_amount': f"{config.trade_amount} SOL",
        'check_interval': config.check_interval,
        'indicator_interval': config.indicator_interval,
    })

@app.route('/api/get_balances', methods=['GET'])
def get_balances_api():
    sol_balance, usdt_balance = get_current_balances()
    sol_price = get_current_price()
    
    if sol_price:
        sol_value = sol_balance * sol_price
        total_value = usdt_balance + sol_value
    else:
        sol_value = 0.0
        total_value = usdt_balance
        
    return jsonify({
        'status': 'success',
        'sol_balance': sol_balance,
        'usdt_balance': usdt_balance,
        'sol_price': sol_price,
        'sol_value': sol_value,
        'total_value': total_value,
        'last_position': trading_state.last_position,
        'last_trade_time': trading_state.last_trade_time,
        'last_signals': trading_state.last_signals,
        'trade_history': trading_state.trade_history,
        'trade_amount': f"{config.trade_amount} SOL",
        'check_interval': config.check_interval,
        'indicator_interval': config.indicator_interval,
    })

@app.route('/api/update_settings', methods=['POST'])
def update_settings():
    try:
        new_trade_amount = request.args.get('trade_amount', type=float)
        new_check_interval = request.args.get('check_interval', type=int)
        new_indicator_interval = request.args.get('indicator_interval', type=str)
        
        if new_trade_amount is not None and new_trade_amount >= config.min_trade_amount:
            config.trade_amount = new_trade_amount
            
        if new_check_interval is not None and new_check_interval >= 60:
            config.check_interval = new_check_interval
            
        if new_indicator_interval in ['1m', '5m', '15m', '30m', '1H', '4H', '1D']:
            config.indicator_interval = new_indicator_interval
            
        return jsonify({'status': 'success', 'message': 'Settings updated.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/api/manual_buy', methods=['POST'])
def manual_buy():
    try:
        if not config.is_configured:
            return jsonify({'status': 'error', 'message': 'API credentials not configured'}), 400
            
        trade_result = execute_buy_order()
        
        if trade_result:
            amount_traded, cost, price = trade_result
            trading_state.trade_history.append({
                'time': get_ny_time().isoformat(),
                'action': 'MANUAL BUY',
                'amount_sol': amount_traded,
                'cost_usdt': cost,
                'price_sol': price,
                'signal': 'MANUAL'
            })
            trading_state.last_trade_time = get_ny_time().isoformat()
            trading_state.last_position = 'SOL'
            return jsonify({'status': 'success', 'message': f'Manual BUY of {amount_traded:.6f} SOL successful.'})
        else:
            return jsonify({'status': 'error', 'message': 'Manual BUY failed. Check logs for details.'}), 400
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/api/manual_sell', methods=['POST'])
def manual_sell():
    try:
        if not config.is_configured:
            return jsonify({'status': 'error', 'message': 'API credentials not configured'}), 400
            
        trade_result = execute_sell_order()
        
        if trade_result:
            amount_traded, proceeds, price = trade_result
            trading_state.trade_history.append({
                'time': get_ny_time().isoformat(),
                'action': 'MANUAL SELL',
                'amount_sol': amount_traded,
                'proceeds_usdt': proceeds,
                'price_sol': price,
                'signal': 'MANUAL'
            })
            trading_state.last_trade_time = get_ny_time().isoformat()
            trading_state.last_position = 'USDT'
            return jsonify({'status': 'success', 'message': f'Manual SELL of {amount_traded:.6f} SOL successful.'})
        else:
            return jsonify({'status': 'error', 'message': 'Manual SELL failed. Check logs for details.'}), 400
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

if __name__ == '__main__':
    # Initial balance check
    get_current_balances()
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))
