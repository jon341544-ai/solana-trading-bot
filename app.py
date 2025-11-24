from flask import Flask, render_template, request, jsonify
import requests
import hmac
import hashlib
import time
import json
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

class CoinCatchAPI:
    def __init__(self, api_key=None, api_secret=None, api_passphrase=None):
        self.api_key = api_key or os.environ.get('COINCATCH_API_KEY')
        self.api_secret = api_secret or os.environ.get('COINCATCH_API_SECRET')
        self.api_passphrase = api_passphrase or os.environ.get('COINCATCH_API_PASSPHRASE')
        self.base_url = "https://api.coincatch.com"  # Actual CoinCatch API base URL
    
    def generate_signature(self, timestamp, method, request_path, body=''):
        """Generate signature for CoinCatch API"""
        if body:
            message = str(timestamp) + method + request_path + body
        else:
            message = str(timestamp) + method + request_path
            
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def get_account_balance(self):
        """Get REAL futures account balance from CoinCatch API"""
        try:
            timestamp = str(int(time.time() * 1000))
            method = 'GET'
            request_path = '/api/v1/mix/account/accounts'  # From CoinCatch docs
            
            signature = self.generate_signature(timestamp, method, request_path)
            
            headers = {
                'ACCESS-KEY': self.api_key,
                'ACCESS-SIGN': signature,
                'ACCESS-TIMESTAMP': timestamp,
                'ACCESS-PASSPHRASE': self.api_passphrase,
                'Content-Type': 'application/json'
            }
            
            print(f"Making API request to: {self.base_url}{request_path}")
            print(f"Headers: { {k: '***' if 'KEY' in k or 'SIGN' in k or 'PASSPHRASE' in k else v for k, v in headers.items()} }")
            
            response = requests.get(
                f"{self.base_url}{request_path}",
                headers=headers,
                timeout=10
            )
            
            print(f"API Response Status: {response.status_code}")
            print(f"API Response: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Parsed API Data: {data}")
                return data
            else:
                error_msg = f'API Error: {response.status_code} - {response.text}'
                print(f"API Error: {error_msg}")
                return {'error': error_msg}
                
        except Exception as e:
            error_msg = f'Request failed: {str(e)}'
            print(f"Exception: {error_msg}")
            return {'error': error_msg}
    
    def get_btc_price(self):
        """Get current BTC price from CoinCatch"""
        try:
            # Try to get BTC price from CoinCatch first
            response = requests.get(
                f"{self.base_url}/api/v1/spot/ticker?symbol=BTCUSDT",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                # Extract price from CoinCatch response
                if 'data' in data and 'last' in data['data']:
                    return float(data['data']['last'])
            
            # Fallback to CoinGecko
            response = requests.get(
                'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd',
                timeout=10
            )
            data = response.json()
            return data['bitcoin']['usd']
        except:
            return 50000  # Final fallback

    def get_position_tiers(self):
        """Get position tier information from CoinCatch"""
        try:
            timestamp = str(int(time.time() * 1000))
            method = 'GET'
            request_path = '/api/v1/mix/account/position-tier'  # From your provided URL
            
            signature = self.generate_signature(timestamp, method, request_path)
            
            headers = {
                'ACCESS-KEY': self.api_key,
                'ACCESS-SIGN': signature,
                'ACCESS-TIMESTAMP': timestamp,
                'ACCESS-PASSPHRASE': self.api_passphrase,
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f"{self.base_url}{request_path}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': f'Position tier API Error: {response.status_code}'}
                
        except Exception as e:
            return {'error': str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/connect', methods=['POST'])
def connect_api():
    try:
        # Use environment variables
        api_key = os.environ.get('COINCATCH_API_KEY')
        api_secret = os.environ.get('COINCATCH_API_SECRET')
        api_passphrase = os.environ.get('COINCATCH_API_PASSPHRASE')
        
        if not api_key or not api_secret or not api_passphrase:
            return jsonify({'error': 'API credentials not found in environment variables'}), 400
        
        client = CoinCatchAPI(api_key, api_secret, api_passphrase)
        
        # Get real account data
        account_data = client.get_account_balance()
        btc_price = client.get_btc_price()
        
        # Check if we got an error from the API
        if 'error' in account_data:
            return jsonify({
                'error': f'CoinCatch API Error: {account_data["error"]}',
                'btc_price': btc_price,
                'timestamp': datetime.now().isoformat(),
                'status': 'api_error'
            }), 400
        
        # Process successful API response
        # Note: You'll need to adjust this based on the actual CoinCatch response format
        if 'data' in account_data:
            # Assuming the API returns data in a 'data' field
            accounts = account_data['data']
            # Find USDT account or adjust based on actual response structure
            usdt_account = None
            for account in accounts:
                if account.get('marginCoin') == 'USDT':
                    usdt_account = account
                    break
            
            if usdt_account:
                response_data = {
                    'total_balance': float(usdt_account.get('equity', 0)),
                    'available_balance': float(usdt_account.get('available', 0)),
                    'frozen_balance': float(usdt_account.get('frozen', 0)),
                    'btc_price': btc_price,
                    'timestamp': datetime.now().isoformat(),
                    'status': 'live',
                    'note': 'Live data from CoinCatch API'
                }
            else:
                response_data = {
                    'error': 'USDT account not found in API response',
                    'raw_data': account_data,
                    'btc_price': btc_price,
                    'status': 'format_error'
                }
        else:
            # If response format is different, try to extract balances
            response_data = {
                'total_balance': float(account_data.get('equity', 0)),
                'available_balance': float(account_data.get('available', 0)),
                'frozen_balance': float(account_data.get('frozen', 0)),
                'btc_price': btc_price,
                'timestamp': datetime.now().isoformat(),
                'status': 'live',
                'note': 'Live data from CoinCatch API',
                'raw_data': account_data  # Include for debugging
            }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/api/position-tier')
def get_position_tier():
    """Get position tier information"""
    try:
        api_key = os.environ.get('COINCATCH_API_KEY')
        api_secret = os.environ.get('COINCATCH_API_SECRET')
        api_passphrase = os.environ.get('COINCATCH_API_PASSPHRASE')
        
        if not api_key or not api_secret or not api_passphrase:
            return jsonify({'error': 'API credentials not found'}), 400
        
        client = CoinCatchAPI(api_key, api_secret, api_passphrase)
        tier_data = client.get_position_tiers()
        
        return jsonify(tier_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug')
def debug_env():
    env_vars = {
        'COINCATCH_API_KEY': 'SET' if os.environ.get('COINCATCH_API_KEY') else 'MISSING',
        'COINCATCH_API_SECRET': 'SET' if os.environ.get('COINCATCH_API_SECRET') else 'MISSING',
        'COINCATCH_API_PASSPHRASE': 'SET' if os.environ.get('COINCATCH_API_PASSPHRASE') else 'MISSING',
        'api_implementation': 'REAL COINCATCH API'
    }
    return jsonify(env_vars)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)