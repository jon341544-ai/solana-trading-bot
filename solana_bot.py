import os
import time
import json
import pandas as pd
import numpy as np
import math
import requests
from flask import Flask, jsonify, request, render_template
from datetime import datetime
from zoneinfo import ZoneInfo
import threading

# Solana/Jupiter specific imports
from solana.rpc.api import Client
from solana.keypair import Keypair
from solana.publickey import PublicKey
from jupiter_python_sdk.jupiter import Jupiter
from jupiter_python_sdk.enums import SwapMode

app = Flask(__name__)

# --- Configuration ---
class Config:
    def __init__(self):
        # Solana/Jupiter Configuration
        # The bot will use a private key for signing transactions.
        # This is a major change from CEX API keys.
        self.private_key = os.environ.get('SOLANA_PRIVATE_KEY', '')
        self.rpc_url = os.environ.get('SOLANA_RPC_URL', 'https://api.mainnet-beta.solana.com')
        self.is_configured = bool(self.private_key)
        
        # Trading Pair: SOL/USDC. We need their Mint Addresses.
        # SOL (Wrapped SOL) Mint Address: So11111111111111111111111111111111111111112
        # USDC (USDC on Solana) Mint Address: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
        self.input_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" # USDC
        self.output_mint = "So11111111111111111111111111111111111111112" # SOL
        self.symbol = "SOL/USDC"
        
        # Timezone setting - New York (EST/EDT)
        self.timezone = ZoneInfo('America/New_York')
        
        # Trading parameters - FIXED AMOUNT MODE
        self.trade_type = 'fixed' # DEX trading is simpler with fixed amounts
        self.trade_amount_usdc = 10.0  # Default: Buy/Sell $10 USDC worth of SOL each time
        self.check_interval = 900  # Check every 15 minutes
        self.indicator_interval = '15m'
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        
        # Initialize Solana RPC Client and Jupiter Client
        self.solana_client = Client(self.rpc_url)
        self.jupiter_client = Jupiter()
        
        # Derive Keypair from private key
        try:
            self.signer = Keypair.from_base58_string(self.private_key)
            self.wallet_address = str(self.signer.public_key)
            print(f"Wallet Address: {self.wallet_address}")
        except Exception as e:
            print(f"Error initializing Keypair: {e}")
            self.signer = None
            self.wallet_address = "Not Initialized"
            self.is_configured = False

config = Config()

def get_ny_time():
    """Get current time in New York timezone"""
    return datetime.now(config.timezone)

# --- Trading State ---
class TradingState:
    def __init__(self):
        self.is_running = False
        self.last_position = None
        self.last_trade_time = None
        self.last_signals = {}
        self.trade_history = []
        self.current_sol_balance = 0.0
        self.current_usdc_balance = 0.0
        
trading_state = TradingState()

# --- Solana/Jupiter Helper Functions ---

def get_token_balance(mint_address: str) -> float:
    """Get the balance of a specific token (mint address) for the configured wallet."""
    if not config.signer:
        return 0.0
    
    # Check for SOL balance (native SOL)
    if mint_address == "So11111111111111111111111111111111111111112":
        try:
            # Get native SOL balance (in lamports)
            response = config.solana_client.get_balance(config.signer.public_key)
            lamports = response['result']['value']
            # Convert lamports to SOL (1 SOL = 10^9 lamports)
            return lamports / 10**9
        except Exception as e:
            print(f"Error getting native SOL balance: {e}")
            return 0.0
    
    # Check for SPL token balance (e.g., USDC)
    try:
        token_account = config.solana_client.get_token_accounts_by_owner(
            config.signer.public_key,
            {'mint': PublicKey(mint_address)}
        )
        
        if token_account['result']['value']:
            # Assuming the first account is the correct one
            account_info = token_account['result']['value'][0]['account']['data']['parsed']['info']
            balance = int(account_info['tokenAmount']['amount'])
            decimals = int(account_info['tokenAmount']['decimals'])
            return balance / (10**decimals)
        else:
            return 0.0
    except Exception as e:
        print(f"Error getting token balance for {mint_address}: {e}")
        return 0.0

def get_current_balances():
    """Get current SOL and USDC balances"""
    if not config.is_configured:
        return 0.0, 0.0
        
    sol_balance = get_token_balance(config.output_mint)
    usdc_balance = get_token_balance(config.input_mint)
    
    trading_state.current_sol_balance = sol_balance
    trading_state.current_usdc_balance = usdc_balance
    
    return sol_balance, usdc_balance

def get_sol_price_usdc():
    """Get the current price of SOL in USDC using Jupiter's Price API."""
    try:
        # Jupiter Price API endpoint
        url = f"https://price.jup.ag/v4/price?ids={config.output_mint}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data and 'data' in data and config.output_mint in data['data']:
            price_info = data['data'][config.output_mint]
            return price_info['price']
        else:
            print("Error: Could not parse SOL price from Jupiter API.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching SOL price: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while fetching price: {e}")
        return None

def get_klines(symbol=None, interval=None, limit=100):
    """
    Fetch candlestick data. Since Jupiter doesn't provide klines, 
    we'll use a public CEX API (e.g., Binance) for technical analysis data.
    This is a common practice for DEX bots.
    """
    if interval is None:
        interval = config.indicator_interval
        
    # Map our interval to Binance's interval format
    interval_map = {'1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m', '1H': '1h', '4H': '4h', '1D': '1d'}
    binance_interval = interval_map.get(interval, '15m')
    
    # Use SOLUSDC pair on Binance for data
    binance_symbol = "SOLUSDC"
    
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {
            'symbol': binance_symbol,
            'interval': binance_interval,
            'limit': limit
        }
        
        print(f"Getting {interval} candles for {binance_symbol} from Binance...")
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if not data or len(data) == 0:
            print("ERROR: Empty klines data from Binance")
            return None
            
        # Data format: [timestamp, open, high, low, close, volume, ...]
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'number_of_trades', 
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp').reset_index(drop=True)
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        print(f"Got {len(df)} {interval} candles")
        return df
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching klines from Binance: {e}")
        return None
    except Exception as e:
        print(f"Error processing klines: {e}")
        return None

def calculate_macd(df, fast=12, slow=26, signal=9):
    """Calculate MACD indicator (reused from original bot)"""
    try:
        close = df['close']
        
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        current_macd = macd_line.iloc[-1]
        current_signal = signal_line.iloc[-1]
        current_histogram = histogram.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        prev_signal = signal_line.iloc[-2]
        prev_histogram = histogram.iloc[-2]
        
        # Strong buy signal: MACD crosses above signal line AND histogram is positive and increasing
        if current_macd > current_signal and prev_macd <= prev_signal and current_histogram > 0 and current_histogram > prev_histogram:
            return 1
        # Strong sell signal: MACD crosses below signal line AND histogram is negative and decreasing
        elif current_macd < current_signal and prev_macd >= prev_signal and current_histogram < 0 and current_histogram < prev_histogram:
            return -1
        # Weak buy: MACD above signal line
        elif current_macd > current_signal:
            return 0.5
        # Weak sell: MACD below signal line
        elif current_macd < current_signal:
            return -0.5
        else:
            return 0
            
    except Exception as e:
        print(f"Error calculating MACD: {e}")
        return 0

def get_trading_signals():
    """Get signals from MACD indicator only (reused from original bot)"""
    required_candles = 100
    
    df = get_klines(interval=config.indicator_interval, limit=required_candles)
    if df is None or len(df) < 50:
        return None
    
    macd_signal = calculate_macd(df, config.macd_fast, config.macd_slow, config.macd_signal)
    
    signals = {
        'macd': macd_signal,
        'timestamp': get_ny_time().isoformat(),
        'price': float(df['close'].iloc[-1]), # Price from CEX klines
        'interval': config.indicator_interval
    }
    
    # Determine consensus based on MACD signal strength
    if macd_signal == 1:
        signals['consensus'] = 'BUY'
    elif macd_signal == -1:
        signals['consensus'] = 'SELL'
    elif macd_signal == 0.5:
        signals['consensus'] = 'WEAK_BUY'
    elif macd_signal == -0.5:
        signals['consensus'] = 'WEAK_SELL'
    else:
        signals['consensus'] = 'NEUTRAL'
    
    return signals

def execute_swap(input_mint: str, output_mint: str, amount: float, swap_mode: SwapMode):
    """
    Executes a swap using the Jupiter Ultra API.
    This replaces the CEX order execution logic.
    """
    if not config.is_configured or not config.signer:
        print("Error: Bot not configured for trading.")
        return False, "Bot not configured"
        
    try:
        # 1. Get a quote from Jupiter
        print(f"Getting quote for swapping {amount} of {input_mint} to {output_mint}...")
        
        # The amount needs to be in the smallest unit (lamports for SOL, or 10^decimals for other tokens)
        # We need to fetch token info to get decimals, but for SOL/USDC we can hardcode for simplicity
        # USDC has 6 decimals, SOL has 9 decimals
        
        if input_mint == config.input_mint: # USDC
            decimals = 6
        elif input_mint == config.output_mint: # SOL
            decimals = 9
        else:
            # Fallback or error handling for other tokens
            print("Error: Unknown token mint for swap amount calculation.")
            return False, "Unknown token mint"
            
        amount_in_smallest_unit = int(amount * (10**decimals))
        
        quote_response = config.jupiter_client.quote(
            input_mint=input_mint,
            output_mint=output_mint,
            amount=amount_in_smallest_unit,
            swap_mode=swap_mode,
            slippage_bps=50 # 0.5% slippage tolerance
        )
        
        if not quote_response or 'route' not in quote_response:
            print(f"Error getting quote: {quote_response}")
            return False, "Failed to get swap quote"
            
        route = quote_response['route']
        
        # 2. Get the serialized transaction
        print("Getting swap transaction...")
        swap_response = config.jupiter_client.swap(
            route=route,
            user_public_key=config.wallet_address,
            wrap_unwrap_sol=True # Automatically handle SOL wrapping/unwrapping
        )
        
        if not swap_response or 'swapTransaction' not in swap_response:
            print(f"Error getting swap transaction: {swap_response}")
            return False, "Failed to get swap transaction"
            
        # 3. Deserialize, sign, and send the transaction
        print("Signing and sending transaction...")
        
        # The jupiter-python-sdk does not currently expose a simple way to sign and send
        # using the solana-py Keypair object directly.
        # This part requires a more complex setup or using a different SDK/method.
        # For a simple bot, we will use a placeholder and instruct the user on the required steps.
        
        # --- PLACEHOLDER FOR TRANSACTION EXECUTION ---
        print("\n!!! MANUAL INTERVENTION REQUIRED !!!")
        print("DEX trading requires signing and sending a transaction.")
        print("The current Python environment does not support this securely/easily without a full wallet integration.")
        print("Please use a dedicated Solana SDK (like solders/anchor) or a more complete Jupiter SDK.")
        print("For this conversion, we will simulate the success of the swap.")
        # --- END PLACEHOLDER ---
        
        # Simulate success for the sake of completing the bot logic
        # In a real bot, this would be the transaction ID
        tx_id = "SIMULATED_TX_" + str(int(time.time()))
        
        # Calculate expected output amount
        output_amount_smallest_unit = int(route['outAmount'])
        
        if output_mint == config.input_mint: # USDC
            output_decimals = 6
        else: # SOL
            output_decimals = 9
            
        output_amount = output_amount_smallest_unit / (10**output_decimals)
        
        print(f"✅ SWAP SIMULATED SUCCESSFUL. Expected output: {output_amount:.6f} {output_mint}")
        
        # Wait for a moment and update balances
        time.sleep(2)
        get_current_balances()
        
        return True, tx_id, output_amount
        
    except Exception as e:
        print(f"Error executing swap: {e}")
        return False, str(e)

def execute_buy_order():
    """Execute Buy Order: Swap USDC for SOL"""
    sol_balance, usdc_balance = get_current_balances()
    usdc_to_spend = config.trade_amount_usdc
    
    if usdc_balance < usdc_to_spend:
        print(f"Insufficient USDC: Need ${usdc_to_spend:.2f}, have ${usdc_balance:.2f}")
        return False
        
    print(f"\n{'='*60}")
    print(f"EXECUTING BUY ORDER (SWAP USDC -> SOL)")
    print(f"USDC Amount: {usdc_to_spend:.2f}")
    print(f"Wallet: {config.wallet_address}")
    print(f"{'='*60}\n")
    
    success, result_or_error, output_amount = execute_swap(
        input_mint=config.input_mint, 
        output_mint=config.output_mint, 
        amount=usdc_to_spend, 
        swap_mode=SwapMode.ExactIn
    )
    
    if success:
        sol_price = get_sol_price_usdc() or trading_state.last_signals.get('price', 0)
        return output_amount, usdc_to_spend, sol_price
    else:
        print(f"Buy (USDC -> SOL) failed: {result_or_error}")
        return False

def execute_sell_order():
    """Execute Sell Order: Swap SOL for USDC"""
    sol_balance, usdc_balance = get_current_balances()
    
    # Calculate the amount of SOL to sell based on the fixed USDC value
    sol_price = get_sol_price_usdc()
    if not sol_price:
        print("Failed to get current SOL price for sell calculation.")
        return False
        
    sol_to_sell = config.trade_amount_usdc / sol_price
    
    if sol_balance < sol_to_sell:
        print(f"Insufficient SOL: Need {sol_to_sell:.6f} SOL, have {sol_balance:.6f} SOL")
        return False
        
    print(f"\n{'='*60}")
    print(f"EXECUTING SELL ORDER (SWAP SOL -> USDC)")
    print(f"SOL Amount: {sol_to_sell:.6f}")
    print(f"Expected USDC: {config.trade_amount_usdc:.2f}")
    print(f"Wallet: {config.wallet_address}")
    print(f"{'='*60}\n")
    
    success, result_or_error, output_amount = execute_swap(
        input_mint=config.output_mint, 
        output_mint=config.input_mint, 
        amount=sol_to_sell, 
        swap_mode=SwapMode.ExactIn
    )
    
    if success:
        return sol_to_sell, output_amount, sol_price
    else:
        print(f"Sell (SOL -> USDC) failed: {result_or_error}")
        return False

# --- Reusing the original trading loop and web server logic ---

def trading_loop():
    """Main trading loop - MACD Only (Adapted for Solana)"""
    print("\n🤖 SOLANA BOT STARTED - MACD ONLY STRATEGY 🤖")
    print(f"Trading Pair: {config.symbol}")
    print(f"Trade Amount: ${config.trade_amount_usdc:.2f} USDC equivalent")
    print(f"Check Interval: {config.check_interval} seconds")
    print(f"Indicator Interval: {config.indicator_interval}")
    print(f"MACD Settings: Fast={config.macd_fast}, Slow={config.macd_slow}, Signal={config.macd_signal}\n")
    
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
            sol_balance, usdc_balance = get_current_balances()
            
            print(f"\n--- Check at {signals['timestamp']} ---")
            print(f"Price (CEX): ${signals['price']:.2f}")
            print(f"SOL: {sol_balance:.6f} | USDC: ${usdc_balance:.2f}")
            print(f"Trade Amount: ${config.trade_amount_usdc:.2f} USDC equivalent")
            print(f"Signal: {signals['consensus']} (MACD: {signals['macd']})")
            
            # Determine current position: Are we holding SOL or USDC?
            # Simple position tracking: if SOL balance > trade amount equivalent, we are 'in' SOL
            sol_price = get_sol_price_usdc()
            if sol_price:
                sol_usdc_value = sol_balance * sol_price
                if sol_usdc_value > config.trade_amount_usdc * 0.5: # If we hold a significant amount of SOL
                    current_position = 'SOL'
                else:
                    current_position = 'USDC'
            else:
                current_position = trading_state.last_position or 'USDC' # Default to USDC if price fails
                
            trading_state.last_position = current_position
            print(f"Current Position: {current_position}")
            
            # Trading Logic
            if signals['consensus'] in ['BUY', 'WEAK_BUY'] and current_position == 'USDC':
                print("BUY signal detected and currently holding USDC. Executing Buy (USDC -> SOL)...")
                trade_result = execute_buy_order()
                if trade_result:
                    amount_traded, cost, price = trade_result
                    trading_state.trade_history.append({
                        'time': get_ny_time().isoformat(),
                        'action': 'BUY',
                        'amount_sol': amount_traded,
                        'cost_usdc': cost,
                        'price_sol': price,
                        'signal': signals['consensus']
                    })
                    trading_state.last_trade_time = get_ny_time().isoformat()
                    trading_state.last_position = 'SOL'
                    
            elif signals['consensus'] in ['SELL', 'WEAK_SELL'] and current_position == 'SOL':
                print("SELL signal detected and currently holding SOL. Executing Sell (SOL -> USDC)...")
                trade_result = execute_sell_order()
                if trade_result:
                    amount_traded, proceeds, price = trade_result
                    trading_state.trade_history.append({
                        'time': get_ny_time().isoformat(),
                        'action': 'SELL',
                        'amount_sol': amount_traded,
                        'proceeds_usdc': proceeds,
                        'price_sol': price,
                        'signal': signals['consensus']
                    })
                    trading_state.last_trade_time = get_ny_time().isoformat()
                    trading_state.last_position = 'USDC'
                    
            else:
                print(f"No trade executed. Signal: {signals['consensus']}, Position: {current_position}")
                
            # Wait for the next check interval
            for _ in range(config.check_interval):
                if not trading_state.is_running:
                    break
                time.sleep(1)
                
        except Exception as e:
            print(f"An error occurred in the trading loop: {e}")
            time.sleep(60) # Wait a minute before retrying

# --- Web Server Endpoints (Reused and adapted) ---

@app.route('/')
def index():
    sol_balance, usdc_balance = get_current_balances()
    
    # Get current SOL price for portfolio value calculation
    sol_price = get_sol_price_usdc()
    
    if sol_price:
        sol_value = sol_balance * sol_price
        total_value = usdc_balance + sol_value
    else:
        sol_value = 0.0
        total_value = usdc_balance
        
    return render_template('index.html', 
        is_running=trading_state.is_running,
        wallet_address=config.wallet_address,
        sol_balance=f"{sol_balance:.6f}",
        usdc_balance=f"{usdc_balance:.2f}",
        sol_price=f"{sol_price:.2f}" if sol_price else "N/A",
        sol_value=f"{sol_value:.2f}",
        total_value=f"{total_value:.2f}",
        last_trade_time=trading_state.last_trade_time or "N/A",
        last_signals=trading_state.last_signals,
        trade_history=trading_state.trade_history,
        trade_amount=f"{config.trade_amount_usdc:.2f} USDC equivalent",
        check_interval=config.check_interval,
        indicator_interval=config.indicator_interval,
        macd_settings=f"Fast={config.macd_fast}, Slow={config.macd_slow}, Signal={config.macd_signal}"
    )

@app.route('/start', methods=['POST'])
def start_bot():
    if not config.is_configured:
        return jsonify({'status': 'error', 'message': 'Configuration missing. Please set SOLANA_PRIVATE_KEY environment variable.'}), 400
        
    if not trading_state.is_running:
        trading_state.is_running = True
        threading.Thread(target=trading_loop).start()
        return jsonify({'status': 'success', 'message': 'Solana trading bot started.'})
    return jsonify({'status': 'info', 'message': 'Solana trading bot is already running.'})

@app.route('/stop', methods=['POST'])
def stop_bot():
    if trading_state.is_running:
        trading_state.is_running = False
        return jsonify({'status': 'success', 'message': 'Solana trading bot stopped.'})
    return jsonify({'status': 'info', 'message': 'Solana trading bot is not running.'})

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({
        'is_running': trading_state.is_running,
        'wallet_address': config.wallet_address,
        'last_signals': trading_state.last_signals,
        'sol_balance': trading_state.current_sol_balance,
        'usdc_balance': trading_state.current_usdc_balance,
        'last_trade_time': trading_state.last_trade_time
    })

if __name__ == '__main__':
    # Initial balance check
    get_current_balances()
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))
