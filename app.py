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
import base64

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
            message = str(timestamp) + str(method) + str(request_path) + str(body)
        else:
            message = str(timestamp) + str(method) + str(request_path)
            
        print(f"Signature message length: {len(message)}")
        mac = hmac.new(
            bytes(self.api_secret, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        signature = base64.b64encode(mac.digest()).decode()
        return signature
    
    def make_api_request(self, method, request_path, params=None):
        """Make authenticated API request to CoinCatch"""
        try:
            timestamp = str(int(time.time() * 1000))
            
            # Prepare query string for GET requests
            query_string = ""
            if params and method == 'GET':
                # Filter out None values
                clean_params = {k: v for k, v in params.items() if v is not None}
                if clean_params:
                    query_string = '?' + urllib.parse.urlencode(clean_params)
            request_path_with_query = request_path + query_string
            
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
            print(f"=== API REQUEST ===")
            print(f"URL: {url}")
            print(f"Method: {method}")
            print(f"Timestamp: {timestamp}")
            print(f"Signature: {signature[:20]}...")
            if params:
                print(f"Params: {params}")
            if body:
                print(f"Body: {body}")
            
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            else:
                response = requests.post(url, headers=headers, data=body, timeout=10)
            
            print(f"=== API RESPONSE ===")
            print(f"Status: {response.status_code}")
            print(f"Headers: {dict(response.headers)}")
            print(f"Response: {response.text}")
            print(f"====================")
            
            if response.status_code == 200:
                try:
                    return response.json()
                except json.JSONDecodeError:
                    return {'data': response.text}
            else:
                # Try to parse error response
                try:
                    error_data = response.json()
                    return {'error': error_data}
                except:
                    return {'error': {'code': response.status_code, 'msg': response.text}}
                
        except Exception as e:
            print(f"=== API EXCEPTION ===")
            print(f"Error: {str(e)}")
            return {'error': {'code': 'EXCEPTION', 'msg': str(e)}}
    
    def get_account_balance(self):
        """Get futures account balance from CoinCatch API"""
        print("=== GETTING ACCOUNT BALANCE ===")
        
        # Try different endpoints and parameter combinations
        endpoints_to_try = [
            # Endpoint with different parameters
            ('/api/mix/v1/account/accounts', {'productType': 'umcbl'}),
            ('/api/mix/v1/account/accounts', {'symbol': 'BTCUSDT_UMCBL'}),
            ('/api/mix/v1/account/accounts', {'marginCoin': 'USDT'}),
            ('/api/mix/v1/account/accounts', {'productType': 'USDT-MIX'}),
            ('/api/mix/v1/account/accounts', {}),  # No params
            
            # Alternative endpoints
            ('/api/v1/account', {}),
            ('/api/v1/account/balance', {'currency': 'USDT'}),
            ('/api/v1/user/balance', {}),
            
            # Mix endpoints from documentation
            ('/api/mix/v1/account/account', {'symbol': 'BTCUSDT'}),
            ('/api/mix/v1/account/account', {'productType': 'umcbl', 'marginCoin': 'USDT'}),
        ]
        
        for endpoint, params in endpoints_to_try:
            print(f"Trying endpoint: {endpoint} with params: {params}")
            result = self.make_api_request('GET', endpoint, params)
            
            # If successful, return the result
            if 'error' not in result:
                print(f"SUCCESS with {endpoint}")
                return result
            
            # If it's a 400 error, log it but continue trying
            error_code = str(result.get('error', {}).get('code', ''))
            if '400' in error_code:
                print(f"400 error with {endpoint}: {result['error']}")
                # Continue to next endpoint
            else:
                print(f"Other error with {endpoint}: {result['error']}")
                # For non-400 errors, we might want to stop or continue based on the error
        
        # If all endpoints failed, return the last error
        return result
    
    def get_btc_price(self):
        """Get current BTC price"""
        try:
            # Try CoinCatch public endpoints
            public_endpoints = [
                '/api/mix/v1/market/ticker?symbol=BTCUSDT',
                '/api/v1/market/ticker?symbol=BTCUSDT',
                '/api/spot/v1/market/ticker?symbol=BTCUSDT'
            ]
            
            for endpoint in public_endpoints:
                try:
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        print(f"BTC Price from {endpoint}: {data}")
                        # Extract price from different response formats
                        if 'data' in data and 'last' in data['data']:
                            return float(data['data']['last'])
                        elif 'last' in data:
                            return float(data['last'])
                        elif 'data' in data and isinstance(data['data'], dict) and 'last' in data['data']:
                            return float(data['data']['last'])
                except Exception as e:
                    print(f"Failed to get BTC price from {endpoint}: {e}")
                    continue
            
            # Fallback to CoinGecko
            response = requests.get(
                'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd',
                timeout=10
            )
            data = response.json()
            return data['bitcoin']['usd']
        except Exception as e:
            print(f"All BTC price methods failed: {e}")
            return 50000

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
        
        print("=== STARTING API CONNECTION ===")
        client = CoinCatchAPI(api_key, api_secret, api_passphrase)
        account_data = client.get_account_balance()
        btc_price = client.get_btc_price()
        
        print(f"Account data result: {account_data}")
        print(f"BTC price: {btc_price}")
        
        # Check if we got an error from the API
        if 'error' in account_data:
            return jsonify({
                'error': f'API Error: {account_data["error"]}',
                'btc_price': btc_price,
                'timestamp': datetime.now().isoformat(),
                'status': 'api_error',
                'note': 'Unable to fetch account data from CoinCatch API'
            }), 400
        
        # Process successful API response
        # This will need to be adjusted based on the actual API response format
        response_data = {
            'total_balance': 0,
            'available_balance': 0,
            'frozen_balance': 0,
            'btc_price': btc_price,
            'timestamp': datetime.now().isoformat(),
            'status': 'live',
            'note': 'BTC price is live, but account data format needs adjustment',
            'raw_data': account_data
        }
        
        # Try to extract balances from different response formats
        if 'data' in account_data:
            data = account_data['data']
            if isinstance(data, list) and len(data) > 0:
                # Multiple accounts
                account = data[0]
                response_data.update({
                    'total_balance': float(account.get('equity', account.get('marginBalance', 0))),
                    'available_balance': float(account.get('available', account.get('availableBalance', 0))),
                    'frozen_balance': float(account.get('frozen', account.get('locked', 0)))
                })
            elif isinstance(data, dict):
                # Single account
                response_data.update({
                    'total_balance': float(data.get('equity', data.get('marginBalance', 0))),
                    'available_balance': float(data.get('available', data.get('availableBalance', 0))),
                    'frozen_balance': float(data.get('frozen', data.get('locked', 0)))
                })
        else:
            # Direct response
            response_data.update({
                'total_balance': float(account_data.get('equity', account_data.get('marginBalance', 0))),
                'available_balance': float(account_data.get('available', account_data.get('availableBalance', 0))),
                'frozen_balance': float(account_data.get('frozen', account_data.get('locked', 0)))
            })
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"=== CONNECT API EXCEPTION ===")
        print(f"Error: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/api/debug')
def debug_env():
    env_vars = {
        'COINCATCH_API_KEY': 'SET' if os.environ.get('COINCATCH_API_KEY') else 'MISSING',
        'COINCATCH_API_SECRET': 'SET' if os.environ.get('COINCATCH_API_SECRET') else 'MISSING',
        'COINCATCH_API_PASSPHRASE': 'SET' if os.environ.get('COINCATCH_API_PASSPHRASE') else 'MISSING',
    }
    return jsonify(env_vars)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
