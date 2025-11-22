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

# AGGRESSIVE GROWTH CONFIGURATION
class Config:
    def __init__(self):
        self.api_key = os.environ.get('COINCATCH_API_KEY', '')
        self.api_secret = os.environ.get('COINCATCH_API_SECRET', '') 
        self.passphrase = os.environ.get('COINCATCH_PASSPHRASE', '')
        self.base_url = "https://api.coincatch.com"
        self.is_configured = bool(self.api_key and self.api_secret and self.passphrase)
        
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
        if df is None or len(df) < 20:
            return None
        
        # Core signals
        rsi = calculate_rsi(df, config.rsi_period)
        macd_signal = calculate_momentum_macd(df, config.macd_fast, config.macd_slow, config.macd_signal)
        volume_strength = calculate_volume_strength(df, config.volume_ma)
        trend_strength = calculate_trend_strength(df)
        
        current_price = float(df['close'].iloc[-1])
        
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
        return None

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

# ... (keep the existing make_api_request, get_klines, execute_buy_order, execute_sell_order functions from previous bot)
# ... (keep the existing Flask routes and basic functions)

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

# Replace the existing trading_loop call with:
@app.route('/api/start_bot',methods=['POST'])
def start_bot():
    if trading_state.is_running:
        return jsonify({'status':'error','message':'Bot already running'})
    
    if not config.is_configured:
        return jsonify({'status':'error','message':'API not configured'})
    
    trading_state.is_running=True
    trading_thread=threading.Thread(target=aggressive_trading_loop,daemon=True)
    trading_thread.start()
    
    return jsonify({'status':'success','message':'🚀 Aggressive growth bot activated!'})

if __name__=='__main__':
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
    
    app.run(debug=True,host='0.0.0.0',port=5000)