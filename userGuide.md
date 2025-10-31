# Solana Trading Bot - User Guide

**Website:** https://solana-trading-bot-production-1fc4.up.railway.app

**Purpose:** Automated SOL/USDC trading bot that monitors market trends using SuperTrend, MACD, and Bixord FVMA indicators to execute trades on the Hyperliquid exchange.

**Access:** Public - No login required

---

## Powered by Manus

**Technology Stack:**
- **Frontend:** React 19 + TypeScript + Tailwind CSS 4 + shadcn/ui components
- **Backend:** Node.js + Express + tRPC 11 + Drizzle ORM
- **Database:** MySQL with Drizzle migrations
- **Trading:** Hyperliquid Spot Trading API with multi-indicator strategy
- **Deployment:** Railway with auto-scaling infrastructure and global CDN

The bot combines three technical indicators (SuperTrend, MACD, and Bixord FVMA) to generate high-confidence trading signals, executing real trades on the Hyperliquid exchange with professional-grade reliability.

---

## Using Your Website

### 1. **Monitor Bot Status**
The dashboard displays your bot's current state at a glance:
- **Status Indicator:** Shows "Running" (green) or "Stopped" (red)
- **SOL Balance:** Your current SOL holdings on Hyperliquid
- **USDC Balance:** Your current USDC holdings for trading
- **Current Price:** Live SOL/USDC price from Hyperliquid
- **Trend:** Current market trend (Up/Down) based on indicators

### 2. **Control the Trading Bot**
In the "Control" tab, you have two main controls:

**Start Bot:** Click "Start Bot" to begin automated trading. The bot will monitor market indicators and execute trades automatically based on your configured strategy.

**Stop Bot:** Click "Stop Bot" to halt all automated trading. The bot will stop checking for signals and won't execute new trades.

### 3. **Test Transactions**
Before running the bot with real funds, test the trading mechanism:

1. Enter a test amount in "Test Amount (SOL)" field (e.g., 0.1 SOL)
2. Click "Test BUY" to simulate a buy order (USDC → SOL)
3. Click "Test SELL" to simulate a sell order (SOL → USDC)

Test transactions execute real orders on Hyperliquid at current market prices. Use small amounts to verify the bot can execute trades successfully before enabling automated trading.

### 4. **View Trading Activity**
The "Logs" tab shows real-time activity:
- **Recent Logs:** Shows the most recent bot actions and trade executions
- **Auto-Refresh:** Logs update every 3 seconds to show live activity
- **Trade History:** Detailed record of all executed trades with prices and amounts

---

## Managing Your Website

### Dashboard Panel
Access via the "View" button on the project card to see a live preview of your bot's current state.

### Settings Panel
Configure your bot's behavior:
- **General:** Update website name and logo (VITE_APP_TITLE, VITE_APP_LOGO)
- **Secrets:** Store your Hyperliquid credentials securely
  - `HYPERLIQUID_PRIVATE_KEY`: Your Hyperliquid account private key
  - `HYPERLIQUID_WALLET_ADDRESS`: Your Hyperliquid wallet address

### Database Panel
View and manage your trading data:
- **Trades Table:** All executed trades with timestamps and amounts
- **Logs Table:** Complete activity log for debugging and monitoring

---

## Next Steps

**Talk to Manus AI anytime to request changes or add features.** You can ask to:
- Adjust trading parameters (indicator periods, signal thresholds)
- Add new indicators or modify the trading strategy
- Change the update frequency or trade execution timing
- Add email/SMS notifications for trades
- Export trading history and performance reports

**Ready to trade?** Start by clicking "Start Bot" to begin automated trading on Hyperliquid. Monitor the logs to ensure the bot is detecting signals and executing trades correctly. Use test transactions first if you want to verify everything works before enabling live trading.

---

## Production Readiness

Your bot is configured to use environment variables for all sensitive credentials. Before going live:

1. **Hyperliquid Credentials:** Ensure `HYPERLIQUID_PRIVATE_KEY` and `HYPERLIQUID_WALLET_ADDRESS` are set in Settings → Secrets
2. **Database:** Verify MySQL connection is working (check in Database panel)
3. **Test First:** Run test transactions to confirm connectivity before enabling automated trading

The bot is production-ready and deployed on Railway with auto-scaling infrastructure. All trades execute on the live Hyperliquid mainnet.

