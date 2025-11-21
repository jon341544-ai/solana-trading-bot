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
from datetime import datetime, timedelta
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
        
        # Trading parameters - FIXED SOL AMOUNT MODE
        self.sol_trade_amount = 0.1  # Default: Buy/Sell 0.1 SOL each time
        self.check_interval = 900  # Check every 15 minutes
        self.indicator_interval = '15m'
        self.supertrend_period = 10
        self.supertrend_multiplier = 3
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        # ADX Filter Parameters
        self.adx_period = 14
        self.adx_threshold = 25  # Only trade when ADX is above this value (strong trend)

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
        
        # Performance tracking
        self.performance_data = {
            'starting_balance_usdt': 0.0,
            'starting_timestamp': None,
            'daily_pnl': 0.0,
            'weekly_pnl': 0.0,
            'total_pnl': 0.0,
            'total_pnl_percentage': 0.0,
            'balance_snapshots': [],  # Store balance over time for charts
            'last_24h_snapshot': None,
            'last_7d_snapshot': None
        }
        
trading_state = TradingState()

def calculate_performance_metrics(current_sol_balance, current_usdt_balance, current_sol_price):
    """Calculate P&L metrics based on current balances"""
    try:
        current_total_value = (current_sol_balance * current_sol_price) + current_usdt_balance
        
        # Initialize starting balance if not set
        if trading_state.performance_data['starting_balance_usdt'] == 0:
            trading_state.performance_data['starting_balance_usdt'] = current_total_value
            trading_state.performance_data['starting_timestamp'] = get_ny_time()
            trading_state.performance_data['last_24h_snapshot'] = {
                'timestamp': get_ny_time(),
                'total_value': current_total_value
            }
            trading_state.performance_data['last_7d_snapshot'] = {
                'timestamp': get_ny_time(),
                'total_value': current_total_value
            }
        
        # Calculate total P&L
        starting_balance = trading_state.performance_data['starting_balance_usdt']
        trading_state.performance_data['total_pnl'] = current_total_value - starting_balance
        trading_state.performance_data['total_pnl_percentage'] = (
            (current_total_value - starting_balance) / starting_balance * 100 
            if starting_balance > 0 else 0
        )
        
        # Calculate 24h P&L
        if trading_state.performance_data['last_24h_snapshot']:
            time_diff = get_ny_time() - trading_state.performance_data['last_24h_snapshot']['timestamp']
            if time_diff.total_seconds() > 86400:  # 24 hours
                # Update 24h snapshot
                trading_state.performance_data['last_24h_snapshot'] = {
                    'timestamp': get_ny_time(),
                    'total_value': current_total_value
                }
            
            twenty_four_h_ago_value = trading_state.performance_data['last_24h_snapshot']['total_value']
            trading_state.performance_data['daily_pnl'] = current_total_value - twenty_four_h_ago_value
        
        # Calculate 7d P&L  
        if trading_state.performance_data['last_7d_snapshot']:
            time_diff = get_ny_time() - trading_state.performance_data['last_7d_snapshot']['timestamp']
            if time_diff.total_seconds() > 604800:  # 7 days
                # Update 7d snapshot
                trading_state.performance_data['last_7d_snapshot'] = {
                    'timestamp': get_ny_time(),
                    'total_value': current_total_value
                }
            
            seven_d_ago_value = trading_state.performance_data['last_7d_snapshot']['total_value']
            trading_state.performance_data['weekly_pnl'] = current_total_value - seven_d_ago_value
        
        # Store balance snapshot (keep last 100)
        trading_state.performance_data['balance_snapshots'].append({
            'timestamp': get_ny_time().isoformat(),
            'total_value': current_total_value,
            'sol_balance': current_sol_balance,
            'usdt_balance': current_usdt_balance,
            'sol_price': current_sol_price
        })
        
        # Keep only last 100 snapshots
        if len(trading_state.performance_data['balance_snapshots']) > 100:
            trading_state.performance_data['balance_snapshots'] = trading_state.performance_data['balance_snapshots'][-100:]
            
    except Exception as e:
        print(f"Error calculating performance metrics: {e}")

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
        endpoint = f'/api/mix/v1/market/candles?symbol={symbol_mix}&granularity={granularity}&startTime={start_time}&endTime={end_time}'  # FIXED: endTime not endTime
        
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
        if df is None or len(df) < period:
            print(f"Supertrend: Not enough data (need {period}, have {len(df) if df is not None else 0})")
            return 0
            
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
        
        signal = direction.iloc[-1] if not pd.isna(direction.iloc[-1]) else 0
        print(f"Supertrend signal: {signal}")
        return signal
    except Exception as e:
        print(f"Error calculating Supertrend: {e}")
        return 0

def calculate_macd(df, fast=12, slow=26, signal=9):
    """Calculate MACD indicator"""
    try:
        if df is None or len(df) < slow:
            print(f"MACD: Not enough data (need {slow}, have {len(df) if df is not None else 0})")
            return 0
            
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
            signal = 1
        elif current_macd < current_signal and prev_macd >= prev_signal:
            signal = -1
        elif current_macd > current_signal:
            signal = 1
        else:
            signal = -1
            
        print(f"MACD signal: {signal} (MACD: {current_macd:.4f}, Signal: {current_signal:.4f})")
        return signal
            
    except Exception as e:
        print(f"Error calculating MACD: {e}")
        return 0

def calculate_fantail_vma(df, length=50, power=2):
    """Calculate Bixord_FantailVMA indicator"""
    try:
        if df is None or len(df) < length:
            print(f"FantailVMA: Not enough data (need {length}, have {len(df) if df is not None else 0})")
            return 0
            
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
            signal = 1
        elif current_price < current_vwma and current_vwma < prev_vwma:
            signal = -1
        else:
            signal = 0
            
        print(f"FantailVMA signal: {signal} (Price: {current_price:.2f}, VWMA: {current_vwma:.2f})")
        return signal
            
    except Exception as e:
        print(f"Error calculating FantailVMA: {e}")
        return 0

def calculate_adx(df, period=14):
    """Calculate ADX (Average Directional Index) indicator"""
    try:
        if df is None or len(df) < period * 2:
            print(f"ADX: Not enough data (need {period * 2}, have {len(df) if df is not None else 0})")
            return 0
            
        high = df['high']
        low = df['low']
        close = df['close']
        
        # Calculate True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Calculate +DM and -DM
        plus_dm = high.diff()
        minus_dm = low.diff().abs() * -1
        
        plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
        minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)
        
        # Calculate smoothed values
        tr_smooth = tr.rolling(window=period).mean()
        plus_dm_smooth = pd.Series(plus_dm).rolling(window=period).mean()
        minus_dm_smooth = pd.Series(minus_dm).rolling(window=period).mean()
        
        # Calculate +DI and -DI
        plus_di = 100 * (plus_dm_smooth / tr_smooth)
        minus_di = 100 * (minus_dm_smooth / tr_smooth)
        
        # Calculate DX and ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        adx_value = adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 0
        print(f"ADX: {adx_value:.2f}")
        return adx_value
        
    except Exception as e:
        print(f"Error calculating ADX: {e}")
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

def get_current_sol_price():
    """Get current SOL price directly for display"""
    try:
        ticker_result = make_api_request('GET', '/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL')
        
        if 'error' in ticker_result:
            print(f"Failed to get SOL price: {ticker_result.get('message')}")
            return None
        
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
                current_price = ticker_result.get('close') or ticker_result.get('last') or ticker_result.get('price')
        
        if current_price:
            return float(current_price)
        else:
            print(f"Could not parse SOL price from response: {ticker_result}")
            return None
            
    except Exception as e:
        print(f"Error getting SOL price: {e}")
        return None

def get_trading_signals():
    """Get signals from all three indicators plus ADX filter"""
    required_candles = max(200, config.supertrend_period + 50, config.adx_period * 2, 50)
    
    df = get_klines(interval=config.indicator_interval, limit=required_candles)
    if df is None or len(df) < 50:
        print("ERROR: Not enough candle data for indicators")
        return None
    
    print(f"Calculating indicators for {len(df)} candles...")
    
    # Calculate main indicators
    supertrend_signal = calculate_supertrend(df, config.supertrend_period, config.supertrend_multiplier)
    macd_signal = calculate_macd(df, config.macd_fast, config.macd_slow, config.macd_signal)
    fantail_vma_signal = calculate_fantail_vma(df)
    
    # Calculate ADX for trend strength filter
    adx_value = calculate_adx(df, config.adx_period)
    
    # Get current price directly if candle data fails
    current_price = float(df['close'].iloc[-1]) if not df.empty else get_current_sol_price()
    if current_price is None:
        print("ERROR: Could not get current price")
        return None
    
    signals = {
        'supertrend': supertrend_signal,
        'macd': macd_signal,
        'fantail_vma': fantail_vma_signal,
        'adx': adx_value,
        'adx_threshold': config.adx_threshold,
        'timestamp': get_ny_time().isoformat(),
        'price': current_price,
        'interval': config.indicator_interval
    }
    
    buy_votes = sum([1 for v in [signals['supertrend'], signals['macd'], signals['fantail_vma']] if v == 1])
    sell_votes = sum([1 for v in [signals['supertrend'], signals['macd'], signals['fantail_vma']] if v == -1])
    
    # Determine consensus
    if buy_votes >= 2:
        signals['consensus'] = 'BUY'
    elif sell_votes >= 2:
        signals['consensus'] = 'SELL'
    else:
        signals['consensus'] = 'NEUTRAL'
    
    # Apply ADX filter - only trade when trend is strong
    if adx_value >= config.adx_threshold:
        signals['trend_strength'] = 'STRONG'
        signals['adx_filter'] = 'PASS'
    else:
        signals['trend_strength'] = 'WEAK'
        signals['adx_filter'] = 'BLOCK'
        # Override consensus to NEUTRAL if ADX filter blocks the trade
        if signals['consensus'] in ['BUY', 'SELL']:
            signals['consensus'] = 'NEUTRAL (Weak Trend)'
    
    print(f"Final consensus: {signals['consensus']} (Buy votes: {buy_votes}, Sell votes: {sell_votes})")
    return signals

def execute_buy_order():
    """Execute buy order for FIXED SOL amount"""
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
    """Execute sell order - sells actual SOL balance (accounting for fees)"""
    try:
        if not trading_state.is_running:
            return False
            
        sol_balance, usdt_balance = get_current_balances()
        
        # Check if we have at least 90% of the target amount (to account for buy fees)
        minimum_needed = config.sol_trade_amount * 0.9
        
        if sol_balance < minimum_needed:
            print(f"Insufficient SOL: Need at least {minimum_needed:.4f} SOL, have {sol_balance} SOL")
            return False
        
        # Sell the ACTUAL balance we have (not the fixed amount)
        # This accounts for fees from the buy
        # Round DOWN to nearest 0.1 SOL increment (CoinCatch requirement)
        # Example: 0.1410 → 0.1, 0.2456 → 0.2, 0.9812 → 0.9
        sol_amount_rounded = math.floor(sol_balance * 10) / 10
        
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
        print(f"Target Amount: {config.sol_trade_amount:.4f} SOL")
        print(f"Available Balance: {sol_balance:.4f} SOL") 
        print(f"Selling: {sol_amount_rounded:.4f} SOL (actual balance)")
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
        
        return True
        
    except Exception as e:
        print(f"Error executing sell order: {e}")
        return False

def trading_loop():
    """Main trading loop - FIXED SOL AMOUNT with ADX Filter"""
    print("\n🤖 BOT STARTED - FIXED SOL AMOUNT MODE 🤖")
    print(f"Fixed Amount: {config.sol_trade_amount} SOL per trade")
    print(f"Check Interval: {config.check_interval} seconds")
    print(f"Indicator Interval: {config.indicator_interval}")
    print(f"ADX Filter: ON (Threshold: {config.adx_threshold})\n")
    
    # Emergency exit counter
    emergency_exit_count = 0
    
    while trading_state.is_running:
        try:
            if not trading_state.is_running:
                break
                
            signals = get_trading_signals()
            
            if signals is None:
                print("Failed to get signals, retrying...")
                emergency_exit_count += 1
                
                # Emergency exit if we can't get signals for too long
                if emergency_exit_count >= 3 and trading_state.last_position:
                    print("🚨 EMERGENCY: Cannot get signals - exiting position for safety")
                    if trading_state.last_position == 'short':
                        if execute_buy_order():
                            trading_state.last_position = None
                            print("✅ Emergency short cover executed")
                    elif trading_state.last_position == 'long':
                        if execute_sell_order():
                            trading_state.last_position = None
                            print("✅ Emergency long exit executed")
                
                for _ in range(config.check_interval):
                    if not trading_state.is_running:
                        break
                    time.sleep(1)
                continue
            
            # Reset emergency counter if we got signals
            emergency_exit_count = 0
            
            trading_state.last_signals = signals
            sol_balance, usdt_balance = get_current_balances()
            
            # Calculate performance metrics
            calculate_performance_metrics(sol_balance, usdt_balance, signals['price'])
            
            print(f"\n--- Check at {signals['timestamp']} ---")
            print(f"Price: ${signals['price']:.2f}")
            print(f"SOL: {sol_balance:.4f} | USDT: ${usdt_balance:.2f}")
            print(f"Trade Amount: {config.sol_trade_amount} SOL")
            print(f"24h P&L: ${trading_state.performance_data['daily_pnl']:+.2f}")
            print(f"Total P&L: ${trading_state.performance_data['total_pnl']:+.2f} ({trading_state.performance_data['total_pnl_percentage']:+.2f}%)")
            print(f"Supertrend: {'🟢' if signals['supertrend'] == 1 else '🔴' if signals['supertrend'] == -1 else '⚪'}")
            print(f"MACD: {'🟢' if signals['macd'] == 1 else '🔴' if signals['macd'] == -1 else '⚪'}")
            print(f"FantailVMA: {'🟢' if signals['fantail_vma'] == 1 else '🔴' if signals['fantail_vma'] == -1 else '⚪'}")
            print(f"ADX: {signals['adx']:.2f} (Threshold: {config.adx_threshold}) - Trend: {signals['trend_strength']}")
            print(f"ADX Filter: {signals['adx_filter']}")
            print(f"CONSENSUS: {signals['consensus']}")
            print(f"Position: {trading_state.last_position or 'NONE'}")
            
            if not trading_state.is_running:
                break
                
            # NEW: Safety exit if position held too long (4 hours)
            if trading_state.last_trade_time and trading_state.last_position:
                time_in_position = (get_ny_time() - trading_state.last_trade_time).total_seconds()
                if time_in_position > 14400:  # 4 hours
                    print(f"⏰ Safety exit: Position held for {time_in_position/3600:.1f} hours")
                    if trading_state.last_position == 'short':
                        if execute_buy_order():
                            trading_state.last_position = None
                            print("✅ Safety short cover executed")
                    elif trading_state.last_position == 'long':
                        if execute_sell_order():
                            trading_state.last_position = None
                            print("✅ Safety long exit executed")
                    continue
                
            # Only execute trades if ADX filter passes (strong trend)
            if signals['consensus'] == 'BUY' and trading_state.last_position != 'long' and signals['adx_filter'] == 'PASS':
                print(f"\n🚀 STRONG TREND BUY SIGNAL - Buying {config.sol_trade_amount} SOL...")
                
                if execute_buy_order():
                    trading_state.last_position = 'long'
                    trading_state.last_trade_time = get_ny_time()
                    trading_state.trade_history.append({
                        'time': get_ny_time().isoformat(),
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
                    
            elif signals['consensus'] == 'SELL' and trading_state.last_position != 'short' and signals['adx_filter'] == 'PASS':
                print(f"\n📉 STRONG TREND SELL SIGNAL - Selling {config.sol_trade_amount} SOL...")
                
                if execute_sell_order():
                    trading_state.last_position = 'short'
                    trading_state.last_trade_time = get_ny_time()
                    trading_state.trade_history.append({
                        'time': get_ny_time().isoformat(),
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
                if signals['adx_filter'] == 'BLOCK':
                    print(f"⏸️  No action - Weak trend (ADX: {signals['adx']:.2f} < {config.adx_threshold})")
                else:
                    print(f"⏸️  No action - No clear signal")
            
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
    # Get current SOL price for display even if bot is stopped
    current_sol_price = get_current_sol_price()
    
    return jsonify({
        'status':'success',
        'is_running':trading_state.is_running,
        'last_position':trading_state.last_position,
        'last_trade_time':trading_state.last_trade_time.isoformat() if trading_state.last_trade_time else None,
        'signals':trading_state.last_signals,
        'trade_history':trading_state.trade_history,
        'performance_data': trading_state.performance_data,
        'sol_trade_amount':config.sol_trade_amount,
        'check_interval':config.check_interval,
        'indicator_interval':config.indicator_interval,
        'adx_threshold': config.adx_threshold,
        'sol_balance':trading_state.current_sol_balance,
        'usdt_balance':trading_state.current_usdt_balance,
        'current_sol_price': current_sol_price  # Add direct price for display
    })

@app.route('/api/update_settings',methods=['POST'])
def update_settings():
    try:
        sol_trade_amount=float(request.args.get('sol_trade_amount',0.1))
        check_interval=int(request.args.get('check_interval',900))
        indicator_interval=request.args.get('indicator_interval','15m')
        adx_threshold=float(request.args.get('adx_threshold',25))
        
        if sol_trade_amount<0.1 or sol_trade_amount>100:
            return jsonify({'status':'error','message':'SOL amount must be 0.1-100'})
        
        if check_interval<60:
            return jsonify({'status':'error','message':'Min check interval is 60 sec'})
        
        valid_intervals=['1m','5m','15m','30m','1H','4H','1D']
        if indicator_interval not in valid_intervals:
            return jsonify({'status':'error','message':'Invalid interval'})
        
        if adx_threshold < 10 or adx_threshold > 50:
            return jsonify({'status':'error','message':'ADX threshold must be 10-50'})
        
        config.sol_trade_amount=sol_trade_amount
        config.check_interval=check_interval
        config.indicator_interval=indicator_interval
        config.adx_threshold=adx_threshold
        
        return jsonify({'status':'success','message':f'Updated: {sol_trade_amount} SOL, {check_interval}s, {indicator_interval}, ADX: {adx_threshold}'})
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
        
        # Try to get price with better error handling
        ticker_result=make_api_request('GET','/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL')
        
        print(f"Manual buy - Ticker response: {ticker_result}")  # Debug log
        
        if 'error' in ticker_result:
            return jsonify({'status':'error','message':'Failed to get price'})
        
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
                current_price = ticker_result.get('close') or ticker_result.get('last') or ticker_result.get('price')
        
        if not current_price:
            print(f"Could not parse price from: {ticker_result}")
            return jsonify({'status':'error','message':'Could not get current price'})
        
        current_price=float(current_price)
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
            'time':get_ny_time().isoformat(),
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
        
        # If trying to sell close to what we have, just sell everything
        # This accounts for small differences due to fees
        if amount > sol_balance * 0.95 and sol_balance >= amount * 0.95:
            print(f"Requested {amount} SOL, have {sol_balance} SOL - selling all available")
            sol_amount_rounded = round(sol_balance, 4)
        elif sol_balance < amount:
            return jsonify({'status':'error','message':f'Insufficient SOL: Need {amount} SOL, have {sol_balance} SOL'})
        else:
            sol_amount_rounded = round(amount, 4)
        
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
            'time':get_ny_time().isoformat(),
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
    print("Strategy: 2 of 3 indicators must agree + ADX Trend Filter")
    print(f"ADX Filter: Only trade when ADX > {config.adx_threshold} (strong trend)")
    print(f"Interval: {config.indicator_interval}")
    print(f"Check: {config.check_interval} seconds")
    print("NEW SAFETY FEATURES:")
    print("- Emergency exit if indicators fail")
    print("- 4-hour maximum position time")
    print("- Better indicator debugging")
    print("- Direct SOL price fetching")
    print("\nAPI Keys from environment variables:")
    print("- COINCATCH_API_KEY")
    print("- COINCATCH_API_SECRET") 
    print("- COINCATCH_PASSPHRASE")
    print("\nStarting server...")
    print("="*60+"\n")
    
    app.run(debug=True,host='0.0.0.0',port=5000)