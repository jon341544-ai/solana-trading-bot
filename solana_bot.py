import os
import time
import hmac
import hashlib
import base64
import requests
import json
import pandas as pd
import numpy as np
from flask import Flask, jsonify, request
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
        
        # Trading parameters
        self.trade_percentage = 50  # Default: 50% of USDT for SOL buys
        self.check_interval = 900  # Check every 15 minutes (900 seconds)
        self.indicator_interval = '15m'  # Default indicator timeframe
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
        self.last_position = None  # 'long', 'short', or None
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
        # Check if we should stop before making the request
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
        
        # Shorter timeout for faster response
        timeout = 5  # 5 seconds instead of 10
        
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, timeout=timeout)
        else:
            response = requests.post(url, headers=headers, json=data, timeout=timeout)
        
        if response.headers.get('content-type', '').startswith('application/json'):
            response_data = response.json()
        else:
            return {
                'error': f'HTTP {response.status_code}',
                'message': 'Server returned non-JSON response'
            }
        
        if response.status_code == 200:
            return response_data
        else:
            return {
                'error': f'HTTP {response.status_code}',
                'message': response_data.get('msg', str(response_data))
            }
            
    except Exception as e:
        return {'error': f'Request failed: {str(e)}'}

def get_klines(symbol='SOLUSDT_SPBL', interval=None, limit=100):
    """Fetch candlestick data - Using public endpoint that doesn't need authentication"""
    if interval is None:
        interval = config.indicator_interval
        
    try:
        # Check if bot should stop
        if not trading_state.is_running:
            return None
            
        # Try the public ticker endpoint first to see if we can get data
        # Since authenticated spot candles endpoint might not exist, we'll use mix candles with spot symbol
        import time
        end_time = int(time.time() * 1000)
        
        # Adjust limit based on interval to get sufficient historical data
        interval_minutes = {
            '1m': 1,
            '5m': 5,
            '15m': 15,
            '30m': 30,
            '1H': 60,
            '4H': 240,
            '1D': 1440
        }
        minutes_per_candle = interval_minutes.get(interval, 15)
        start_time = end_time - (limit * minutes_per_candle * 60 * 1000)
        
        # Convert interval to granularity (seconds)
        interval_map = {
            '1m': '60',
            '5m': '300', 
            '15m': '900',
            '30m': '1800',
            '1H': '3600',
            '4H': '14400',
            '1D': '86400'
        }
        granularity = interval_map.get(interval, '900')
        
        # Try Mix API candles with proper time parameters
        symbol_mix = symbol.replace('_SPBL', '_UMCBL')  # Convert to mix symbol
        endpoint = f'/api/mix/v1/market/candles?symbol={symbol_mix}&granularity={granularity}&startTime={start_time}&endTime={end_time}'
        
        print(f"DEBUG: Getting {interval} candles - endpoint: {endpoint}")
        result = make_api_request('GET', endpoint)
        
        # Check if bot was stopped during API call
        if not trading_state.is_running:
            return None
            
        print(f"DEBUG: Klines result type: {type(result)}")
        
        if 'error' in result:
            print(f"ERROR in klines: {result.get('error')} - {result.get('message')}")
            return None
            
        # Mix API returns array directly (not wrapped in 'data')
        if isinstance(result, list):
            data = result
        elif isinstance(result, dict) and 'data' in result:
            data = result['data']
        else:
            print(f"ERROR: Unexpected klines format: {type(result)}")
            return None
            
        if not data or len(data) == 0:
            print("ERROR: Empty klines data")
            return None
            
        print(f"DEBUG: Got {len(data)} {interval} candles")
            
        # Convert to dataframe
        df = pd.DataFrame(data)
        if df.empty:
            print("ERROR: Empty dataframe after conversion")
            return None
        
        print(f"DEBUG: DataFrame shape: {df.shape}")
            
        # Mix API returns: [timestamp, open, high, low, close, volume, quote_volume]
        if len(df.columns) >= 6:
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume'] + list(df.columns[6:])
        else:
            print(f"ERROR: Unexpected number of columns: {len(df.columns)}")
            return None
        
        # Convert to numeric
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Keep only what we need
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        print(f"DEBUG: Successfully processed {len(df)} {interval} candles")
        print(f"DEBUG: Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        return df
    except Exception as e:
        print(f"Error fetching klines: {e}")
        import traceback
        traceback.print_exc()
        return None

def calculate_supertrend(df, period=10, multiplier=3):
    """Calculate Supertrend indicator"""
    try:
        high = df['high']
        low = df['low']
        close = df['close']
        
        # Calculate ATR
        hl = high - low
        hc = abs(high - close.shift())
        lc = abs(low - close.shift())
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        # Calculate basic bands
        hl_avg = (high + low) / 2
        upper_band = hl_avg + (multiplier * atr)
        lower_band = hl_avg - (multiplier * atr)
        
        # Initialize supertrend
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
        
        # Calculate MACD
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        
        # Determine signal
        current_macd = macd_line.iloc[-1]
        current_signal = signal_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        prev_signal = signal_line.iloc[-2]
        
        # Bullish crossover
        if current_macd > current_signal and prev_macd <= prev_signal:
            return 1
        # Bearish crossover
        elif current_macd < current_signal and prev_macd >= prev_signal:
            return -1
        # Continue current trend
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
        
        # Volume-weighted moving average with power factor
        vwma_values = []
        
        for i in range(length - 1, len(df)):
            window_close = close.iloc[i - length + 1:i + 1]
            window_volume = volume.iloc[i - length + 1:i + 1]
            
            # Apply power to volume
            powered_volume = window_volume ** power
            
            # Calculate VWMA
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
        
        # Bullish: price above VWMA and VWMA trending up
        if current_price > current_vwma and current_vwma > prev_vwma:
            return 1
        # Bearish: price below VWMA and VWMA trending down
        elif current_price < current_vwma and current_vwma < prev_vwma:
            return -1
        # Neutral
        else:
            return 0
            
    except Exception as e:
        print(f"Error calculating FantailVMA: {e}")
        return 0

def get_current_balances():
    """Get current SOL and USDT balances with better error handling"""
    try:
        result = make_api_request('GET', '/api/spot/v1/account/assets')
        
        print(f"DEBUG: Raw balance result: {result}")
        
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
                    print(f"DEBUG: Asset - {coin_name}: {available}")
                    
                    if coin_name == 'SOL':
                        sol_balance = float(available) if available else 0.0
                    elif coin_name == 'USDT':
                        usdt_balance = float(available) if available else 0.0
        
        print(f"DEBUG: Parsed balances - SOL: {sol_balance}, USDT: {usdt_balance}")
        
        trading_state.current_sol_balance = sol_balance
        trading_state.current_usdt_balance = usdt_balance
        
        return sol_balance, usdt_balance
    except Exception as e:
        print(f"Error getting balances: {e}")
        return 0.0, 0.0

def get_trading_signals():
    """Get signals from all three indicators"""
    # Adjust limit based on interval to ensure sufficient data
    interval_minutes = {
        '1m': 1,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1H': 60,
        '4H': 240,
        '1D': 1440
    }
    minutes_per_candle = interval_minutes.get(config.indicator_interval, 15)
    
    # Calculate required candles to get enough historical data (at least 200 periods for indicators)
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
    
    # Calculate consensus (2 out of 3)
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
    """Execute REAL buy order using percentage of USDT"""
    try:
        # Check if bot should stop
        if not trading_state.is_running:
            return False
            
        # Get current balances
        sol_balance, usdt_balance = get_current_balances()
        
        if usdt_balance <= 0:
            print("No USDT available for buying")
            return False
        
        # Calculate buy amount based on percentage
        buy_amount_usdt = usdt_balance * (config.trade_percentage / 100.0)
        
        # Get current price
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
        sol_amount = buy_amount_usdt / current_price
        
        # ROUND to 4 decimal places for SOL (adjust based on CoinCatch requirements)
        sol_amount_rounded = round(sol_amount, 4)
        
        # Ensure minimum order size (adjust based on CoinCatch requirements for SOL)
        if sol_amount_rounded < 0.01:
            print(f"Buy amount too small: {sol_amount_rounded} SOL (min: 0.01 SOL)")
            return False
        
        # Use market order for better execution
        order_data = {
            "symbol": "SOLUSDT_SPBL",
            "side": "buy",
            "orderType": "market",
            "quantity": str(sol_amount_rounded),
            "force": "normal"
        }
        
        print(f"\n{'='*60}")
        print(f"EXECUTING REAL BUY ORDER")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"USDT Balance: ${usdt_balance:.2f}")
        print(f"Trade Percentage: {config.trade_percentage}%")
        print(f"Buy Amount: ${buy_amount_usdt:.2f} USDT")
        print(f"SOL Amount: {sol_amount_rounded:.4f} SOL (rounded from {sol_amount:.6f} SOL)")
        print(f"Current Price: ${current_price:.2f}")
        print(f"Order Type: MARKET")
        print(f"Interval: {config.indicator_interval}")
        print(f"{'='*60}\n")
        
        result = make_api_request('POST', '/api/spot/v1/trade/orders', order_data)
        
        # Check if bot was stopped during order
        if not trading_state.is_running:
            return False
            
        if 'error' in result:
            print(f"Market order failed, trying limit order...")
            limit_price = round(current_price * 1.005, 2)  # 0.5% above market, rounded to 2 decimal places
            
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
        
        print(f"✅ BUY ORDER SUCCESSFUL: {result}")
        
        # Update balances after successful buy
        get_current_balances()
        
        return True
        
    except Exception as e:
        print(f"Error executing buy order: {e}")
        import traceback
        traceback.print_exc()
        return False

def execute_sell_order():
    """Execute REAL sell order - ALWAYS SELL 100% OF SOL"""
    try:
        # Check if bot should stop
        if not trading_state.is_running:
            return False
            
        # Get current balances - refresh to ensure we have latest
        sol_balance, usdt_balance = get_current_balances()
        
        print(f"DEBUG: SOL Balance before sell: {sol_balance}")
        
        if sol_balance <= 0:
            print("No SOL available for selling")
            return False
        
        # Always sell 100% of SOL balance, but ensure minimum order size
        sol_amount = sol_balance
        
        # Check minimum order size (adjust based on exchange requirements for SOL)
        if sol_amount < 0.01:  # Minimum SOL order size
            print(f"SOL amount too small for sell order: {sol_amount} SOL")
            return False
        
        # ROUND to 4 decimal places for SOL
        sol_amount_rounded = round(sol_amount, 4)
        print(f"DEBUG: Original amount: {sol_amount}, Rounded amount: {sol_amount_rounded}")
        
        # Get current price
        ticker_result = make_api_request('GET', '/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL')
        if 'error' in ticker_result:
            print(f"Failed to get price for sell: {ticker_result.get('message')}")
            return False
        
        data = ticker_result.get('data', {})
        price_field = data.get('close') or data.get('last') or data.get('price')
        if not price_field:
            print("Could not get current SOL price for sell")
            return False
        
 