/**
 * Trading Bot Engine
 * 
 * Orchestrates the entire trading workflow:
 * 1. Fetch market data
 * 2. Calculate SuperTrend indicators
 * 3. Generate buy/sell signals
 * 4. Execute trades
 * 5. Log activity
 */

import { Connection, Keypair, PublicKey } from "@solana/web3.js";
import { calculateSuperTrend, detectTrendChange, getLatestSuperTrendSignal, SuperTrendResult, OHLCV } from "./supertrend";
import {
  fetchSOLPrice,
  fetchHistoricalOHLCV,
  generateSimulatedOHLCV,
  solToLamports,
  lamportsToSol,
  PriceData,
} from "./marketData";
import {
  createConnection,
  createKeypairFromBase58,
  getWalletBalance,
  getTokenBalance,
  executeTrade,
  calculateTradeAmount,
  TradeParams,
  TradeResult,
} from "./solanaTrading";
import { getDb } from "../db";
import { trades, marketData, botLogs, InsertTrade, InsertMarketData, InsertBotLog } from "../../drizzle/schema";

export interface BotConfig {
  userId: string;
  configId: string;
  privateKey: string;
  rpcUrl: string;
  walletAddress: string;
  period: number;
  multiplier: number;
  tradeAmountPercent: number;
  slippageTolerance: number;
  autoTrade: boolean;
}

export interface BotState {
  isRunning: boolean;
  lastSignal: SuperTrendResult | null;
  lastTradeTime: number;
  balance: number; // SOL balance in lamports
  usdcBalance: number; // USDC balance in smallest units
  lastPrice: number;
}

export class TradingBotEngine {
  private config: BotConfig;
  private state: BotState;
  private connection: Connection;
  private keypair: Keypair;
  private updateInterval: ReturnType<typeof setInterval> | null = null;
  private minTimeBetweenTrades: number = 15000; // 15 seconds minimum between trades (reduced for more frequent trading)

  constructor(config: BotConfig) {
    this.config = config;
    this.connection = createConnection(config.rpcUrl);
    this.keypair = createKeypairFromBase58(config.privateKey);
    this.state = {
      isRunning: false,
      lastSignal: null,
      lastTradeTime: 0,
      balance: 0,
      usdcBalance: 0,
      lastPrice: 0,
    };
  }

  /**
   * Start the bot
   */
  async start(): Promise<void> {
    if (this.state.isRunning) {
      await this.addLog("Bot is already running", "warning");
      return;
    }

    this.state.isRunning = true;
    await this.addLog("🤖 Bot started", "success");

    try {
      // Update balance
      const balance = await getWalletBalance(this.connection, this.keypair.publicKey);
      this.state.balance = balance;
      await this.addLog(`💰 Wallet balance: ${lamportsToSol(balance).toFixed(4)} SOL`, "info");

      // Start the trading loop
      this.updateInterval = setInterval(() => {
        this.update().catch((error) => {
          console.error("Error in bot update:", error);
        });
      }, 30000); // Update every 30 seconds

      // Run first update immediately
      await this.update();
    } catch (error) {
      this.state.isRunning = false;
      await this.addLog(`❌ Failed to start bot: ${error}`, "error");
      throw error;
    }
  }

  /**
   * Stop the bot
   */
  async stop(): Promise<void> {
    if (!this.state.isRunning) {
      await this.addLog("Bot is not running", "warning");
      return;
    }

    this.state.isRunning = false;

    if (this.updateInterval) {
      clearInterval(this.updateInterval);
      this.updateInterval = null;
    }

    await this.addLog("🛑 Bot stopped", "error");
  }

  /**
   * Main bot update loop
   */
  private async update(): Promise<void> {
    try {
      // Fetch current price with retry logic and fallback
      let priceData: PriceData | null = null;
      let priceRetries = 0;
      
      while (priceRetries < 3) {
        try {
          priceData = await fetchSOLPrice();
          if (priceData && priceData.price > 0) {
            this.state.lastPrice = priceData.price;
            break;
          }
        } catch (error) {
          priceRetries++;
          if (priceRetries < 3) {
            await this.addLog(`Retrying price fetch (attempt ${priceRetries}/3)...`, "info");
            await new Promise((resolve) => setTimeout(resolve, 2000 * priceRetries));
          }
        }
      }
      
      // If we still don't have price data, use a fallback
      if (!priceData || priceData.price === 0) {
        await this.addLog(`Warning: Could not fetch live price, using cached price: $${this.state.lastPrice.toFixed(2)}`, "warning");
        // Continue with cached price instead of returning
        if (this.state.lastPrice === 0) {
          // Use a reasonable default if we have no price at all
          this.state.lastPrice = 190; // Default SOL price
        }
      } else {
        await this.addLog(`✅ Price updated: $${this.state.lastPrice.toFixed(2)}`, "info");
      }

      // Fetch current balances (SOL and USDC) every update
      try {
        const solBalance = await getWalletBalance(this.connection, this.keypair.publicKey);
        this.state.balance = solBalance;
        
        const usdcBalance = await getTokenBalance(this.connection, this.keypair.publicKey, "EPjFWaJY3xt5G7j5whEbCVn4wyWEZ1ZLLpmJ5SnCr7T");
        this.state.usdcBalance = usdcBalance;
      } catch (error) {
        // Silently fail - use cached balances
      }

      // Fetch historical data for SuperTrend calculation
      let candles: OHLCV[];
      const currentPrice = this.state.lastPrice;
      try {
        candles = await fetchHistoricalOHLCV(30, "daily");
      } catch (error) {
        // Fallback to simulated data if API fails
        await this.addLog("⚠️ Using simulated market data", "warning");
        candles = generateSimulatedOHLCV(currentPrice, 50);
      }

      // Calculate SuperTrend
      const superTrendResults = calculateSuperTrend(
        candles,
        this.config.period,
        this.config.multiplier
      );

      const currentSignal = superTrendResults[superTrendResults.length - 1];
      const previousSignal = superTrendResults.length > 1 ? superTrendResults[superTrendResults.length - 2] : null;

      // Store market data
      await this.storeMarketData(currentPrice, currentSignal);

      // Detect trend change
      const signal = detectTrendChange(this.state.lastSignal, currentSignal);

      if (signal) {
        await this.addLog(
          `📊 SuperTrend Signal: ${signal.toUpperCase()} at $${currentPrice.toFixed(2)}`,
          "trade"
        );

        // Check if enough time has passed since last trade
        const timeSinceLastTrade = Date.now() - this.state.lastTradeTime;
        if (timeSinceLastTrade < this.minTimeBetweenTrades) {
          await this.addLog(
            `⏳ Waiting ${Math.ceil((this.minTimeBetweenTrades - timeSinceLastTrade) / 1000)}s before next trade`,
            "info"
          );
        } else if (this.config.autoTrade) {
          // Execute trade
          await this.executeTrade(signal, currentPrice, currentSignal);
          this.state.lastTradeTime = Date.now();
        } else {
          await this.addLog(`🔔 Trade signal detected but auto-trade is disabled`, "info");
        }
      }

      this.state.lastSignal = currentSignal;
    } catch (error) {
      await this.addLog(`❌ Update error: ${error}`, "error");
    }
  }

  /**
   * Execute a trade
   */
  private async executeTrade(
    signal: "buy" | "sell",
    price: number,
    superTrendSignal: SuperTrendResult
  ): Promise<void> {
    try {
      // Update SOL and USDC balances
      let balance: number;
      let usdcBalance: number;
      try {
        balance = await getWalletBalance(this.connection, this.keypair.publicKey);
        usdcBalance = await getTokenBalance(this.connection, this.keypair.publicKey, "EPjFWaJY3xt5G7j5whEbCVn4wyWEZ1ZLLpmJ5SnCr7T");
        this.state.balance = balance;
        this.state.usdcBalance = usdcBalance;
      } catch (error) {
        await this.addLog(`⚠️ Failed to fetch balances, using cached`, "warning");
        balance = this.state.balance;
        usdcBalance = this.state.usdcBalance;
      }
      
      await this.addLog(`💰 Wallet: ${lamportsToSol(balance).toFixed(4)} SOL, ${(usdcBalance / 1e6).toFixed(2)} USDC`, "info");

      // Calculate trade amount based on signal type
      let tradeAmount: number;
      let insufficientBalance = false;
      let balanceErrorMsg = "";

      if (signal === "buy") {
        // For BUY: use 50% of USDC balance
        // If no USDC, convert 50% of SOL to USDC first
        if (usdcBalance === 0 && balance > solToLamports(0.01)) {
          await this.addLog(`🔄 No USDC found. Converting 50% of SOL to USDC...`, "info");
          const solToConvert = calculateTradeAmount(balance, this.config.tradeAmountPercent);
          
          try {
            const conversionResult = await executeTrade(
              this.connection,
              this.keypair,
              {
                inputMint: "So11111111111111111111111111111111111111112",
                outputMint: "EPjFWaJY3xt5G7j5whEbCVn4wyWEZ1ZLLpmJ5SnCr7T",
                amount: solToConvert,
                slippageBps: Math.floor(this.config.slippageTolerance * 100),
              }
            );
            
            if (conversionResult.status === "success") {
              await this.addLog(`✅ Converted ${lamportsToSol(solToConvert).toFixed(4)} SOL to ${(conversionResult.outputAmount / 1e6).toFixed(2)} USDC`, "success");
              usdcBalance = conversionResult.outputAmount;
              this.state.usdcBalance = usdcBalance;
            } else {
              await this.addLog(`❌ Failed to convert SOL to USDC: ${conversionResult.error}`, "error");
              return;
            }
          } catch (error) {
            await this.addLog(`❌ Conversion error: ${error}`, "error");
            return;
          }
        }
        
        tradeAmount = Math.floor((usdcBalance * this.config.tradeAmountPercent) / 100);
        
        if (tradeAmount < 1000) {
          await this.addLog(`⚠️ USDC balance too small to trade: ${(usdcBalance / 1e6).toFixed(2)} USDC`, "warning");
          return;
        }
        
        if (usdcBalance < tradeAmount) {
          insufficientBalance = true;
          balanceErrorMsg = `Insufficient USDC balance. Need: ${(tradeAmount / 1e6).toFixed(2)} USDC, Have: ${(usdcBalance / 1e6).toFixed(2)} USDC`;
        }
      } else {
        // For SELL: use 50% of SOL balance
        tradeAmount = calculateTradeAmount(balance, this.config.tradeAmountPercent);
        
        if (tradeAmount < 1000) {
          await this.addLog(`⚠️ SOL balance too small to trade: ${lamportsToSol(tradeAmount).toFixed(4)} SOL`, "warning");
          return;
        }
        
        if (balance < tradeAmount + 5000000) { // 0.005 SOL for fees
          insufficientBalance = true;
          balanceErrorMsg = `Insufficient SOL balance. Need: ${lamportsToSol(tradeAmount + 5000000).toFixed(4)} SOL, Have: ${lamportsToSol(balance).toFixed(4)} SOL`;
        }
      }

      if (insufficientBalance) {
        await this.addLog(`⚠️ ${balanceErrorMsg}`, "warning");
        return;
      }

      let result: TradeResult;

      if (signal === "buy") {
        // Buy SOL with USDC - REAL ON-CHAIN EXECUTION
        await this.addLog(`🔄 Executing BUY trade: Spending ${(tradeAmount / 1e6).toFixed(2)} USDC to buy SOL`, "trade");
        
        result = await executeTrade(
          this.connection,
          this.keypair,
          {
            inputMint: "EPjFWaJY3xt5G7j5whEbCVn4wyWEZ1ZLLpmJ5SnCr7T", // USDC
            outputMint: "So11111111111111111111111111111111111111112", // SOL
            amount: tradeAmount,
            slippageBps: Math.floor(this.config.slippageTolerance * 100),
          }
        );

        if (result.status === "success") {
          await this.addLog(`✅ BUY EXECUTED: Spent ${(result.inputAmount / 1e6).toFixed(2)} USDC, Received ${lamportsToSol(result.outputAmount).toFixed(4)} SOL | TX: ${result.txHash.slice(0, 20)}...`, "success");
        } else {
          await this.addLog(`❌ BUY FAILED: ${result.error}`, "error");
          // Retry logic is handled in executeTrade, but log the failure
          await this.addLog(`💡 Tip: Check network connectivity. Bot will retry on next signal.`, "info");
        }
      } else {
        // Sell SOL for USDC - REAL ON-CHAIN EXECUTION
        await this.addLog(`🔄 Executing SELL trade: ${lamportsToSol(tradeAmount).toFixed(4)} SOL`, "trade");
        
        result = await executeTrade(
          this.connection,
          this.keypair,
          {
            inputMint: "So11111111111111111111111111111111111111112", // SOL
            outputMint: "EPjFWaJY3xt5G7j5whEbCVn4wyWEZ1ZLLpmJ5SnCr7T", // USDC
            amount: tradeAmount,
            slippageBps: Math.floor(this.config.slippageTolerance * 100),
          }
        );

        if (result.status === "success") {
          await this.addLog(`✅ SELL EXECUTED: ${lamportsToSol(result.inputAmount).toFixed(4)} SOL -> ${lamportsToSol(result.outputAmount).toFixed(4)} USDC | TX: ${result.txHash.slice(0, 20)}...`, "success");
        } else {
          await this.addLog(`❌ SELL FAILED: ${result.error}`, "error");
          // Retry logic is handled in executeTrade, but log the failure
          await this.addLog(`💡 Tip: Check network connectivity. Bot will retry on next signal.`, "info");
        }
      }

      // Store trade in database
      await this.storeTrade(signal, result, price, superTrendSignal);
    } catch (error) {
      await this.addLog(`❌ Trade execution failed: ${error}`, "error");
    }
  }

  /**
   * Store market data in database
   */
  private async storeMarketData(price: number, signal: SuperTrendResult): Promise<void> {
    try {
      const db = await getDb();
      if (!db) return;

      const data: InsertMarketData = {
        id: `md_${Date.now()}_${Math.random().toString(36).substring(7)}`,
        timestamp: new Date(),
        solPrice: price.toString(),
        high: signal.upperBand.toString(),
        low: signal.lowerBand.toString(),
        close: price.toString(),
        volume: "0",
        superTrendValue: signal.value.toString(),
        trendDirection: signal.direction,
      };

      await db.insert(marketData).values(data);
    } catch (error) {
      console.error("Failed to store market data:", error);
    }
  }

  /**
   * Store trade in database
   */
  private async storeTrade(
    signal: "buy" | "sell",
    result: TradeResult,
    price: number,
    superTrendSignal: SuperTrendResult
  ): Promise<void> {
    try {
      const db = await getDb();
      if (!db) return;

      const trade: InsertTrade = {
        id: `trade_${Date.now()}_${Math.random().toString(36).substring(7)}`,
        userId: this.config.userId,
        configId: this.config.configId,
        tradeType: signal,
        tokenIn: signal === "buy" ? "USDC" : "SOL",
        tokenOut: signal === "buy" ? "SOL" : "USDC",
        amountIn: result.inputAmount.toString(),
        amountOut: result.outputAmount.toString(),
        priceAtExecution: price.toString(),
        superTrendSignal: signal,
        superTrendValue: superTrendSignal.value.toString(),
        txHash: result.txHash,
        status: result.status === "success" ? "success" : "failed",
      };

      await db.insert(trades).values(trade);
    } catch (error) {
      console.error("Failed to store trade:", error);
    }
  }

  /**
   * Add log entry
   */
  private async addLog(message: string, type: "info" | "success" | "error" | "warning" | "trade"): Promise<void> {
    try {
      const db = await getDb();
      if (!db) {
        console.log(`[${type}] ${message}`);
        return;
      }

      const log: InsertBotLog = {
        id: `log_${Date.now()}_${Math.random().toString(36).substring(7)}`,
        userId: this.config.userId,
        configId: this.config.configId,
        logType: type,
        message,
      };

      await db.insert(botLogs).values(log);
    } catch (error) {
      console.error("Failed to store log:", error);
    }
  }

  /**
   * Get bot status
   */
  getStatus() {
    return {
      isRunning: this.state.isRunning,
      balance: lamportsToSol(this.state.balance),
      usdcBalance: this.state.usdcBalance / 1e6, // Convert to USDC (6 decimals)
      currentPrice: this.state.lastPrice,
      lastSignal: this.state.lastSignal,
      lastTradeTime: new Date(this.state.lastTradeTime),
      trend: this.state.lastSignal?.direction === "up" ? "up" : "down",
    };
  }
}

