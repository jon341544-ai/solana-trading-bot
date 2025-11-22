#!/usr/bin/env python3
"""
Futures trading bot for SOL/USDT on CoinCatch.
With improved API credential validation.
"""

import os
import time
import hmac
import hashlib
import base64
import json
import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import requests
from flask import Flask, jsonify, request, render_template

# --------------------------------------------------------------------------- #
# Logging configuration
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
)
log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Flask app
# --------------------------------------------------------------------------- #

app = Flask(__name__)

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

class Config:
    """Load environment variables and hold static trading parameters."""
    def __init__(self):
        self.api_key = os.getenv("COINCATCH_API_KEY", "").strip()
        self.api_secret = os.getenv("COINCATCH_API_SECRET", "").strip()
        self.passphrase = os.getenv("COINCATCH_PASSPHRASE", "").strip()
        self.base_url = "https://api.coincatch.com"
        self.is_configured = bool(self.api_key and self.api_secret and self.passphrase)
        
        # Log credential status (without revealing secrets)
        log.info(f"API Key configured: {'Yes' if self.api_key else 'No'}")
        log.info(f"API Secret configured: {'Yes' if self.api_secret else 'No'}")
        log.info(f"Passphrase configured: {'Yes' if self.passphrase else 'No'}")
        
        if self.is_configured:
            log.info("✅ All API credentials are present")
        else:
            log.error("❌ Missing API credentials")
        
        # Timezone used for timestamps shown to the user
        self.timezone = ZoneInfo("America/New_York")
        
        # -------------------- USER-CONFIGURABLE SETTINGS --------------------
        self.leverage_multiplier = 5  # 1-20×
        self.base_position_size = 0.1  # SOL (before leverage)
        self.check_interval = 300  # seconds (5 min)
        
        # Indicator parameters
        self.rsi_period = 7
        self.macd_fast = 6
        self.macd_slow = 13
        self.macd_signal = 5
        
        # Risk management
        self.max_daily_loss = 0.10  # 10% of daily starting balance
        self.stop_loss_pct = 0.05  # 5%
        self.take_profit_pct = 0.10  # 10%
        
        # Trading specifics
        self.symbol = "SOLUSDT"
        self.margin_mode = "crossed"
        self.position_side = "LONG"

config = Config()

# [REST OF THE CODE REMAINS THE SAME - just use the previous working version]

def get_ny_time() -> datetime:
    return datetime.now(config.timezone)

class TradingState:
    def __init__(self):
        self.lock = threading.Lock()
        self.is_running = False
        self.current_position = None
        self.position_size = 0.0
        self.entry_price = 0.0
        self.unrealized_pnl = 0.0
        self.realized_pnl = 0.0
        self.last_trade_time = None
        self.last_signals = {}
        self.trade_history = []
        self.daily_starting_balance = 0.0
        self.daily_start_time = get_ny_time()
        self.total_trades = 0
        self.winning_trades = 0

trading_state = TradingState()

def make_api_request(method: str, endpoint: str, data: dict | None = None) -> dict:
    if not config.is_configured:
        return {"error": "API credentials not configured"}
    
    try:
        timestamp = str(int(time.time() * 1000))
        body_str = json.dumps(data, separators=(',', ':')) if data else ""
        message = f"{timestamp}{method.upper()}{endpoint}{body_str}"
        
        hmac_obj = hmac.new(
            config.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        )
        signature_digest = hmac_obj.digest()
        signature = base64.b64encode(signature_digest).decode()
        
        headers = {
            "X-CC-APIKEY": config.api_key,
            "X-CC-TIMESTAMP": timestamp,
            "X-CC-SIGN": signature,
            "Content-Type": "application/json",
        }
        
        url = config.base_url + endpoint
        timeout = 10
        
        log.info(f"Making {method} request to {endpoint}")
        
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, timeout=timeout)
        else:
            resp = requests.post(url, headers=headers, json=data, timeout=timeout)
        
        log.info(f"Response status: {resp.status_code}")
        
        try:
            payload = resp.json()
            log.info(f"Response data: {payload}")
        except ValueError:
            return {
                "error": f"Non-JSON response (HTTP {resp.status_code})",
                "message": resp.text,
                "status_code": resp.status_code
            }
        
        if resp.status_code == 200:
            return payload
        else:
            error_msg = payload.get("msg") or payload.get("error") or payload.get("message") or str(payload)
            if "ACCESS_KEY" in error_msg:
                log.error("❌ INVALID API CREDENTIALS - Please check your API Key, Secret, and Passphrase")
            return {
                "error": f"HTTP {resp.status_code}",
                "message": error_msg,
                "status_code": resp.status_code
            }
    except Exception as exc:
        log.exception("Request to %s failed", endpoint)
        return {"error": f"Request failed: {exc}"}

# [REST OF THE FUNCTIONS REMAIN THE SAME AS THE PREVIOUS WORKING VERSION]
