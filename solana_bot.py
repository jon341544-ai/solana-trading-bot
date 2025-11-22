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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import threading

app = Flask(__name__)

# FUTURES TRADING CONFIGURATION
class Config:
    def __init__(self):
        self.api_key = os.environ.get('COINCATCH_API_KEY', '')
        self.api_secret = os.environ.get('COINCATCH_API_SECRET', '') 
        self.passphrase = os.environ.get('COINCATCH_PASSPHRASE', '')
        self.base_url = "https://api.coincatch.com"
        self.is_configured = bool(self.api_key and self.api_secret and self.passphrase)
        
        self.timezone = ZoneInfo('America/New_York')
        
        # 🚀 FUTURES SETTINGS 🚀
        self.leverage_multiplier = 5  # Your simple multiplier: 1-20x
        self.base_position_size = 0.1  # Base position size in SOL
        self.check_interval = 300  # 5 minutes
        
        # Aggressive Indicators
        self.rsi_period = 7
        self.macd_fast = 6
        self.macd_slow = 13  
        self.macd_signal = 5
        
        # Risk Management
        self.max_daily_loss = 0.10  # 10% daily loss limit
        self.stop_loss_pct = 0.05   # 5% stop loss
        self.take_profit_pct = 0.10 # 10% take profit
        
        # Trading parameters
        self.symbol = "SOLUSDT_UMCBL"  # Futures symbol
        self.margin_mode = "crossed"   # or "isolated"
        self.position_side = "LONG"    # or "SHORT" - auto-decided

config = Config()

def get_ny_time():
    return datetime.now(config.timezone)

class TradingState:
    def __init__(self):
        self.is_running = False
        self.current_position = None  # 'long', 'short', or None
        self.position_size = 0.0
        self.entry_price = 0.0
        self.unrealized_pnl = 0.0
        self.realized_pnl = 0.0
        self.last_trade_time = None
        self.last_signals = {}
        self.trade_history = []
        
        # Performance tracking
        self.daily_starting_balance = 0.0
        self.daily_start_time = get_ny_time()
        self.total_trades = 0
        self.winning_trades = 0
        
trading_state = TradingState()

def make_api_request(method, endpoint, data=None):
    """Make authenticated API request for futures"""
    if not config.is_configured:
        return {'error': 'API credentials not configured'}
    
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

def get_current_price():
    """Get current SOL price from futures market"""
    try:
        result = make_api_request('GET', f'/api/mix/v1/market/ticker?symbol={config.symbol}')
        
        if 'error' in result:
            print(f"Failed to get price: {result.get('message')}")
            return None
        
        if 'data' in result:
            data = result['data']
            if isinstance(data, dict):
                return float(data.get('lastPr', data.get('last', 0)))
            elif isinstance(data, list) and len(data) > 0:
                return float(data[0].get('lastPr', data[0].get('last', 0)))
        
        return None
    except Exception as e:
        print(f"Error getting price: {e}")
        return None

def get_klines(interval='5m', limit=50):
    """Fetch candlestick data for futures"""
    try:
        interval_map = {'1m': '60', '5m': '300', '15m': '900', '30m': '1800', '1H': '3600', '4H': '14400', '1D': '86400'}
        granularity = interval_map.get(interval, '300')
        
        endpoint = f'/api/mix/v1/market/candles?symbol={config.symbol}&granularity={granularity}&limit={limit}'
        result = make_api_request('GET', endpoint)
        
        if 'error' in result:
            return None
            
        if 'data' in result:
            data = result['data']
            df = pd.DataFrame(data)
            if df.empty:
                return None
                
            if len(df.columns) >= 6:
                df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume'] + list(df.columns[6:])
                
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
        return None
    except Exception as e:
        print(f"Error fetching klines: {e}")
        return None

def calculate_rsi(df, period=14):
    """Calculate RSI"""
    try:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
    except:
        return 50

def calculate_macd(df, fast=12, slow=26, signal=9):
    """Calculate MACD"""
    try:
        close = df['close']
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        current_macd = macd_line.iloc[-1]
        current_signal = signal_line.iloc[-1]
        
        if current_macd > current_signal:
            return 1  # Bullish
        else:
            return -1  # Bearish
    except:
        return 0

def calculate_trend_strength(df):
    """Calculate trend strength"""
    try:
        # Multiple timeframe analysis
        price_change_5 = (df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5]
        price_change_10 = (df['close'].iloc[-1] - df['close'].iloc[-10]) / df['close'].iloc[-10]
        
        # Combined strength
        strength = (abs(price_change_5) + abs(price_change_10)) / 2
        direction = 1 if price_change_5 > 0 else -1
        
        return strength * direction
    except:
        return 0

def get_trading_signals():
    """Generate trading signals for futures"""
    try:
        df = get_klines(interval='5m', limit=50)
        current_price = get_current_price()
        
        if df is None or current_price is None:
            return None
        
        # Calculate indicators
        rsi = calculate_rsi(df, config.rsi_period)
        macd_signal = calculate_macd(df, config.macd_fast, config.macd_slow, config.macd_signal)
        trend_strength = calculate_trend_strength(df)
        
        signals = {
            'rsi': rsi,
            'macd': macd_signal,
            'trend_strength': abs(trend_strength),
            'trend_direction': 1 if trend_strength > 0 else -1,
            'price': current_price,
            'timestamp': get_ny_time().isoformat()
        }
        
        # Decision logic
        bullish_score = 0
        bearish_score = 0
        
        # Bullish conditions
        if macd_signal == 1:
            bullish_score += 2
        if rsi < 70:
            bullish_score += 1
        if trend_strength > 0 and abs(trend_strength) > 0.3:
            bullish_score += 2
            
        # Bearish conditions
        if macd_signal == -1:
            bearish_score += 2
        if rsi > 30:
            bearish_score += 1
        if trend_strength < 0 and abs(trend_strength) > 0.3:
            bearish_score += 2
        
        # Make decision
        if bullish_score >= 3 and bearish_score < 3:
            signals['action'] = 'LONG'
            signals['confidence'] = min(1.0, bullish_score / 5.0)
        elif bearish_score >= 3 and bullish_score < 3:
            signals['action'] = 'SHORT' 
            signals['confidence'] = min(1.0, bearish_score / 5.0)
        else:
            signals['action'] = 'HOLD'
            signals['confidence'] = 0.5
            
        return signals
        
    except Exception as e:
        print(f"Error getting signals: {e}")
        return None

def set_leverage():
    """Set leverage for the futures position"""
    try:
        leverage_data = {
            "symbol": config.symbol,
            "marginMode": config.margin_mode,
            "leverage": str(config.leverage_multiplier)
        }
        result = make_api_request('POST', '/api/mix/v1/account/setLeverage', leverage_data)
        return 'error' not in result
    except Exception as e:
        print(f"Error setting leverage: {e}")
        return False

def get_account_balance():
    """Get futures account balance"""
    try:
        result = make_api_request('GET', '/api/mix/v1/account/accounts')
        if 'error' not in result and 'data' in result:
            # Assuming USDT-M futures, look for USDT balance
            for account in result['data']:
                if account.get('marginCoin') == 'USDT':
                    return float(account.get('available', 0))
        return 0.0
    except Exception as e:
        print(f"Error getting balance: {e}")
        return 0.0

def open_long_position(quantity):
    """Open a long futures position"""
    try:
        order_data = {
            "symbol": config.symbol,
            "marginCoin": "USDT",
            "side": "open_long",
            "orderType": "market",
            "size": str(quantity),
            "timInForce": "normal"
        }
        result = make_api_request('POST', '/api/mix/v1/order/placeOrder', order_data)
        return 'error' not in result
    except Exception as e:
        print(f"Error opening long: {e}")
        return False

def open_short_position(quantity):
    """Open a short futures position"""
    try:
        order_data = {
            "symbol": config.symbol,
            "marginCoin": "USDT",
            "side": "open_short", 
            "orderType": "market",
            "size": str(quantity),
            "timInForce": "normal"
        }
        result = make_api_request('POST', '/api/mix/v1/order/placeOrder', order_data)
        return 'error' not in result
    except Exception as e:
        print(f"Error opening short: {e}")
        return False

def close_position():
    """Close current futures position"""
    try:
        if trading_state.current_position == 'long':
            side = "close_long"
        elif trading_state.current_position == 'short':
            side = "close_short"
        else:
            return True
            
        order_data = {
            "symbol": config.symbol,
            "marginCoin": "USDT",
            "side": side,
            "orderType": "market",
            "size": str(trading_state.position_size),
            "timInForce": "normal"
        }
        result = make_api_request('POST', '/api/mix/v1/order/placeOrder', order_data)
        
        if 'error' not in result:
            # Calculate P&L
            current_price = get_current_price()
            if current_price and trading_state.entry_price:
                if trading_state.current_position == 'long':
                    pnl = (current_price - trading_state.entry_price) * trading_state.position_size
                else:
                    pnl = (trading_state.entry_price - current_price) * trading_state.position_size
                
                trading_state.realized_pnl += pnl
                if pnl > 0:
                    trading_state.winning_trades += 1
                    
            trading_state.current_position = None
            trading_state.position_size = 0.0
            trading_state.entry_price = 0.0
            return True
        return False
    except Exception as e:
        print(f"Error closing position: {e}")
        return False

def check_position_health():
    """Check if current position needs to be closed due to stop loss/take profit"""
    if not trading_state.current_position or trading_state.entry_price == 0:
        return True
        
    current_price = get_current_price()
    if not current_price:
        return True
        
    # Calculate P&L percentage
    if trading_state.current_position == 'long':
        pnl_pct = (current_price - trading_state.entry_price) / trading_state.entry_price
    else:
        pnl_pct = (trading_state.entry_price - current_price) / trading_state.entry_price
        
    trading_state.unrealized_pnl = pnl_pct
    
    # Check stop loss and take profit
    if pnl_pct <= -config.stop_loss_pct:
        print(f"🚨 STOP LOSS HIT: {pnl_pct:.2%}")
        return close_position()
    elif pnl_pct >= config.take_profit_pct:
        print(f"🎯 TAKE PROFIT HIT: {pnl_pct:.2%}")
        return close_position()
        
    return True

def check_risk_limits():
    """Check daily loss limits"""
    try:
        current_balance = get_account_balance()
        if trading_state.daily_starting_balance > 0:
            daily_pnl_pct = (current_balance - trading_state.daily_starting_balance) / trading_state.daily_starting_balance
            if daily_pnl_pct <= -config.max_daily_loss:
                print(f"🚨 DAILY LOSS LIMIT REACHED: {daily_pnl_pct:.1%}")
                return False
        
        # Reset daily tracking if new day
        current_time = get_ny_time()
        if current_time.date() != trading_state.daily_start_time.date():
            trading_state.daily_starting_balance = current_balance
            trading_state.daily_start_time = current_time
            
        return True
    except:
        return True

def futures_trading_loop():
    """🚀 MAIN FUTURES TRADING LOOP 🚀"""
    print("\n" + "="*70)
    print("🚀 FUTURES TRADING BOT ACTIVATED 🚀")
    print(f"Leverage: {config.leverage_multiplier}x")
    print(f"Symbol: {config.symbol}")
    print("STRATEGY: Auto Long/Short with Trend Following")
    print("="*70)
    
    # Set initial leverage
    if not set_leverage():
        print("❌ Failed to set leverage")
        trading_state.is_running = False
        return
        
    trading_state.daily_starting_balance = get_account_balance()
    
    while trading_state.is_running:
        try:
            if not trading_state.is_running:
                break
                
            # Check risk limits
            if not check_risk_limits():
                print("🛑 Risk limits exceeded - stopping bot")
                trading_state.is_running = False
                break
                
            # Check current position health
            if not check_position_health():
                print("❌ Position health check failed")
                continue
                
            # Get trading signals
            signals = get_trading_signals()
            if signals is None:
                time.sleep(config.check_interval)
                continue
                
            trading_state.last_signals = signals
            current_balance = get_account_balance()
            
            print(f"\n⏰ {signals['timestamp'][11:19]} | Price: ${signals['price']:.2f}")
            print(f"📊 RSI: {signals['rsi']:.1f} | MACD: {signals['macd']} | Trend: {signals['trend_strength']:.2f}")
            print(f"💰 Balance: ${current_balance:.2f} | Position: {trading_state.current_position or 'NONE'}")
            print(f"🎯 Signal: {signals['action']} | Confidence: {signals['confidence']:.1%}")
            
            # Calculate position size based on leverage and confidence
            effective_size = config.base_position_size * config.leverage_multiplier * signals['confidence']
            
            # Execute trading logic
            if signals['action'] == 'LONG' and trading_state.current_position != 'long':
                # Close any existing position first
                if trading_state.current_position:
                    close_position()
                    time.sleep(1)
                    
                print(f"🚀 OPENING LONG: {effective_size:.3f} SOL with {config.leverage_multiplier}x leverage")
                if open_long_position(effective_size):
                    trading_state.current_position = 'long'
                    trading_state.position_size = effective_size
                    trading_state.entry_price = signals['price']
                    trading_state.last_trade_time = get_ny_time()
                    trading_state.total_trades += 1
                    
                    trading_state.trade_history.append({
                        'time': get_ny_time().isoformat(),
                        'action': 'LONG',
                        'size': effective_size,
                        'leverage': config.leverage_multiplier,
                        'entry_price': signals['price'],
                        'confidence': signals['confidence']
                    })
                    
            elif signals['action'] == 'SHORT' and trading_state.current_position != 'short':
                # Close any existing position first
                if trading_state.current_position:
                    close_position()
                    time.sleep(1)
                    
                print(f"📉 OPENING SHORT: {effective_size:.3f} SOL with {config.leverage_multiplier}x leverage")
                if open_short_position(effective_size):
                    trading_state.current_position = 'short'
                    trading_state.position_size = effective_size
                    trading_state.entry_price = signals['price']
                    trading_state.last_trade_time = get_ny_time()
                    trading_state.total_trades += 1
                    
                    trading_state.trade_history.append({
                        'time': get_ny_time().isoformat(),
                        'action': 'SHORT', 
                        'size': effective_size,
                        'leverage': config.leverage_multiplier,
                        'entry_price': signals['price'],
                        'confidence': signals['confidence']
                    })
                    
            elif signals['action'] == 'HOLD' and trading_state.current_position:
                print("⏸️  Holding position - monitoring...")
                
            time.sleep(config.check_interval)
            
        except Exception as e:
            print(f"Error in trading loop: {e}")
            time.sleep(config.check_interval)
    
    # Close any open position when stopping
    if trading_state.current_position:
        close_position()
        
    print("\n🛑 FUTURES BOT STOPPED")

# ========== FLASK ROUTES ==========

@app.route('/')
def index():
    return render_template('futures_index.html')

@app.route('/api/start_bot', methods=['POST'])
def start_bot():
    if trading_state.is_running:
        return jsonify({'status':'error','message':'Bot already running'})
    
    if not config.is_configured:
        return jsonify({'status':'error','message':'API not configured'})
    
    trading_state.is_running = True
    trading_thread = threading.Thread(target=futures_trading_loop, daemon=True)
    trading_thread.start()
    
    return jsonify({'status':'success','message':'🚀 Futures trading bot activated!'})

@app.route('/api/stop_bot', methods=['POST'])
def stop_bot():
    if not trading_state.is_running:
        return jsonify({'status':'error','message':'Bot not running'})
    
    trading_state.is_running = False
    return jsonify({'status':'success','message':'Futures bot stopped'})

@app.route('/api/status')
def get_status():
    current_price = get_current_price()
    balance = get_account_balance()
    
    return jsonify({
        'status': 'success',
        'is_running': trading_state.is_running,
        'current_position': trading_state.current_position,
        'position_size': trading_state.position_size,
        'entry_price': trading_state.entry_price,
        'unrealized_pnl': trading_state.unrealized_pnl,
        'realized_pnl': trading_state.realized_pnl,
        'current_price': current_price,
        'account_balance': balance,
        'leverage': config.leverage_multiplier,
        'signals': trading_state.last_signals,
        'trade_history': trading_state.trade_history[-10:],
        'performance': {
            'total_trades': trading_state.total_trades,
            'winning_trades': trading_state.winning_trades,
            'win_rate': trading_state.winning_trades / trading_state.total_trades if trading_state.total_trades > 0 else 0
        }
    })

@app.route('/api/update_settings', methods=['POST'])
def update_settings():
    try:
        leverage = int(request.args.get('leverage', config.leverage_multiplier))
        base_size = float(request.args.get('base_size', config.base_position_size))
        
        if leverage < 1 or leverage > 20:
            return jsonify({'status':'error','message':'Leverage must be 1-20x'})
            
        if base_size < 0.01 or base_size > 10:
            return jsonify({'status':'error','message':'Base size must be 0.01-10 SOL'})
        
        config.leverage_multiplier = leverage
        config.base_position_size = base_size
        
        # Update leverage in real-time
        set_leverage()
        
        return jsonify({'status':'success','message':f'Updated: {leverage}x leverage, {base_size} SOL base'})
        
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

@app.route('/api/close_position', methods=['POST'])
def manual_close_position():
    try:
        if close_position():
            return jsonify({'status':'success','message':'Position closed'})
        else:
            return jsonify({'status':'error','message':'Failed to close position'})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

@app.route('/api/balance')
def get_balance():
    try:
        balance = get_account_balance()
        return jsonify({'status':'success','balance': balance})
    except Exception as e:
        return jsonify({'status':'error','message':str(e)})

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 FUTURES TRADING BOT")
    print("="*70)
    print(f"LEVERAGE: {config.leverage_multiplier}x")
    print(f"BASE SIZE: {config.base_position_size} SOL")
    print(f"SYMBOL: {config.symbol}")
    print(f"CHECK INTERVAL: {config.check_interval}s")
    print("\n⚠️  WARNING: HIGH RISK - LEVERAGE TRADING")
    print("⚠️  Potential for complete loss of capital")
    print("⚠️  Only use risk capital you can afford to lose")
    print("="*70)
    
    app.run(debug=True, host='0.0.0.0', port=5000)