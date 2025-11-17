# Simple CoinCatch SOL Trading Bot

A minimal Flask application to test CoinCatch API connection and buy SOL with USDT.

## Features

- 🔍 Test API connection
- 💰 View USDT and SOL balances
- 💎 Automated percentage-based SOL trading
- 📊 Real-time SOL price display
- 📈 Multiple technical indicators (Supertrend, MACD, FantailVMA)

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
```

Then visit `http://localhost:8080`

## Usage

1. **Configure Settings**: Set your trade percentage (% of USDT to use for buys) and check interval
2. **Start Bot**: Click "START AUTOMATED TRADING" to begin
3. **Monitor**: The bot will automatically buy and sell SOL based on technical indicators
4. **Stop Bot**: Click "STOP TRADING" when you want to pause

## Trading Strategy

- **Buy Strategy**: Uses specified percentage of USDT balance (default 50%)
- **Sell Strategy**: Always sells 100% of SOL balance
- **Signal Consensus**: 2 out of 3 indicators must agree (Supertrend, MACD, FantailVMA)
- **Timeframes**: Adjustable from 1 minute to 1 day candles

## API Endpoints

- `GET /` - Main page with web interface
- `POST /api/start_bot` - Start automated trading
- `POST /api/stop_bot` - Stop automated trading
- `POST /api/force_stop` - Force stop immediately
- `GET /api/status` - Get bot status and signals
- `POST /api/update_settings` - Update trading settings
- `GET /api/balance` - Get account balances
- `GET /api/debug_sell` - Debug sell order issues

## Important Notes

- This bot uses **real money** on the CoinCatch spot market
- Buys use a **percentage** of your USDT balance (configurable)
- Sells **always use 100%** of your SOL balance
- Make sure you have sufficient USDT balance before starting
- All transactions are logged in the console
- Higher timeframes (4H, 1D) = fewer trades and lower fees
- Lower timeframes (1m, 5m) = more trades but higher fees

## Troubleshooting

### "API not configured" error
- Make sure environment variables are set correctly
- Check that variable names are exact: `COINCATCH_API_KEY`, `COINCATCH_API_SECRET`, `COINCATCH_PASSPHRASE`

### "Signature invalid" error
- Verify your API credentials are correct
- Make sure there are no extra spaces in your credentials
- Check that your API key has trade permissions enabled

### "Insufficient balance" error
- You need sufficient USDT in your spot account to make a purchase
- Check your trade percentage setting

### Bot not executing trades
- Verify that 2 out of 3 indicators are giving the same signal
- Check the current position - bot won't buy if already long, or sell if already short
- Review the indicator signals on the dashboard

## Security

- Never commit your API keys to GitHub
- Always use environment variables for credentials
- Consider using Railway's secret management
- Enable IP whitelist on CoinCatch if possible

## Files

- `solana_bot.py` - Main Flask application
- `Simple_SOL.html` - Simple web interface
- `requirements.txt` - Python dependencies
- `Procfile` - Railway deployment configuration
- `README.md` - This file
- `.gitignore` - Git ignore rules

## License

MIT
