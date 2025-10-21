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
  executeTrade,
  simulateTrade,
  calculateTradeAmount,
  validateTradeParams,
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
  balance: number;
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
      // Fetch current price with retry logic
      let priceData: PriceData | null = null;
      let priceRetries = 0;
      while (priceRetries < 3) {
        try {
          priceData = await fetchSOLPrice();
          break;
        } catch (error) {
          priceRetries++;
          if (priceRetries >= 3) {
            await this.addLog(`Warning: Failed to fetch price after 3 attempts: ${error}`, "warning");
            return; // Skip this update cycle
          }
          await this.addLog(`Retrying price fetch (attempt ${priceRetries}/3)...`, "info");
          await new Promise((resolve) => setTimeout(resolve, 2000 * priceRetries));
        }
      }
      if (!priceData) {
        await this.addLog("Error: Could not fetch price data", "error");
        return;
      }
      this.state.lastPrice = priceData.price;

      // Fetch historical data for SuperTrend calculation
      let candles: OHLCV[];
      try {
        candles = await fetchHistoricalOHLCV(30, "daily");
      } catch (error) {
        // Fallback to simulated data if API fails
        await this.addLog("⚠️ Using simulated market data", "warning");
        candles = generateSimulatedOHLCV(priceData.price, 50);
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
      await this.storeMarketData(priceData.price, currentSignal);

      // Detect trend change
      const signal = detectTrendChange(this.state.lastSignal, currentSignal);

      if (signal) {
        await this.addLog(
          `📊 SuperTrend Signal: ${signal.toUpperCase()} at $${priceData.price.toFixed(2)}`,
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
          await this.executeTrade(signal, priceData.price, currentSignal);
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
      // Update balance
      let balance: number;
      try {
        balance = await getWalletBalance(this.connection, this.keypair.publicKey);
        this.state.balance = balance;
      } catch (error) {
        await this.addLog(`⚠️ Failed to fetch balance, using cached: ${lamportsToSol(this.state.balance).toFixed(4)} SOL`, "warning");
        balance = this.state.balance;
      }

      // Calculate trade amount (50% of wallet)
      const tradeAmount = calculateTradeAmount(balance, this.config.tradeAmountPercent);

      if (tradeAmount < 1000) {
        await this.addLog(`⚠️ Trade amount too small: ${lamportsToSol(tradeAmount).toFixed(4)} SOL`, "warning");
        return;
      }

      if (balance < tradeAmount + 5000000) { // 0.005 SOL for fees
        await this.addLog(`⚠️ Insufficient balance for trade. Need: ${lamportsToSol(tradeAmount + 5000000).toFixed(4)} SOL, Have: ${lamportsToSol(balance).toFixed(4)} SOL`, "warning");
        return;
      }

      let result: TradeResult;

      if (signal === "buy") {
        // Buy SOL with USDC - REAL ON-CHAIN EXECUTION
        await this.addLog(`🔄 Executing BUY trade: ${lamportsToSol(tradeAmount).toFixed(4)} SOL worth of USDC`, "trade");
        
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
          await this.addLog(`✅ BUY EXECUTED: ${lamportsToSol(result.outputAmount).toFixed(4)} SOL | TX: ${result.txHash.slice(0, 20)}...`, "success");
        } else {
          await this.addLog(`❌ BUY FAILED: ${result.error}`, "error");
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
          await this.addLog(`✅ SELL EXECUTED: ${lamportsToSol(result.inputAmount).toFixed(4)} SOL | TX: ${result.txHash.slice(0, 20)}...`, "success");
        } else {
          await this.addLog(`❌ SELL FAILED: ${result.error}`, "error");
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
      lastPrice: this.state.lastPrice,
      lastSignal: this.state.lastSignal,
      lastTradeTime: new Date(this.state.lastTradeTime),
    };
  }
}

