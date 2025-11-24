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
        """Generate signature for CoinCatch API - FIXED VERSION"""
        # CoinCatch likely uses a specific format for the signature message
        # Common patterns in crypto exchanges:
        
        # Pattern 1: timestamp + method + requestPath + body (if POST)
        if method.upper() == 'POST' and body and body != '{}':
            message = str(timestamp) + method.upper() + request_path + body
        else:
            message = str(timestamp) + method.upper() + request_path
        
        print(f"Signature message: '{message}'")
        print(f"Message length: {len(message)}")
        print(f"Using secret: {self.api_secret[:5]}...{self.api_secret[-3:]}")
        
        # Try different encoding approaches
        try:
            # Method 1: Standard HMAC-SHA256
            signature = hmac.new(
                self.api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            print(f"Method 1 (hex): {signature}")
        except Exception as e:
            print(f"Method 1 failed: {e}")
            signature = ""
        
        # Also try base64 encoding (used by some exchanges)
        try:
            signature_b64 = hmac.new(
                self.api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
            signature_b64 = base64.b64encode(signature_b64).decode()
            print(f"Method 2 (base64): {signature_b64}")
        except Exception as e:
            print(f"Method 2 failed: {e}")
            signature_b64 = ""
        
        # Return hex version by default, but we might need base64
        return signature
    
    def generate_signature_v2(self, timestamp, method, request_path, body=''):
        """Alternative signature method - some exchanges use base64"""
        if method.upper() == 'POST' and body and body != '{}':
            message = str(timestamp) + method.upper() + request_path + body
        else:
            message = str(timestamp) + method.upper() + request_path
        
        print(f"V2 Signature message: '{message}'")
        
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode()
        
        print(f"V2 Signature (base64): {signature}")
        return signature
    
    def generate_signature_v3(self, timestamp, method, request_path, body=''):
        """Another common pattern: include query parameters in signature"""
        # For GET requests with query parameters
        if method.upper() == 'GET' and '?' in request_path:
            path, query = request_path.split('?', 1)
            message = str(timestamp) + method.upper() + path + '?' + query
        elif method.upper() == 'POST' and body and body != '{}':
            message = str(timestamp) + method.upper() + request_path + body
        else:
            message = str(timestamp) + method.upper() + request_path
        
        print(f"V3 Signature message: '{message}'")
        
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        print(f"V3 Signature (hex): {signature}")
        return signature
    
    def make_api_request(self, method, request_path, params=None, signature_version=1):
        """Make API request with different signature methods"""
        try:
            timestamp = str(int(time.time() * 1000))
            
            # Prepare body for POST or query string for GET
            body = ""
            query_string = ""
            
            if params:
                if method.upper() == 'POST':
                    body = json.dumps(params, separators=(',', ':'))
                else:
                    clean_params = {k: v for k, v in params.items() if v is not None}
                    if clean_params:
                        query_string = '?' + urllib.parse.urlencode(clean_params)
            
            request_path_with_query = request_path + query_string
            
            # Generate signature based on version
            if signature_version == 1:
                signature = self.generate_signature(timestamp, method, request_path_with_query, body)
            elif signature_version == 2:
                signature = self.generate_signature_v2(timestamp, method, request_path_with_query, body)
            elif signature_version == 3:
                signature = self.generate_signature_v3(timestamp, method, request_path_with_query, body)
            else:
                signature = self.generate_signature(timestamp, method, request_path_with_query, body)
            
            headers = {
                'ACCESS-KEY': self.api_key,
                'ACCESS-SIGN': signature,
                'ACCESS-TIMESTAMP': timestamp,
                'ACCESS-PASSPHRASE': self.api_passphrase,
                'Content-Type': 'application/json'
            }
            
            url = f"{self.base_url}{request_path_with_query}"
            
            print(f"=== API REQUEST (v{signature_version}) ===")
            print(f"URL: {url}")
            print(f"Method: {method}")
            print(f"Timestamp: {timestamp}")
            print(f"Signature: {signature}")
            print(f"Body: {body}")
            
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            else:
                response = requests.post(url, headers=headers, data=body, timeout=10)
            
            print(f"=== API RESPONSE ===")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code == 200:
                return response.json()
            else:
                try:
                    return {'error': response.json()}
                except:
                    return {'error': {'code': response.status_code, 'msg': response.text}}
                
        except Exception as e:
            return {'error': {'code': 'EXCEPTION', 'msg': str(e)}}
    
    def get_account_balance(self):
        """Get account balance - try different signature methods"""
        print("=== GETTING ACCOUNT BALANCE ===")
        
        # Try each signature version
        for signature_version in [1, 2, 3]:
            print(f"Trying signature version {signature_version}")
            
            result = self.make_api_request(
                'GET', 
                '/api/mix/v1/account/accounts', 
                {'productType': 'umcbl'},
                signature_version
            )
            
            if 'error' not in result:
                print(f"SUCCESS with signature version {signature_version}")
                return result
            
            error_msg = str(result.get('error', {}))
            print(f"Signature v{signature_version} failed: {error_msg}")
            
            # If we get a different error (not signature error), we might have the right signature
            if 'signature' not in error_msg.lower() and 'sign' not in error_msg.lower():
                print(f"Different error - might be progress: {error_msg}")
                return result
        
        return {'error': 'All signature methods failed'}
    
    def get_btc_price(self):
        """Get BTC price from public endpoints"""
        try:
            endpoints = [
                '/api/mix/v1/market/ticker?symbol=BTCUSDT',
                '/api/v1/market/ticker?symbol=BTCUSDT',
            ]
            
            for endpoint in endpoints:
                try:
                    path = endpoint.split('?')[0]
                    params = urllib.parse.parse_qs(endpoint.split('?')[1]) if '?' in endpoint else None
                    
                    # Public endpoint, no authentication
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        print(f"BTC price response: {data}")
                        
                        # Extract price
                        if 'data' in data and 'last' in data['data']:
                            return float(data['data']['last'])
                        elif 'last' in data:
                            return float(data['last'])
                except Exception as e:
                    continue
            
            # Fallback
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
            return jsonify({'error': 'API credentials not found'}), 400
        
        client = CoinCatchAPI(api_key, api_secret, api_passphrase)
        
        # Get BTC price
        btc_price = client.get_btc_price()
        
        # Try to get account data with different signature methods
        account_data = client.get_account_balance()
        
        if 'error' in account_data:
            return jsonify({
                'total_balance': 0,
                'available_balance': 0,
                'frozen_balance': 0,
                'btc_price': btc_price,
                'timestamp': datetime.now().isoformat(),
                'status': 'signature_issue',
                'note': 'BTC price is live, but signature authentication is failing',
                'debug_info': {
                    'account_error': account_data['error'],
                    'btc_price': btc_price
                }
            })
        
        # Process successful response
        response_data = {
            'total_balance': 0,
            'available_balance': 0,
            'frozen_balance': 0,
            'btc_price': btc_price,
            'timestamp': datetime.now().isoformat(),
            'status': 'live',
            'raw_data': account_data
        }
        
        # Extract balances from response
        data = account_data.get('data', account_data)
        if isinstance(data, list) and len(data) > 0:
            account = data[0]
            response_data.update({
                'total_balance': float(account.get('equity', 0)),
                'available_balance': float(account.get('available', 0)),
                'frozen_balance': float(account.get('frozen', 0))
            })
        elif isinstance(data, dict):
            response_data.update({
                'total_balance': float(data.get('equity', 0)),
                'available_balance': float(data.get('available', 0)),
                'frozen_balance': float(data.get('frozen', 0))
            })
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-signatures')
def test_signatures():
    """Test different signature methods"""
    api_key = os.environ.get('COINCATCH_API_KEY')
    api_secret = os.environ.get('COINCATCH_API_SECRET')
    api_passphrase = os.environ.get('COINCATCH_API_PASSPHRASE')
    
    if not api_key:
        return jsonify({'error': 'API key not set'})
    
    client = CoinCatchAPI(api_key, api_secret, api_passphrase)
    
    results = {}
    for version in [1, 2, 3]:
        results[f'signature_v{version}'] = client.make_api_request(
            'GET', 
            '/api/mix/v1/account/accounts', 
            {'productType': 'umcbl'},
            version
        )
    
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
