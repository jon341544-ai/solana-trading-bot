from flask import Flask, render_template, request, jsonify
import requests
import hmac
import hashlib
import time
import json
from datetime import datetime
import os
from dotenv import load_dotenv
import base64

load_dotenv()

app = Flask(__name__)

class CoinCatchAPI:
    def __init__(self, api_key=None, api_secret=None, api_passphrase=None):
        self.api_key = api_key or os.environ.get('COINCATCH_API_KEY')
        self.api_secret = api_secret or os.environ.get('COINCATCH_API_SECRET')
        self.api_passphrase = api_passphrase or os.environ.get('COINCATCH_API_PASSPHRASE')
        self.base_url = "https://api.coincatch.com"  # CoinCatch API base URL
    
    def generate_signature(self, timestamp, method, request_path, body=''):
        """Generate signature for CoinCatch API"""
        if body:
            message = timestamp + method + request_path + body
        else:
            message = timestamp + method + request_path
            
        mac = hmac.new(
            bytes(self.api_secret, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        return base64.b64encode(mac.digest()).decode()
    
    def get_account_balance(self):
        """Get futures account balance from CoinCatch API"""
        try:
            timestamp = str(int(time.time() * 1000))
            method = 'GET'
            
            # Try different possible endpoints
            endpoints = [
                '/api/mix/v1/account/accounts',
                '/api/v1/mix/account/accounts', 
                '/api/account/balance',
                '/api/v1/account',
                '/api/v1/account/balance'
            ]
            
            for request_path in endpoints:
                signature = self.generate_signature(timestamp, method, request_path)
                
                headers = {
                    'ACCESS-KEY': self.api_key,
                    'ACCESS-SIGN': signature,
                    'ACCESS-TIMESTAMP': timestamp,
                    'ACCESS-PASSPHRASE': self.api_passphrase,
                    'Content-Type': 'application/json'
                }
                
                print(f"Trying endpoint: {request_path}")
                response = requests.get(
                    f"{self.base_url}{request_path}",
                    headers=headers,
                    timeout=10
                )
                
                print(f"Response Status for {request_path}: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"Success with endpoint: {request_path}")
                    print(f"Response data: {data}")
                    return data
                elif response.status_code != 404:
                    print(f"Non-404 error for {request_path}: {response.status_code} - {response.text}")
            
            # If all endpoints failed, try without authentication for public data
            print("Trying public endpoints...")
            public_endpoints = [
                '/api/v1/market/ticker?symbol=BTCUSDT',
                '/api/v1/spot/public/products'
            ]
            
            for endpoint in public_endpoints:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=10)
                if response.status_code == 200:
                    print(f"Public endpoint {endpoint} works")
                    # Return mock data but indicate public API works
                    return {
                        'public_api_works': True,
                        'endpoint': endpoint,
                        'note': 'Public API accessible, but private endpoints failing'
                    }
            
            return {'error': 'All API endpoints failed. Please check API documentation.'}
                
        except Exception as e:
            return {'error': f'Request failed: {str(e)}'}
    
    def get_btc_price(self):
        """Get current BTC price"""
        try:
            # Try CoinCatch public API first
            endpoints = [
                '/api/v1/market/ticker?symbol=BTCUSDT',
                '/api/v1/spot/public/ticker?symbol=BTCUSDT',
                '/api/v1/market/tickers?symbol=BTCUSDT'
            ]
            
            for endpoint in endpoints:
                try:
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        # Try to extract price from different response formats
                        if 'data' in data and 'last' in data['data']:
                            return float(data['data']['last'])
                        elif 'last' in data:
                            return float(data['last'])
                        elif 'price' in data:
                            return float(data['price'])
                except:
                    continue
            
            # Fallback to CoinGecko
            response = requests.get(
                'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd',
                timeout=10
            )
            data = response.json()
            return data['bitcoin']['usd']
        except:
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
        
        client = CoinCatchAPI(api_key, api_secret, api_passphrase)
        account_data = client.get_account_balance()
        btc_price = client.get_btc_price()
        
        # Check if we got an error from the API
        if 'error' in account_data:
            return jsonify({
                'error': f'CoinCatch API Error: {account_data["error"]}',
                'btc_price': btc_price,
                'timestamp': datetime.now().isoformat(),
                'status': 'api_error',
                'note': 'Unable to connect to CoinCatch private API'
            }), 400
        
        # If public API works but private doesn't
        if account_data.get('public_api_works'):
            return jsonify({
                'total_balance': 0,
                'available_balance': 0,
                'frozen_balance': 0,
                'btc_price': btc_price,
                'timestamp': datetime.now().isoformat(),
                'status': 'public_only',
                'note': 'Public API accessible, but private endpoints failing. Check API documentation.',
                'debug_info': account_data
            })
        
        # Process successful API response
        # Adjust this based on actual CoinCatch response format
        response_data = {
            'total_balance': float(account_data.get('equity', 0)),
            'available_balance': float(account_data.get('available', 0)),
            'frozen_balance': float(account_data.get('frozen', 0)),
            'btc_price': btc_price,
            'timestamp': datetime.now().isoformat(),
            'status': 'live',
            'note': 'Live data from CoinCatch API',
            'raw_data': account_data
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/api/test-endpoints')
def test_endpoints():
    """Test various API endpoints to find the correct ones"""
    results = {}
    api_key = os.environ.get('COINCATCH_API_KEY')
    api_secret = os.environ.get('COINCATCH_API_SECRET')
    api_passphrase = os.environ.get('COINCATCH_API_PASSPHRASE')
    
    if not api_key:
        return jsonify({'error': 'API key not set'})
    
    client = CoinCatchAPI(api_key, api_secret, api_passphrase)
    
    # Test public endpoints
    public_endpoints = [
        '/api/v1/market/ticker?symbol=BTCUSDT',
        '/api/v1/spot/public/products',
        '/api/v1/market/tickers',
        '/api/v1/spot/ticker?symbol=BTCUSDT'
    ]
    
    for endpoint in public_endpoints:
        try:
            response = requests.get(f"{client.base_url}{endpoint}", timeout=5)
            results[endpoint] = {
                'status': response.status_code,
                'public': True
            }
        except Exception as e:
            results[endpoint] = {'error': str(e), 'public': True}
    
    return jsonify(results)

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