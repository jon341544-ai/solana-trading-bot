#!/usr/bin/env python3
"""
Test script to verify CoinCatch API credentials
"""

import os
import time
import hmac
import hashlib
import base64
import json
import requests

def test_api_credentials():
    api_key = os.getenv("COINCATCH_API_KEY", "")
    api_secret = os.getenv("COINCATCH_API_SECRET", "")
    passphrase = os.getenv("COINCATCH_PASSPHRASE", "")
    
    print(f"API Key: {api_key[:10]}...{api_key[-5:] if len(api_key) > 15 else ''}")
    print(f"API Secret: {'*' * len(api_secret)}")
    print(f"Passphrase: {'*' * len(passphrase)}")
    
    if not all([api_key, api_secret, passphrase]):
        print("❌ Missing API credentials")
        return False
    
    # Test endpoint - get account balance
    endpoint = "/api/mix/v1/account/accounts"
    timestamp = str(int(time.time() * 1000))
    message = f"{timestamp}GET{endpoint}"
    
    try:
        # Create HMAC signature
        hmac_obj = hmac.new(
            api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        )
        signature_digest = hmac_obj.digest()
        signature = base64.b64encode(signature_digest).decode()
        
        headers = {
            "X-CC-APIKEY": api_key,
            "X-CC-TIMESTAMP": timestamp,
            "X-CC-SIGN": signature,
            "Content-Type": "application/json",
        }
        
        url = "https://api.coincatch.com" + endpoint
        
        print(f"\nTesting API call to: {endpoint}")
        print(f"Headers (without signature): { {k: v for k, v in headers.items() if k != 'X-CC-SIGN'} }")
        
        resp = requests.get(url, headers=headers, timeout=10)
        
        print(f"Response Status: {resp.status_code}")
        print(f"Response Headers: {dict(resp.headers)}")
        print(f"Response Body: {resp.text}")
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "00000":
                print("✅ API credentials are valid!")
                return True
            else:
                print(f"❌ API error: {data}")
                return False
        else:
            print(f"❌ HTTP error: {resp.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

if __name__ == "__main__":
    test_api_credentials()
