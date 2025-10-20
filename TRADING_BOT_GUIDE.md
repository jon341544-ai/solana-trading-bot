# Solana SuperTrend Trading Bot - Complete Guide

## Overview

The Solana SuperTrend Trading Bot is a full-stack automated trading application that uses the SuperTrend technical indicator to generate buy and sell signals for SOL/USDC trading pairs on the Solana blockchain. The bot continuously monitors market data, calculates SuperTrend values, and executes trades based on trend changes.

## Features

- **SuperTrend Indicator**: Automated calculation of SuperTrend values using Average True Range (ATR)
- **Real-time Market Data**: Fetches live SOL/USD prices from CoinGecko API
- **Automated Trading**: Executes buy/sell orders on Solana blockchain via Jupiter DEX aggregator
- **Risk Management**: Configurable trade amount (default 50% of wallet), slippage tolerance, and position sizing
- **Activity Logging**: Comprehensive logs of all bot actions and trades
- **Trade History**: Complete record of all executed trades with timestamps and prices
- **Web Dashboard**: User-friendly interface for configuration, monitoring, and control

## Architecture

### Backend Components

The backend is built with Node.js, Express, and tRPC and includes:

- **SuperTrend Calculator** (`server/trading/supertrend.ts`): Implements the SuperTrend indicator algorithm with ATR calculation
- **Market Data Fetcher** (`server/trading/marketData.ts`): Fetches real-time and historical OHLCV data
- **Solana Trading Module** (`server/trading/solanaTrading.ts`): Handles blockchain interactions and trade execution
- **Bot Engine** (`server/trading/botEngine.ts`): Orchestrates the entire trading workflow
- **Database Layer** (`server/db.ts`): Manages configuration, logs, and trade history

### Frontend Components

The frontend is built with React and includes:

- **Configuration Panel**: Set up trading parameters and Solana wallet
- **Bot Control**: Start/stop the trading bot with safety warnings
- **Status Dashboard**: Real-time display of bot status, balance, and current price
- **Activity Log**: Stream of bot actions and trading signals
- **Trade History**: Table of all executed trades

### Database Schema

The application uses MySQL with the following tables:

- `trading_configs`: User trading settings and wallet information
- `market_data`: Historical price data and SuperTrend values
- `trades`: Complete record of all trades executed
- `bot_logs`: Activity logs for debugging and monitoring

## Installation & Setup

### Prerequisites

- Node.js 18+ and pnpm
- Solana wallet with SOL and USDC for trading
- Private key in Base58 format (from Phantom or other Solana wallets)
- MySQL database (provided by Manus platform)

### Initial Setup

1. **Clone and Install**
   ```bash
   cd /home/ubuntu/solana-trading-bot
   pnpm install
   ```

2. **Configure Environment**
   The application uses environment variables automatically injected by the Manus platform:
   - `DATABASE_URL`: MySQL connection string
   - `JWT_SECRET`: Session signing key
   - `VITE_APP_ID`: OAuth application ID
   - `OAUTH_SERVER_URL`: OAuth server endpoint

3. **Start Development Server**
   ```bash
   pnpm dev
   ```

4. **Access the Application**
   Open your browser and navigate to the provided development URL

## Configuration Guide

### Trading Parameters

**SuperTrend Period** (Default: 10)
- Number of candles used for ATR calculation
- Lower values (5-10) respond faster to price changes
- Higher values (20-50) filter out noise but lag behind trends
- Recommended: 10-20 for SOL/USDC

**Multiplier** (Default: 3.0)
- Multiplier applied to ATR for band calculation
- Controls the distance of support/resistance bands
- Higher values = wider bands, fewer signals
- Lower values = tighter bands, more signals
- Recommended: 2.5-3.5

**Trade Amount** (Default: 50%)
- Percentage of wallet to use per trade
- Conservative: 25-30%
- Moderate: 40-50%
- Aggressive: 60-75%
- **Never use 100%** - always keep reserves

**Slippage Tolerance** (Default: 1.5%)
- Maximum acceptable price impact on trades
- Higher values = more likely to execute, worse prices
- Lower values = better prices, may fail to execute
- Recommended: 1.0-2.0% for SOL/USDC

**RPC URL** (Default: Mainnet)
- Solana RPC endpoint for blockchain interaction
- Mainnet: `https://api.mainnet-beta.solana.com`
- Devnet (testing): `https://api.devnet.solana.com`

### Wallet Setup

1. Export your private key from Phantom:
   - Click settings → Export private key
   - Copy the Base58 format key
   - **Never share this key with anyone**

2. Paste into the bot configuration
   - The key is stored securely and never transmitted
   - Only used for signing transactions locally

3. Ensure wallet has sufficient balance:
   - Minimum 0.1 SOL for transaction fees
   - Additional SOL/USDC for trading

## How the Bot Works

### Trading Cycle

1. **Fetch Market Data** (Every 30 seconds)
   - Retrieves current SOL/USD price
   - Fetches 30 days of historical OHLCV data
   - Falls back to simulated data if API fails

2. **Calculate SuperTrend**
   - Computes ATR (Average True Range) from historical data
   - Calculates upper and lower bands
   - Determines current trend direction (up/down)

3. **Detect Signals**
   - Compares current trend to previous trend
   - Buy signal: Trend changes from down to up
   - Sell signal: Trend changes from up to down

4. **Execute Trade** (If auto-trade enabled)
   - Validates trade parameters
   - Calculates trade amount (50% of wallet)
   - Submits transaction to Solana blockchain
   - Logs result in database

5. **Update Status**
   - Refreshes wallet balance
   - Stores market data in database
   - Updates logs and trade history

### SuperTrend Indicator Explained

The SuperTrend indicator is a trend-following tool that uses Average True Range (ATR) to create dynamic support and resistance levels:

**True Range (TR)** = Maximum of:
- High - Low
- |High - Previous Close|
- |Low - Previous Close|

**Average True Range (ATR)** = SMA of TR over N periods

**SuperTrend Bands**:
- Upper Band = HL2 + (Multiplier × ATR)
- Lower Band = HL2 - (Multiplier × ATR)

Where HL2 = (High + Low) / 2

**Trend Direction**:
- **Uptrend**: Price closes above lower band
- **Downtrend**: Price closes below upper band

## Safety Features

### Built-in Protections

1. **Minimum Time Between Trades**: 1 minute to prevent rapid-fire trades
2. **Balance Validation**: Checks sufficient balance before trading
3. **Amount Validation**: Ensures trade amount meets minimum thresholds
4. **Slippage Limits**: Enforces maximum acceptable price impact
5. **Error Handling**: Gracefully handles network failures and API errors

### Risk Management Best Practices

1. **Start Small**
   - Begin with 0.1-0.5 SOL wallet
   - Use 25-30% trade amount
   - Monitor for 24-48 hours before increasing

2. **Monitor Actively**
   - Check logs regularly for errors
   - Review trade history for patterns
   - Adjust parameters if needed

3. **Keep Reserves**
   - Never use 100% of wallet
   - Maintain 0.1+ SOL for fees
   - Keep emergency liquidity

4. **Test First**
   - Use Devnet for testing
   - Run in demo mode before real trading
   - Verify all settings before enabling auto-trade

## Troubleshooting

### Bot Won't Start

**Error**: "Trading configuration not found"
- **Solution**: Complete the Configuration tab and save settings

**Error**: "Invalid private key format"
- **Solution**: Ensure private key is in Base58 format from Phantom

**Error**: "Failed to connect to Solana network"
- **Solution**: Check RPC URL is correct and accessible

### No Trades Executing

**Issue**: Bot running but no trades
- Check if auto-trade is enabled in configuration
- Verify sufficient balance in wallet
- Review logs for SuperTrend signals
- Increase multiplier to generate more signals

**Issue**: Trades failing with high slippage
- Reduce trade amount percentage
- Increase slippage tolerance
- Try during less volatile periods

### Database Issues

**Error**: "Database not available"
- **Solution**: Verify DATABASE_URL environment variable is set
- Check MySQL connection string is valid
- Ensure database tables are created (`pnpm db:push`)

## API Reference

### tRPC Procedures

#### `trading.getConfig`
Retrieves current trading configuration
```typescript
const config = await trpc.trading.getConfig.useQuery();
```

#### `trading.updateConfig`
Updates trading configuration
```typescript
await trpc.trading.updateConfig.useMutation({
  period: 15,
  multiplier: 3.5,
  autoTrade: true,
});
```

#### `trading.startBot`
Starts the trading bot
```typescript
await trpc.trading.startBot.useMutation();
```

#### `trading.stopBot`
Stops the trading bot
```typescript
await trpc.trading.stopBot.useMutation();
```

#### `trading.getBotStatus`
Gets current bot status
```typescript
const status = await trpc.trading.getBotStatus.useQuery();
// Returns: { isRunning, balance, lastPrice, lastSignal, lastTradeTime }
```

#### `trading.getLogs`
Retrieves activity logs
```typescript
const logs = await trpc.trading.getLogs.useQuery({ limit: 100 });
```

#### `trading.getTradeHistory`
Retrieves trade history
```typescript
const trades = await trpc.trading.getTradeHistory.useQuery({ limit: 50 });
```

#### `trading.getTradeStats`
Gets trading statistics
```typescript
const stats = await trpc.trading.getTradeStats.useQuery();
// Returns: { totalTrades, buyTrades, sellTrades, successfulTrades, failedTrades }
```

## Performance Optimization

### Database Queries
- Logs are limited to 100 entries by default
- Trade history limited to 50 entries
- Adjust limits based on your needs

### API Calls
- Market data fetched every 30 seconds
- CoinGecko API has rate limits (50 calls/minute free tier)
- Historical data cached to reduce API calls

### Frontend Updates
- Bot status refreshes every 5 seconds
- Logs refresh every 3 seconds
- Trade history refreshes every 10 seconds

## Advanced Configuration

### Custom RPC Providers

For better reliability, use premium RPC providers:

- **Helius**: `https://mainnet.helius-rpc.com/?api-key=YOUR_KEY`
- **QuickNode**: `https://solana-mainnet.quiknode.pro/YOUR_KEY/`
- **Alchemy**: `https://solana-mainnet.g.alchemy.com/v2/YOUR_KEY`

### Multiple Trading Pairs

Currently configured for SOL/USDC. To add other pairs:

1. Update token mint addresses in `solanaTrading.ts`
2. Modify market data fetching for new pairs
3. Adjust SuperTrend parameters for different volatility

### Custom Indicators

To add additional indicators:

1. Create new indicator file in `server/trading/`
2. Implement calculation logic
3. Integrate into `botEngine.ts`
4. Add to database schema if storing results

## Monitoring & Analytics

### Key Metrics to Track

- **Win Rate**: Successful trades / Total trades
- **Profit Factor**: Gross profit / Gross loss
- **Average Trade Duration**: Time between entry and exit
- **Drawdown**: Maximum loss from peak balance
- **Sharpe Ratio**: Risk-adjusted returns

### Log Analysis

Review logs for:
- Frequency of signals
- Success rate of trades
- Network errors or failures
- Balance changes over time

## Security Considerations

1. **Private Key Storage**
   - Never commit private keys to version control
   - Use environment variables for sensitive data
   - Consider using hardware wallets for large amounts

2. **API Keys**
   - Rotate API keys regularly
   - Use separate keys for different environments
   - Monitor API usage for unauthorized access

3. **Network Security**
   - Use HTTPS for all connections
   - Verify RPC endpoint certificates
   - Consider using VPN for additional security

4. **Access Control**
   - Secure database credentials
   - Limit API access to authorized users
   - Use strong passwords and 2FA

## Deployment

### Production Deployment

1. **Environment Setup**
   - Set all required environment variables
   - Configure production database
   - Use production RPC endpoints

2. **Testing**
   - Run on Devnet first
   - Test with small amounts
   - Monitor for 24+ hours

3. **Monitoring**
   - Set up error alerts
   - Monitor bot logs continuously
   - Track performance metrics

4. **Backup & Recovery**
   - Regular database backups
   - Document all configurations
   - Have rollback procedures

## Support & Resources

- **Solana Documentation**: https://docs.solana.com
- **Jupiter API**: https://station.jup.ag/docs/apis/swap-api
- **CoinGecko API**: https://www.coingecko.com/en/api
- **Phantom Wallet**: https://phantom.app

## Disclaimer

**⚠️ IMPORTANT**: This trading bot executes real trades with real money on the Solana blockchain. Trading cryptocurrencies carries significant risk of loss. Past performance does not guarantee future results. Only invest what you can afford to lose. Always test thoroughly before enabling automated trading with real funds.

## License

This project is provided as-is for educational and trading purposes.

---

**Version**: 1.0.0  
**Last Updated**: October 2025  
**Author**: Manus AI

