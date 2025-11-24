from flask import Flask, render_template, request, jsonify
import requests
import hmac
import hashlib
import time
import json
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)

class CoinCatchAPI:
    def __init__(self, api_key=None, api_secret=None, api_passphrase=None):
        self.api_key = api_key or os.environ.get('COINCATCH_API_KEY')
        self.api_secret = api_secret or os.environ.get('COINCATCH_API_SECRET')
        self.api_passphrase = api_passphrase or os.environ.get('COINCATCH_API_PASSPHRASE')
        self.base_url = "https://api.coincatch.com"  # Replace with actual CoinCatch API URL
    
    def generate_signature(self, timestamp, method, request_path, body=''):
        """Generate signature for CoinCatch API"""
        message = str(timestamp) + method + request_path + body
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def get_account_balance(self):
        """Get futures account balance"""
        try:
            timestamp = str(int(time.time() * 1000))
            method = 'GET'
            request_path = '/api/v1/account'  # Replace with actual endpoint
            
            signature = self.generate_signature(timestamp, method, request_path)
            
            headers = {
                'X-API-KEY': self.api_key,
                'X-API-SIGNATURE': signature,
                'X-API-TIMESTAMP': timestamp,
                'X-API-PASSPHRASE': self.api_passphrase,
                'Content-Type': 'application/json'
            }
            
            # This is a placeholder - replace with actual CoinCatch API endpoint
            response = requests.get(
                f"{self.base_url}{request_path}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': f'API Error: {response.status_code} - {response.text}'}
                
        except Exception as e:
            return {'error': str(e)}
    
    def get_btc_price(self):
        """Get current BTC price"""
        try:
            # Using CoinGecko as fallback
            response = requests.get(
                'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd',
                timeout=10
            )
            data = response.json()
            return data['bitcoin']['usd']
        except:
            # Fallback price
            return 50000

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/connect', methods=['POST'])
def connect_api():
    data = request.json
    api_key = data.get('api_key')
    api_secret = data.get('api_secret')
    api_passphrase = data.get('api_passphrase')
    
    if not api_key or not api_secret or not api_passphrase:
        return jsonify({'error': 'API key, secret, and passphrase are required'}), 400
    
    # Initialize API client
    client = CoinCatchAPI(api_key, api_secret, api_passphrase)
    
    # Get account data
    account_data = client.get_account_balance()
    btc_price = client.get_btc_price()
    
    # Mock data for demonstration (remove in production)
    if 'error' in account_data:
        # Return mock data for demo purposes
        mock_data = {
            'total_balance': 12547.32,
            'available_balance': 9845.67,
            'frozen_balance': 2701.65,
            'btc_price': btc_price,
            'timestamp': datetime.now().isoformat()
        }
        return jsonify(mock_data)
    
    # Process real API response here
    # You'll need to adapt this based on CoinCatch's actual response format
    processed_data = {
        'total_balance': account_data.get('totalBalance', 0),
        'available_balance': account_data.get('availableBalance', 0),
        'frozen_balance': account_data.get('frozenBalance', 0),
        'btc_price': btc_price,
        'timestamp': datetime.now().isoformat()
    }
    
    return jsonify(processed_data)

@app.route('/api/btc-price')
def get_btc_price():
    """Get BTC price only"""
    try:
        client = CoinCatchAPI('', '', '')  # Empty credentials for price check
        price = client.get_btc_price()
        return jsonify({'btc_price': price})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)