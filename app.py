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
    
    def generate_signature_v1(self, timestamp, method, request_path, body=''):
        """Version 1: timestamp + method + requestPath"""
        message = timestamp + method + request_path
        print(f"V1 Message: '{message}'")
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def generate_signature_v2(self, timestamp, method, request_path, body=''):
        """Version 2: timestamp + method + requestPath + body (base64)"""
        if body and body != '{}':
            message = timestamp + method + request_path + body
        else:
            message = timestamp + method + request_path
        print(f"V2 Message: '{message}'")
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode()
        return signature
    
    def generate_signature_v3(self, timestamp, method, request_path, body=''):
        """Version 3: timestamp + method + requestPath (with query)"""
        message = timestamp + method + request_path
        print(f"V3 Message: '{message}'")
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def generate_signature_v4(self, timestamp, method, request_path, body=''):
        """Version 4: Like V3 but uppercase method"""
        message = timestamp + method.upper() + request_path
        print(f"V4 Message: '{message}'")
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def generate_signature_v5(self, timestamp, method, request_path, body=''):
        """Version 5: Like V2 but with hex instead of base64"""
        if body and body != '{}':
            message = timestamp + method + request_path + body
        else:
            message = timestamp + method + request_path
        print(f"V5 Message: '{message}'")
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def generate_signature_v6(self, timestamp, method, request_path, body=''):
        """Version 6: Only timestamp + requestPath (no method)"""
        message = timestamp + request_path
        print(f"V6 Message: '{message}'")
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def generate_signature_v7(self, timestamp, method, request_path, body=''):
        """Version 7: requestPath + timestamp"""
        message = request_path + timestamp
        print(f"V7 Message: '{message}'")
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def generate_signature_v8(self, timestamp, method, request_path, body=''):
        """Version 8: Like V2 but with different body handling"""
        # Some exchanges want the raw body string, not JSON
        if body and body != '{}':
            # Try with raw params instead of JSON
            message = timestamp + method + request_path + body
        else:
            message = timestamp + method + request_path
        print(f"V8 Message: '{message}'")
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode()
        return signature
    
    def generate_signature_v9(self, timestamp, method, request_path, body=''):
        """Version 9: Passphrase included in signature"""
        message = timestamp + method + request_path + self.api_passphrase
        print(f"V9 Message: '{message}'")
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def generate_signature_v10(self, timestamp, method, request_path, body=''):
        """Version 10: Passphrase + base64"""
        message = timestamp + method + request_path + self.api_passphrase
        print(f"V10 Message: '{message}'")
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode()
        return signature

    def make_api_request(self, method, request_path, params=None, signature_version=1):
        """Make API request with specific signature version"""
        try:
            timestamp = str(int(time.time() * 1000))
            
            # Prepare body and query string
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
            
            # Select signature method
            signature_methods = {
                1: self.generate_signature_v1,
                2: self.generate_signature_v2,
                3: self.generate_signature_v3,
                4: self.generate_signature_v4,
                5: self.generate_signature_v5,
                6: self.generate_signature_v6,
                7: self.generate_signature_v7,
                8: self.generate_signature_v8,
                9: self.generate_signature_v9,
                10: self.generate_signature_v10,
            }
            
            signature_func = signature_methods.get(signature_version, self.generate_signature_v1)
            signature = signature_func(timestamp, method.upper(), request_path_with_query, body)
            
            headers = {
                'ACCESS-KEY': self.api_key,
                'ACCESS-SIGN': signature,
                'ACCESS-TIMESTAMP': timestamp,
                'ACCESS-PASSPHRASE': self.api_passphrase,
                'Content-Type': 'application/json'
            }
            
            url = f"{self.base_url}{request_path_with_query}"
            
            print(f"=== SIGNATURE V{signature_version} ===")
            print(f"URL: {url}")
            print(f"Signature: {signature}")
            
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            else:
                response = requests.post(url, headers=headers, data=body, timeout=10)
            
            print(f"Response: {response.status_code} - {response.text[:100]}")
            
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
        """Try all signature versions to find the correct one"""
        print("=== TESTING ALL SIGNATURE VERSIONS ===")
        
        for version in range(1, 11):
            print(f"\n--- Testing Signature Version {version} ---")
            result = self.make_api_request(
                'GET', 
                '/api/mix/v1/account/accounts', 
                {'productType': 'umcbl'},
                version
            )
            
            if 'error' not in result:
                print(f"🎉 SUCCESS with signature version {version}!")
                return result
            
            error_data = result.get('error', {})
            error_msg = error_data.get('msg', str(error_data))
            print(f"Version {version} failed: {error_msg}")
            
            # If we get a different error (not signature error), we might have the right signature
            if 'signature' not in error_msg.lower() and 'sign' not in error_msg.lower():
                print(f"⚠️ Different error - might be progress: {error_msg}")
                # Continue to see if we get a better result, but note this version
                if '40009' not in str(error_data.get('code', '')):
                    return result
        
        return {'error': 'All signature versions failed'}
    
    def get_btc_price(self):
        """Get BTC price"""
        try:
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
        
        # Try to get account data
        account_data = client.get_account_balance()
        
        if 'error' in account_data:
            return jsonify({
                'total_balance': 0,
                'available_balance': 0,
                'frozen_balance': 0,
                'btc_price': btc_price,
                'timestamp': datetime.now().isoformat(),
                'status': 'testing_signatures',
                'note': 'Testing different signature methods. Check server logs for details.',
                'debug_info': {
                    'btc_price': btc_price,
                    'signature_testing': 'in_progress'
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
            'raw_data': account_data,
            'note': 'Successfully connected with correct signature method!'
        }
        
        # Extract balances
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

@app.route('/api/test-all-signatures')
def test_all_signatures():
    """Test all signature methods and return results"""
    api_key = os.environ.get('COINCATCH_API_KEY')
    api_secret = os.environ.get('COINCATCH_API_SECRET')
    api_passphrase = os.environ.get('COINCATCH_API_PASSPHRASE')
    
    if not api_key:
        return jsonify({'error': 'API credentials not set'})
    
    client = CoinCatchAPI(api_key, api_secret, api_passphrase)
    
    results = {}
    for version in range(1, 11):
        result = client.make_api_request(
            'GET', 
            '/api/mix/v1/account/accounts', 
            {'productType': 'umcbl'},
            version
        )
        results[f'v{version}'] = result
    
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
