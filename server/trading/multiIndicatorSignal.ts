/**
 * Multi-Indicator Signal Combiner
 * 
 * Combines SuperTrend, MACD, and Bixord FVMA indicators
 * 
 * BUY Signal: ALL 3 indicators must be bullish
 * SELL Signal: At least 2 out of 3 indicators must be bearish
 */

import { calculateSuperTrend } from "./supertrend";
import { getMACDSignal } from "./macd";
import { getFVMASignal } from "./bixordFVMA";

export interface OHLCV {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MultiIndicatorSignal {
  superTrendSignal: "buy" | "sell" | "hold";
  macdSignal: "buy" | "sell" | "hold";
  fvmaSignal: "buy" | "sell" | "hold";
  combinedSignal: "buy" | "sell" | "hold";
  bullishCount: number;
  bearishCount: number;
  confidence: number; // 0-100, higher = more confident
  timestamp?: number;
}

/**
 * Get combined multi-indicator signal
 * 
 * BUY: All 3 indicators bullish (100% confidence)
 * SELL: At least 2 indicators bearish
 * HOLD: Otherwise
 */
export function getMultiIndicatorSignal(ohlcv: OHLCV[]): MultiIndicatorSignal {
  if (ohlcv.length < 26) {
    console.log("[MultiIndicator] Not enough data for multi-indicator analysis");
    return {
      superTrendSignal: "hold",
      macdSignal: "hold",
      fvmaSignal: "hold",
      combinedSignal: "hold",
      bullishCount: 0,
      bearishCount: 0,
      confidence: 0,
    };
  }

  // Get individual signals
  const superTrendResults = calculateSuperTrend(ohlcv);
  const superTrendResult = superTrendResults[superTrendResults.length - 1]; // Get latest
  const superTrendSignal = superTrendResult.direction === "up" ? "buy" : superTrendResult.direction === "down" ? "sell" : "hold";

  const macdSignal = getMACDSignal(ohlcv);
  const fvmaSignal = getFVMASignal(ohlcv);

  // Count bullish and bearish signals
  let bullishCount = 0;
  let bearishCount = 0;

  if (superTrendSignal === "buy") bullishCount++;
  else if (superTrendSignal === "sell") bearishCount++;

  if (macdSignal === "buy") bullishCount++;
  else if (macdSignal === "sell") bearishCount++;

  if (fvmaSignal === "buy") bullishCount++;
  else if (fvmaSignal === "sell") bearishCount++;

  // Determine combined signal
  let combinedSignal: "buy" | "sell" | "hold" = "hold";
  let confidence = 0;

  // BUY: All 3 indicators must be bullish
  if (bullishCount === 3) {
    combinedSignal = "buy";
    confidence = 100;
  }
  // SELL: At least 2 indicators must be bearish
  else if (bearishCount >= 2) {
    combinedSignal = "sell";
    confidence = bearishCount === 3 ? 100 : 67; // 100% if all 3, 67% if 2 out of 3
  }
  // HOLD: Otherwise
  else {
    combinedSignal = "hold";
    confidence = (bullishCount / 3) * 100; // Partial confidence for holds
  }

  console.log(`[MultiIndicator] SuperTrend: ${superTrendSignal}, MACD: ${macdSignal}, FVMA: ${fvmaSignal}`);
  console.log(`[MultiIndicator] Bullish: ${bullishCount}, Bearish: ${bearishCount}`);
  console.log(`[MultiIndicator] Combined Signal: ${combinedSignal} (${confidence.toFixed(0)}% confidence)`);

  return {
    superTrendSignal,
    macdSignal,
    fvmaSignal,
    combinedSignal,
    bullishCount,
    bearishCount,
    confidence,
  };
}

/**
 * Detect trend change using multi-indicator signal
 */
export function detectMultiIndicatorTrendChange(
  previousSignal: MultiIndicatorSignal | null,
  currentSignal: MultiIndicatorSignal
): "buy" | "sell" | "hold" {
  // If no previous signal, use current signal
  if (!previousSignal) {
    return currentSignal.combinedSignal;
  }

  // Detect change
  if (previousSignal.combinedSignal !== currentSignal.combinedSignal) {
    return currentSignal.combinedSignal;
  }

  return "hold";
}

