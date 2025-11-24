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
    
    def generate_signature(self, timestamp, method, endpoint, params=None):
        """Generate signature based on common exchange patterns"""
        # Pattern 1: timestamp + method + endpoint + query_string (most common)
        if params and method.upper() == 'GET':
            query_string = '?' + urllib.parse.urlencode(params)
            message = f"{timestamp}{method.upper()}{endpoint}{query_string}"
        elif params and method.upper() == 'POST':
            message = f"{timestamp}{method.upper()}{endpoint}{json.dumps(params)}"
        else:
            message = f"{timestamp}{method.upper()}{endpoint}"
        
        print(f"Signature message: {message}")
        
        # Most exchanges use base64 encoding for the signature
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        return base64.b64encode(signature).decode()
    
    def make_request(self, method, endpoint, params=None):
        """Make authenticated request to CoinCatch API"""
        try:
            timestamp = str(int(time.time() * 1000))
            signature = self.generate_signature(timestamp, method, endpoint, params)
            
            headers = {
                'ACCESS-KEY': self.api_key,
                'ACCESS-SIGN': signature,
                'ACCESS-TIMESTAMP': timestamp,
                'ACCESS-PASSPHRASE': self.api_passphrase,
                'Content-Type': 'application/json'
            }
            
            url = f"{self.base_url}{endpoint}"
            if params and method.upper() == 'GET':
                url += '?' + urllib.parse.urlencode(params)
            
            print(f"Making {method} request to: {url}")
            print(f"Signature: {signature}")
            
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            else:
                response = requests.post(url, headers=headers, json=params, timeout=10)
            
            print(f"Response: {response.status_code} - {response.text}")
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': response.json() if response.text else {'code': response.status_code}}
                
        except Exception as e:
            return {'error': str(e)}
    
    def get_position_tier(self):
        """Get position tier information - from the documentation URL"""
        # This endpoint is specifically mentioned in your URL
        return self.make_request('GET', '/api/mix/v1/account/position-tier', {
            'productType': 'umcbl',
            'symbol': 'BTCUSDT'
        })
    
    def get_account_balance(self):
        """Get account balance"""
        return self.make_request('GET', '/api/mix/v1/account/accounts', {
            'productType': 'umcbl'
        })
    
    def get_btc_price(self):
        """Get BTC price"""
        try:
            # Try to get from CoinCatch public API
            response = requests.get(f"{self.base_url}/api/mix/v1/market/ticker?symbol=BTCUSDT", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and 'last' in data['data']:
                    return float(data['data']['last'])
            
            # Fallback to CoinGecko
            response = requests.get(
                'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd',
                timeout=10
            )
            return response.json()['bitcoin']['usd']
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
            return jsonify({'error': 'API credentials not found'}), 400
        
        client = CoinCatchAPI(api_key, api_secret, api_passphrase)
        
        # Get BTC price (this should work)
        btc_price = client.get_btc_price()
        
        # Try to get account data
        account_data = client.get_account_balance()
        
        # Also try position tier (from the specific endpoint in your URL)
        position_tier = client.get_position_tier()
        
        if 'error' in account_data and 'error' in position_tier:
            return jsonify({
                'total_balance': 0,
                'available_balance': 0,
                'frozen_balance': 0,
                'btc_price': btc_price,
                'timestamp': datetime.now().isoformat(),
                'status': 'authentication_issue',
                'note': 'Authentication failing. Please check the exact signature format in CoinCatch documentation.',
                'debug_info': {
                    'account_error': account_data.get('error'),
                    'position_tier_error': position_tier.get('error'),
                    'btc_price': btc_price
                }
            })
        
        # If we get here, at least one API call worked
        response_data = {
            'total_balance': 0,
            'available_balance': 0,
            'frozen_balance': 0,
            'btc_price': btc_price,
            'timestamp': datetime.now().isoformat(),
            'status': 'partial_success'
        }
        
        # Process account data if available
        if 'error' not in account_data:
            response_data['status'] = 'live'
            response_data['raw_account_data'] = account_data
            # Extract balances from response (adjust based on actual format)
            data = account_data.get('data', account_data)
            if isinstance(data, list) and len(data) > 0:
                account = data[0]
                response_data.update({
                    'total_balance': float(account.get('equity', 0)),
                    'available_balance': float(account.get('available', 0)),
                    'frozen_balance': float(account.get('frozen', 0))
                })
        
        # Add position tier data if available
        if 'error' not in position_tier:
            response_data['position_tier_data'] = position_tier
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-position-tier')
def test_position_tier():
    """Test the specific endpoint from the documentation"""
    api_key = os.environ.get('COINCATCH_API_KEY')
    api_secret = os.environ.get('COINCATCH_API_SECRET')
    api_passphrase = os.environ.get('COINCATCH_API_PASSPHRASE')
    
    if not api_key:
        return jsonify({'error': 'API credentials not set'})
    
    client = CoinCatchAPI(api_key, api_secret, api_passphrase)
    result = client.get_position_tier()
    
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
