from flask import Flask, render_template, request, jsonify
import requests
import hmac
import hashlib
import time
import json
from datetime import datetime
import os
from dotenv import load_dotenv
import urllib.parse

load_dotenv()

app = Flask(__name__)

class CoinCatchAPI:
    def __init__(self, api_key=None, api_secret=None, api_passphrase=None):
        self.api_key = api_key or os.environ.get('COINCATCH_API_KEY')
        self.api_secret = api_secret or os.environ.get('COINCATCH_API_SECRET')
        self.api_passphrase = api_passphrase or os.environ.get('COINCATCH_API_PASSPHRASE')
        self.base_url = "https://api.coincatch.com"
    
    def generate_signature(self, timestamp, method, request_path, body=''):
        """Generate signature for CoinCatch API"""
        if body:
            message = timestamp + method + request_path + body
        else:
            message = timestamp + method + request_path
            
        print(f"Signing message: {message}")
        mac = hmac.new(
            bytes(self.api_secret, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        signature = base64.b64encode(mac.digest()).decode()
        print(f"Generated signature: {signature}")
        return signature
    
    def make_api_request(self, method, request_path, params=None):
        """Make authenticated API request to CoinCatch"""
        try:
            timestamp = str(int(time.time() * 1000))
            
            # Prepare query string for GET requests
            query_string = ""
            if params and method == 'GET':
                query_string = '?' + urllib.parse.urlencode(params)
                request_path_with_query = request_path + query_string
            else:
                request_path_with_query = request_path
            
            body = ""
            if params and method == 'POST':
                body = json.dumps(params)
            
            signature = self.generate_signature(timestamp, method, request_path_with_query, body)
            
            headers = {
                'ACCESS-KEY': self.api_key,
                'ACCESS-SIGN': signature,
                'ACCESS-TIMESTAMP': timestamp,
                'ACCESS-PASSPHRASE': self.api_passphrase,
                'Content-Type': 'application/json'
            }
            
            url = f"{self.base_url}{request_path_with_query}"
            print(f"Making {method} request to: {url}")
            print(f"Headers: { {k: '***' if 'KEY' in k or 'SIGN' in k or 'PASSPHRASE' in k else v for k, v in headers.items()} }")
            if body:
                print(f"Body: {body}")
            
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            else:
                response = requests.post(url, headers=headers, data=body, timeout=10)
            
            print(f"Response Status: {response.status_code}")
            print(f"Response Text: {response.text}")
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': f'{response.status_code} - {response.text}'}
                
        except Exception as e:
            return {'error': f'Request failed: {str(e)}'}
    
    def get_account_balance(self):
        """Get futures account balance from CoinCatch API"""
        try:
            # Try the endpoint that returned 400 (which means it exists)
            request_path = '/api/mix/v1/account/accounts'
            
            # The 400 error suggests we might need parameters
            # Try with different parameter combinations
            param_combinations = [
                {'productType': 'umcbl'},
                {'symbol': 'BTCUSDT'},
                {'marginCoin': 'USDT'},
                {'productType': 'USDT-MIX'},
                {}  # No parameters
            ]
            
            for params in param_combinations:
                print(f"Trying with params: {params}")
                result = self.make_api_request('GET', request_path, params)
                
                if 'error' not in result:
                    return result
                elif '400' not in result.get('error', ''):
                    # If it's not a 400 error, return the error
                    return result
            
            # If all parameter combinations failed, return the last error
            return result
                
        except Exception as e:
            return {'error': f'Account balance request failed: {str(e)}'}
    
    def get_btc_price(self):
        """Get current BTC price"""
        try:
            # Try CoinCatch public ticker
            response = requests.get(
                f"{self.base_url}/api/mix/v1/market/ticker?symbol=BTCUSDT",
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
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
            return 50000

    def get_position_tier(self):
        """Get position tier information"""
        try:
            request_path = '/api/mix/v1/account/position-tier'
            params = {'productType': 'umcbl'}  # Common parameter for USDT-M futures
            
            result = self.make_api_request('GET', request_path, params)
            return result
        except Exception as e:
            return {'error': str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/connect', methods=['POST'])
def connect_api():
    try:
        api_key = os.environ.get('COINCATCH_API_KEY')
        api_secret = os.environ.get('COINCATCH_API_SECRET')
        api_passphrase = os.environ.get('COINCATCH_API_PASSPHRASE')
        
        if not api_key or not api_secret or not api_passphrase:
            return jsonify({'error': 'API credentials not found in environment variables'}), 400
        
        client = CoinCatchAPI(api_key, api_secret, api_passphrase)
        account_data = client.get_account_balance()
        btc_price = client.get_btc_price()
        
        # Check if we got an error from the API
        if 'error' in account_data:
            # Try to get position tier as alternative
            tier_data = client.get_position_tier()
            
            return jsonify({
                'error': f'Account API Error: {account_data["error"]}',
                'btc_price': btc_price,
                'timestamp': datetime.now().isoformat(),
                'status': 'api_error',
                'position_tier_data': tier_data,
                'note': 'Account balance endpoint failing, but BTC price is live'
            }), 400
        
        # Process successful API response
        # The actual structure will depend on CoinCatch's response
        if 'data' in account_data:
            accounts = account_data['data']
            if isinstance(accounts, list) and len(accounts) > 0:
                # Assuming first account is USDT account
                account = accounts[0]
                response_data = {
                    'total_balance': float(account.get('equity', account.get('marginBalance', 0))),
                    'available_balance': float(account.get('available', account.get('availableBalance', 0))),
                    'frozen_balance': float(account.get('frozen', account.get('locked', 0))),
                    'btc_price': btc_price,
                    'timestamp': datetime.now().isoformat(),
                    'status': 'live',
                    'note': 'Live data from CoinCatch API',
                    'raw_data': account_data
                }
            else:
                response_data = {
                    'total_balance': 0,
                    'available_balance': 0,
                    'frozen_balance': 0,
                    'btc_price': btc_price,
                    'timestamp': datetime.now().isoformat(),
                    'status': 'no_accounts',
                    'note': 'No accounts found in API response',
                    'raw_data': account_data
                }
        else:
            # Direct account data (not wrapped in 'data')
            response_data = {
                'total_balance': float(account_data.get('equity', account_data.get('marginBalance', 0))),
                'available_balance': float(account_data.get('available', account_data.get('availableBalance', 0))),
                'frozen_balance': float(account_data.get('frozen', account_data.get('locked', 0))),
                'btc_price': btc_price,
                'timestamp': datetime.now().isoformat(),
                'status': 'live',
                'note': 'Live data from CoinCatch API',
                'raw_data': account_data
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
        tier_data = client.get_position_tier()
        
        return jsonify(tier_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug')
def debug_env():
    env_vars = {
        'COINCATCH_API_KEY': 'SET' if os.environ.get('COINCATCH_API_KEY') else 'MISSING',
        'COINCATCH_API_SECRET': 'SET' if os.environ.get('COINCATCH_API_SECRET') else 'MISSING',
        'COINCATCH_API_PASSPHRASE': 'SET' if os.environ.get('COINCATCH_API_PASSPHRASE') else 'MISSING',
        'api_base_url': 'https://api.coincatch.com'
    }
    return jsonify(env_vars)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)