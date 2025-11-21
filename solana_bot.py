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
import threading
import logging
from flask import Flask, jsonify, request, render_template
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Try to handle timezone even on older Python versions
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for older python without zoneinfo
    from dateutil.tz import gettz as ZoneInfo

app = Flask(__name__)

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
class Config:
    def __init__(self):
        self.api_key = os.environ.get('COINCATCH_API_KEY', '')
        self.api_secret = os.environ.get('COINCATCH_API_SECRET', '') 
        self.passphrase = os.environ.get('COINCATCH_PASSPHRASE', '')
        self.base_url = "https://api.coincatch.com"
        self.is_configured = bool(self.api_key and self.api_secret and self.passphrase)
        
        # Timezone setting - New York (EST/EDT)
        try:
            self.timezone = ZoneInfo('America/New_York')
        except:
            self.timezone = None # Fallback to system time
        
        # Trading parameters
        self.sol_trade_amount = 0.1  
        self.check_interval = 900  # 15 minutes
        self.indicator_interval = '15m'
        
        # Strategy Params
        self.supertrend_period = 10
        self.supertrend_multiplier = 3
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        
        # Safety Checks
        self.min_usdt_order_value = 10.0  # Minimum order size in USDT to avoid API errors

config = Config()

# --- API SESSION SETUP (Retries) ---
def get_api_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

api_session = get_api_session()

# --- TRADING STATE ---
class TradingState:
    def __init__(self):
        self.is_running = False
        self.stop_event = threading.Event()  # Better thread control
        self.lock = threading.Lock()         # Prevents data corruption
        self.last_position = None
        self.last_trade_time = None
        self.last_signals = {}
        self.trade_history = []
        self.current_sol_balance = 0.0
        self.current_usdt_balance = 0.0

trading_state = TradingState()

def get_ny_time():
    """Get current time in New York timezone"""
    if config.timezone:
        return datetime.now(config.timezone)
    return datetime.now()

def make_api_request(method, endpoint, data=None):
    """Make authenticated API request with retries and error handling"""
    if not config.is_configured:
        return {'error': 'API credentials not configured'}
    
    # Allow asset checks even if stopped, but block trading
    if not trading_state.is_running and endpoint not in ['/api/spot/v1/account/assets']:
        return {'error': 'Bot stopped'}
            
    try:
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
        
        if method.upper() == 'GET':
            response = api_session.get(url, headers=headers, timeout=10)
        else:
            response = api_session.post(url, headers=headers, json=data, timeout=10)
        
        try:
            response_data = response.json()
        except ValueError:
            return {'error': f'HTTP {response.status_code}', 'message': 'Invalid JSON response'}
        
        if response.status_code == 200:
            if response_data.get('code') == '00000': # CoinCatch success code
                return response_data
            # Some endpoints return data directly, others wrap in code/msg
            return response_data
        else:
            logger.error(f"API Error {response.status_code}: {response.text}")
            return {'error': f'HTTP {response.status_code}', 'message': response_data.get('msg', str(response_data))}
            
    except Exception as e:
        logger.error(f"Request Exception: {str(e)}")
        return {'error': f'Request failed: {str(e)}'}

def get_klines(symbol='SOLUSDT_SPBL', interval=None, limit=100):
    """Fetch candlestick data"""
    if interval is None:
        interval = config.indicator_interval
        
    try:
        if not trading_state.is_running:
            return None
            
        end_time = int(time.time() * 1000)
        
        # Map standard intervals to CoinCatch format
        interval_minutes = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1H': 60, '4H': 240, '1D': 1440}
        minutes = interval_minutes.get(interval, 15)
        start_time = end_time - (limit * minutes * 60 * 1000)
        
        granularity_map = {'1m': '60', '5m': '300', '15m': '900', '30m': '1800', '1H': '3600', '4H': '14400', '1D': '86400'}
        granularity = granularity_map.get(interval, '900')
        
        # CoinCatch often splits Spot and Mix (Futures) tickers. 
        # Ensure we are using the correct one for candles.
        # Defaulting to Mix candles for indicators is common if Spot history is limited, 
        # but strictly we should match. Leaving your logic intact but adding safety.
        symbol_req = symbol.replace('_SPBL', '_UMCBL') 
        
        endpoint = f'/api/mix/v1/market/candles?symbol={symbol_req}&granularity={granularity}&startTime={start_time}&endTime={end_time}'
        
        result = make_api_request('GET', endpoint)
        
        if not result or 'error' in result:
            # Fallback: Try Spot Candle Endpoint if Mix fails
            endpoint_spot = f'/api/spot/v1/market/candles?symbol={symbol}&granularity={granularity}&startTime={start_time}&endTime={end_time}'
            result = make_api_request('GET', endpoint_spot)
            
        if not result or 'error' in result:
             logger.warning(f"Could not fetch candles: {result.get('message') if result else 'No response'}")
             return None

        # Parse data
        data = result if isinstance(result, list) else result.get('data', [])
            
        if not data:
            return None
            
        df = pd.DataFrame(data)
        
        # Handle varying column lengths returned by different API versions
        cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        if len(df.columns) >= 6:
             # Slice first 6 columns regardless of extra data
            df = df.iloc[:, :6]
            df.columns = cols
        else:
            return None
        
        # Convert types
        for col in cols[1:]:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        return df
    except Exception as e:
        logger.error(f"Error fetching klines: {e}")
        return None

def calculate_supertrend(df, period=10, multiplier=3):
    """Calculate Supertrend indicator"""
    try:
        high = df['high']
        low = df['low']
        close = df['close']
        
        # ATR Calculation
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
        
        # Initialize first value
        supertrend.iloc[period] = lower_band.iloc[period]
        direction.iloc[period] = 1
        
        for i in range(period + 1, len(df)):
            if close.iloc[i] > supertrend.iloc[i-1]:
                direction.iloc[i] = 1
                supertrend.iloc[i] = max(lower_band.iloc[i], supertrend.iloc[i-1])
            else:
                direction.iloc[i] = -1
                supertrend.iloc[i] = min(upper_band.iloc[i], supertrend.iloc[i-1])
        
        return direction.iloc[-1] if not pd.isna(direction.iloc[-1]) else 0
    except Exception as e:
        logger.error(f"Supertrend calc error: {e}")
        return 0

def calculate_macd(df, fast=12, slow=26, signal=9):
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
            return 1 # Crossover Up
        elif current_macd < current_signal and prev_macd >= prev_signal:
            return -1 # Crossover Down
        elif current_macd > current_signal:
            return 1 # Bullish
        else:
            return -1 # Bearish
    except Exception as e:
        logger.error(f"MACD calc error: {e}")
        return 0

def calculate_fantail_vma(df, length=50, power=2):
    try:
        close = df['close']
        volume = df['volume']
        vwma_values = []
        
        # Need at least 'length' data points
        if len(df) < length:
            return 0

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
            
        if close.iloc[-1] > vwma_values[-1] and vwma_values[-1] > vwma_values[-2]:
            return 1
        elif close.iloc[-1] < vwma_values[-1] and vwma_values[-1] < vwma_values[-2]:
            return -1
        return 0
    except Exception as e:
        logger.error(f"Fantail VMA calc error: {e}")
        return 0

def get_current_price():
    """Helper to get price safely"""
    try:
        ticker_result = make_api_request('GET', '/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL')
        
        current_price = None
        if isinstance(ticker_result, dict):
            data = ticker_result.get('data')
            if isinstance(data, dict):
                current_price = data.get('close') or data.get('last') or data.get('price')
            elif isinstance(data, list) and len(data) > 0:
                current_price = data[0].get('close') or data[0].get('last') or data[0].get('price')
            elif not data: # Root level
                 current_price = ticker_result.get('close') or ticker_result.get('last') or ticker_result.get('price')
                 
        if current_price:
            return float(current_price)
        return None
    except Exception as e:
        logger.error(f"Error getting price: {e}")
        return None

def get_current_balances():
    """Get current SOL and USDT balances with thread safety"""
    try:
        result = make_api_request('GET', '/api/spot/v1/account/assets')
        
        if 'error' in result:
            logger.error(f"Failed to get balances: {result.get('message')}")
            return 0.0, 0.0
        
        sol = 0.0
        usdt = 0.0
        
        if result and 'data' in result:
            assets = result['data']
            if isinstance(assets, list):
                for asset in assets:
                    coin = asset.get('coinName', '').upper()
                    avail = float(asset.get('available', '0'))
                    if coin == 'SOL': sol = avail
                    elif coin == 'USDT': usdt = avail
        
        with trading_state.lock:
            trading_state.current_sol_balance = sol
            trading_state.current_usdt_balance = usdt
        
        return sol, usdt
    except Exception as e:
        logger.error(f"Error getting balances: {e}")
        return 0.0, 0.0

def get_trading_signals():
    """Get signals from all three indicators"""
    try:
        required_candles = max(200, config.supertrend_period + 50)
        df = get_klines(interval=config.indicator_interval, limit=required_candles)
        
        if df is None or len(df) < 50:
            return None
        
        signals = {
            'supertrend': calculate_supertrend(df, config.supertrend_period, config.supertrend_multiplier),
            'macd': calculate_macd(df, config.macd_fast, config.macd_slow, config.macd_signal),
            'fantail_vma': calculate_fantail_vma(df),
            'timestamp': get_ny_time().isoformat(),
            'price': float(df['close'].iloc[-1]),
            'interval': config.indicator_interval
        }
        
        buy_votes = sum(1 for k in ['supertrend', 'macd', 'fantail_vma'] if signals[k] == 1)
        sell_votes = sum(1 for k in ['supertrend', 'macd', 'fantail_vma'] if signals[k] == -1)
        
        if buy_votes >= 2:
            signals['consensus'] = 'BUY'
        elif sell_votes >= 2:
            signals['consensus'] = 'SELL'
        else:
            signals['consensus'] = 'NEUTRAL'
        
        return signals
    except Exception as e:
        logger.error(f"Error generating signals: {e}")
        return None

def execute_buy_order():
    try:
        if not trading_state.is_running: return False
        
        current_price = get_current_price()
        if not current_price: return False
        
        sol_balance, usdt_balance = get_current_balances()
        
        # Calculate cost
        usdt_needed = config.sol_trade_amount * current_price
        
        # Safety Checks
        if usdt_needed < config.min_usdt_order_value:
             logger.warning(f"Order value ${usdt_needed:.2f} too small (Min ${config.min_usdt_order_value})")
             return False
             
        if usdt_balance < usdt_needed:
            logger.warning(f"Insufficient USDT: Have ${usdt_balance:.2f}, Need ${usdt_needed:.2f}")
            return False

        # Rounding: Buy normally allows 4 decimals for SOL
        sol_qty = f"{config.sol_trade_amount:.4f}"
        
        order_data = {
            "symbol": "SOLUSDT_SPBL",
            "side": "buy",
            "orderType": "market",
            "quantity": sol_qty,
            "force": "normal"
        }
        
        logger.info(f"BUYING {sol_qty} SOL at ~${current_price}")
        result = make_api_request('POST', '/api/spot/v1/trade/orders', order_data)
        
        if 'error' in result:
            logger.error(f"Buy failed: {result.get('message')}")
            return False
            
        logger.info("✅ BUY EXECUTED")
        return True
        
    except Exception as e:
        logger.error(f"Buy Exception: {e}")
        return False

def execute_sell_order():
    try:
        if not trading_state.is_running: return False
        
        current_price = get_current_price()
        if not current_price: return False
        
        sol_balance, usdt_balance = get_current_balances()
        
        # Logic: Sell nearly all balance, but safely
        # If balance is very close to target trade amount, sell balance.
        # Otherwise sell target amount if we have it.
        
        trade_amt = config.sol_trade_amount
        amount_to_sell = 0.0
        
        if sol_balance >= trade_amt:
            amount_to_sell = trade_amt
        elif sol_balance > (trade_amt * 0.9):
            # If we have 90% of the amount, just sell what we have (cleanup)
            amount_to_sell = sol_balance
        else:
            logger.warning(f"Insufficient SOL to sell: {sol_balance}")
            return False
            
        # SAFETY ROUNDING:
        # Don't floor/round aggressively. Use 2 decimal places to be safe on CEXs.
        # Or 3 if the exchange supports it. 2 is safest for 'Fixed' sell.
        amount_to_sell = math.floor(amount_to_sell * 100) / 100.0
        
        # Check Min Value
        if (amount_to_sell * current_price) < config.min_usdt_order_value:
             logger.warning(f"Sell value too low: ${amount_to_sell * current_price:.2f}")
             return False

        order_data = {
            "symbol": "SOLUSDT_SPBL",
            "side": "sell",
            "orderType": "market",
            "quantity": f"{amount_to_sell:.2f}", 
            "force": "normal"
        }
        
        logger.info(f"SELLING {amount_to_sell} SOL at ~${current_price}")
        result = make_api_request('POST', '/api/spot/v1/trade/orders', order_data)
        
        if 'error' in result:
            logger.error(f"Sell failed: {result.get('message')}")
            return False
            
        logger.info("✅ SELL EXECUTED")
        return True
        
    except Exception as e:
        logger.error(f"Sell Exception: {e}")
        return False

def trading_loop():
    """Main Loop with Graceful Exit"""
    logger.info(f"BOT STARTED | {config.sol_trade_amount} SOL per trade")
    
    while trading_state.is_running:
        try:
            # Check Stop Signal
            if trading_state.stop_event.is_set():
                break
                
            signals = get_trading_signals()
            
            if signals:
                with trading_state.lock:
                    trading_state.last_signals = signals
                
                sol_bal, usdt_bal = get_current_balances()
                price = signals['price']
                
                logger.info(f"Signal: {signals['consensus']} | Price: ${price} | SOL: {sol_bal:.2f}")
                
                # Logic
                if signals['consensus'] == 'BUY' and trading_state.last_position != 'long':
                    if execute_buy_order():
                        trading_state.last_position = 'long'
                        trading_state.last_trade_time = get_ny_time()
                        
                elif signals['consensus'] == 'SELL' and trading_state.last_position != 'short':
                    if execute_sell_order():
                        trading_state.last_position = 'short'
                        trading_state.last_trade_time = get_ny_time()
            
            # Wait for next interval (Non-blocking sleep)
            # We check the stop_event every 1 second
            for _ in range(config.check_interval):
                if trading_state.stop_event.is_set():
                    break
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Loop Error: {e}")
            time.sleep(5) # Short sleep on error
            
    logger.info("Bot execution stopped.")

# --- FLASK ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/start_bot', methods=['POST'])
def start_bot():
    if trading_state.is_running:
        return jsonify({'status': 'error', 'message': 'Already running'})
    
    if not config.is_configured:
        return jsonify({'status': 'error', 'message': 'API Keys missing'})
        
    trading_state.is_running = True
    trading_state.stop_event.clear()
    
    # Start thread
    t = threading.Thread(target=trading_loop, daemon=True)
    t.start()
    
    return jsonify({'status': 'success', 'message': 'Bot Started'})

@app.route('/api/stop_bot', methods=['POST'])
def stop_bot():
    if not trading_state.is_running:
        return jsonify({'status': 'error', 'message': 'Not running'})
        
    trading_state.is_running = False
    trading_state.stop_event.set() # Signal thread to stop immediately
    return jsonify({'status': 'success', 'message': 'Stopping bot...'})

@app.route('/api/status')
def get_status():
    sol, usdt = get_current_balances()
    with trading_state.lock:
        return jsonify({
            'is_running': trading_state.is_running,
            'last_position': trading_state.last_position,
            'signals': trading_state.last_signals,
            'sol_balance': sol,
            'usdt_balance': usdt,
            'trade_amount': config.sol_trade_amount
        })

if __name__ == '__main__':
    print("\n--- SOLANA BOT (FIXED & OPTIMIZED) ---")
    print("Starting Web Server on Port 5000...")
    # Start Flask without threading=True to avoid duplicate bot threads
    # in dev mode, but since we control the thread manually, it is fine.
    app.run(host='0.0.0.0', port=5000, debug=False) 
