# Solana Trading Bot

RSI-based automated trading bot for Solana (SOL) on CoinCatch exchange with profit protection.

## Features

- ✅ RSI-only trading strategy
- ✅ Profit protection (never sells at a loss)
- ✅ Configurable profit targets
- ✅ RSI cycle tracking
- ✅ Manual trading controls
- ✅ Real-time profit dashboard
- ✅ Trade history tracking

## Deployment on Railway

### Prerequisites

1. CoinCatch account with API credentials
2. GitHub account
3. Railway account

### Setup Instructions

1. **Fork/Clone this repository**

2. **Set up Railway project:**
   - Go to [Railway.app](https://railway.app)
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose this repository

3. **Configure Environment Variables in Railway:**
   
   Go to your Railway project → Variables tab and add:
   
   ```
   COINCATCH_API_KEY=your_api_key_here
   COINCATCH_API_SECRET=your_api_secret_here
   COINCATCH_PASSPHRASE=your_passphrase_here
   PORT=5000
   ```

4. **Deploy:**
   - Railway will automatically detect the Procfile and deploy
   - Wait for deployment to complete
   - Access your bot via the generated Railway URL

## Configuration

### Trading Parameters

- **Trade Type:** Percentage or Fixed amount
- **Trade Percentage:** 1-100% of available USDT (for buys)
- **Fixed SOL Amount:** 0.01-1000 SOL per trade
- **Profit Target:** 0.1-50% profit before selling
- **Check Interval:** How often to check signals (minimum 60 seconds)
- **Timeframe:** Candle timeframe for RSI calculation (1m, 5m, 15m, 30m, 1H, 4H, 1D)

### RSI Settings

- **Period:** 6-30 (default: 14)
- **Oversold:** 10-40 (default: 30)
- **Overbought:** 60-90 (default: 70)

## Important Notes

⚠️ **Sell Behavior:** The bot ALWAYS sells 100% of your SOL balance when a sell signal triggers or profit target is reached.

⚠️ **Profit Protection:** The bot will never sell at a loss. It will only sell when:
1. Profit target is reached, OR
2. RSI sell signal occurs AND current price is at or above break-even

⚠️ **API Permissions:** Ensure your CoinCatch API key has trading permissions enabled.

## Project Structure

```
.
├── solana_bot.py          # Main Flask application
├── templates/
│   └── index.html         # Web interface
├── requirements.txt       # Python dependencies
├── Procfile              # Railway deployment config
├── runtime.txt           # Python version
├── railway.json          # Railway settings (optional)
├── .gitignore            # Git ignore rules
└── README.md             # This file
```

## Local Development

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables:**
   ```bash
   export COINCATCH_API_KEY="your_key"
   export COINCATCH_API_SECRET="your_secret"
   export COINCATCH_PASSPHRASE="your_passphrase"
   ```

3. **Run the bot:**
   ```bash
   python solana_bot.py
   ```

4. **Access the interface:**
   Open http://localhost:5000 in your browser

## Monitoring

- View real-time status in the web interface
- Check Railway logs for detailed trading activity
- Monitor profit dashboard for performance metrics

## Security

- Never commit API credentials to Git
- Always use environment variables for sensitive data
- Enable 2FA on your CoinCatch account
- Use API key IP restrictions if available

## Disclaimer

This bot is for educational purposes. Cryptocurrency trading carries significant risk. Only trade with money you can afford to lose. Past performance does not guarantee future results.

## License

MIT License - Use at your own risk
