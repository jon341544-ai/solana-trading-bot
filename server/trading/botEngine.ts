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
  lastPrice: number;
  solBalance: number;
  usdcBalance: number;
  lastTradeTime: number;
  lastUpdate: Date;
}

const USDC_MINT = "EPjFWaJY3xt5G7j5whEbCVn4wyWEZ1ZLLpmJ5SnCr7T";

export class TradingBotEngine {
  private config: BotConfig;
  private state: BotState;
  private connection: Connection;
  private keypair: Keypair;
  private updateInterval: ReturnType<typeof setInterval> | null = null;
  private minTimeBetweenTrades = 15000; // 15 seconds minimum between trades

  constructor(config: BotConfig) {
    this.config = config;
    this.connection = createConnection(config.rpcUrl);
    this.keypair = createKeypairFromBase58(config.privateKey);

    this.state = {
      isRunning: false,
      lastSignal: null,
      lastPrice: 0,
      solBalance: 0,
      usdcBalance: 0,
      lastTradeTime: 0,
      lastUpdate: new Date(),
    };
  }

  /**
   * Start the trading bot
   */
  public async start(): Promise<void> {
    if (this.state.isRunning) {
      console.log("[Bot] Bot is already running");
      return;
    }

    this.state.isRunning = true;
    await this.addLog("🤖 Bot started", "info");

    // Run update immediately
    await this.update();

    // Then set up interval for subsequent updates
    this.updateInterval = setInterval(() => this.update(), 30000); // Update every 30 seconds
  }

  /**
   * Stop the trading bot
   */
  public async stop(): Promise<void> {
    if (!this.state.isRunning) {
      console.log("[Bot] Bot is not running");
      return;
    }

    this.state.isRunning = false;

    if (this.updateInterval) {
      clearInterval(this.updateInterval);
      this.updateInterval = null;
    }

    await this.addLog("🛑 Bot stopped", "info");
  }

  /**
   * Get current bot status
   */
  public getStatus() {
      return {
        isRunning: this.state.isRunning,
        lastPrice: this.state.lastPrice,
        solBalance: this.state.solBalance,
        usdcBalance: this.state.usdcBalance,
        lastSignal: this.state.lastSignal || null,
        lastUpdate: this.state.lastUpdate,
      };
  }

  /**
   * Main bot update loop
   */
  private async update(): Promise<void> {
    try {
      // Fetch current price with retry logic
      let priceData: PriceData | null = null;
      let priceRetries = 0;

      while (priceRetries < 3 && (!priceData || priceData.price === 0)) {
        try {
          priceData = await fetchSOLPrice();
          if (priceData && priceData.price > 0) {
            this.state.lastPrice = priceData.price;
            await this.addLog(`✅ Price updated: $${this.state.lastPrice.toFixed(2)}`, "info");
            break;
          }
        } catch (error) {
          priceRetries++;
          await this.addLog(`Price fetch attempt ${priceRetries}/3 failed, retrying...`, "warning");
          if (priceRetries < 3) {
            await new Promise((resolve) => setTimeout(resolve, 1000 * priceRetries));
          }
        }
      }

      // If we still don't have price data, use a fallback
      if (!priceData || priceData.price === 0) {
        if (this.state.lastPrice === 0) {
          this.state.lastPrice = 190; // Default SOL price
          await this.addLog(`⚠️ Using default price: $${this.state.lastPrice}`, "warning");
        } else {
          await this.addLog(`⚠️ Using cached price: $${this.state.lastPrice.toFixed(2)}`, "warning");
        }
      }

      // Fetch wallet balances
      try {
        const solBalance = await getWalletBalance(this.connection, this.keypair.publicKey);
        this.state.solBalance = solBalance;
        await this.addLog(`💰 SOL Balance: ${lamportsToSol(solBalance).toFixed(4)} SOL`, "info");
      } catch (error) {
        await this.addLog(`Failed to fetch SOL balance: ${error}`, "warning");
      }

      try {
        const usdcBalance = await getTokenBalance(this.connection, this.keypair.publicKey, USDC_MINT);
        this.state.usdcBalance = usdcBalance;
        await this.addLog(`💵 USDC Balance: ${(usdcBalance / 1e6).toFixed(2)} USDC`, "info");
      } catch (error) {
        await this.addLog(`Failed to fetch USDC balance: ${error}`, "warning");
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
      this.state.lastUpdate = new Date();
    } catch (error) {
      await this.addLog(`❌ Update error: ${error}`, "error");
    }
  }

  /**
   * Execute a trade
   */
  private async executeTrade(
    signal: string,
    price: number,
    superTrendResult: SuperTrendResult
  ): Promise<void> {
    try {
      await this.addLog(`🔄 Executing ${signal} trade: ${this.config.tradeAmountPercent}% of wallet`, "trade");

      // Calculate trade amount
      const tradeAmount = calculateTradeAmount(this.state.solBalance, this.config.tradeAmountPercent);

      if (tradeAmount <= 0) {
        await this.addLog(`❌ Insufficient balance for trade`, "error");
        return;
      }

      const params: TradeParams = {
        inputMint: signal === "buy" ? USDC_MINT : "So11111111111111111111111111111111111111112",
        outputMint: signal === "buy" ? "So11111111111111111111111111111111111111112" : USDC_MINT,
        amount: tradeAmount,
        slippageBps: Math.floor(this.config.slippageTolerance * 100),
      };

      const result = await executeTrade(this.connection, this.keypair, params);

      if (result.status === "success") {
        await this.addLog(
          `✅ ${signal.toUpperCase()} EXECUTED: ${result.inputAmount} → ${result.outputAmount} (TX: ${result.txHash})`,
          "trade"
        );
        await this.storeTrade(signal, price, result);
      } else {
        await this.addLog(
          `❌ ${signal.toUpperCase()} FAILED: ${result.error}`,
          "error"
        );
        await this.storeTrade(signal, price, result);
      }
    } catch (error) {
      await this.addLog(`❌ Trade execution error: ${error}`, "error");
    }
  }

  /**
   * Store market data to database
   */
  private async storeMarketData(price: number, superTrendResult: SuperTrendResult): Promise<void> {
    try {
      const db = await getDb();
      if (!db) return;

      const data: InsertMarketData = {
        id: `md_${Date.now()}_${Math.random()}`,
        close: price.toString(),
        solPrice: price.toString(),
        high: price.toString(),
        low: price.toString(),
        volume: "0",
        superTrendValue: price.toString(),
        trendDirection: "up",
        timestamp: new Date(),
      };

      await db.insert(marketData).values(data);
    } catch (error) {
      console.error("[Bot] Failed to store market data:", error);
    }
  }

  /**
   * Store trade to database
   */
  private async storeTrade(signal: string, price: number, result: TradeResult): Promise<void> {
    try {
      const db = await getDb();
      if (!db) return;

      const trade: InsertTrade = {
        id: `trade_${Date.now()}_${Math.random()}`,
        userId: this.config.userId,
        configId: this.config.configId,
        tradeType: signal as "buy" | "sell",
        tokenIn: signal === "buy" ? USDC_MINT : "So11111111111111111111111111111111111111112",
        tokenOut: signal === "buy" ? "So11111111111111111111111111111111111111112" : USDC_MINT,
        amountIn: result.inputAmount.toString(),
        amountOut: result.outputAmount.toString(),
        priceAtExecution: price.toString(),
        superTrendSignal: signal as "buy" | "sell",
        txHash: result.txHash,
        status: result.status,
      };

      await db.insert(trades).values(trade);
    } catch (error) {
      console.error("[Bot] Failed to store trade:", error);
    }
  }

  /**
   * Add log entry
   */
  private async addLog(message: string, type: string = "info"): Promise<void> {
    try {
      console.log(`[Bot] ${message}`);
      const db = await getDb();
      if (!db) return;

      const log: InsertBotLog = {
        id: `log_${Date.now()}_${Math.random()}`,
        userId: this.config.userId,
        configId: this.config.configId,
        message,
        logType: type as "error" | "success" | "info" | "warning" | "trade",
      };

      await db.insert(botLogs).values(log);
    } catch (error) {
      console.error("[Bot] Failed to add log:", error);
    }
  }
}

