/**
 * Perpetuals Trading Engine
 * Manages Perps trading with:
 * - Position sizing (50% of account)
 * - 2x leverage
 * - 3.5% stop loss
 * - 12% daily loss limit
 */

import {
  fetchPerpsBalance,
  fetchOpenPositions,
  placePerpsOrder,
  closePosition,
  fetchCurrentPrice,
} from "../hyperliquid/perpsApi";
import { TradingBotEngine, Signal } from "./botEngine";

export interface PerpsTradingConfig {
  walletAddress: string;
  privateKey: string;
  leverage: number; // 2x
  positionSizePercent: number; // 50%
  stopLossPercent: number; // 3.5%
  maxDailyLossPercent: number; // 12%
}

export interface DailyStats {
  startBalance: number;
  currentBalance: number;
  totalLoss: number;
  totalGain: number;
  trades: number;
  date: string;
}

export class PerpsTradingEngine {
  private config: PerpsTradingConfig;
  private dailyStats: DailyStats;
  private botEngine: TradingBotEngine;
  private currentPosition: {
    coin: string;
    side: "long" | "short";
    size: number;
    entryPrice: number;
    stopLossPrice: number;
  } | null = null;

  constructor(config: PerpsTradingConfig, botEngine: TradingBotEngine) {
    this.config = config;
    this.botEngine = botEngine;
    this.dailyStats = {
      startBalance: 0,
      currentBalance: 0,
      totalLoss: 0,
      totalGain: 0,
      trades: 0,
      date: new Date().toISOString().split("T")[0],
    };
  }

  /**
   * Initialize daily stats
   */
  async initializeDailyStats() {
    const balance = await fetchPerpsBalance(this.config.walletAddress);
    if (balance) {
      this.dailyStats.startBalance = balance.accountValue;
      this.dailyStats.currentBalance = balance.accountValue;
    }
  }

  /**
   * Check if daily loss limit exceeded
   */
  private isDailyLossLimitExceeded(): boolean {
    const maxDailyLoss =
      this.dailyStats.startBalance *
      (this.config.maxDailyLossPercent / 100);
    const currentLoss =
      this.dailyStats.startBalance - this.dailyStats.currentBalance;

    console.log(
      `[Perps] Daily loss check: ${currentLoss.toFixed(2)} / ${maxDailyLoss.toFixed(2)}`
    );

    if (currentLoss > maxDailyLoss) {
      console.warn(
        `[Perps] ⚠️ Daily loss limit exceeded! Loss: $${currentLoss.toFixed(2)} > Limit: $${maxDailyLoss.toFixed(2)}`
      );
      return true;
    }

    return false;
  }

  /**
   * Calculate position size based on account balance
   */
  private async calculatePositionSize(): Promise<number> {
    const balance = await fetchPerpsBalance(this.config.walletAddress);
    if (!balance) {
      console.error("[Perps] Could not fetch balance for position sizing");
      return 0;
    }

    const positionValue =
      balance.accountValue * (this.config.positionSizePercent / 100);
    console.log(
      `[Perps] Account balance: $${balance.accountValue.toFixed(2)}, Position size: $${positionValue.toFixed(2)}`
    );

    return positionValue;
  }

  /**
   * Execute trade based on signal
   */
  async executeTrade(signal: Signal, currentPrice: number) {
    try {
      console.log(`[Perps] Executing trade - Signal: ${signal}, Price: $${currentPrice}`);

      // Check daily loss limit
      if (this.isDailyLossLimitExceeded()) {
        console.warn("[Perps] Daily loss limit exceeded, stopping trades");
        return;
      }

      // Close existing position if signal changed
      if (
        this.currentPosition &&
        ((signal === "buy" && this.currentPosition.side === "short") ||
          (signal === "sell" && this.currentPosition.side === "long"))
      ) {
        console.log("[Perps] Closing existing position due to signal change");
        await this.closeCurrentPosition(currentPrice);
      }

      // Don't open new position if already in position
      if (this.currentPosition) {
        console.log("[Perps] Already in position, skipping new trade");
        return;
      }

      // Calculate position size
      const positionValue = await this.calculatePositionSize();
      if (positionValue <= 0) {
        console.error("[Perps] Invalid position size");
        return;
      }

      // Calculate contract size (assuming 1 SOL contract)
      const contractSize = positionValue / currentPrice;

      // Determine side
      const side = signal === "buy" ? "A" : "B"; // A = long, B = short

      // Calculate stop loss price
      const stopLossPercent = this.config.stopLossPercent / 100;
      const stopLossPrice =
        signal === "buy"
          ? currentPrice * (1 - stopLossPercent)
          : currentPrice * (1 + stopLossPercent);

      console.log(`[Perps] Opening ${signal} position:`);
      console.log(`  - Size: ${contractSize.toFixed(4)} contracts`);
      console.log(`  - Entry: $${currentPrice.toFixed(2)}`);
      console.log(`  - Stop Loss: $${stopLossPrice.toFixed(2)}`);
      console.log(`  - Leverage: ${this.config.leverage}x`);

      // Place order
      const result = await placePerpsOrder(
        this.config.walletAddress,
        this.config.privateKey,
        {
          coin: "SOL",
          side: side,
          sz: contractSize,
          leverage: this.config.leverage,
          orderType: "Market",
          limitPx: currentPrice,
        }
      );

      if (result && result.status === "ok") {
        // Track position
        this.currentPosition = {
          coin: "SOL",
          side: signal === "buy" ? "long" : "short",
          size: contractSize,
          entryPrice: currentPrice,
          stopLossPrice: stopLossPrice,
        };

        this.dailyStats.trades++;
        console.log(`[Perps] ✅ Trade executed successfully!`);
      } else {
        console.error("[Perps] Trade execution failed:", result);
      }
    } catch (error) {
      console.error("[Perps] Error executing trade:", error);
    }
  }

  /**
   * Monitor position for stop loss
   */
  async monitorPosition(currentPrice: number) {
    if (!this.currentPosition) {
      return;
    }

    console.log(
      `[Perps] Monitoring position - Current price: $${currentPrice}, Stop loss: $${this.currentPosition.stopLossPrice.toFixed(2)}`
    );

    // Check stop loss
    const shouldCloseLong =
      this.currentPosition.side === "long" &&
      currentPrice <= this.currentPosition.stopLossPrice;
    const shouldCloseShort =
      this.currentPosition.side === "short" &&
      currentPrice >= this.currentPosition.stopLossPrice;

    if (shouldCloseLong || shouldCloseShort) {
      console.warn(
        `[Perps] 🛑 Stop loss triggered! Closing ${this.currentPosition.side} position`
      );
      await this.closeCurrentPosition(currentPrice);
    }
  }

  /**
   * Close current position
   */
  private async closeCurrentPosition(currentPrice: number) {
    if (!this.currentPosition) {
      return;
    }

    try {
      console.log(
        `[Perps] Closing ${this.currentPosition.side} position at $${currentPrice}`
      );

      const result = await closePosition(
        this.config.walletAddress,
        this.config.privateKey,
        this.currentPosition.coin,
        this.currentPosition.side === "long"
          ? this.currentPosition.size
          : -this.currentPosition.size
      );

      if (result && result.status === "ok") {
        // Calculate P&L
        const pnl =
          this.currentPosition.side === "long"
            ? (currentPrice - this.currentPosition.entryPrice) *
              this.currentPosition.size
            : (this.currentPosition.entryPrice - currentPrice) *
              this.currentPosition.size;

        console.log(
          `[Perps] ✅ Position closed! P&L: $${pnl.toFixed(2)}`
        );

        // Update daily stats
        if (pnl > 0) {
          this.dailyStats.totalGain += pnl;
        } else {
          this.dailyStats.totalLoss += Math.abs(pnl);
        }

        // Update balance
        const balance = await fetchPerpsBalance(
          this.config.walletAddress
        );
        if (balance) {
          this.dailyStats.currentBalance = balance.accountValue;
        }

        this.currentPosition = null;
      } else {
        console.error("[Perps] Failed to close position:", result);
      }
    } catch (error) {
      console.error("[Perps] Error closing position:", error);
    }
  }

  /**
   * Get current stats
   */
  getStats(): DailyStats {
    return this.dailyStats;
  }

  /**
   * Get current position
   */
  getCurrentPosition() {
    return this.currentPosition;
  }
}

