import os
import time
import hmac
import hashlib
import base64
import requests
import json
import pandas as pd
import numpy as np
from flask import Flask, jsonify, request, render_template
from datetime import datetime
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
        
        # Trading parameters - FIXED SOL AMOUNT MODE
        self.sol_trade_amount = 0.1  # Default: Buy/Sell 0.1 SOL each time
        self.check_interval = 900  # Check every 15 minutes
        self.indicator_interval = '15m'
        self.supertrend_period = 10
        self.supertrend_multiplier = 3
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9

config = Config()

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

def calculate_supertrend(df, period=10, multiplier=3):
    """Calculate Supertrend indicator"""
    try:
        high = df['high']
        low = df['low']
        close = df['close']
        
        hl = high - low
        hc = abs(high - close.shift())
        lc = abs(low - close.shift())
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        hl_avg = (high + low) / 2
        upper_band = hl_avg + (multiplier * atr)
        lower_band = hl_avg - (multiplier * atr)
        
        supertrend = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)
        
        for i in range(period, len(df)):
            if i == period:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
            else:
                if close.iloc[i] > supertrend.iloc[i-1]:
                    direction.iloc[i] = 1
                    supertrend.iloc[i] = max(lower_band.iloc[i], supertrend.iloc[i-1])
                else:
                    direction.iloc[i] = -1
                    supertrend.iloc[i] = min(upper_band.iloc[i], supertrend.iloc[i-1])
        
        return direction.iloc[-1] if not pd.isna(direction.iloc[-1]) else 0
    except Exception as e:
        print(f"Error calculating Supertrend: {e}")
        return 0

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
            return 1
        else:
            return -1
            
    except Exception as e:
        print(f"Error calculating MACD: {e}")
        return 0

def calculate_fantail_vma(df, length=50, power=2):
    """Calculate Bixord_FantailVMA indicator"""
    try:
        close = df['close']
        volume = df['volume']
        
        vwma_values = []
        
        for i in range(length - 1, len(df)):
            window_close = close.iloc[i - length + 1:i + 1]
            window_volume = volume.iloc[i - length + 1:i + 1]
            
            powered_volume = window_volume ** power
            
            if powered_volume.sum() > 0:
                vwma = (window_close * powered_volume).sum() / powered_volume.sum()
            else:
                vwma = window_close.mean()
            
            vwma_values.append(vwma)
        
        if len(vwma_values) < 2:
            return 0
        
        current_price = close.iloc[-1]
        current_vwma = vwma_values[-1]
        prev_vwma = vwma_values[-2]
        
        if current_price > current_vwma and current_vwma > prev_vwma:
            return 1
        elif current_price < current_vwma and current_vwma < prev_vwma:
            return -1
        else:
            return 0
            
    except Exception as e:
        print(f"Error calculating FantailVMA: {e}")
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
    """Get signals from all three indicators"""
    required_candles = max(200, config.supertrend_period + 50)
    
    df = get_klines(interval=config.indicator_interval, limit=required_candles)
    if df is None or len(df) < 50:
        return None
    
    signals = {
        'supertrend': calculate_supertrend(df, config.supertrend_period, config.supertrend_multiplier),
        'macd': calculate_macd(df, config.macd_fast, config.macd_slow, config.macd_signal),
        'fantail_vma': calculate_fantail_vma(df),
        'timestamp': datetime.now().isoformat(),
        'price': float(df['close'].iloc[-1]),
        'interval': config.indicator_interval
    }
    
    buy_votes = sum([1 for v in [signals['supertrend'], signals['macd'], signals['fantail_vma']] if v == 1])
    sell_votes = sum([1 for v in [signals['supertrend'], signals['macd'], signals['fantail_vma']] if v == -1])
    
    if buy_votes >= 2:
        signals['consensus'] = 'BUY'
    elif sell_votes >= 2:
        signals['consensus'] = 'SELL'
    else:
        signals['consensus'] = 'NEUTRAL'
    
    return signals

def execute_buy_order():
    """Execute buy order for FIXED SOL amount"""
    try:
        if not trading_state.is_running:
            return False
            
        sol_balance, usdt_balance = get_current_balances()
        
        ticker_result = make_api_request('GET', '/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL')
        if 'error' in ticker_result:
            print(f"Failed to get price for buy: {ticker_result.get('message')}")
            return False
        
        data = ticker_result.get('data', {})
        price_field = data.get('close') or data.get('last') or data.get('price')
        if not price_field:
            print("Could not get current SOL price for buy")
            return False
        
        current_price = float(price_field)
        usdt_needed = config.sol_trade_amount * current_price
        
        if usdt_balance < usdt_needed:
            print(f"Insufficient USDT: Need ${usdt_needed:.2f}, have ${usdt_balance:.2f}")
            return False
        
        sol_amount_rounded = round(config.sol_trade_amount, 4)
        
        if sol_amount_rounded < 0.1:
            print(f"Buy amount too small: {sol_amount_rounded} SOL (min: 0.1 SOL)")
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
        print(f"Fixed SOL Amount: {sol_amount_rounded:.4f} SOL")
        print(f"USDT Cost: ${usdt_needed:.2f}")
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
        
        return True
        
    except Exception as e:
        print(f"Error executing buy order: {e}")
        return False

def execute_sell_order():
    """Execute sell order for FIXED SOL amount"""
    try:
        if not trading_state.is_running:
            return False
            
        sol_balance, usdt_balance = get_current_balances()
        
        if sol_balance < config.sol_trade_amount:
            print(f"Insufficient SOL: Need {config.sol_trade_amount} SOL, have {sol_balance} SOL")
            return False
        
        sol_amount_rounded = round(config.sol_trade_amount, 4)
        
        if sol_amount_rounded < 0.1:
            print(f"Sell amount too small: {sol_amount_rounded} SOL")
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
        
        order_data = {
            "symbol": "SOLUSDT_SPBL",
            "side": "sell",
            "orderType": "market",
            "quantity": str(sol_amount_rounded),
            "force": "normal"
        }
        
        print(f"\n{'='*60}")
        print(f"EXECUTING SELL ORDER")
        print(f"Sell Amount: {sol_amount_rounded:.4f} SOL")
        print(f"Current Price: ${current_price:.2f}")
        print(f"Expected USDT: ${sol_amount_rounded * current_price:.2f}")
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
                print(f"Sell order failed: {result.get('message')}")
                return False
        
        print(f"✅ SELL ORDER SUCCESSFUL")
        time.sleep(1)
        get_current_balances()
        
        return True
        
    except Exception as e:
        print(f"Error executing sell order: {e}")
        return False

def trading_loop():
    """Main trading loop - FIXED SOL AMOUNT"""
    print("\n🤖 BOT STARTED - FIXED SOL AMOUNT MODE 🤖")
    print(f"Fixed Amount: {config.sol_trade_amount} SOL per trade")
    print(f"Check Interval: {config.check_interval} seconds")
    print(f"Indicator Interval: {config.indicator_interval}\n")
    
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
            print(f"Trade Amount: {config.sol_trade_amount} SOL")
            print(f"Supertrend: {'🟢' if signals['supertrend'] == 1 else '🔴' if signals['supertrend'] == -1 else '⚪'}")
            print(f"MACD: {'🟢' if signals['macd'] == 1 else '🔴' if signals['macd'] == -1 else '⚪'}")
            print(f"FantailVMA: {'🟢' if signals['fantail_vma'] == 1 else '🔴' if signals['fantail_vma'] == -1 else '⚪'}")
            print(f"CONSENSUS: {signals['consensus']}")
            print(f"Position: {trading_state.last_position or 'NONE'}")
            
            if not trading_state.is_running:
                break
                
            if signals['consensus'] == 'BUY' and trading_state.last_position != 'long':
                print(f"\n🚀 BUY SIGNAL - Buying {config.sol_trade_amount} SOL...")
                
                if execute_buy_order():
                    trading_state.last_position = 'long'
                    trading_state.last_trade_time = datetime.now()
                    trading_state.trade_history.append({
                        'time': datetime.now().isoformat(),
                        'action': 'BUY',
                        'sol_amount': config.sol_trade_amount,
                        'usdt_amount': config.sol_trade_amount * signals['price'],
                        'price': signals['price'],
                        'interval': config.indicator_interval,
                        'signals': signals
                    })
                    print(f"✅ Position: LONG")
                else:
                    print(f"❌ Buy failed")
                    
            elif signals['consensus'] == 'SELL' and trading_state.last_position != 'short':
                print(f"\n📉 SELL SIGNAL - Selling {config.sol_trade_amount} SOL...")
                
                if execute_sell_order():
                    trading_state.last_position = 'short'
                    trading_state.last_trade_time = datetime.now()
                    trading_state.trade_history.append({
                        'time': datetime.now().isoformat(),
                        'action': 'SELL',
                        'sol_amount': config.sol_trade_amount,
                        'usdt_amount': config.sol_trade_amount * signals['price'],
                        'price': signals['price'],
                        'interval': config.indicator_interval,
                        'signals': signals
                    })
                    print(f"✅ Position: SHORT")
                else:
                    print(f"❌ Sell failed")
            else:
                print(f"⏸️  No action")
            
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
    
    return jsonify({'status':'success','message':f'Bot started - {config.sol_trade_amount} SOL per trade'})

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
        'sol_trade_amount':config.sol_trade_amount,
        'check_interval':config.check_interval,
        'indicator_interval':config.indicator_interval,
        'sol_balance':trading_state.current_sol_balance,
        'usdt_balance':trading_state.current_usdt_balance
    })

@app.route('/api/update_settings',methods=['POST'])
def update_settings():
    try:
        sol_trade_amount=float(request.args.get('sol_trade_amount',0.1))
        check_interval=int(request.args.get('check_interval',900))
        indicator_interval=request.args.get('indicator_interval','15m')
        
        if sol_trade_amount<0.1 or sol_trade_amount>100:
            return jsonify({'status':'error','message':'SOL amount must be 0.1-100'})
        
        if check_interval<60:
            return jsonify({'status':'error','message':'Min check interval is 60 sec'})
        
        valid_intervals=['1m','5m','15m','30m','1H','4H','1D']
        if indicator_interval not in valid_intervals:
            return jsonify({'status':'error','message':'Invalid interval'})
        
        config.sol_trade_amount=sol_trade_amount
        config.check_interval=check_interval
        config.indicator_interval=indicator_interval
        
        return jsonify({'status':'success','message':f'Updated: {sol_trade_amount} SOL, {check_interval}s, {indicator_interval}'})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

@app.route('/api/balance')
def get_balance():
    try:
        result=make_api_request('GET','/api/spot/v1/account/assets')
        
        if 'error' in result:
            return jsonify({'status':'error','message':'Failed to get balance'})
        
        sol_balance,usdt_balance=extract_balances(result)
        
        trading_state.current_sol_balance=float(sol_balance)
        trading_state.current_usdt_balance=float(usdt_balance)
        
        return jsonify({'status':'success','sol_balance':sol_balance,'usdt_balance':usdt_balance})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

@app.route('/api/manual_buy',methods=['POST'])
def manual_buy():
    """Execute manual buy order with specified amount"""
    try:
        amount=float(request.args.get('amount',0.1))
        
        if amount<0.1 or amount>100:
            return jsonify({'status':'error','message':'Amount must be 0.1-100 SOL'})
        
        sol_balance,usdt_balance=get_current_balances()
        
        ticker_result=make_api_request('GET','/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL')
        if 'error' in ticker_result:
            return jsonify({'status':'error','message':'Failed to get price'})
        
        data=ticker_result.get('data',{})
        price_field=data.get('close') or data.get('last') or data.get('price')
        if not price_field:
            return jsonify({'status':'error','message':'Could not get current price'})
        
        current_price=float(price_field)
        usdt_needed=amount*current_price
        
        if usdt_balance<usdt_needed:
            return jsonify({'status':'error','message':f'Insufficient USDT: Need ${usdt_needed:.2f}, have ${usdt_balance:.2f}'})
        
        sol_amount_rounded=round(amount,4)
        
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
        print(f"Cost: ${usdt_needed:.2f} USDT")
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
            'time':datetime.now().isoformat(),
            'action':'MANUAL BUY',
            'sol_amount':sol_amount_rounded,
            'usdt_amount':usdt_needed,
            'price':current_price,
            'interval':'manual',
            'signals':{}
        })
        
        return jsonify({'status':'success','message':f'Manual buy successful: {sol_amount_rounded} SOL for ${usdt_needed:.2f}'})
        
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

@app.route('/api/manual_sell',methods=['POST'])
def manual_sell():
    """Execute manual sell order with specified amount"""
    try:
        amount=float(request.args.get('amount',0.1))
        
        if amount<0.1 or amount>100:
            return jsonify({'status':'error','message':'Amount must be 0.1-100 SOL'})
        
        sol_balance,usdt_balance=get_current_balances()
        
        if sol_balance<amount:
            return jsonify({'status':'error','message':f'Insufficient SOL: Need {amount} SOL, have {sol_balance} SOL'})
        
        sol_amount_rounded=round(amount,4)
        
        ticker_result=make_api_request('GET','/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL')
        if 'error' in ticker_result:
            return jsonify({'status':'error','message':'Failed to get price'})
        
        data=ticker_result.get('data',{})
        price_field=data.get('close') or data.get('last') or data.get('price')
        if not price_field:
            return jsonify({'status':'error','message':'Could not get current price'})
        
        current_price=float(price_field)
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
            'time':datetime.now().isoformat(),
            'action':'MANUAL SELL',
            'sol_amount':sol_amount_rounded,
            'usdt_amount':expected_usdt,
            'price':current_price,
            'interval':'manual',
            'signals':{}
        })
        
        return jsonify({'status':'success','message':f'Manual sell successful: {sol_amount_rounded} SOL for ${expected_usdt:.2f}'})
        
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

if __name__=='__main__':
    print("\n"+"="*60)
    print("SOLANA TRADING BOT - FIXED SOL AMOUNT MODE")
    print("="*60)
    print(f"\nFixed Amount: {config.sol_trade_amount} SOL per trade")
    print("Strategy: 2 of 3 indicators must agree")
    print(f"Interval: {config.indicator_interval}")
    print(f"Check: {config.check_interval} seconds")
    print("\nAPI Keys from environment variables:")
    print("- COINCATCH_API_KEY")
    print("- COINCATCH_API_SECRET") 
    print("- COINCATCH_PASSPHRASE")
    print("\nStarting server...")
    print("="*60+"\n")
    
    app.run(debug=True,host='0.0.0.0',port=5000)
