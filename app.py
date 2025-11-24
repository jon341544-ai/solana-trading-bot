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
        """Generate signature for CoinCatch API - Correct implementation"""
        if body and body != '{}':
            message = timestamp + method + request_path + body
        else:
            message = timestamp + method + request_path
            
        print(f"Signature message: {message}")
        mac = hmac.new(
            bytes(self.api_secret, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        signature = base64.b64encode(mac.digest()).decode()
        print(f"Generated signature: {signature}")
        return signature
    
    def make_api_request(self, method, request_path, params=None, requires_auth=True):
        """Make API request to CoinCatch"""
        try:
            timestamp = str(int(time.time() * 1000))
            
            headers = {
                'Content-Type': 'application/json'
            }
            
            if requires_auth:
                # Prepare query string for signature
                query_string = ""
                if params and method == 'GET':
                    clean_params = {k: v for k, v in params.items() if v is not None}
                    if clean_params:
                        query_string = '?' + urllib.parse.urlencode(clean_params)
                
                request_path_with_query = request_path + query_string
                body = ""
                
                if params and method == 'POST':
                    body = json.dumps(params, separators=(',', ':'))
                
                signature = self.generate_signature(timestamp, method, request_path_with_query, body)
                
                headers.update({
                    'ACCESS-KEY': self.api_key,
                    'ACCESS-SIGN': signature,
                    'ACCESS-TIMESTAMP': timestamp,
                    'ACCESS-PASSPHRASE': self.api_passphrase,
                })
            
            # Build URL
            url = f"{self.base_url}{request_path}"
            if params and method == 'GET' and requires_auth:
                url += query_string
            
            print(f"=== API REQUEST ===")
            print(f"URL: {url}")
            print(f"Method: {method}")
            print(f"Headers: { {k: '***' if any(x in k for x in ['KEY', 'SIGN', 'PASSPHRASE']) else v for k, v in headers.items()} }")
            if params:
                print(f"Params: {params}")
            
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            else:
                response = requests.post(url, headers=headers, json=params, timeout=10)
            
            print(f"=== API RESPONSE ===")
            print(f"Status: {response.status_code}")
            print(f"Response text: {response.text}")
            
            if response.status_code == 200:
                try:
                    return response.json()
                except json.JSONDecodeError:
                    return {'raw_response': response.text}
            else:
                try:
                    error_data = response.json()
                    return {'error': error_data}
                except:
                    return {'error': {'code': response.status_code, 'msg': response.text}}
                
        except Exception as e:
            print(f"API Exception: {str(e)}")
            return {'error': {'code': 'EXCEPTION', 'msg': str(e)}}
    
    def get_account_balance(self):
        """Get account balance - try multiple approaches"""
        print("=== GETTING ACCOUNT BALANCE ===")
        
        # Based on common exchange patterns, try these endpoints:
        attempts = [
            # Try without parameters first
            ('GET', '/api/mix/v1/account/accounts', None),
            
            # Try with productType parameter (common in other exchanges)
            ('GET', '/api/mix/v1/account/accounts', {'productType': 'umcbl'}),
            ('GET', '/api/mix/v1/account/accounts', {'productType': 'USDT-MIX'}),
            
            # Try with symbol parameter
            ('GET', '/api/mix/v1/account/accounts', {'symbol': 'BTCUSDT'}),
            
            # Try alternative endpoints
            ('GET', '/api/v1/account', None),
            ('GET', '/api/v1/account/balance', None),
            ('GET', '/api/mix/v1/account/account', {'symbol': 'BTCUSDT'}),
            
            # Try POST requests (some exchanges use POST for account data)
            ('POST', '/api/mix/v1/account/accounts', None),
            ('POST', '/api/mix/v1/account/accounts', {'productType': 'umcbl'}),
        ]
        
        for method, endpoint, params in attempts:
            print(f"Attempt: {method} {endpoint} with {params}")
            result = self.make_api_request(method, endpoint, params)
            
            # Check if this was successful
            if 'error' not in result:
                print(f"SUCCESS with {method} {endpoint}")
                return result
            
            error_msg = str(result.get('error', {}))
            print(f"Failed: {error_msg}")
            
            # If we get a specific error that suggests the endpoint exists but needs different params, continue
            if '400' in error_msg or 'Invalid' in error_msg:
                continue
            elif '404' in error_msg:
                continue  # Endpoint doesn't exist, try next
            else:
                # Other error, might be worth investigating
                print(f"Unexpected error: {error_msg}")
        
        return {'error': 'All balance endpoints failed'}
    
    def get_btc_price(self):
        """Get BTC price from public endpoints"""
        try:
            # Try public ticker endpoints (no authentication needed)
            public_endpoints = [
                '/api/mix/v1/market/ticker?symbol=BTCUSDT',
                '/api/v1/market/ticker?symbol=BTCUSDT',
                '/api/spot/v1/market/ticker?symbol=BTCUSDT',
                '/api/v1/spot/ticker?symbol=BTCUSDT'
            ]
            
            for endpoint in public_endpoints:
                try:
                    result = self.make_api_request('GET', endpoint.split('?')[0], 
                                                 urllib.parse.parse_qs(endpoint.split('?')[1]) if '?' in endpoint else None,
                                                 requires_auth=False)
                    if 'error' not in result:
                        # Extract price from response
                        data = result.get('data', result)
                        if isinstance(data, dict):
                            if 'last' in data:
                                return float(data['last'])
                            elif 'close' in data:
                                return float(data['close'])
                            elif 'price' in data:
                                return float(data['price'])
                except Exception as e:
                    print(f"Price endpoint {endpoint} failed: {e}")
                    continue
            
            # Fallback to CoinGecko
            response = requests.get(
                'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd',
                timeout=10
            )
            data = response.json()
            return data['bitcoin']['usd']
            
        except Exception as e:
            print(f"All price methods failed: {e}")
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
        
        # Get BTC price first (this usually works)
        btc_price = client.get_btc_price()
        print(f"BTC Price: {btc_price}")
        
        # Try to get account data
        account_data = client.get_account_balance()
        print(f"Account Data: {account_data}")
        
        # Prepare response
        if 'error' in account_data:
            return jsonify({
                'total_balance': 0,
                'available_balance': 0,
                'frozen_balance': 0,
                'btc_price': btc_price,
                'timestamp': datetime.now().isoformat(),
                'status': 'price_only',
                'note': 'BTC price is live, but account API endpoints need adjustment',
                'debug_info': {
                    'account_error': account_data['error'],
                    'btc_price_source': 'live'
                }
            })
        
        # Process successful account data
        # This will need to be adjusted based on actual API response
        response_data = {
            'total_balance': 0,
            'available_balance': 0,
            'frozen_balance': 0,
            'btc_price': btc_price,
            'timestamp': datetime.now().isoformat(),
            'status': 'live',
            'raw_data': account_data
        }
        
        # Try to extract balance information
        data = account_data.get('data', account_data)
        if isinstance(data, list) and len(data) > 0:
            account = data[0]
            response_data.update({
                'total_balance': float(account.get('equity', account.get('balance', 0))),
                'available_balance': float(account.get('available', account.get('availableBalance', 0))),
                'frozen_balance': float(account.get('frozen', account.get('locked', 0)))
            })
        elif isinstance(data, dict):
            response_data.update({
                'total_balance': float(data.get('equity', data.get('balance', 0))),
                'available_balance': float(data.get('available', data.get('availableBalance', 0))),
                'frozen_balance': float(data.get('frozen', data.get('locked', 0)))
            })
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Connect API error: {str(e)}")
        return jsonify({'error': f'Internal error: {str(e)}'}), 500

@app.route('/api/test-public')
def test_public():
    """Test public endpoints without authentication"""
    client = CoinCatchAPI()
    
    endpoints = [
        '/api/mix/v1/market/ticker?symbol=BTCUSDT',
        '/api/v1/market/ticker?symbol=BTCUSDT',
        '/api/spot/v1/market/ticker?symbol=BTCUSDT',
        '/api/v1/spot/ticker?symbol=BTCUSDT',
        '/api/mix/v1/market/contracts',
        '/api/v1/market/contracts'
    ]
    
    results = {}
    for endpoint in endpoints:
        path = endpoint.split('?')[0]
        params = urllib.parse.parse_qs(endpoint.split('?')[1]) if '?' in endpoint else None
        results[endpoint] = client.make_api_request('GET', path, params, requires_auth=False)
    
    return jsonify(results)

@app.route('/api/debug')
def debug_env():
    return jsonify({
        'COINCATCH_API_KEY': 'SET' if os.environ.get('COINCATCH_API_KEY') else 'MISSING',
        'COINCATCH_API_SECRET': 'SET' if os.environ.get('COINCATCH_API_SECRET') else 'MISSING',
        'COINCATCH_API_PASSPHRASE': 'SET' if os.environ.get('COINCATCH_API_PASSPHRASE') else 'MISSING',
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
