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
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Fix for lowercase environment variables
def fix_env_vars():
    env_mapping = {
        'coincatch_api_key': 'COINCATCH_API_KEY',
        'coincatch_api_secret': 'COINCATCH_API_SECRET', 
        'coincatch_passphrase': 'COINCATCH_PASSPHRASE'
    }
    
    for lower_name, upper_name in env_mapping.items():
        if lower_name in os.environ and upper_name not in os.environ:
            os.environ[upper_name] = os.environ[lower_name]

# Call this function before your Config class
fix_env_vars()

# AGGRESSIVE GROWTH CONFIGURATION
class Config:
    def __init__(self):
        # Try multiple possible environment variable names
        self.api_key = (os.environ.get('COINCATCH_API_KEY') or 
                       os.environ.get('coincatch_api_key') or '')
        self.api_secret = (os.environ.get('COINCATCH_API_SECRET') or 
                          os.environ.get('coincatch_api_secret') or '')
        self.passphrase = (os.environ.get('COINCATCH_PASSPHRASE') or 
                          os.environ.get('coincatch_passphrase') or '')
        
        self.is_configured = bool(self.api_key and self.api_secret and self.passphrase)
        
        if not self.is_configured:
            print("❌ API credentials missing. Please check environment variables.")
            print(f"   API Key set: {bool(self.api_key)}")
            print(f"   API Secret set: {bool(self.api_secret)}")
            print(f"   Passphrase set: {bool(self.passphrase)}")
        else:
            print("✅ API credentials configured successfully")
        
        self.timezone = ZoneInfo('America/New_York')
        
        # 🚀 AGGRESSIVE SETTINGS 🚀
        self.base_trade_amount = 0.2  # Base SOL amount
        self.risk_multiplier = 1.5    # Increase size during strong trends
        self.check_interval = 300     # 5 minutes - very active
        self.indicator_interval = '5m' # 5min timeframe for quick entries
        
        # Aggressive Indicators
        self.rsi_period = 7           # Shorter for quicker signals
        self.macd_fast = 6            # Very responsive MACD
        self.macd_slow = 13
        self.macd_signal = 5
        self.volume_ma = 10           # Volume confirmation
        
        # Momentum Filters
        self.min_volume_multiplier = 1.8  # Require 80% above average volume
        self.trend_strength_min = 0.4     # Minimum trend strength (0-1)
        
        # Risk Management (AGGRESSIVE)
        self.max_daily_loss = 0.15    # 15% daily loss limit
        self.trailing_stop = 0.08     # 8% trailing stop
        self.max_position_time = 7200 # 2 hours max position time

config = Config()

def get_ny_time():
    return datetime.now(config.timezone)

class TradingState:
    def __init__(self):
        self.is_running = False
        self.last_position = None
        self.last_trade_time = None
        self.last_signals = {}
        self.trade_history = []
        self.current_sol_balance = 0.0
        self.current_usdt_balance = 0.0
        self.entry_price = None
        self.highest_price_since_entry = None
        self.daily_starting_balance = 0.0
        self.daily_start_time = get_ny_time()
        
        self.performance_data = {
            'starting_balance_usdt': 0.0,
            'starting_timestamp': None,
            'total_trades': 0,
            'winning_trades': 0,
            'total_pnl': 0.0,
            'total_pnl_percentage': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0,
            'current_streak': 0,
            'best_streak': 0,
            'worst_streak': 0
        }
        
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

def get_current_sol_price():
    """Get current SOL price with better error handling"""
    try:
        # Try multiple endpoints
        endpoints = [
            '/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL',
            '/api/spot/v1/market/ticker?symbol=SOLUSDT',
            '/api/v1/market/ticker?symbol=SOLUSDT_SPBL'
        ]
        
        for endpoint in endpoints:
            result = make_api_request('GET', endpoint)
            if 'error' not in result and result:
                # Parse different response formats
                if 'data' in result and isinstance(result['data'], dict):
                    data = result['data']
                    if 'lastPr' in data:
                        return float(data['lastPr'])
                    elif 'last' in data:
                        return float(data['last'])
                    elif 'close' in data:
                        return float(data['close'])
                elif 'last' in result:
                    return float(result['last'])
                elif 'close' in result:
                    return float(result['close'])
        
        print(f"Could not parse price from any endpoint")
        return None
        
    except Exception as e:
        print(f"Error getting SOL price: {e}")
        return None

def get_klines(interval='5m', limit=50):
    """Fetch candlestick data for aggressive trading"""
    try:
        if not trading_state.is_running:
            return None
            
        end_time = int(time.time() * 1000)
        
        interval_minutes = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1H': 60, '4H': 240, '1D': 1440}
        minutes_per_candle = interval_minutes.get(interval, 5)
        start_time = end_time - (limit * minutes_per_candle * 60 * 1000)
        
        interval_map = {'1m': '60', '5m': '300', '15m': '900', '30m': '1800', '1H': '3600', '4H': '14400', '1D': '86400'}
        granularity = interval_map.get(interval, '300')
        
        symbol = 'SOLUSDT_UMCBL'
        endpoint = f'/api/mix/v1/market/candles?symbol={symbol}&granularity={granularity}&startTime={start_time}&endTime={end_time}'
        
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

def calculate_rsi(df, period=14):
    """Calculate RSI with aggressive settings"""
    try:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
    except:
        return 50

def calculate_momentum_macd(df, fast=6, slow=13, signal=5):
    """Aggressive MACD for quick momentum signals"""
    try:
        close = df['close']
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        current_hist = histogram.iloc[-1]
        prev_hist = histogram.iloc[-2]
        
        # Strong momentum signals
        if current_hist > 0 and prev_hist <= 0 and current_hist > abs(prev_hist) * 1.5:
            return 2  # Strong buy
        elif current_hist < 0 and prev_hist >= 0 and abs(current_hist) > abs(prev_hist) * 1.5:
            return -2  # Strong sell
        elif current_hist > 0 and current_hist > abs(signal_line.iloc[-1]) * 0.5:
            return 1   # Buy
        elif current_hist < 0 and abs(current_hist) > abs(signal_line.iloc[-1]) * 0.5:
            return -1  # Sell
        return 0
    except:
        return 0

def calculate_volume_strength(df, period=10):
    """Measure volume momentum"""
    try:
        current_volume = df['volume'].iloc[-1]
        avg_volume = df['volume'].tail(period).mean()
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
        return volume_ratio
    except:
        return 1

def calculate_trend_strength(df):
    """Aggressive trend strength measurement"""
    try:
        # Multiple timeframe momentum
        price_change_5 = (df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5]
        price_change_10 = (df['close'].iloc[-1] - df['close'].iloc[-10]) / df['close'].iloc[-10]
        
        # Volume-weighted price momentum
        volume_trend = df['volume'].tail(5).mean() / df['volume'].tail(20).mean()
        
        # Combined strength (0-1 scale)
        strength = min(1.0, (abs(price_change_5) * 2 + abs(price_change_10) + volume_trend) / 4)
        direction = 1 if price_change_5 > 0 else -1
        
        return strength * direction
    except:
        return 0

def get_aggressive_signals():
    """Generate aggressive momentum signals"""
    try:
        df = get_klines(interval=config.indicator_interval, limit=50)
        
        # First, get current price separately as fallback
        current_price = get_current_sol_price()
        if current_price is None:
            print("Failed to get current SOL price")
            return None
            
        if df is None or len(df) < 20:
            # Return basic signals with current price even if klines fail
            return {
                'rsi': 50,
                'macd': 0,
                'volume_strength': 1.0,
                'trend_strength': 0,
                'trend_direction': 0,
                'price': current_price,
                'timestamp': get_ny_time().isoformat(),
                'action': 'HOLD',
                'trade_multiplier': 1.0
            }
        
        # Core signals
        rsi = calculate_rsi(df, config.rsi_period)
        macd_signal = calculate_momentum_macd(df, config.macd_fast, config.macd_slow, config.macd_signal)
        volume_strength = calculate_volume_strength(df, config.volume_ma)
        trend_strength = calculate_trend_strength(df)
        
        # Aggressive signal logic
        signals = {
            'rsi': rsi,
            'macd': macd_signal,
            'volume_strength': volume_strength,
            'trend_strength': abs(trend_strength),
            'trend_direction': 1 if trend_strength > 0 else -1,
            'price': current_price,
            'timestamp': get_ny_time().isoformat()
        }
        
        # 🚀 AGGRESSIVE ENTRY CRITERIA 🚀
        buy_signals = 0
        sell_signals = 0
        
        # Buy conditions
        if (macd_signal >= 1 and 
            volume_strength >= config.min_volume_multiplier and 
            trend_strength > 0 and 
            abs(trend_strength) >= config.trend_strength_min):
            buy_signals += 2
            
        if rsi < 70 and trend_strength > 0:
            buy_signals += 1
            
        # Sell conditions  
        if (macd_signal <= -1 and 
            volume_strength >= config.min_volume_multiplier and 
            trend_strength < 0 and 
            abs(trend_strength) >= config.trend_strength_min):
            sell_signals += 2
            
        if rsi > 30 and trend_strength < 0:
            sell_signals += 1
        
        # Determine action with momentum weighting
        if buy_signals >= 2:
            signals['action'] = 'BUY'
            # Calculate trade size based on momentum
            momentum_strength = min(2.0, (abs(macd_signal) + volume_strength + abs(trend_strength)) / 3)
            signals['trade_multiplier'] = min(config.risk_multiplier, momentum_strength)
        elif sell_signals >= 2:
            signals['action'] = 'SELL'
            momentum_strength = min(2.0, (abs(macd_signal) + volume_strength + abs(trend_strength)) / 3)
            signals['trade_multiplier'] = min(config.risk_multiplier, momentum_strength)
        else:
            signals['action'] = 'HOLD'
            signals['trade_multiplier'] = 1.0
            
        return signals
        
    except Exception as e:
        print(f"Error getting signals: {e}")
        # Return basic signals with current price as fallback
        current_price = get_current_sol_price()
        if current_price is not None:
            return {
                'rsi': 50,
                'macd': 0,
                'volume_strength': 1.0,
                'trend_strength': 0,
                'trend_direction': 0,
                'price': current_price,
                'timestamp': get_ny_time().isoformat(),
                'action': 'HOLD',
                'trade_multiplier': 1.0
            }
        return None

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

def execute_buy_order(amount=None):
    """Execute buy order for aggressive trading"""
    try:
        if not trading_state.is_running:
            return False
            
        if amount is None:
            amount = config.base_trade_amount
            
        sol_balance, usdt_balance = get_current_balances()
        
        # Get current price
        current_price = get_current_sol_price()
        if current_price is None:
            print("Failed to get current price for buy")
            return False
        
        usdt_needed = amount * current_price
        
        if usdt_balance < usdt_needed:
            print(f"Insufficient USDT: Need ${usdt_needed:.2f}, have ${usdt_balance:.2f}")
            return False
        
        sol_amount_rounded = round(amount, 4)
        
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
        print(f"🚀 AGGRESSIVE BUY ORDER")
        print(f"Amount: {sol_amount_rounded:.4f} SOL")
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
        
        print(f"✅ AGGRESSIVE BUY SUCCESSFUL")
        time.sleep(1)
        get_current_balances()
        
        trading_state.trade_history.append({
            'time': get_ny_time().isoformat(),
            'action': 'AGGRESSIVE BUY',
            'sol_amount': sol_amount_rounded,
            'usdt_amount': usdt_needed,
            'price': current_price,
            'signals': trading_state.last_signals
        })
        
        return True
        
    except Exception as e:
        print(f"Error executing buy order: {e}")
        return False

def execute_sell_order(amount=None):
    """Execute sell order for aggressive trading"""
    try:
        if not trading_state.is_running:
            return False
            
        if amount is None:
            amount = config.base_trade_amount
            
        sol_balance, usdt_balance = get_current_balances()
        
        # Check if we have sufficient balance
        minimum_needed = amount * 0.9
        
        if sol_balance < minimum_needed:
            print(f"Insufficient SOL: Need at least {minimum_needed:.4f} SOL, have {sol_balance} SOL")
            return False
        
        # Use the actual balance we have
        sol_amount_rounded = math.floor(sol_balance * 10) / 10
        
        if sol_amount_rounded < 0.1:
            print(f"Sell amount too small: {sol_amount_rounded} SOL")
            return False
        
        # Get current price
        current_price = get_current_sol_price()
        if current_price is None:
            print("Failed to get current price for sell")
            return False
        
        order_data = {
            "symbol": "SOLUSDT_SPBL",
            "side": "sell",
            "orderType": "market",
            "quantity": str(sol_amount_rounded),
            "force": "normal"
        }
        
        print(f"\n{'='*60}")
        print(f"📉 AGGRESSIVE SELL ORDER")
        print(f"Target Amount: {amount:.4f} SOL")
        print(f"Available Balance: {sol_balance:.4f} SOL") 
        print(f"Selling: {sol_amount_rounded:.4f} SOL")
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
                return False
        
        print(f"✅ AGGRESSIVE SELL SUCCESSFUL")
        time.sleep(1)
        get_current_balances()
        
        trading_state.trade_history.append({
            'time': get_ny_time().isoformat(),
            'action': 'AGGRESSIVE SELL',
            'sol_amount': sol_amount_rounded,
            'usdt_amount': sol_amount_rounded * current_price,
            'price': current_price,
            'signals': trading_state.last_signals
        })
        
        return True
        
    except Exception as e:
        print(f"Error executing sell order: {e}")
        return False

def check_risk_limits():
    """Aggressive but controlled risk management"""
    try:
        current_total = (trading_state.current_sol_balance * trading_state.last_signals.get('price', 0) + 
                        trading_state.current_usdt_balance)
        
        # Daily loss limit
        if trading_state.daily_starting_balance > 0:
            daily_pnl_pct = (current_total - trading_state.daily_starting_balance) / trading_state.daily_starting_balance
            if daily_pnl_pct <= -config.max_daily_loss:
                print(f"🚨 DAILY LOSS LIMIT REACHED: {daily_pnl_pct:.1%}")
                return False
        
        # Reset daily tracking if new day
        current_time = get_ny_time()
        if current_time.date() != trading_state.daily_start_time.date():
            trading_state.daily_starting_balance = current_total
            trading_state.daily_start_time = current_time
            
        return True
    except:
        return True

def check_trailing_stop(current_price):
    """Aggressive trailing stop loss"""
    if trading_state.last_position == 'long' and trading_state.entry_price and trading_state.highest_price_since_entry:
        # Update highest price
        if current_price > trading_state.highest_price_since_entry:
            trading_state.highest_price_since_entry = current_price
            
        # Check trailing stop
        if trading_state.highest_price_since_entry > 0:
            drawdown = (trading_state.highest_price_since_entry - current_price) / trading_state.highest_price_since_entry
            if drawdown >= config.trailing_stop:
                print(f"🚨 TRAILING STOP HIT: {drawdown:.1%} drawdown")
                return True
                
    return False

def aggressive_trading_loop():
    """🚀 AGGRESSIVE GROWTH TRADING LOOP 🚀"""
    print("\n" + "="*70)
    print("🚀 AGGRESSIVE GROWTH BOT ACTIVATED 🚀")
    print("STRATEGY: High-Frequency Momentum Trading")
    print("GOAL: Maximum returns with aggressive risk management")
    print("WARNING: HIGH RISK - POTENTIAL FOR SIGNIFICANT LOSSES")
    print("="*70)
    
    trading_state.daily_starting_balance = (trading_state.current_sol_balance * trading_state.last_signals.get('price', 0) + 
                                          trading_state.current_usdt_balance)
    
    while trading_state.is_running:
        try:
            if not trading_state.is_running:
                break
                
            # Check risk limits first
            if not check_risk_limits():
                print("🛑 Risk limits exceeded - stopping bot")
                trading_state.is_running = False
                break
                
            signals = get_aggressive_signals()
            if signals is None:
                time.sleep(config.check_interval)
                continue
                
            trading_state.last_signals = signals
            sol_balance, usdt_balance = get_current_balances()
            current_price = signals['price']
            
            print(f"\n⏰ {signals['timestamp'][11:19]} | Price: ${current_price:.2f}")
            print(f"📊 RSI: {signals['rsi']:.1f} | MACD: {signals['macd']} | Volume: {signals['volume_strength']:.1f}x")
            print(f"📈 Trend: {signals['trend_strength']:.2f} | Action: {signals['action']} | Multiplier: {signals['trade_multiplier']:.1f}")
            
            # Check trailing stop
            if check_trailing_stop(current_price):
                if trading_state.last_position == 'long':
                    if execute_sell_order():
                        trading_state.last_position = None
                        trading_state.entry_price = None
                        trading_state.highest_price_since_entry = None
                continue
            
            # Check position time limit
            if (trading_state.last_trade_time and trading_state.last_position and
                (get_ny_time() - trading_state.last_trade_time).total_seconds() > config.max_position_time):
                print(f"⏰ Position time limit reached ({config.max_position_time/3600:.1f}h)")
                if trading_state.last_position == 'long':
                    execute_sell_order()
                elif trading_state.last_position == 'short':
                    execute_buy_order()
                trading_state.last_position = None
                continue
            
            # Execute trades based on aggressive signals
            trade_amount = config.base_trade_amount * signals.get('trade_multiplier', 1.0)
            
            if (signals['action'] == 'BUY' and trading_state.last_position != 'long' and 
                trading_state.last_position != 'short'):  # Only enter new positions, don't reverse
                
                print(f"🚀 BUY SIGNAL - Trading {trade_amount:.3f} SOL")
                if execute_buy_order(trade_amount):
                    trading_state.last_position = 'long'
                    trading_state.last_trade_time = get_ny_time()
                    trading_state.entry_price = current_price
                    trading_state.highest_price_since_entry = current_price
                    trading_state.performance_data['total_trades'] += 1
                    
            elif (signals['action'] == 'SELL' and trading_state.last_position != 'short' and
                  trading_state.last_position != 'long'):  # Only enter new positions
                  
                print(f"📉 SELL SIGNAL - Trading {trade_amount:.3f} SOL")  
                if execute_sell_order(trade_amount):
                    trading_state.last_position = 'short'
                    trading_state.last_trade_time = get_ny_time()
                    trading_state.entry_price = current_price
                    trading_state.highest_price_since_entry = current_price
                    trading_state.performance_data['total_trades'] += 1
            
            time.sleep(config.check_interval)
            
        except Exception as e:
            print(f"Error in aggressive loop: {e}")
            time.sleep(config.check_interval)
    
    print("\n🛑 AGGRESSIVE BOT STOPPED")

# ========== FLASK ROUTES ==========

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/test')
def test_api():
    """Test API connection and data flow"""
    try:
        # Test price
        price = get_current_sol_price()
        
        # Test balances
        sol_balance, usdt_balance = get_current_balances()
        
        # Test signals
        signals = get_aggressive_signals()
        
        return jsonify({
            'status': 'success',
            'price': price,
            'sol_balance': sol_balance,
            'usdt_balance': usdt_balance,
            'signals': signals,
            'is_running': trading_state.is_running,
            'api_configured': config.is_configured
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/start_bot', methods=['POST'])
def start_bot():
    if trading_state.is_running:
        return jsonify({'status':'error','message':'Bot already running'})
    
    if not config.is_configured:
        return jsonify({'status':'error','message':'API not configured'})
    
    trading_state.is_running = True
    trading_thread = threading.Thread(target=aggressive_trading_loop, daemon=True)
    trading_thread.start()
    
    return jsonify({'status':'success','message':'🚀 Aggressive growth bot activated!'})

@app.route('/api/stop_bot', methods=['POST'])
def stop_bot():
    if not trading_state.is_running:
        return jsonify({'status':'error','message':'Bot not running'})
    
    trading_state.is_running = False
    return jsonify({'status':'success','message':'Bot stopped'})

@app.route('/api/status')
def get_status():
    print("🔍 Status endpoint called")  # Debug log
    
    # Force refresh balances
    sol_balance, usdt_balance = get_current_balances()
    current_price = get_current_sol_price()
    
    print(f"🔍 Price: {current_price}, SOL: {sol_balance}, USDT: {usdt_balance}")  # Debug log
    
    signals = trading_state.last_signals or {}
    
    # Always try to get current price if signals don't have it
    if not signals.get('price') or signals.get('price') == 0:
        current_price = get_current_sol_price()
        if current_price:
            signals['price'] = current_price
        else:
            signals['price'] = 0.0
    
    return jsonify({
        'status': 'success',
        'is_running': trading_state.is_running,
        'last_position': trading_state.last_position,
        'last_trade_time': trading_state.last_trade_time.isoformat() if trading_state.last_trade_time else None,
        'signals': signals,
        'trade_history': trading_state.trade_history[-20:],  # Last 20 trades
        'sol_balance': trading_state.current_sol_balance,
        'usdt_balance': trading_state.current_usdt_balance,
        'base_trade_amount': config.base_trade_amount,
        'risk_multiplier': config.risk_multiplier,
        'daily_loss_limit': config.max_daily_loss * 100,
        'trailing_stop': config.trailing_stop * 100,
        'check_interval': config.check_interval,
        'indicator_interval': config.indicator_interval,
        'performance_data': trading_state.performance_data
    })

@app.route('/api/current_price')
def get_current_price():
    """Get current SOL price only"""
    try:
        current_price = get_current_sol_price()
        if current_price:
            return jsonify({
                'status': 'success',
                'price': current_price
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to get current price'
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

@app.route('/api/update_settings', methods=['POST'])
def update_settings():
    try:
        base_trade_amount = float(request.args.get('base_trade_amount', config.base_trade_amount))
        risk_multiplier = float(request.args.get('risk_multiplier', config.risk_multiplier))
        daily_loss_limit = float(request.args.get('daily_loss_limit', config.max_daily_loss * 100)) / 100
        trailing_stop = float(request.args.get('trailing_stop', config.trailing_stop * 100)) / 100
        check_interval = int(request.args.get('check_interval', config.check_interval))
        
        if base_trade_amount < 0.1 or base_trade_amount > 100:
            return jsonify({'status':'error','message':'Base trade amount must be 0.1-100 SOL'})
        
        if risk_multiplier < 1 or risk_multiplier > 3:
            return jsonify({'status':'error','message':'Risk multiplier must be 1.0-3.0'})
        
        if daily_loss_limit < 0.05 or daily_loss_limit > 0.5:
            return jsonify({'status':'error','message':'Daily loss limit must be 5-50%'})
        
        if trailing_stop < 0.03 or trailing_stop > 0.2:
            return jsonify({'status':'error','message':'Trailing stop must be 3-20%'})
        
        if check_interval < 60:
            return jsonify({'status':'error','message':'Check interval must be at least 60 seconds'})
        
        config.base_trade_amount = base_trade_amount
        config.risk_multiplier = risk_multiplier
        config.max_daily_loss = daily_loss_limit
        config.trailing_stop = trailing_stop
        config.check_interval = check_interval
        
        return jsonify({'status':'success','message':'Aggressive settings updated'})
        
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

@app.route('/api/balance')
def get_balance():
    try:
        sol_balance, usdt_balance = get_current_balances()
        return jsonify({
            'status': 'success',
            'sol_balance': sol_balance,
            'usdt_balance': usdt_balance
        })
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

@app.route('/api/manual_buy', methods=['POST'])
def manual_buy():
    try:
        amount = float(request.args.get('amount', config.base_trade_amount))
        
        if amount < 0.1 or amount > 100:
            return jsonify({'status':'error','message':'Amount must be 0.1-100 SOL'})
        
        if execute_buy_order(amount):
            return jsonify({'status':'success','message':f'Manual buy of {amount} SOL executed'})
        else:
            return jsonify({'status':'error','message':'Manual buy failed'})
            
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

@app.route('/api/manual_sell', methods=['POST'])
def manual_sell():
    try:
        amount = float(request.args.get('amount', config.base_trade_amount))
        
        if amount < 0.1 or amount > 100:
            return jsonify({'status':'error','message':'Amount must be 0.1-100 SOL'})
        
        if execute_sell_order(amount):
            return jsonify({'status':'success','message':f'Manual sell of {amount} SOL executed'})
        else:
            return jsonify({'status':'error','message':'Manual sell failed'})
            
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 AGGRESSIVE GROWTH TRADING BOT")
    print("="*70)
    print("STRATEGY: High-Frequency Momentum Trading")
    print(f"BASE TRADE: {config.base_trade_amount} SOL")
    print(f"MAX MULTIPLIER: {config.risk_multiplier}x")
    print(f"CHECK INTERVAL: {config.check_interval}s")
    print(f"TIMEFRAME: {config.indicator_interval}")
    print(f"DAILY LOSS LIMIT: {config.max_daily_loss:.1%}")
    print(f"TRAILING STOP: {config.trailing_stop:.1%}")
    print(f"MAX POSITION TIME: {config.max_position_time/3600:.1f}h")
    print("\n⚠️  WARNING: HIGH RISK STRATEGY")
    print("⚠️  Only risk capital you can afford to lose completely")
    print("⚠️  Potential for significant losses")
    print("="*70)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
