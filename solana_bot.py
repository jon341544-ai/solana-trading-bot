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
        # Enhanced environment variable loading with debug info
        self.api_key = os.environ.get('COINCATCH_API_KEY', '')
        self.api_secret = os.environ.get('COINCATCH_API_SECRET', '') 
        self.passphrase = os.environ.get('COINCATCH_PASSPHRASE', '')
        self.base_url = "https://api.coincatch.com"
        
        # Debug logging
        print(f"🔑 API Key configured: {'Yes' if self.api_key else 'No'}")
        print(f"🔒 API Secret configured: {'Yes' if self.api_secret else 'No'}")
        print(f"🗝️ Passphrase configured: {'Yes' if self.passphrase else 'No'}")
        
        self.is_configured = bool(self.api_key and self.api_secret and self.passphrase)
        print(f"✅ Full configuration: {'COMPLETE' if self.is_configured else 'INCOMPLETE'}")
        
        # Timezone setting - New York (EST/EDT)
        self.timezone = ZoneInfo('America/New_York')
        
        # Trading parameters - FIXED SOL AMOUNT MODE
        self.trade_type = 'percentage' # 'percentage' or 'fixed'
        self.trade_percentage = 50 # Default: 50% of available balance
        self.sol_trade_amount = 1.0  # Default: Buy/Sell 1.0 SOL each time (used if trade_type is 'fixed')
        self.check_interval = 900  # Check every 15 minutes
        self.indicator_interval = '15m'
        self.rsi_period = 14
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        self.profit_target_percent = 1.0  # NEW: Default 1% profit target
        self.require_rsi_cycle = True  # NEW: Require RSI cycle before buying back

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
        self.last_buy_price = None  # NEW: Track last buy price
        self.rsi_cycle_complete = True  # NEW: Track if RSI has cycled
        self.last_rsi_value = 50  # NEW: Track last RSI value
        self.profit_stats = {  # NEW: Profit tracking
            'today': {'profit': 0.0, 'trades': 0},
            'week': {'profit': 0.0, 'trades': 0},
            'month': {'profit': 0.0, 'trades': 0},
            'year': {'profit': 0.0, 'trades': 0},
            'all_time': {'profit': 0.0, 'trades': 0}
        }
        
trading_state = TradingState()

def calculate_profit_stats():
    """Calculate profit statistics for different time periods"""
    try:
        now = get_ny_time()
        today_start = datetime(now.year, now.month, now.day, tzinfo=config.timezone)
        week_start = today_start - timedelta(days=now.weekday())
        month_start = datetime(now.year, now.month, 1, tzinfo=config.timezone)
        year_start = datetime(now.year, 1, 1, tzinfo=config.timezone)
        
        # Reset stats
        trading_state.profit_stats = {
            'today': {'profit': 0.0, 'trades': 0, 'buy_volume': 0.0, 'sell_volume': 0.0},
            'week': {'profit': 0.0, 'trades': 0, 'buy_volume': 0.0, 'sell_volume': 0.0},
            'month': {'profit': 0.0, 'trades': 0, 'buy_volume': 0.0, 'sell_volume': 0.0},
            'year': {'profit': 0.0, 'trades': 0, 'buy_volume': 0.0, 'sell_volume': 0.0},
            'all_time': {'profit': 0.0, 'trades': 0, 'buy_volume': 0.0, 'sell_volume': 0.0}
        }
        
        for trade in trading_state.trade_history:
            trade_time = datetime.fromisoformat(trade['time'].replace('Z', '+00:00')).astimezone(config.timezone)
            usdt_amount = trade.get('usdt_amount', 0)
            
            # Determine if this is a buy or sell for volume tracking
            if 'BUY' in trade['action']:
                volume_key = 'buy_volume'
                profit_impact = -usdt_amount  # Buying spends money
            else:
                volume_key = 'sell_volume'
                profit_impact = usdt_amount  # Selling earns money
            
            # All time stats
            trading_state.profit_stats['all_time']['profit'] += profit_impact
            trading_state.profit_stats['all_time']['trades'] += 1
            trading_state.profit_stats['all_time'][volume_key] += usdt_amount
            
            # Yearly stats
            if trade_time >= year_start:
                trading_state.profit_stats['year']['profit'] += profit_impact
                trading_state.profit_stats['year']['trades'] += 1
                trading_state.profit_stats['year'][volume_key] += usdt_amount
            
            # Monthly stats
            if trade_time >= month_start:
                trading_state.profit_stats['month']['profit'] += profit_impact
                trading_state.profit_stats['month']['trades'] += 1
                trading_state.profit_stats['month'][volume_key] += usdt_amount
            
            # Weekly stats
            if trade_time >= week_start:
                trading_state.profit_stats['week']['profit'] += profit_impact
                trading_state.profit_stats['week']['trades'] += 1
                trading_state.profit_stats['week'][volume_key] += usdt_amount
            
            # Daily stats
            if trade_time >= today_start:
                trading_state.profit_stats['today']['profit'] += profit_impact
                trading_state.profit_stats['today']['trades'] += 1
                trading_state.profit_stats['today'][volume_key] += usdt_amount
                
    except Exception as e:
        print(f"Error calculating profit stats: {e}")

def make_api_request(method, endpoint, data=None):
    """Make authenticated API request with corrected signature"""
    if not config.is_configured:
        return {'error': 'API credentials not configured'}
    
    try:
        if not trading_state.is_running and endpoint not in ['/api/spot/v1/account/assets']:
            return {'error': 'Bot stopped'}
            
        timestamp = str(int(time.time() * 1000))
        
        # CoinCatch API signature format - CORRECTED
        if method.upper() == 'GET':
            if '?' in endpoint:
                # For GET requests with query parameters
                message = f"{timestamp}{method.upper()}{endpoint}"
            else:
                message = f"{timestamp}{method.upper()}{endpoint}"
        else:
            # For POST requests with body
            body_string = json.dumps(data) if data else ''
            message = f"{timestamp}{method.upper()}{endpoint}{body_string}"
        
        print(f"🔐 Signature debug - Timestamp: {timestamp}")
        print(f"🔐 Signature debug - Method: {method.upper()}")
        print(f"🔐 Signature debug - Endpoint: {endpoint}")
        
        # Create signature - CORRECTED
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
        timeout = 10  # Increased timeout
        
        print(f"🌐 Making {method} request to: {url}")
        
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, timeout=timeout)
        else:
            response = requests.post(url, headers=headers, json=data, timeout=timeout)
        
        print(f"📡 Response status: {response.status_code}")
        
        # Handle response
        if response.status_code == 200:
            try:
                response_data = response.json()
                print(f"✅ API request successful")
                return response_data
            except json.JSONDecodeError:
                return {'error': 'Invalid JSON response', 'raw_response': response.text}
        else:
            error_msg = f'HTTP {response.status_code}'
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail}"
            except:
                error_msg += f" - {response.text}"
            return {'error': error_msg}
            
    except requests.exceptions.Timeout:
        return {'error': 'Request timeout'}
    except requests.exceptions.ConnectionError:
        return {'error': 'Connection error'}
    except Exception as e:
        return {'error': f'Request failed: {str(e)}'}

def test_api_connection():
    """Test API connection and configuration"""
    print("\n🔧 Testing API Configuration...")
    
    if not config.is_configured:
        print("❌ API credentials not configured")
        print("Please set environment variables:")
        print("  - COINCATCH_API_KEY")
        print("  - COINCATCH_API_SECRET") 
        print("  - COINCATCH_PASSPHRASE")
        return False
    
    print("✅ API credentials found")
    
    # Test with a simple endpoint first
    print("🔌 Testing API connection...")
    
    # Test 1: Public endpoint (no auth required)
    try:
        public_result = requests.get(f"{config.base_url}/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL", timeout=5)
        if public_result.status_code == 200:
            print("✅ Public API endpoint accessible")
        else:
            print(f"⚠️ Public endpoint returned: {public_result.status_code}")
    except Exception as e:
        print(f"⚠️ Cannot reach public API: {e}")
    
    # Test 2: Authenticated endpoint
    result = make_api_request('GET', '/api/spot/v1/account/assets')
    
    if 'error' in result:
        print(f"❌ API authentication failed: {result.get('error')}")
        
        # Provide more specific debugging
        if "signature" in str(result.get('error')).lower():
            print("🔍 Signature error detected - checking configuration:")
            print(f"   API Key length: {len(config.api_key)}")
            print(f"   API Secret length: {len(config.api_secret)}")
            print(f"   Passphrase length: {len(config.passphrase)}")
            print("   Please verify your API credentials are correct")
        return False
    
    print("✅ API connection successful")
    
    # Check if SOL balance can be retrieved
    sol_balance, usdt_balance = get_current_balances()
    print(f"💰 Balance check: SOL={sol_balance:.4f}, USDT=${usdt_balance:.2f}")
    
    return True

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

def calculate_rsi(df, period=14):
    """Calculate RSI indicator and return both signal and current RSI value"""
    try:
        close = df['close']
        
        # Calculate price changes
        delta = close.diff()
        
        # Separate gains and losses
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # Calculate average gains and losses
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        current_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2] if len(rsi) > 1 else current_rsi
        
        # Generate signals based on RSI levels
        if current_rsi <= config.rsi_oversold and prev_rsi > config.rsi_oversold:
            # RSI crossed below oversold level - STRONG BUY
            signal = 1
        elif current_rsi >= config.rsi_overbought and prev_rsi < config.rsi_overbought:
            # RSI crossed above overbought level - STRONG SELL
            signal = -1
        elif current_rsi < config.rsi_oversold:
            # RSI is in oversold territory - WEAK BUY
            signal = 0.5
        elif current_rsi > config.rsi_overbought:
            # RSI is in overbought territory - WEAK SELL
            signal = -0.5
        else:
            # RSI is in neutral territory
            signal = 0
            
        return signal, current_rsi
            
    except Exception as e:
        print(f"Error calculating RSI: {e}")
        return 0, 50

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
    """Get signals from RSI indicator only"""
    required_candles = 100
    
    df = get_klines(interval=config.indicator_interval, limit=required_candles)
    if df is None or len(df) < 50:
        return None
    
    rsi_signal, current_rsi = calculate_rsi(df, config.rsi_period)
    
    # NEW: Track RSI cycle for buy-back logic
    if config.require_rsi_cycle:
        if trading_state.last_position == 'long':
            # If we're in a long position, check if RSI has cycled from overbought to oversold
            if trading_state.last_rsi_value > config.rsi_overbought and current_rsi < config.rsi_oversold:
                trading_state.rsi_cycle_complete = True
                print(f"✅ RSI cycle complete: {trading_state.last_rsi_value:.1f} -> {current_rsi:.1f}")
        else:
            # If we're not in a position, reset cycle tracking
            trading_state.rsi_cycle_complete = True
        
        trading_state.last_rsi_value = current_rsi
    
    signals = {
        'rsi': rsi_signal,
        'rsi_value': current_rsi,  # NEW: Include actual RSI value
        'timestamp': get_ny_time().isoformat(),
        'price': float(df['close'].iloc[-1]),
        'interval': config.indicator_interval
    }
    
    # NEW: Check profit condition for selling
    if trading_state.last_position == 'long' and trading_state.last_buy_price:
        current_price = signals['price']
        profit_percent = ((current_price - trading_state.last_buy_price) / trading_state.last_buy_price) * 100
        signals['profit_percent'] = profit_percent
        signals['profit_target_reached'] = profit_percent >= config.profit_target_percent
    else:
        signals['profit_percent'] = 0
        signals['profit_target_reached'] = False
    
    # Determine consensus based on RSI signal strength and profit conditions
    if rsi_signal == 1 and (trading_state.rsi_cycle_complete or not config.require_rsi_cycle):
        signals['consensus'] = 'BUY'
    elif signals['profit_target_reached']:
        signals['consensus'] = 'PROFIT_SELL'  # NEW: Profit-based sell signal
    elif rsi_signal == -1:
        signals['consensus'] = 'RSI_SELL'  # NEW: RSI-based sell signal
    elif rsi_signal == 0.5 and (trading_state.rsi_cycle_complete or not config.require_rsi_cycle):
        signals['consensus'] = 'WEAK_BUY'
    elif rsi_signal == -0.5:
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
        
        # NEW: Store buy price and reset RSI cycle tracking
        trading_state.last_buy_price = current_price
        if config.require_rsi_cycle:
            trading_state.rsi_cycle_complete = False
            print(f"📊 RSI cycle tracking reset - waiting for cycle completion before next buy")
        
        time.sleep(1)
        get_current_balances()
        
        return sol_amount_rounded, usdt_to_spend, current_price
        
    except Exception as e:
        print(f"Error executing buy order: {e}")
        return False

def execute_sell_order():
    """Execute sell order - ALWAYS sells 100% of SOL balance"""
    try:
        if not trading_state.is_running:
            return False
            
        sol_balance, usdt_balance = get_current_balances()
        
        # --- ALWAYS sell 100% of SOL balance ---
        sol_amount_to_sell = sol_balance
        print(f"SELL: 100% of {sol_balance:.4f} SOL")
            
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
        
        # NEW: Calculate profit/loss
        if trading_state.last_buy_price:
            profit_percent = ((current_price - trading_state.last_buy_price) / trading_state.last_buy_price) * 100
            print(f"📊 Profit/Loss: {profit_percent:+.2f}% (Buy: ${trading_state.last_buy_price:.2f}, Current: ${current_price:.2f})")
        else:
            profit_percent = 0
            print("📊 No previous buy price recorded")
        
        order_data = {
            "symbol": "SOLUSDT_SPBL",
            "side": "sell",
            "orderType": "market",
            "quantity": str(sol_amount_rounded),
            "force": "normal"
        }
        
        print(f"\n{'='*60}")
        print(f"EXECUTING SELL ORDER")
        print(f"Selling: {sol_amount_rounded:.4f} SOL (100% of balance)")
        print(f"Current Price: ${current_price:.2f}")
        print(f"Expected USDT: ${expected_usdt:.2f}")
        if trading_state.last_buy_price:
            print(f"Profit/Loss: {profit_percent:+.2f}%")
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
        
        # NEW: Clear buy price after successful sell
        trading_state.last_buy_price = None
        
        time.sleep(1)
        get_current_balances()
        
        return sol_amount_rounded, expected_usdt, current_price
        
    except Exception as e:
        print(f"Error executing sell order: {e}")
        return False

def trading_loop():
    """Main trading loop - RSI Only with Profit Protection"""
    print("\n🤖 BOT STARTED - RSI ONLY STRATEGY WITH PROFIT PROTECTION 🤖")
    print(f"Trade Type: {config.trade_type}")
    if config.trade_type == 'percentage':
        print(f"Trade Percentage: {config.trade_percentage}%")
    else:
        print(f"Fixed SOL Amount: {config.sol_trade_amount} SOL")
    print(f"SELL: ALWAYS 100% of SOL balance")
    print(f"Check Interval: {config.check_interval} seconds")
    print(f"Indicator Interval: {config.indicator_interval}")
    print(f"RSI Settings: Period={config.rsi_period}, Oversold={config.rsi_oversold}, Overbought={config.rsi_overbought}")
    print(f"Profit Target: {config.profit_target_percent}%")  # NEW
    print(f"Require RSI Cycle: {config.require_rsi_cycle}")  # NEW
    print()
    
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
                print(f"Buy Amount: {config.trade_percentage}% of balance")
            else:
                print(f"Buy Amount: {config.sol_trade_amount} SOL")
            print(f"Sell Amount: 100% of SOL balance")
            
            # NEW: Display profit information
            if trading_state.last_position == 'long' and trading_state.last_buy_price:
                profit_percent = signals.get('profit_percent', 0)
                profit_status = f"{profit_percent:+.2f}%"
                if profit_percent >= config.profit_target_percent:
                    profit_status = f"🎯 {profit_status} - TARGET REACHED!"
                print(f"Current Profit: {profit_status}")
            
            # Display RSI signal with more detail
            rsi_value = signals['rsi']
            rsi_actual = signals.get('rsi_value', 50)
            if rsi_value == 1:
                rsi_display = "🟢 STRONG BUY (RSI crossed below oversold)"
            elif rsi_value == -1:
                rsi_display = "🔴 STRONG SELL (RSI crossed above overbought)"
            elif rsi_value == 0.5:
                rsi_display = "🟡 WEAK BUY (RSI in oversold territory)"
            elif rsi_value == -0.5:
                rsi_display = "🟠 WEAK SELL (RSI in overbought territory)"
            else:
                rsi_display = "⚪ NEUTRAL (RSI in normal range)"
                
            print(f"RSI: {rsi_actual:.1f} - {rsi_display}")
            
            # NEW: Display RSI cycle status
            if config.require_rsi_cycle:
                cycle_status = "✅ READY" if trading_state.rsi_cycle_complete else "⏳ WAITING FOR CYCLE"
                print(f"RSI Cycle: {cycle_status}")
            
            print(f"CONSENSUS: {signals['consensus']}")
            print(f"Position: {trading_state.last_position or 'NONE'}")
            
            if not trading_state.is_running:
                break
                
            # NEW: Enhanced trading logic with profit protection
            if signals['consensus'] == 'BUY' and trading_state.last_position != 'long':
                print(f"\n🚀 STRONG BUY SIGNAL - Executing trade...")
                
                result = execute_buy_order()
                if result:
                    sol_amount, usdt_amount, price = result
                    trading_state.last_position = 'long'
                    trading_state.last_trade_time = get_ny_time()
                    trade_record = {
                        'time': get_ny_time().isoformat(),
                        'action': 'BUY',
                        'sol_amount': sol_amount,
                        'usdt_amount': usdt_amount,
                        'price': price,
                        'interval': config.indicator_interval,
                        'signals': signals
                    }
                    trading_state.trade_history.append(trade_record)
                    # Update profit stats after trade
                    calculate_profit_stats()
                    print(f"✅ Position: LONG - Bought {sol_amount:.4f} SOL for ${usdt_amount:.2f}")
                else:
                    print(f"❌ Buy failed")
                    
            elif signals['consensus'] == 'PROFIT_SELL' and trading_state.last_position == 'long':
                print(f"\n💰 PROFIT TARGET REACHED - Executing sell...")
                
                result = execute_sell_order()
                if result:
                    sol_amount, usdt_amount, price = result
                    trading_state.last_position = 'short'
                    trading_state.last_trade_time = get_ny_time()
                    trade_record = {
                        'time': get_ny_time().isoformat(),
                        'action': 'PROFIT_SELL',
                        'sol_amount': sol_amount,
                        'usdt_amount': usdt_amount,
                        'price': price,
                        'interval': config.indicator_interval,
                        'signals': signals
                    }
                    trading_state.trade_history.append(trade_record)
                    # Update profit stats after trade
                    calculate_profit_stats()
                    profit_percent = signals.get('profit_percent', 0)
                    print(f"✅ Position: SOLD - Sold {sol_amount:.4f} SOL for ${usdt_amount:.2f}")
                    print(f"🎯 Profit: {profit_percent:+.2f}%")
                else:
                    print(f"❌ Sell failed")
                    
            elif signals['consensus'] == 'RSI_SELL' and trading_state.last_position == 'long':
                # NEW: Check if we would sell at a loss
                if trading_state.last_buy_price:
                    current_price = signals['price']
                    profit_percent = ((current_price - trading_state.last_buy_price) / trading_state.last_buy_price) * 100
                    
                    if profit_percent < 0:
                        print(f"⏸️  RSI sell signal ignored - would sell at a loss ({profit_percent:+.2f}%)")
                    else:
                        print(f"\n📉 RSI SELL SIGNAL - Executing sell...")
                        
                        result = execute_sell_order()
                        if result:
                            sol_amount, usdt_amount, price = result
                            trading_state.last_position = 'short'
                            trading_state.last_trade_time = get_ny_time()
                            trade_record = {
                                'time': get_ny_time().isoformat(),
                                'action': 'RSI_SELL',
                                'sol_amount': sol_amount,
                                'usdt_amount': usdt_amount,
                                'price': price,
                                'interval': config.indicator_interval,
                                'signals': signals
                            }
                            trading_state.trade_history.append(trade_record)
                            # Update profit stats after trade
                            calculate_profit_stats()
                            print(f"✅ Position: SOLD - Sold {sol_amount:.4f} SOL for ${usdt_amount:.2f}")
                            print(f"📊 Profit: {profit_percent:+.2f}%")
                        else:
                            print(f"❌ Sell failed")
                else:
                    print(f"⏸️  RSI sell signal ignored - no buy price recorded")
            else:
                if signals['consensus'] in ['WEAK_BUY', 'WEAK_SELL']:
                    print(f"⏸️  Weak signal - no action taken")
                else:
                    print(f"⏸️  No action - waiting for appropriate signal")
            
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
    
    return jsonify({'status':'success','message':f'Bot started - RSI Only Strategy with Profit Protection'})

@app.route('/api/stop_bot',methods=['POST'])
def stop_bot():
    if not trading_state.is_running:
        return jsonify({'status':'error','message':'Bot not running'})
    
    trading_state.is_running=False
    return jsonify({'status':'success','message':'Bot stopped'})

@app.route('/api/status')
def get_status():
    # Update profit stats before returning status
    calculate_profit_stats()
    
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
        'rsi_period': config.rsi_period,
        'rsi_oversold': config.rsi_oversold,
        'rsi_overbought': config.rsi_overbought,
        'profit_target_percent': config.profit_target_percent,  # NEW
        'require_rsi_cycle': config.require_rsi_cycle,  # NEW
        'last_buy_price': trading_state.last_buy_price,  # NEW
        'rsi_cycle_complete': trading_state.rsi_cycle_complete,  # NEW
        'profit_stats': trading_state.profit_stats,  # NEW: Profit statistics
        'sol_balance':trading_state.current_sol_balance,
        'usdt_balance':trading_state.current_usdt_balance
    })

@app.route('/api/update_settings',methods=['POST'])
def update_settings():
    try:
        trade_type = request.args.get('trade_type', 'percentage')
        trade_percentage = int(request.args.get('trade_percentage', 50))
        sol_trade_amount = float(request.args.get('sol_trade_amount', 1.0))
        check_interval = int(request.args.get('check_interval', 900))
        indicator_interval = request.args.get('indicator_interval', '15m')
        rsi_period = int(request.args.get('rsi_period', 14))
        rsi_oversold = int(request.args.get('rsi_oversold', 30))
        rsi_overbought = int(request.args.get('rsi_overbought', 70))
        profit_target_percent = float(request.args.get('profit_target_percent', 1.0))  # NEW
        require_rsi_cycle = request.args.get('require_rsi_cycle', 'true').lower() == 'true'  # NEW
        
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
        
        if rsi_period < 6 or rsi_period > 30:
            return jsonify({'status':'error','message':'RSI period must be 6-30'})
        
        if rsi_oversold < 10 or rsi_oversold > 40:
            return jsonify({'status':'error','message':'RSI oversold must be 10-40'})
        
        if rsi_overbought < 60 or rsi_overbought > 90:
            return jsonify({'status':'error','message':'RSI overbought must be 60-90'})
        
        if profit_target_percent < 0.1 or profit_target_percent > 50:  # NEW
            return jsonify({'status':'error','message':'Profit target must be 0.1-50%'})
        
        config.trade_type = trade_type
        config.trade_percentage = trade_percentage
        config.sol_trade_amount = sol_trade_amount
        config.check_interval = check_interval
        config.indicator_interval = indicator_interval
        config.rsi_period = rsi_period
        config.rsi_oversold = rsi_oversold
        config.rsi_overbought = rsi_overbought
        config.profit_target_percent = profit_target_percent  # NEW
        config.require_rsi_cycle = require_rsi_cycle  # NEW
        
        return jsonify({'status':'success','message':f'Updated: {trade_type} mode, {sol_trade_amount} SOL, {check_interval}s, {indicator_interval}, RSI({rsi_period},{rsi_oversold},{rsi_overbought}), Profit Target: {profit_target_percent}%, RSI Cycle: {require_rsi_cycle}'})
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

@app.route('/api/health')
def health_check():
    """Health check endpoint for monitoring"""
    health_status = {
        'status': 'success',
        'bot_running': trading_state.is_running,
        'api_configured': config.is_configured,
        'timestamp': get_ny_time().isoformat()
    }
    
    # Test API connection
    try:
        result = make_api_request('GET', '/api/spot/v1/account/assets')
        health_status['api_connected'] = 'error' not in result
        if 'error' in result:
            health_status['api_error'] = result.get('error')
    except Exception as e:
        health_status['api_connected'] = False
        health_status['api_error'] = str(e)
    
    return jsonify(health_status)

@app.route('/api/debug')
def debug_info():
    """Debug endpoint to check configuration"""
    debug_info = {
        'api_key_configured': bool(config.api_key),
        'api_secret_configured': bool(config.api_secret),
        'passphrase_configured': bool(config.passphrase),
        'api_key_length': len(config.api_key) if config.api_key else 0,
        'api_secret_length': len(config.api_secret) if config.api_secret else 0,
        'is_fully_configured': config.is_configured
    }
    return jsonify(debug_info)

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
        
        # NEW: Store buy price for manual buys too
        trading_state.last_buy_price = current_price
        if config.require_rsi_cycle:
            trading_state.rsi_cycle_complete = False
        
        time.sleep(1)
        get_current_balances()
        
        trade_record = {
            'time':get_ny_time().isoformat(),
            'action':'MANUAL BUY',
            'sol_amount':sol_amount_rounded,
            'usdt_amount':sol_amount_rounded * current_price,
            'price':current_price,
            'interval':'manual',
            'signals':{}
        }
        trading_state.trade_history.append(trade_record)
        # Update profit stats after trade
        calculate_profit_stats()
        
        return jsonify({'status':'success','message':f'{log_message} successful: {sol_amount_rounded:.4f} SOL for ${usdt_to_spend:.2f}'})
        
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

@app.route('/api/manual_sell',methods=['POST'])
def manual_sell():
    """Execute manual sell order - ALWAYS sells 100% of SOL balance"""
    try:
        sol_balance, usdt_balance = get_current_balances()
        
        # --- ALWAYS sell 100% of SOL balance ---
        sol_amount_to_sell = sol_balance
            
        if sol_balance < sol_amount_to_sell:
            return jsonify({'status':'error','message':f'Insufficient SOL: Need {sol_amount_to_sell:.4f} SOL, have {sol_balance:.4f} SOL'})
            
        sol_amount_rounded=round(sol_amount_to_sell,4)
        
        # Try to get price with better error handling
        ticker_result = make_api_request('GET', '/api/spot/v1/market/ticker?symbol=SOLUSDT_SPBL')
        
        if 'error' in ticker_result:
            return jsonify({'status':'error','message':'Failed to get price'})
        
        data=ticker_result.get('data',{})
        price_field=data.get('close') or data.get('last') or data.get('price')
        if not price_field:
            return jsonify({'status':'error','message':'Could not get current price'})
        
        current_price=float(price_field)
        expected_usdt=sol_amount_rounded*current_price
        
        log_message = f'Manual SELL of 100% SOL ({sol_amount_rounded:.4f} SOL)'
            
        order_data={
            "symbol":"SOLUSDT_SPBL",
            "side":"sell",
            "orderType":"market",
            "quantity":str(sol_amount_rounded),
            "force":"normal"
        }
        
        print(f"\n{'='*60}")
        print(f"MANUAL SELL ORDER")
        print(f"Amount: {sol_amount_rounded:.4f} SOL (100% of balance)")
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
        
        # NEW: Clear buy price after manual sell
        trading_state.last_buy_price = None
        
        time.sleep(1)
        get_current_balances()
        
        trade_record = {
            'time':get_ny_time().isoformat(),
            'action':'MANUAL SELL',
            'sol_amount':sol_amount_rounded,
            'usdt_amount':expected_usdt,
            'price':current_price,
            'interval':'manual',
            'signals':{}
        }
        trading_state.trade_history.append(trade_record)
        # Update profit stats after trade
        calculate_profit_stats()
        
        return jsonify({'status':'success','message':f'{log_message} successful: {sol_amount_rounded:.4f} SOL for ${expected_usdt:.2f}'})
        
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

if __name__=='__main__':
    print("\n"+"="*60)
    print("SOLANA TRADING BOT - RSI ONLY STRATEGY WITH PROFIT PROTECTION")
    print("="*60)
    
    # Test API connection first
    if not test_api_connection():
        print("\n⚠️  Bot cannot start due to configuration issues")
        print("Please check your API credentials and try again")
    else:
        if config.trade_type == 'percentage':
            print(f"\nBuy Amount: {config.trade_percentage}% of balance per trade")
        else:
            print(f"\nBuy Amount: {config.sol_trade_amount} SOL per trade")
        print("Sell Amount: 100% of SOL balance")
        print("Strategy: RSI Only (Oversold/Overbought levels)")
        print(f"RSI Settings: Period={config.rsi_period}, Oversold={config.rsi_oversold}, Overbought={config.rsi_overbought}")
        print(f"Profit Protection: Never sell at loss, target {config.profit_target_percent}% profit")
        print(f"RSI Cycle Required: {config.require_rsi_cycle}")
        print(f"Interval: {config.indicator_interval}")
        print(f"Check: {config.check_interval} seconds")
    
    print("\nStarting server...")
    print("="*60+"\n")
    
    app.run(debug=True,host='0.0.0.0',port=5000)
