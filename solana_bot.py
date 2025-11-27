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
        
        # Trading parameters
        self.symbol = 'SOLUSDT_SPBL' # CHANGED from BTCUSDT_SPBL
        self.base_asset = 'SOL' # NEW
        self.quote_asset = 'USDT' # NEW
        self.trade_type = 'percentage' # 'percentage' or 'fixed'
        self.trade_percentage = 50 # Default: 50% of available balance
        self.trade_amount = 0.1  # Default: Buy/Sell 0.1 SOL each time (used if trade_type is 'fixed')
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
        self.current_base_asset_balance = 0.0 # RENAMED from current_btc_balance
        self.current_quote_asset_balance = 0.0 # RENAMED from current_usdt_balance
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

def get_klines(symbol=None, interval=None, limit=100):
    """Fetch candlestick data"""
    if symbol is None:
        symbol = config.symbol
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
        
        print(f"Getting {interval} candles for {symbol}...")
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
        
        # Calculate moving averages of gains and losses
        avg_gain = gain.rolling(window=period, min_periods=1).mean()
        avg_loss = loss.rolling(window=period, min_periods=1).mean()
        
        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        current_rsi = rsi.iloc[-1]
        trading_state.last_rsi_value = current_rsi
        
        # Determine signal
        if current_rsi > config.rsi_overbought:
            signal = 'SELL'
        elif current_rsi < config.rsi_oversold:
            signal = 'BUY'
        else:
            signal = 'HOLD'
            
        # Update RSI cycle status
        if trading_state.last_position == 'BUY' and current_rsi > 50:
            trading_state.rsi_cycle_complete = True
            
        return signal, current_rsi
    except Exception as e:
        print(f"Error calculating RSI: {e}")
        return 'HOLD', 50

def get_account_balance():
    """Fetch account balance for base and quote assets"""
    try:
        endpoint = '/api/spot/v1/account/assets'
        result = make_api_request('GET', endpoint)
        
        if 'error' in result:
            print(f"ERROR getting balance: {result.get('error')} - {result.get('message')}")
            return False
        
        if 'data' in result and isinstance(result['data'], list):
            for asset in result['data']:
                if asset.get('coinName') == config.base_asset:
                    trading_state.current_base_asset_balance = float(asset.get('available', 0))
                elif asset.get('coinName') == config.quote_asset:
                    trading_state.current_quote_asset_balance = float(asset.get('available', 0))
            return True
        else:
            print("ERROR: Unexpected balance format")
            return False
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return False

def place_order(symbol, side, trade_amount, order_type='market'):
    """Place a trade order"""
    try:
        endpoint = '/api/spot/v1/trade/orders'
        data = {
            'symbol': symbol,
            'side': side.lower(),
            'orderType': order_type,
            'size': str(trade_amount)
        }
        
        print(f"Placing {side} order for {trade_amount} {config.base_asset}...")
        result = make_api_request('POST', endpoint, data)
        
        if 'error' in result:
            print(f"ERROR placing order: {result.get('error')} - {result.get('message')}")
            return None
        
        if 'data' in result and 'orderId' in result['data']:
            order_id = result['data']['orderId']
            print(f"Order placed successfully. Order ID: {order_id}")
            return order_id
        else:
            print(f"ERROR: Order placement failed. Response: {result}")
            return None
    except Exception as e:
        print(f"Error placing order: {e}")
        return None

def get_order_details(order_id):
    """Fetch details of a specific order"""
    try:
        endpoint = f'/api/spot/v1/trade/orderInfo?orderId={order_id}'
        result = make_api_request('GET', endpoint)
        
        if 'error' in result:
            print(f"ERROR getting order details: {result.get('error')} - {result.get('message')}")
            return None
        
        if 'data' in result:
            return result['data']
        else:
            print(f"ERROR: Unexpected order details format. Response: {result}")
            return None
    except Exception as e:
        print(f"Error getting order details: {e}")
        return None

def get_last_price(symbol):
    """Get the last traded price for a symbol"""
    try:
        endpoint = f'/api/spot/v1/market/ticker?symbol={symbol}'
        result = make_api_request('GET', endpoint)
        if 'error' in result:
            print(f"ERROR getting price: {result.get('error')} - {result.get('message')}")
            return None
        if 'data' in result and 'last' in result['data']:
            return float(result['data']['last'])
        else:
            print(f"ERROR: Unexpected price format. Response: {result}")
            return None
    except Exception as e:
        print(f"Error getting last price: {e}")
        return None

def trading_logic():
    """Main trading logic loop"""
    while trading_state.is_running:
        try:
            print(f"\n--- New Check ({get_ny_time().strftime('%Y-%m-%d %H:%M:%S')}) ---")
            
            # 1. Fetch data
            klines = get_klines(config.symbol, config.indicator_interval)
            if klines is None:
                time.sleep(config.check_interval)
                continue
            
            # 2. Calculate indicators
            rsi_signal, current_rsi = calculate_rsi(klines, config.rsi_period)
            last_price = klines['close'].iloc[-1]
            
            trading_state.last_signals = {
                'RSI Signal': rsi_signal,
                'RSI Value': f"{current_rsi:.2f}",
                'Last Price': f"{last_price:.2f}"
            }
            print(f"Signals: {trading_state.last_signals}")
            
            # 3. Update balance
            if not get_account_balance():
                time.sleep(config.check_interval)
                continue
            
            print(f"Balance: {trading_state.current_base_asset_balance:.4f} {config.base_asset}, {trading_state.current_quote_asset_balance:.2f} {config.quote_asset}")
            
            # 4. Trading logic
            # SELL logic
            if trading_state.last_position == 'BUY':
                profit_target_price = trading_state.last_buy_price * (1 + config.profit_target_percent / 100)
                
                sell_condition_rsi = rsi_signal == 'SELL'
                sell_condition_profit = last_price >= profit_target_price
                
                if sell_condition_rsi or sell_condition_profit:
                    if sell_condition_profit:
                        print(f"Profit target of {config.profit_target_percent}% hit!")
                    
                    sell_amount = trading_state.current_base_asset_balance
                    if sell_amount > 0.0001: # Min trade size check (using a generic small number, actual min size might vary for SOL)
                        order_id = place_order(config.symbol, 'SELL', sell_amount)
                        if order_id:
                            time.sleep(5) # Wait for order to fill
                            order_details = get_order_details(order_id)
                            if order_details and order_details.get('status') == 'filled':
                                filled_qty = float(order_details['dealSize'])
                                filled_price = float(order_details['averagePrice'])
                                usdt_amount = filled_qty * filled_price
                                
                                trading_state.last_position = 'SELL'
                                trading_state.last_trade_time = get_ny_time().isoformat()
                                trading_state.trade_history.append({
                                    'time': trading_state.last_trade_time,
                                    'action': f"SELL {config.base_asset}",
                                    'price': filled_price,
                                    'amount': filled_qty,
                                    'usdt_amount': usdt_amount
                                })
                                trading_state.rsi_cycle_complete = False # Require RSI to cycle before buying again
                                calculate_profit_stats()
                                print(f"SELL order filled: {filled_qty} {config.base_asset} at {filled_price}")
                            else:
                                print("SELL order not filled or details not available.")
                        else:
                            print("SELL order placement failed.")
                    else:
                        print("Not enough balance to sell.")
                else:
                    print("HOLD. Waiting for sell signal or profit target.")
            
            # BUY logic
            elif rsi_signal == 'BUY':
                if config.require_rsi_cycle and not trading_state.rsi_cycle_complete:
                    print("HOLD. Waiting for RSI to cycle above 50 before buying again.")
                else:
                    if config.trade_type == 'percentage':
                        usdt_to_spend = trading_state.current_quote_asset_balance * (config.trade_percentage / 100)
                        buy_amount = usdt_to_spend / last_price
                    else: # fixed amount
                        buy_amount = config.trade_amount
                    
                    if trading_state.current_quote_asset_balance > 1: # Min USDT check
                        order_id = place_order(config.symbol, 'BUY', buy_amount)
                        if order_id:
                            time.sleep(5) # Wait for order to fill
                            order_details = get_order_details(order_id)
                            if order_details and order_details.get('status') == 'filled':
                                filled_qty = float(order_details['dealSize'])
                                filled_price = float(order_details['averagePrice'])
                                usdt_amount = filled_qty * filled_price
                                
                                trading_state.last_position = 'BUY'
                                trading_state.last_trade_time = get_ny_time().isoformat()
                                trading_state.last_buy_price = filled_price
                                trading_state.trade_history.append({
                                    'time': trading_state.last_trade_time,
                                    'action': f"BUY {config.base_asset}",
                                    'price': filled_price,
                                    'amount': filled_qty,
                                    'usdt_amount': usdt_amount
                                })
                                calculate_profit_stats()
                                print(f"BUY order filled: {filled_qty} {config.base_asset} at {filled_price}")
                            else:
                                print("BUY order not filled or details not available.")
                        else:
                            print("BUY order placement failed.")
                    else:
                        print("Not enough USDT to buy.")
            else:
                print("HOLD. No buy signal.")

        except Exception as e:
            print(f"An error occurred in the trading loop: {e}")
        
        time.sleep(config.check_interval)

@app.route('/')
def index():
    return render_template('index.html', is_configured=config.is_configured)

@app.route('/start', methods=['POST'])
def start_bot():
    if not trading_state.is_running:
        trading_state.is_running = True
        # Reset state on start
        trading_state.last_position = None
        trading_state.last_buy_price = None
        trading_state.rsi_cycle_complete = True
        
        # Load trade history if available
        try:
            with open('trade_history.json', 'r') as f:
                trading_state.trade_history = json.load(f)
                calculate_profit_stats()
        except FileNotFoundError:
            pass # No history yet
            
        thread = threading.Thread(target=trading_logic)
        thread.start()
        return jsonify({'status': 'Bot started'})
    return jsonify({'status': 'Bot is already running'})

@app.route('/stop', methods=['POST'])
def stop_bot():
    if trading_state.is_running:
        trading_state.is_running = False
        # Save trade history
        with open('trade_history.json', 'w') as f:
            json.dump(trading_state.trade_history, f, indent=4)
        return jsonify({'status': 'Bot stopped'})
    return jsonify({'status': 'Bot is not running'})

@app.route('/status', methods=['GET'])
def get_status():
    if not config.is_configured:
        return jsonify({'error': 'API credentials not configured. Please set environment variables.'}), 400
        
    get_account_balance() # Update balance on status check
    calculate_profit_stats() # Recalculate profits
    
    return jsonify({
        'is_running': trading_state.is_running,
        'last_position': trading_state.last_position,
        'last_trade_time': trading_state.last_trade_time,
        'last_signals': trading_state.last_signals,
        'current_base_asset_balance': trading_state.current_base_asset_balance,
        'current_quote_asset_balance': trading_state.current_quote_asset_balance,
        'base_asset': config.base_asset,
        'quote_asset': config.quote_asset,
        'last_buy_price': trading_state.last_buy_price,
        'rsi_cycle_complete': trading_state.rsi_cycle_complete,
        'last_rsi_value': trading_state.last_rsi_value,
        'profit_stats': trading_state.profit_stats,
        'trade_history': trading_state.trade_history[-20:] # Last 20 trades
    })

@app.route('/config', methods=['GET', 'POST'])
def manage_config():
    if request.method == 'POST':
        data = request.get_json()
        try:
            config.trade_type = data.get('trade_type', config.trade_type)
            config.trade_percentage = int(data.get('trade_percentage', config.trade_percentage))
            config.trade_amount = float(data.get('trade_amount', config.trade_amount))
            config.check_interval = int(data.get('check_interval', config.check_interval))
            config.indicator_interval = data.get('indicator_interval', config.indicator_interval)
            config.rsi_period = int(data.get('rsi_period', config.rsi_period))
            config.rsi_oversold = int(data.get('rsi_oversold', config.rsi_oversold))
            config.rsi_overbought = int(data.get('rsi_overbought', config.rsi_overbought))
            config.profit_target_percent = float(data.get('profit_target_percent', config.profit_target_percent))
            config.require_rsi_cycle = bool(data.get('require_rsi_cycle', config.require_rsi_cycle))
            
            return jsonify({'status': 'Configuration updated'})
        except (ValueError, TypeError) as e:
            return jsonify({'error': f'Invalid value in configuration: {e}'}), 400
    else:
        return jsonify({
            'trade_type': config.trade_type,
            'trade_percentage': config.trade_percentage,
            'trade_amount': config.trade_amount,
            'check_interval': config.check_interval,
            'indicator_interval': config.indicator_interval,
            'rsi_period': config.rsi_period,
            'rsi_oversold': config.rsi_oversold,
            'rsi_overbought': config.rsi_overbought,
            'profit_target_percent': config.profit_target_percent,
            'require_rsi_cycle': config.require_rsi_cycle
        })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
