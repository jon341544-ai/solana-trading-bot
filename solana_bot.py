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
        timeout = 5
        
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

def get_klines(symbol='SOLUSDT_SPBL', interval=None, limit=100):
    """Fetch candlestick data"""
    if interval is None:
        interval = config.indicator_interval
        
    try:
        if not trading_state.is_running:
            return None
            
        import time
        end_time = int(time.time() * 1000)
        
        interval_minutes = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1H': 60, '4H': 240, '1D': 1440}
        minutes_per_candle = interval_minutes.get(interval, 15)
        start_time = end_time - (limit * minutes_per_candle * 60 * 1000)
        
        interval_map = {'1m': '60', '5m': '300', '15m': '900', '30m': '1800', '1H': '3600', '4H': '14400', '1D': '86400'}
        granularity = interval_map.get(interval, '900')
        
        symbol_mix = symbol.replace('_SPBL', '_UMCBL')
        endpoint = f'/api/mix/v1/market/candles?symbol={symbol_mix}&granularity={granularity}&startTime={start_time}&endTime={end_time}'
        
        print(f"Getting {interval} candles...")
        result = make_api_request('GET', endpoint)
        
        if not trading_state.is_running:
            return None
        
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
        current_histogram = histogram.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        prev_signal = signal_line.iloc[-2]
        prev_histogram = histogram.iloc[-2]
        
        # Strong buy signal: MACD crosses above signal line AND histogram is positive and increasing
        if current_macd > current_signal and prev_macd <= prev_signal and current_histogram > 0 and current_histogram > prev_histogram:
            return 1
        # Strong sell signal: MACD crosses below signal line AND histogram is negative and decreasing
        elif current_macd < current_signal and prev_macd >= prev_signal and current_histogram < 0 and current_histogram < prev_histogram:
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
    """Get current SOL and USDT balances"""
    try:
        result = make_api_request('GET', '/api/spot/v1/account/assets')
        
        if 'error' in result:
            print(f"Failed to get balances: {result.get('message')}")
            return 0.0, 0.0
        
        sol_balance = 0.0
        usdt_balance = 0.0
        
        if result and 'data' in result:
            assets = result['data']
            if isinstance(assets, list):
                for asset in assets:
                    coin_name = asset.get('coinName', '').upper()
                    available = asset.get('available', '0')
                    
                    if coin_name == 'SOL':
                        sol_balance = float(available) if available else 0.0
                    elif coin_name == 'USDT':
                        usdt_balance = float(available) if available else 0.0
        
        trading_state.current_sol_balance = sol_balance
        trading_state.current_usdt_balance = usdt_balance
        
        return sol_balance, usdt_balance
    except Exception as e:
        print(f"Error getting balances: {e}")
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

def execute_buy_order():
    """Execute buy order for DYNAMIC amount (percentage or fixed)"""
    try:
        if not trading_state.is_running:
            return False
            
        sol_balance, usdt_balance = get_current_balances()
        
        # Try to get price with better error handling
        ticker_result = make_api_request('GET', '/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL')
        
        print(f"Ticker response: {ticker_result}")  # Debug log
        
        if 'error' in ticker_result:
            print(f"Failed to get price for buy: {ticker_result.get('message')}")
            return False
        
        # Handle different response formats
        current_price = None
        if isinstance(ticker_result, dict):
            if 'data' in ticker_result:
                data = ticker_result['data']
                if isinstance(data, dict):
                    current_price = data.get('close') or data.get('last') or data.get('price') or data.get('lastPr')
                elif isinstance(data, list) and len(data) > 0:
                    current_price = data[0].get('close') or data[0].get('last') or data[0].get('price')
            else:
                # Response might be the data directly
                current_price = ticker_result.get('close') or ticker_result.get('last') or ticker_result.get('price')
        
        if not current_price:
            print(f"Could not parse SOL price from response: {ticker_result}")
            return False
        
        current_price = float(current_price)
        
        # --- Calculate SOL amount based on trade type ---
        if config.trade_type == 'percentage':
            usdt_to_spend = usdt_balance * (config.trade_percentage / 100.0)
            sol_amount = usdt_to_spend / current_price
            print(f"Percentage Buy: {config.trade_percentage}% of ${usdt_balance:.2f} USDT = ${usdt_to_spend:.2f} USDT")
        else: # fixed
            sol_amount = config.sol_trade_amount
            usdt_to_spend = sol_amount * current_price
            print(f"Fixed Buy: {sol_amount:.4f} SOL = ${usdt_to_spend:.2f} USDT")
            
        if usdt_balance < usdt_to_spend:
            print(f"Insufficient USDT: Need ${usdt_to_spend:.2f}, have ${usdt_balance:.2f}")
            return False
        
        sol_amount_rounded = round(sol_amount, 4)
        
        if sol_amount_rounded < 0.01:
            print(f"Buy amount too small: {sol_amount_rounded} SOL (min: 0.01 SOL)")
            return False
        
        order_data = {
            "symbol": "SOLUSDT_SPBL",
            "side": "buy",
            "orderType": "market",
            "quantity": str(sol_amount_rounded),
            "force": "normal"
        }
        
        print(f"\n{'='*60}")
        print(f"EXECUTING BUY ORDER")
        print(f"SOL Amount: {sol_amount_rounded:.4f} SOL")
        print(f"USDT Cost: ${usdt_to_spend:.2f}")
        print(f"Current Price: ${current_price:.2f}")
        print(f"{'='*60}\n")
        
        result = make_api_request('POST', '/api/spot/v1/trade/orders', order_data)
        
        if not trading_state.is_running:
            return False
            
        if 'error' in result:
            print(f"Market order failed, trying limit order...")
            limit_price = round(current_price * 1.005, 2)
            
            limit_order_data = {
                "symbol": "SOLUSDT_SPBL",
                "side": "buy",
                "orderType": "limit",
                "price": str(limit_price),
                "quantity": str(sol_amount_rounded),
                "force": "normal"
            }
            result = make_api_request('POST', '/api/spot/v1/trade/orders', limit_order_data)
            
            if 'error' in result:
                print(f"Buy order failed: {result.get('message')}")
                return False
        
        print(f"✅ BUY ORDER SUCCESSFUL")
        time.sleep(1)
        get_current_balances()
        
        return sol_amount_rounded, usdt_to_spend, current_price
        
    except Exception as e:
        print(f"Error executing buy order: {e}")
        return False

def execute_sell_order():
    """Execute sell order - sells DYNAMIC amount (percentage or fixed)"""
    try:
        if not trading_state.is_running:
            return False
            
        sol_balance, usdt_balance = get_current_balances()
        
        # --- Calculate SOL amount to sell based on trade type ---
        if config.trade_type == 'percentage':
            sol_amount_to_sell = sol_balance * (config.trade_percentage / 100.0)
            print(f"Percentage Sell: {config.trade_percentage}% of {sol_balance:.4f} SOL")
        else: # fixed
            sol_amount_to_sell = config.sol_trade_amount
            print(f"Fixed Sell: {sol_amount_to_sell:.4f} SOL")
            
        if sol_balance < sol_amount_to_sell:
            print(f"Insufficient SOL: Need {sol_amount_to_sell:.4f} SOL, have {sol_balance:.4f} SOL")
            return False
        
        # Round to 4 decimal places for SOL
        sol_amount_rounded = round(sol_amount_to_sell, 4)
        
        if sol_amount_rounded < 0.01:
            print(f"Sell amount too small: {sol_amount_rounded} SOL (min: 0.01 SOL)")
            return False
        
        ticker_result = make_api_request('GET', '/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL')
        if 'error' in ticker_result:
            print(f"Failed to get price for sell: {ticker_result.get('message')}")
            return False
        
        data = ticker_result.get('data', {})
        price_field = data.get('close') or data.get('last') or data.get('price')
        if not price_field:
            print("Could not get current SOL price for sell")
            return False
        
        current_price = float(price_field)
        expected_usdt = sol_amount_rounded * current_price
        
        order_data = {
            "symbol": "SOLUSDT_SPBL",
            "side": "sell",
            "orderType": "market",
            "quantity": str(sol_amount_rounded),
            "force": "normal"
        }
        
        print(f"\n{'='*60}")
        print(f"EXECUTING SELL ORDER")
        print(f"Selling: {sol_amount_rounded:.4f} SOL")
        print(f"Current Price: ${current_price:.2f}")
        print(f"Expected USDT: ${expected_usdt:.2f}")
        print(f"{'='*60}\n")
        
        result = make_api_request('POST', '/api/spot/v1/trade/orders', order_data)
        
        if not trading_state.is_running:
            return False
            
        if 'error' in result:
            print(f"Market order failed, trying limit order...")
            limit_price = round(current_price * 0.995, 2)
            
            limit_order_data = {
                "symbol": "SOLUSDT_SPBL",
                "side": "sell",
                "orderType": "limit",
                "price": str(limit_price),
                "quantity": str(sol_amount_rounded),
                "force": "normal"
            }
            
            result = make_api_request('POST', '/api/spot/v1/trade/orders', limit_order_data)
            
            if 'error' in result:
                error_msg = result.get('message', 'Unknown error')
                print(f"Sell order failed: {error_msg}")
                print(f"Full API response: {result}")
                
                # Check if it's a minimum order value issue
                if 'minimum' in str(error_msg).lower() or 'insufficient' in str(error_msg).lower():
                    print(f"⚠️  Order value too low: ${sol_amount_rounded * current_price:.2f}")
                    print(f"   CoinCatch may have minimum order value requirement")
                    print(f"   Try buying more SOL to meet minimum sell requirements")
                
                return False
        
        print(f"✅ SELL ORDER SUCCESSFUL")
        time.sleep(1)
        get_current_balances()
        
        return sol_amount_rounded, expected_usdt, current_price
        
    except Exception as e:
        print(f"Error executing sell order: {e}")
        return False

def trading_loop():
    """Main trading loop - MACD Only"""
    print("\n🤖 BOT STARTED - MACD ONLY STRATEGY 🤖")
    print(f"Trade Type: {config.trade_type}")
    if config.trade_type == 'percentage':
        print(f"Trade Percentage: {config.trade_percentage}%")
    else:
        print(f"Fixed SOL Amount: {config.sol_trade_amount} SOL")
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
            print(f"SOL: {sol_balance:.4f} | USDT: ${usdt_balance:.2f}")
            if config.trade_type == 'percentage':
                print(f"Trade Amount: {config.trade_percentage}% of balance")
            else:
                print(f"Trade Amount: {config.sol_trade_amount} SOL")
            
            # Display MACD signal with more detail
            macd_value = signals['macd']
            if macd_value == 1:
                macd_display = "🟢 STRONG BUY (Crossover + Positive Histogram)"
            elif macd_value == -1:
                macd_display = "🔴 STRONG SELL (Crossover + Negative Histogram)"
            elif macd_value == 0.5:
                macd_display = "🟡 WEAK BUY (Above Signal Line)"
            elif macd_value == -0.5:
                macd_display = "🟠 WEAK SELL (Below Signal Line)"
            else:
                macd_display = "⚪ NEUTRAL"
                
            print(f"MACD Signal: {macd_display}")
            print(f"CONSENSUS: {signals['consensus']}")
            print(f"Position: {trading_state.last_position or 'NONE'}")
            
            if not trading_state.is_running:
                break
                
            # Only trade on strong signals (1 or -1)
            if signals['consensus'] == 'BUY' and trading_state.last_position != 'long':
                print(f"\n🚀 STRONG BUY SIGNAL - Executing trade...")
                
                result = execute_buy_order()
                if result:
                    sol_amount, usdt_amount, price = result
                    trading_state.last_position = 'long'
                    trading_state.last_trade_time = get_ny_time()
                    trading_state.trade_history.append({
                        'time': get_ny_time().isoformat(),
                        'action': 'BUY',
                        'sol_amount': sol_amount,
                        'usdt_amount': usdt_amount,
                        'price': price,
                        'interval': config.indicator_interval,
                        'signals': signals
                    })
                    print(f"✅ Position: LONG - Bought {sol_amount:.4f} SOL for ${usdt_amount:.2f}")
                else:
                    print(f"❌ Buy failed")
                    
            elif signals['consensus'] == 'SELL' and trading_state.last_position != 'short':
                print(f"\n📉 STRONG SELL SIGNAL - Executing trade...")
                
                result = execute_sell_order()
                if result:
                    sol_amount, usdt_amount, price = result
                    trading_state.last_position = 'short'
                    trading_state.last_trade_time = get_ny_time()
                    trading_state.trade_history.append({
                        'time': get_ny_time().isoformat(),
                        'action': 'SELL',
                        'sol_amount': sol_amount,
                        'usdt_amount': usdt_amount,
                        'price': price,
                        'interval': config.indicator_interval,
                        'signals': signals
                    })
                    print(f"✅ Position: SHORT - Sold {sol_amount:.4f} SOL for ${usdt_amount:.2f}")
                else:
                    print(f"❌ Sell failed")
            else:
                if signals['consensus'] in ['WEAK_BUY', 'WEAK_SELL']:
                    print(f"⏸️  Weak signal - no action taken")
                else:
                    print(f"⏸️  No action - waiting for strong signal")
            
            if trading_state.is_running:
                for _ in range(config.check_interval):
                    if not trading_state.is_running:
                        break
                    time.sleep(1)
            
        except Exception as e:
            print(f"Error in trading loop: {e}")
            if trading_state.is_running:
                for _ in range(config.check_interval):
                    if not trading_state.is_running:
                        break
                    time.sleep(1)
    
    print("\n🛑 BOT STOPPED")

def extract_balances(balance_data):
    """Extract SOL and USDT balances"""
    sol_balance = '0'
    usdt_balance = '0'
    
    try:
        if balance_data and 'data' in balance_data:
            assets = balance_data['data']
            if isinstance(assets, list):
                for asset in assets:
                    coin_name = asset.get('coinName', '').upper()
                    available = asset.get('available', '0')
                    
                    if coin_name == 'SOL':
                        sol_balance = available
                    elif coin_name == 'USDT':
                        usdt_balance = available
    except Exception:
        pass
    
    return sol_balance, usdt_balance

@app.route('/')
def index():
    return render_template('index.html')

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

@app.route('/api/update_settings',methods=['POST'])
def update_settings():
    try:
        trade_type = request.args.get('trade_type', 'percentage')
        trade_percentage = int(request.args.get('trade_percentage', 50))
        sol_trade_amount = float(request.args.get('sol_trade_amount', 0.1))
        check_interval = int(request.args.get('check_interval', 900))
        indicator_interval = request.args.get('indicator_interval', '15m')
        
        if trade_type not in ['percentage', 'fixed']:
            return jsonify({'status':'error','message':'Trade type must be percentage or fixed'})
        
        if trade_percentage < 1 or trade_percentage > 100:
            return jsonify({'status':'error','message':'Trade percentage must be 1-100'})
        
        if sol_trade_amount < 0.01 or sol_trade_amount > 1000:
            return jsonify({'status':'error','message':'SOL amount must be 0.01-1000'})
        
        if check_interval < 60:
            return jsonify({'status':'error','message':'Min check interval is 60 sec'})
        
        valid_intervals = ['1m','5m','15m','30m','1H','4H','1D']
        if indicator_interval not in valid_intervals:
            return jsonify({'status':'error','message':'Invalid interval'})
        
        config.trade_type = trade_type
        config.trade_percentage = trade_percentage
        config.sol_trade_amount = sol_trade_amount
        config.check_interval = check_interval
        config.indicator_interval = indicator_interval
        
        return jsonify({'status':'success','message':f'Updated: {trade_type} mode, {sol_trade_amount} SOL, {check_interval}s, {indicator_interval}'})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

@app.route('/api/balance')
def get_balance():
    try:
        result = make_api_request('GET','/api/spot/v1/account/assets')
        
        if 'error' in result:
            return jsonify({'status':'error','message':'Failed to get balance'})
        
        sol_balance, usdt_balance = extract_balances(result)
        
        trading_state.current_sol_balance = float(sol_balance)
        trading_state.current_usdt_balance = float(usdt_balance)
        
        return jsonify({'status':'success','sol_balance':sol_balance,'usdt_balance':usdt_balance})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

@app.route('/api/manual_buy',methods=['POST'])
def manual_buy():
    """Execute manual buy order with specified amount (percentage or fixed)"""
    try:
        percentage = request.args.get('percentage')
        sol_amount = request.args.get('sol_amount')
        
        sol_balance, usdt_balance = get_current_balances()
        
        # Try to get price with better error handling
        ticker_result = make_api_request('GET', '/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL')
        
        if 'error' in ticker_result:
            return jsonify({'status':'error','message':'Failed to get price'})
        
        current_price = None
        if isinstance(ticker_result, dict):
            if 'data' in ticker_result:
                data = ticker_result['data']
                if isinstance(data, dict):
                    current_price = data.get('close') or data.get('last') or data.get('price') or data.get('lastPr')
                elif isinstance(data, list) and len(data) > 0:
                    current_price = data[0].get('close') or data[0].get('last') or data[0].get('price')
            else:
                current_price = ticker_result.get('close') or ticker_result.get('last') or ticker_result.get('price')
        
        if not current_price:
            return jsonify({'status':'error','message':'Could not get current price'})
        
        current_price = float(current_price)
        
        if percentage:
            percentage = int(percentage)
            if percentage < 1 or percentage > 100:
                return jsonify({'status':'error','message':'Percentage must be 1-100'})
            
            usdt_to_spend = usdt_balance * (percentage / 100.0)
            sol_amount_to_buy = usdt_to_spend / current_price
            
            if usdt_balance < usdt_to_spend:
                return jsonify({'status':'error','message':f'Insufficient USDT: Need ${usdt_to_spend:.2f}, have ${usdt_balance:.2f}'})
            
            log_message = f'Manual BUY of {percentage}% of USDT (${usdt_to_spend:.2f})'
            
        elif sol_amount:
            sol_amount_to_buy = float(sol_amount)
            if sol_amount_to_buy < 0.01 or sol_amount_to_buy > 1000:
                return jsonify({'status':'error','message':'SOL amount must be 0.01-1000 SOL'})
            
            usdt_to_spend = sol_amount_to_buy * current_price
            
            if usdt_balance < usdt_to_spend:
                return jsonify({'status':'error','message':f'Insufficient USDT: Need ${usdt_to_spend:.2f}, have ${usdt_balance:.2f}'})
            
            log_message = f'Manual BUY of {sol_amount_to_buy} SOL'
            
        else:
            return jsonify({'status':'error','message':'Missing percentage or sol_amount parameter'})
            
        sol_amount_rounded = round(sol_amount_to_buy, 4)
        
        order_data={
            "symbol":"SOLUSDT_SPBL",
            "side":"buy",
            "orderType":"market",
            "quantity":str(sol_amount_rounded),
            "force":"normal"
        }
        
        print(f"\n{'='*60}")
        print(f"MANUAL BUY ORDER")
        print(f"Amount: {sol_amount_rounded:.4f} SOL")
        print(f"Cost: ${usdt_to_spend:.2f} USDT")
        print(f"Price: ${current_price:.2f}")
        print(f"{'='*60}\n")
        
        result=make_api_request('POST','/api/spot/v1/trade/orders',order_data)
        
        if 'error' in result:
            limit_price=round(current_price*1.005,2)
            limit_order_data={
                "symbol":"SOLUSDT_SPBL",
                "side":"buy",
                "orderType":"limit",
                "price":str(limit_price),
                "quantity":str(sol_amount_rounded),
                "force":"normal"
            }
            result=make_api_request('POST','/api/spot/v1/trade/orders',limit_order_data)
            
            if 'error' in result:
                return jsonify({'status':'error','message':f"Buy failed: {result.get('message')}"})
        
        print(f"✅ MANUAL BUY SUCCESSFUL")
        time.sleep(1)
        get_current_balances()
        
        trading_state.trade_history.append({
            'time':get_ny_time().isoformat(),
            'action':'MANUAL BUY',
            'sol_amount':sol_amount_rounded,
            'usdt_amount':sol_amount_rounded * current_price,
            'price':current_price,
            'interval':'manual',
            'signals':{}
        })
        
        return jsonify({'status':'success','message':f'{log_message} successful: {sol_amount_rounded:.4f} SOL for ${usdt_to_spend:.2f}'})
        
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

@app.route('/api/manual_sell',methods=['POST'])
def manual_sell():
    """Execute manual sell order with specified amount (percentage or fixed)"""
    try:
        percentage = request.args.get('percentage')
        sol_amount = request.args.get('sol_amount')
        
        sol_balance, usdt_balance = get_current_balances()
        
        # Try to get price with better error handling
        ticker_result = make_api_request('GET', '/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL')
        
        if 'error' in ticker_result:
            return jsonify({'status':'error','message':'Failed to get price'})
        
        data=ticker_result.get('data',{})
        price_field=data.get('close') or data.get('last') or data.get('price')
        if not price_field:
            return jsonify({'status':'error','message':'Could not get current price'})
        
        current_price=float(price_field)
        
        if percentage:
            percentage = int(percentage)
            if percentage < 1 or percentage > 100:
                return jsonify({'status':'error','message':'Percentage must be 1-100'})
            
            sol_amount_to_sell = sol_balance * (percentage / 100.0)
            
            if sol_balance < sol_amount_to_sell:
                return jsonify({'status':'error','message':f'Insufficient SOL: Need {sol_amount_to_sell:.4f} SOL, have {sol_balance:.4f} SOL'})
            
            log_message = f'Manual SELL of {percentage}% of SOL ({sol_amount_to_sell:.4f} SOL)'
            
        elif sol_amount:
            sol_amount_to_sell = float(sol_amount)
            if sol_amount_to_sell < 0.01 or sol_amount_to_sell > 1000:
                return jsonify({'status':'error','message':'SOL amount must be 0.01-1000 SOL'})
            
            if sol_balance < sol_amount_to_sell:
                return jsonify({'status':'error','message':f'Insufficient SOL: Need {sol_amount_to_sell} SOL, have {sol_balance} SOL'})
            
            log_message = f'Manual SELL of {sol_amount_to_sell} SOL'
            
        else:
            return jsonify({'status':'error','message':'Missing percentage or sol_amount parameter'})
            
        sol_amount_rounded=round(sol_amount_to_sell,4)
        expected_usdt=sol_amount_rounded*current_price
        
        order_data={
            "symbol":"SOLUSDT_SPBL",
            "side":"sell",
            "orderType":"market",
            "quantity":str(sol_amount_rounded),
            "force":"normal"
        }
        
        print(f"\n{'='*60}")
        print(f"MANUAL SELL ORDER")
        print(f"Amount: {sol_amount_rounded:.4f} SOL")
        print(f"Expected: ${expected_usdt:.2f} USDT")
        print(f"Price: ${current_price:.2f}")
        print(f"{'='*60}\n")
        
        result=make_api_request('POST','/api/spot/v1/trade/orders',order_data)
        
        if 'error' in result:
            limit_price=round(current_price*0.995,2)
            limit_order_data={
                "symbol":"SOLUSDT_SPBL",
                "side":"sell",
                "orderType":"limit",
                "price":str(limit_price),
                "quantity":str(sol_amount_rounded),
                "force":"normal"
            }
            result=make_api_request('POST','/api/spot/v1/trade/orders',limit_order_data)
            
            if 'error' in result:
                return jsonify({'status':'error','message':f"Sell failed: {result.get('message')}"})
        
        print(f"✅ MANUAL SELL SUCCESSFUL")
        time.sleep(1)
        get_current_balances()
        
        trading_state.trade_history.append({
            'time':get_ny_time().isoformat(),
            'action':'MANUAL SELL',
            'sol_amount':sol_amount_rounded,
            'usdt_amount':expected_usdt,
            'price':current_price,
            'interval':'manual',
            'signals':{}
        })
        
        return jsonify({'status':'success','message':f'{log_message} successful: {sol_amount_rounded:.4f} SOL for ${expected_usdt:.2f}'})
        
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

if __name__=='__main__':
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
    print("\nAPI Keys from environment variables:")
    print("- COINCATCH_API_KEY")
    print("- COINCATCH_API_SECRET") 
    print("- COINCATCH_PASSPHRASE")
    print("\nStarting server...")
    print("="*60+"\n")
    
    app.run(debug=True,host='0.0.0.0',port=5000)