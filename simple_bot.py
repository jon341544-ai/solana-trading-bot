import os
import time
import hmac
import hashlib
import base64
import requests
import json
from flask import Flask, jsonify, request
from datetime import datetime
import threading

app = Flask(__name__)

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'message': 'Bot is running'})

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
        timeout = 5
        
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

def get_klines_simple(interval=None, limit=100):
    """Fetch candlestick data without pandas"""
    if interval is None:
        interval = config.indicator_interval
        
    try:
        # Check if bot should stop
        if not trading_state.is_running:
            return None
            
        # Convert interval to granularity
        interval_map = {
            '1m': '60', '5m': '300', '15m': '900', '30m': '1800',
            '1H': '3600', '4H': '14400', '1D': '86400'
        }
        granularity = interval_map.get(interval, '900')
        
        # Get recent candles
        symbol_mix = 'SOLUSDT_UMCBL'
        endpoint = f'/api/mix/v1/market/candles?symbol={symbol_mix}&granularity={granularity}&limit={limit}'
        
        result = make_api_request('GET', endpoint)
        
        # Check if bot was stopped during API call
        if not trading_state.is_running:
            return None
            
        if 'error' in result:
            print(f"ERROR in klines: {result.get('error')}")
            return None
            
        # Process candles data
        if isinstance(result, list):
            candles = result
        elif isinstance(result, dict) and 'data' in result:
            candles = result['data']
        else:
            return None
            
        if not candles:
            return None
            
        # Extract close prices and basic OHLC data
        closes = []
        highs = []
        lows = []
        
        for candle in candles[-100:]:  # Use last 100 candles
            if len(candle) >= 5:
                try:
                    closes.append(float(candle[4]))  # close price
                    highs.append(float(candle[2]))   # high price
                    lows.append(float(candle[3]))    # low price
                except (ValueError, IndexError):
                    continue
        
        return {
            'closes': closes,
            'highs': highs,
            'lows': lows,
            'current_price': closes[-1] if closes else 0
        }
    except Exception as e:
        print(f"Error fetching klines: {e}")
        return None

def calculate_supertrend_simple(data, period=10, multiplier=3):
    """Calculate Supertrend without pandas"""
    try:
        highs = data['highs'][-period*2:]  # Get enough data
        lows = data['lows'][-period*2:]
        closes = data['closes'][-period*2:]
        
        if len(closes) < period:
            return 0
            
        # Calculate ATR (simplified)
        tr_values = []
        for i in range(1, len(highs)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i-1])
            lc = abs(lows[i] - closes[i-1])
            tr = max(hl, hc, lc)
            tr_values.append(tr)
        
        # Simple ATR calculation
        atr = sum(tr_values[-period:]) / period if tr_values else 0
        
        # Basic supertrend logic
        current_high = highs[-1]
        current_low = lows[-1]
        current_close = closes[-1]
        
        hl_avg = (current_high + current_low) / 2
        upper_band = hl_avg + (multiplier * atr)
        lower_band = hl_avg - (multiplier * atr)
        
        # Simple trend detection
        if current_close > upper_band:
            return 1  # Uptrend
        elif current_close < lower_band:
            return -1  # Downtrend
        else:
            return 0  # Neutral
            
    except Exception as e:
        print(f"Error calculating Supertrend: {e}")
        return 0

def calculate_macd_simple(data, fast=12, slow=26, signal=9):
    """Calculate MACD without pandas"""
    try:
        closes = data['closes']
        
        if len(closes) < slow:
            return 0
            
        # Simple EMA calculation
        def calculate_ema(prices, period):
            if len(prices) < period:
                return prices[-1] if prices else 0
                
            ema = prices[-period]
            multiplier = 2 / (period + 1)
            
            for price in prices[-period+1:]:
                ema = (price - ema) * multiplier + ema
                
            return ema
        
        # Calculate MACD components
        ema_fast = calculate_ema(closes, fast)
        ema_slow = calculate_ema(closes, slow)
        macd_line = ema_fast - ema_slow
        
        # For signal line, use a shorter period of recent MACD values
        recent_macds = []
        for i in range(min(signal, len(closes))):
            fast_ema = calculate_ema(closes[:-(i+1)], fast) if len(closes) > (i+1) else 0
            slow_ema = calculate_ema(closes[:-(i+1)], slow) if len(closes) > (i+1) else 0
            recent_macds.append(fast_ema - slow_ema)
        
        signal_line = sum(recent_macds) / len(recent_macds) if recent_macds else macd_line
        
        # Determine signal
        if macd_line > signal_line:
            return 1
        else:
            return -1
            
    except Exception as e:
        print(f"Error calculating MACD: {e}")
        return 0

def calculate_rsi_simple(data, period=14):
    """Calculate RSI as a third indicator instead of FantailVMA"""
    try:
        closes = data['closes']
        
        if len(closes) <= period:
            return 0
            
        gains = []
        losses = []
        
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        # Use recent period
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 1 if avg_gain > 0 else 0
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        if rsi > 70:
            return -1  # Overbought
        elif rsi < 30:
            return 1   # Oversold
        else:
            return 0   # Neutral
            
    except Exception as e:
        print(f"Error calculating RSI: {e}")
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
                        sol_balance = float(available)
                    elif coin_name == 'USDT':
                        usdt_balance = float(available)
        
        trading_state.current_sol_balance = sol_balance
        trading_state.current_usdt_balance = usdt_balance
        
        return sol_balance, usdt_balance
    except Exception as e:
        print(f"Error getting balances: {e}")
        return 0.0, 0.0

def get_trading_signals():
    """Get signals from all three indicators"""
    data = get_klines_simple(interval=config.indicator_interval, limit=100)
    if data is None or not data['closes']:
        return None
    
    signals = {
        'supertrend': calculate_supertrend_simple(data),
        'macd': calculate_macd_simple(data),
        'rsi': calculate_rsi_simple(data),
        'timestamp': datetime.now().isoformat(),
        'price': data['current_price'],
        'interval': config.indicator_interval
    }
    
    # Calculate consensus (2 out of 3)
    buy_votes = sum([1 for v in [signals['supertrend'], signals['macd'], signals['rsi']] if v == 1])
    sell_votes = sum([1 for v in [signals['supertrend'], signals['macd'], signals['rsi']] if v == -1])
    
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
        
        # Ensure minimum order size - CoinCatch API minimum: 0.1 SOL
        if sol_amount < 0.1:
            print(f"Buy amount too small: {sol_amount} SOL (min: 0.1 SOL per CoinCatch API)")
            return False
        
        # Also check minimum notional value (approximately $15-20 USD)
        notional_value = sol_amount * current_price
        if notional_value < 15:
            print(f"Buy amount too small in USD value: ${notional_value:.2f} (min: ~$15-20 USD)")
            return False
        
        limit_price = current_price * 1.005  # 0.5% above market
        
        order_data = {
            "symbol": "SOLUSDT_SPBL",
            "side": "buy",
            "orderType": "limit",
            "price": str(round(limit_price, 2)),
            "quantity": str(round(sol_amount, 4)),
            "force": "normal"
        }
        
        print(f"\n{'='*60}")
        print(f"EXECUTING REAL BUY ORDER")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"USDT Balance: ${usdt_balance:.2f}")
        print(f"Trade Percentage: {config.trade_percentage}%")
        print(f"Buy Amount: ${buy_amount_usdt:.2f} USDT")
        print(f"SOL Amount: {sol_amount:.4f} SOL")
        print(f"Price: ${limit_price:.2f}")
        print(f"Notional Value: ${notional_value:.2f} USD")
        print(f"Interval: {config.indicator_interval}")
        print(f"{'='*60}\n")
        
        result = make_api_request('POST', '/api/spot/v1/trade/orders', order_data)
        
        # Check if bot was stopped during order
        if not trading_state.is_running:
            return False
            
        if 'error' in result:
            print(f"Limit order failed, trying market order...")
            market_order_data = {
                "symbol": "SOLUSDT_SPBL",
                "side": "buy",
                "orderType": "market",
                "quantity": str(round(sol_amount, 4)),
                "force": "normal"
            }
            result = make_api_request('POST', '/api/spot/v1/trade/orders', market_order_data)
            
            if 'error' in result:
                print(f"Buy order failed: {result.get('message')}")
                return False
        
        print(f"✅ BUY ORDER SUCCESSFUL: {result}")
        return True
        
    except Exception as e:
        print(f"Error executing buy order: {e}")
        return False

def execute_sell_order():
    """Execute REAL sell order - ALWAYS SELL 100% OF SOL"""
    try:
        # Check if bot should stop
        if not trading_state.is_running:
            return False
            
        # Get current balances
        sol_balance, usdt_balance = get_current_balances()
        
        if sol_balance <= 0:
            print("No SOL available for selling")
            return False
        
        # Always sell 100% of SOL balance
        sol_amount = sol_balance
        
        # Check if we meet minimum sell amount - CoinCatch API minimum: 0.1 SOL
        if sol_amount < 0.1:
            print(f"Sell amount too small: {sol_amount} SOL (min: 0.1 SOL per CoinCatch API)")
            return False
        
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
        
        current_price = float(price_field)
        limit_price = current_price * 0.995  # 0.5% below market
        
        # Check minimum notional value
        notional_value = sol_amount * current_price
        if notional_value < 15:
            print(f"Sell amount too small in USD value: ${notional_value:.2f} (min: ~$15-20 USD)")
            return False
        
        order_data = {
            "symbol": "SOLUSDT_SPBL",
            "side": "sell",
            "orderType": "limit",
            "price": str(round(limit_price, 2)),
            "quantity": str(round(sol_amount, 4)),
            "force": "normal"
        }
        
        print(f"\n{'='*60}")
        print(f"EXECUTING REAL SELL ORDER")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"SOL Balance: {sol_balance:.4f} SOL")
        print(f"Sell Amount: {sol_amount:.4f} SOL (100% of balance)")
        print(f"Price: ${limit_price:.2f}")
        print(f"Expected USDT: ${sol_amount * limit_price:.2f}")
        print(f"Notional Value: ${notional_value:.2f} USD")
        print(f"Interval: {config.indicator_interval}")
        print(f"{'='*60}\n")
        
        result = make_api_request('POST', '/api/spot/v1/trade/orders', order_data)
        
        # Check if bot was stopped during order
        if not trading_state.is_running:
            return False
            
        if 'error' in result:
            print(f"Limit order failed, trying market order...")
            market_order_data = {
                "symbol": "SOLUSDT_SPBL",
                "side": "sell",
                "orderType": "market",
                "quantity": str(round(sol_amount, 4)),
                "force": "normal"
            }
            result = make_api_request('POST', '/api/spot/v1/trade/orders', market_order_data)
            
            if 'error' in result:
                print(f"Sell order failed: {result.get('message')}")
                return False
        
        print(f"✅ SELL ORDER SUCCESSFUL: {result}")
        return True
        
    except Exception as e:
        print(f"Error executing sell order: {e}")
        return False

def trading_loop():
    """Main trading loop - PERCENTAGE BASED BUYS, 100% SELLS"""
    print("\n🤖 AUTOMATED SOL TRADING BOT STARTED - REAL TRADING MODE 🤖")
    print(f"Trade Percentage: {config.trade_percentage}% of USDT for SOL buys")
    print(f"Sell Strategy: ALWAYS 100% of SOL balance")
    print(f"Check Interval: {config.check_interval} seconds")
    print(f"Indicator Interval: {config.indicator_interval}")
    print(f"Strategy: 2 out of 3 indicators must agree")
    print(f"Minimum Trade: 0.1 SOL (CoinCatch API Requirement)")
    print(f"Minimum Notional: ~$15-20 USD\n")
    
    while trading_state.is_running:
        try:
            # Get current signals with interruption check
            if not trading_state.is_running:
                break
                
            signals = get_trading_signals()
            
            if signals is None:
                print("Failed to get trading signals, retrying...")
                # Check flag during sleep with smaller intervals
                for _ in range(config.check_interval):
                    if not trading_state.is_running:
                        break
                    time.sleep(1)
                continue
            
            trading_state.last_signals = signals
            
            # Get current balances for display
            sol_balance, usdt_balance = get_current_balances()
            
            print(f"\n--- Trading Check at {signals['timestamp']} ---")
            print(f"Price: ${signals['price']:.2f}")
            print(f"SOL Balance: {sol_balance:.4f} SOL")
            print(f"USDT Balance: ${usdt_balance:.2f}")
            print(f"Trade Percentage: {config.trade_percentage}%")
            print(f"Interval: {signals['interval']}")
            print(f"Supertrend: {'🟢 LONG' if signals['supertrend'] == 1 else '🔴 SHORT' if signals['supertrend'] == -1 else '⚪ NEUTRAL'}")
            print(f"MACD: {'🟢 LONG' if signals['macd'] == 1 else '🔴 SHORT' if signals['macd'] == -1 else '⚪ NEUTRAL'}")
            print(f"RSI: {'🟢 LONG' if signals['rsi'] == 1 else '🔴 SHORT' if signals['rsi'] == -1 else '⚪ NEUTRAL'}")
            print(f"CONSENSUS: {signals['consensus']}")
            print(f"Current Position: {trading_state.last_position or 'NONE'}")
            
            # Check if we should stop before executing trades
            if not trading_state.is_running:
                break
                
            # Trading logic: PERCENTAGE BUYS, 100% SELLS
            if signals['consensus'] == 'BUY' and trading_state.last_position != 'long':
                print("\n🚀 BUY SIGNAL DETECTED - Executing REAL BUY order...")
                
                if execute_buy_order():
                    trading_state.last_position = 'long'
                    trading_state.last_trade_time = datetime.now()
                    trading_state.trade_history.append({
                        'time': datetime.now().isoformat(),
                        'action': 'BUY',
                        'percentage': config.trade_percentage,
                        'sol_amount': sol_balance,
                        'usdt_amount': usdt_balance * (config.trade_percentage / 100.0),
                        'price': signals['price'],
                        'interval': config.indicator_interval,
                        'signals': signals
                    })
                    print(f"✅ Position changed to LONG")
                else:
                    print(f"❌ Buy order failed")
                    
            elif signals['consensus'] == 'SELL' and trading_state.last_position != 'short':
                print("\n📉 SELL SIGNAL DETECTED - Executing REAL SELL order...")
                
                if execute_sell_order():
                    trading_state.last_position = 'short'
                    trading_state.last_trade_time = datetime.now()
                    trading_state.trade_history.append({
                        'time': datetime.now().isoformat(),
                        'action': 'SELL',
                        'percentage': 100,  # Always 100% for sells
                        'sol_amount': sol_balance,
                        'usdt_amount': sol_balance * signals['price'],
                        'price': signals['price'],
                        'interval': config.indicator_interval,
                        'signals': signals
                    })
                    print(f"✅ Position changed to SHORT")
                else:
                    print(f"❌ Sell order failed")
            else:
                print(f"⏸️  No action taken - Either neutral signal or already in position")
            
            # Wait before next check with interruptible sleep
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
    
    print("\n🛑 AUTOMATED TRADING BOT STOPPED")

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

# Flask Routes
@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Automated SOL Trading Bot</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f0f0f0; }
            .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px; text-align: center; }
            button { background: #667eea; color: white; border: none; padding: 12px 20px; margin: 5px; border-radius: 5px; cursor: pointer; font-size: 14px; }
            button:hover { background: #5568d3; }
            button:disabled { background: #cccccc; cursor: not-allowed; }
            .start-button { background: #28a745; font-size: 16px; padding: 15px 30px; }
            .start-button:hover { background: #218838; }
            .stop-button { background: #dc3545; font-size: 16px; padding: 15px 30px; }
            .stop-button:hover { background: #c82333; }
            .force-stop-button { background: #ff0000; font-size: 16px; padding: 15px 30px; }
            .force-stop-button:hover { background: #cc0000; }
            .status-running { color: #28a745; font-weight: bold; }
            .status-stopped { color: #dc3545; font-weight: bold; }
            .signal-long { color: #28a745; }
            .signal-short { color: #dc3545; }
            .signal-neutral { color: #6c757d; }
            input[type="number"] { padding: 8px; border: 1px solid #ddd; border-radius: 4px; width: 150px; }
            select { padding: 8px; border: 1px solid #ddd; border-radius: 4px; width: 150px; }
            .settings { background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0; }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; }
            th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
            th { background: #f8f9fa; font-weight: bold; }
            .trade-buy { color: #28a745; font-weight: bold; }
            .trade-sell { color: #dc3545; font-weight: bold; }
            .setting-group { margin-bottom: 15px; }
            .setting-group label { display: block; margin-bottom: 5px; font-weight: bold; }
            .warning { background: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; margin: 10px 0; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🤖 Automated SOL Trading Bot</h1>
            <p>Percentage-Based Trading - Buys: X% of USDT, Sells: 100% of SOL</p>
        </div>
        
        <div class="warning">
            <strong>⚠️ Minimum Trade Requirements:</strong><br>
            • Minimum Order: 0.1 SOL<br>
            • Minimum Notional Value: ~$15-20 USD<br>
            • Ensure sufficient balance for minimum trades
        </div>
        
        <div class="card">
            <h3>Bot Status</h3>
            <div>
                <strong>Status:</strong> <span id="botStatus" class="status-stopped">STOPPED</span><br>
                <strong>Current Position:</strong> <span id="currentPosition">NONE</span><br>
                <strong>Last Trade:</strong> <span id="lastTrade">Never</span><br>
                <strong>Current Interval:</strong> <span id="currentInterval">15m</span>
            </div>
        </div>

        <div class="card">
            <h3>Market Data & Balances</h3>
            <strong>SOL Price:</strong> $<span id="solPrice">--</span><br>
            <strong>USDT Balance:</strong> $<span id="usdtBalance">--</span><br>
            <strong>SOL Balance:</strong> <span id="solBalance">--</span> SOL<br>
            <strong>Trade Percentage:</strong> <span id="tradePercentage">50</span>% of USDT for buys<br>
            <strong>Sell Strategy:</strong> <span style="color: #dc3545;">ALWAYS 100% of SOL</span>
        </div>

        <div class="card">
            <h3>Indicator Signals (2 out of 3 needed)</h3>
            <table>
                <tr>
                    <th>Indicator</th>
                    <th>Signal</th>
                </tr>
                <tr>
                    <td>Supertrend</td>
                    <td id="supertrendSignal">--</td>
                </tr>
                <tr>
                    <td>MACD</td>
                    <td id="macdSignal">--</td>
                </tr>
                <tr>
                    <td>RSI</td>
                    <td id="rsiSignal">--</td>
                </tr>
                <tr style="background: #f8f9fa; font-weight: bold;">
                    <td>CONSENSUS</td>
                    <td id="consensusSignal">--</td>
                </tr>
            </table>
        </div>

        <div class="card settings">
            <h3>⚙️ Trading Settings</h3>
            
            <div class="setting-group">
                <label><strong>Trade Percentage (% of USDT):</strong></label>
                <input type="number" id="tradePercentageInput" value="50" min="1" max="100" step="1">
                <div style="font-size: 12px; color: #666;">Percentage of USDT to use for SOL buys</div>
            </div>

            <div class="setting-group">
                <label><strong>Check Interval (seconds):</strong></label>
                <input type="number" id="checkInterval" value="900" min="60" step="60">
                <div style="font-size: 12px; color: #666;">Time between signal checks</div>
            </div>

            <div class="setting-group">
                <label><strong>Indicator Timeframe:</strong></label>
                <select id="indicatorInterval">
                    <option value="1m">1 Minute</option>
                    <option value="5m">5 Minutes</option>
                    <option value="15m" selected>15 Minutes</option>
                    <option value="30m">30 Minutes</option>
                    <option value="1H">1 Hour</option>
                    <option value="4H">4 Hours</option>
                    <option value="1D">1 Day</option>
                </select>
                <div style="font-size: 12px; color: #666;">Higher timeframes = fewer trades, lower fees</div>
            </div>

            <button onclick="updateSettings()">Update All Settings</button>
            <div style="margin-top: 10px; font-size: 12px; color: #666;">
                Note: Buys use X% of USDT balance. Sells always use 100% of SOL balance.<br>
                Minimum trade: 0.1 SOL (~$15-20 USD minimum notional value)
            </div>
        </div>

        <div class="card" style="text-align: center;">
            <button onclick="startBot()" id="startButton" class="start-button">▶️ START AUTOMATED TRADING</button>
            <button onclick="stopBot()" id="stopButton" class="stop-button" disabled>⏹️ STOP TRADING</button>
            <button onclick="forceStopBot()" id="forceStopButton" class="force-stop-button" disabled>🛑 FORCE STOP</button>
        </div>

        <div class="card">
            <h3>📊 Trade History (Last 10)</h3>
            <div id="tradeHistory">No trades yet</div>
        </div>

        <div class="card">
            <button onclick="refreshData()">🔄 Refresh Data</button>
            <button onclick="getBalance()">💰 Get Balance</button>
        </div>

        <div id="result" style="margin-top: 20px;"></div>

        <script>
            let refreshInterval;

            async function apiCall(endpoint, method = 'GET') {
                try {
                    const response = await fetch(endpoint, { method });
                    return await response.json();
                } catch (error) {
                    console.error('API call error:', error);
                    return { status: 'error', message: error.message };
                }
            }

            function formatSignal(value) {
                if (value === 1) return '<span class="signal-long">🟢 LONG</span>';
                if (value === -1) return '<span class="signal-short">🔴 SHORT</span>';
                return '<span class="signal-neutral">⚪ NEUTRAL</span>';
            }

            async function startBot() {
                const result = document.getElementById('result');
                result.innerHTML = 'Starting automated trading...';
                
                const data = await apiCall('/api/start_bot', 'POST');
                
                if (data.status === 'success') {
                    result.innerHTML = '<div style="color: green;">✅ ' + data.message + '</div>';
                    document.getElementById('botStatus').textContent = 'RUNNING';
                    document.getElementById('botStatus').className = 'status-running';
                    document.getElementById('startButton').disabled = true;
                    document.getElementById('stopButton').disabled = false;
                    document.getElementById('forceStopButton').disabled = false;
                    
                    // Start auto-refresh
                    refreshInterval = setInterval(refreshData, 5000);
                } else {
                    result.innerHTML = '<div style="color: red;">❌ ' + data.message + '</div>';
                }
            }

            async function stopBot() {
                const result = document.getElementById('result');
                result.innerHTML = 'Stopping automated trading...';
                
                const data = await apiCall('/api/stop_bot', 'POST');
                
                if (data.status === 'success') {
                    result.innerHTML = '<div style="color: orange;">⏹️ ' + data.message + '</div>';
                    document.getElementById('botStatus').textContent = 'STOPPED';
                    document.getElementById('botStatus').className = 'status-stopped';
                    document.getElementById('startButton').disabled = false;
                    document.getElementById('stopButton').disabled = true;
                    document.getElementById('forceStopButton').disabled = true;
                    
                    // Stop auto-refresh
                    if (refreshInterval) clearInterval(refreshInterval);
                } else {
                    result.innerHTML = '<div style="color: red;">❌ ' + data.message + '</div>';
                }
            }

            async function forceStopBot() {
                const result = document.getElementById('result');
                result.innerHTML = 'Force stopping bot immediately...';
                
                const data = await apiCall('/api/force_stop', 'POST');
                
                if (data.status === 'success') {
                    result.innerHTML = '<div style="color: red;">🛑 ' + data.message + '</div>';
                    document.getElementById('botStatus').textContent = 'STOPPED';
                    document.getElementById('botStatus').className = 'status-stopped';
                    document.getElementById('startButton').disabled = false;
                    document.getElementById('stopButton').disabled = true;
                    document.getElementById('forceStopButton').disabled = true;
                    
                    // Stop auto-refresh
                    if (refreshInterval) clearInterval(refreshInterval);
                } else {
                    result.innerHTML = '<div style="color: red;">❌ ' + data.message + '</div>';
                }
            }

            async function updateSettings() {
                const tradePercentage = parseInt(document.getElementById('tradePercentageInput').value);
                const checkInterval = parseInt(document.getElementById('checkInterval').value);
                const indicatorInterval = document.getElementById('indicatorInterval').value;
                
                if (tradePercentage < 1 || tradePercentage > 100) {
                    alert('Trade percentage must be between 1% and 100%');
                    return;
                }
                
                if (checkInterval < 60) {
                    alert('Minimum check interval is 60 seconds');
                    return;
                }
                
                const data = await apiCall(`/api/update_settings?trade_percentage=${tradePercentage}&check_interval=${checkInterval}&indicator_interval=${indicatorInterval}`, 'POST');
                
                if (data.status === 'success') {
                    document.getElementById('result').innerHTML = '<div style="color: green;">✅ Settings updated</div>';
                    document.getElementById('currentInterval').textContent = indicatorInterval;
                    document.getElementById('tradePercentage').textContent = tradePercentage;
                } else {
                    document.getElementById('result').innerHTML = '<div style="color: red;">❌ ' + data.message + '</div>';
                }
            }

            async function refreshData() {
                const data = await apiCall('/api/status');
                
                if (data.status === 'success') {
                    // Update bot status
                    if (data.is_running) {
                        document.getElementById('botStatus').textContent = 'RUNNING';
                        document.getElementById('botStatus').className = 'status-running';
                        document.getElementById('startButton').disabled = true;
                        document.getElementById('stopButton').disabled = false;
                        document.getElementById('forceStopButton').disabled = false;
                    } else {
                        document.getElementById('botStatus').textContent = 'STOPPED';
                        document.getElementById('botStatus').className = 'status-stopped';
                        document.getElementById('startButton').disabled = false;
                        document.getElementById('stopButton').disabled = true;
                        document.getElementById('forceStopButton').disabled = true;
                    }
                    
                    // Update position and settings
                    document.getElementById('currentPosition').textContent = data.last_position || 'NONE';
                    document.getElementById('lastTrade').textContent = data.last_trade_time || 'Never';
                    document.getElementById('currentInterval').textContent = data.indicator_interval || '15m';
                    document.getElementById('tradePercentage').textContent = data.trade_percentage || '50';
                    
                    // Update settings form values
                    document.getElementById('tradePercentageInput').value = data.trade_percentage || 50;
                    document.getElementById('checkInterval').value = data.check_interval || 900;
                    document.getElementById('indicatorInterval').value = data.indicator_interval || '15m';
                    
                    // Update market data
                    if (data.signals) {
                        document.getElementById('solPrice').textContent = data.signals.price.toFixed(2);
                        document.getElementById('supertrendSignal').innerHTML = formatSignal(data.signals.supertrend);
                        document.getElementById('macdSignal').innerHTML = formatSignal(data.signals.macd);
                        document.getElementById('rsiSignal').innerHTML = formatSignal(data.signals.rsi);
                        
                        let consensusHTML = data.signals.consensus;
                        if (data.signals.consensus === 'BUY') {
                            consensusHTML = '<span class="signal-long">🚀 BUY</span>';
                        } else if (data.signals.consensus === 'SELL') {
                            consensusHTML = '<span class="signal-short">📉 SELL</span>';
                        } else {
                            consensusHTML = '<span class="signal-neutral">⏸️ NEUTRAL</span>';
                        }
                        document.getElementById('consensusSignal').innerHTML = consensusHTML;
                    }
                    
                    // Update balances
                    document.getElementById('solBalance').textContent = data.sol_balance || '--';
                    document.getElementById('usdtBalance').textContent = data.usdt_balance || '--';
                    
                    // Update trade history
                    if (data.trade_history && data.trade_history.length > 0) {
                        let historyHTML = '<table><tr><th>Time</th><th>Action</th><th>Percentage</th><th>Amount</th><th>Price</th><th>Interval</th></tr>';
                        data.trade_history.slice(-10).reverse().forEach(trade => {
                            const tradeClass = trade.action === 'BUY' ? 'trade-buy' : 'trade-sell';
                            const amountDisplay = trade.action === 'BUY' 
                                ? `$${trade.usdt_amount?.toFixed(2) || '0'} USDT` 
                                : `${trade.sol_amount?.toFixed(4) || '0'} SOL`;
                            historyHTML += `<tr>
                                <td>${new Date(trade.time).toLocaleString()}</td>
                                <td class="${tradeClass}">${trade.action}</td>
                                <td>${trade.percentage}%</td>
                                <td>${amountDisplay}</td>
                                <td>$${trade.price?.toFixed(2) || '0'}</td>
                                <td>${trade.interval || '15m'}</td>
                            </tr>`;
                        });
                        historyHTML += '</table>';
                        document.getElementById('tradeHistory').innerHTML = historyHTML;
                    }
                }
            }

            async function getBalance() {
                const data = await apiCall('/api/balance');
                
                if (data.status === 'success') {
                    document.getElementById('solBalance').textContent = data.sol_balance;
                    document.getElementById('usdtBalance').textContent = data.usdt_balance;
                    document.getElementById('result').innerHTML = '<div style="color: green;">✅ Balance updated</div>';
                }
            }

            // Initial load
            refreshData();
            getBalance();
        </script>
    </body>
    </html>
    '''

@app.route('/api/start_bot', methods=['POST'])
def start_bot():
    """Start the automated trading bot"""
    if trading_state.is_running:
        return jsonify({
            'status': 'error',
            'message': 'Bot is already running'
        })
    
    if not config.is_configured:
        return jsonify({
            'status': 'error',
            'message': 'API credentials not configured'
        })
    
    trading_state.is_running = True
    trading_thread = threading.Thread(target=trading_loop, daemon=True)
    trading_thread.start()
    
    return jsonify({
        'status': 'success',
        'message': 'Automated SOL trading bot started - PERCENTAGE MODE'
    })

@app.route('/api/stop_bot', methods=['POST'])
def stop_bot():
    """Stop the automated trading bot"""
    if not trading_state.is_running:
        return jsonify({
            'status': 'error',
            'message': 'Bot is not running'
        })
    
    trading_state.is_running = False
    
    return jsonify({
        'status': 'success',
        'message': 'Automated trading bot stopped'
    })

@app.route('/api/force_stop', methods=['POST'])
def force_stop():
    """Force stop the bot immediately"""
    trading_state.is_running = False
    
    return jsonify({
        'status': 'success',
        'message': 'Bot force stopped immediately'
    })

@app.route('/api/status')
def get_status():
    """Get current bot status"""
    return jsonify({
        'status': 'success',
        'is_running': trading_state.is_running,
        'last_position': trading_state.last_position,
        'last_trade_time': trading_state.last_trade_time.isoformat() if trading_state.last_trade_time else None,
        'signals': trading_state.last_signals,
        'trade_history': trading_state.trade_history,
        'trade_percentage': config.trade_percentage,
        'check_interval': config.check_interval,
        'indicator_interval': config.indicator_interval,
        'sol_balance': trading_state.current_sol_balance,
        'usdt_balance': trading_state.current_usdt_balance
    })

@app.route('/api/update_settings', methods=['POST'])
def update_settings():
    """Update trading settings"""
    try:
        trade_percentage = int(request.args.get('trade_percentage', 50))
        check_interval = int(request.args.get('check_interval', 900))
        indicator_interval = request.args.get('indicator_interval', '15m')
        
        # Validate inputs
        if trade_percentage < 1 or trade_percentage > 100:
            return jsonify({
                'status': 'error',
                'message': 'Trade percentage must be between 1% and 100%'
            })
        
        if check_interval < 60:
            return jsonify({
                'status': 'error', 
                'message': 'Minimum check interval is 60 seconds'
            })
        
        valid_intervals = ['1m', '5m', '15m', '30m', '1H', '4H', '1D']
        if indicator_interval not in valid_intervals:
            return jsonify({
                'status': 'error',
                'message': f'Invalid interval. Must be one of: {", ".join(valid_intervals)}'
            })
        
        # Update config
        config.trade_percentage = trade_percentage
        config.check_interval = check_interval
        config.indicator_interval = indicator_interval
        
        return jsonify({
            'status': 'success',
            'message': f'Settings updated: {trade_percentage}% of USDT, {check_interval}s check, {indicator_interval} timeframe'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

@app.route('/api/balance')
def get_balance():
    """Get current balance"""
    try:
        result = make_api_request('GET', '/api/spot/v1/account/assets')
        
        if 'error' in result:
            return jsonify({
                'status': 'error',
                'message': 'Failed to get balance'
            })
        
        sol_balance, usdt_balance = extract_balances(result)
        
        # Update trading state
        trading_state.current_sol_balance = float(sol_balance)
        trading_state.current_usdt_balance = float(usdt_balance)
        
        return jsonify({
            'status': 'success',
            'sol_balance': sol_balance,
            'usdt_balance': usdt_balance
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
