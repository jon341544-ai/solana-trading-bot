# Quick Start Guide - Solana SuperTrend Trading Bot

## 5-Minute Setup

### Step 1: Get Your Private Key
1. Open Phantom Wallet
2. Click Settings → Export Private Key
3. Copy the Base58 format key
4. **Keep this secret!**

### Step 2: Access the Bot
1. Open the bot web interface
2. Click "Sign In with Manus"
3. Authenticate with your Manus account

### Step 3: Configure the Bot
1. Go to **Configuration** tab
2. Paste your private key
3. Keep default settings (or adjust):
   - SuperTrend Period: 10
   - Multiplier: 3.0
   - Trade Amount: 50%
   - Slippage: 1.5%
4. Click **Save Configuration**

### Step 4: Start Trading
1. Go to **Control** tab
2. Review the warning ⚠️
3. Click **Start Bot**
4. Monitor the **Logs** tab

## Default Settings Explained

| Parameter | Default | Meaning |
|-----------|---------|---------|
| Period | 10 | Use 10 candles for trend calculation |
| Multiplier | 3.0 | 3× ATR for support/resistance bands |
| Trade Amount | 50% | Use half your wallet per trade |
| Slippage | 1.5% | Accept up to 1.5% price impact |

## What Happens Next

1. **Bot starts monitoring** SOL/USD price every 30 seconds
2. **Calculates SuperTrend** based on market data
3. **Detects trend changes** (buy/sell signals)
4. **Executes trades** automatically if enabled
5. **Logs all activity** for your review

## Real Example

```
[19:30:00] 🤖 Bot started
[19:30:15] 📊 Market data updated: SOL/USD = $142.50
[19:30:45] 📈 SuperTrend Signal: BUY at $142.50
[19:30:46] ✅ BUY signal executed: 0.3521 SOL
[19:31:00] 💰 Wallet balance: 1.2450 SOL
```

## Monitoring Your Bot

### Check These Regularly
- **Status**: Is it running? (green = yes)
- **Balance**: How much SOL do you have?
- **Logs**: Any errors or warnings?
- **Trades**: How many trades executed?

### View Trade History
1. Go to **Trades** tab
2. See all executed trades with:
   - Buy/Sell type
   - Amount traded
   - Price at execution
   - Status (success/failed)
   - Exact timestamp

## Safety Checklist

- [ ] Tested with small amount (0.1 SOL)
- [ ] Monitored for at least 1 hour
- [ ] Reviewed all logs for errors
- [ ] Understand the risks
- [ ] Have backup funds
- [ ] Know how to stop the bot

## Troubleshooting

### Bot won't start?
- Check private key is correct
- Ensure wallet has SOL for fees
- Check internet connection

### No trades executing?
- Check "Enable Automatic Trading" is ON
- Review logs for signals
- Increase multiplier for more signals

### Trades failing?
- Increase slippage tolerance
- Reduce trade amount percentage
- Check wallet balance

## Next Steps

1. **Read Full Guide**: See `TRADING_BOT_GUIDE.md` for detailed information
2. **Optimize Settings**: Adjust parameters based on market conditions
3. **Monitor Performance**: Track win rate and profit
4. **Scale Up**: Increase trade amount as you gain confidence

## Important Warnings

⚠️ **This bot trades with REAL money**
- Start with small amounts only
- Only invest what you can afford to lose
- Past performance ≠ future results
- Cryptocurrency is volatile
- Always keep emergency reserves

## Key Keyboard Shortcuts

- **Stop Bot**: Click ⏹️ button immediately
- **View Logs**: Click **Logs** tab
- **Check Balance**: Look at Bot Status card
- **Save Settings**: Click **Save Configuration**

## Support

If something goes wrong:
1. Check the **Logs** tab for error messages
2. Stop the bot with ⏹️ button
3. Review the full guide: `TRADING_BOT_GUIDE.md`
4. Verify your configuration settings

---

**Ready to trade?** Go to the Configuration tab and get started! 🚀

Remember: Start small, monitor closely, scale gradually.

