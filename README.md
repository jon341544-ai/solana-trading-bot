# Solana Spot Trading Bot for CoinCatch

A Flask-based automated trading bot for Solana (SOL/USDT) spot trading on CoinCatch exchange.

## Features

- 🔍 Test API connection
- 💰 View USDT and SOL balances
- 💎 Automated fixed-amount SOL trading
- 📊 Real-time SOL price display
- 📈 MACD technical indicator
- 🎯 Fixed SOL amount per trade (default: 0.1 SOL)

## Setup for Railway

### 1. Get your CoinCatch API credentials

1. Log in to [CoinCatch](https://www.coincatch.com)
2. Go to Account → API Management
3. Create a new API key with:
   - **Read permission** (required)
   - **Trade permission** (required for buying)
4. Save your:
   - API Key
   - API Secret
   - Passphrase

### 2. Deploy to Railway

1. Push this code to GitHub
2. Go to [Railway.app](https://railway.app)
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your repository
5. Add environment variables:
   - `COINCATCH_API_KEY` = your API key
   - `COINCATCH_API_SECRET` = your API secret
   - `COINCATCH_PASSPHRASE` = your passphrase

### 3. Access your bot

Once deployed, Railway will give you a URL like `https://your-app.up.railway.app`

## Local Testing

```bash
# Set environment variables
export COINCATCH_API_KEY="your_key_here"
export COINCATCH_API_SECRET="your_secret_here"
export COINCATCH_PASSPHRASE="your_passphrase_here"

# Install dependencies
pip install -r requirements.txt

# Run the app
python solana_bot.py
