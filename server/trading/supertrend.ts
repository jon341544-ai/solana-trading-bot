/**
 * SuperTrend Indicator Implementation
 * 
 * The SuperTrend indicator is a trend-following indicator that uses Average True Range (ATR)
 * to calculate dynamic support and resistance levels.
 */

export interface OHLCV {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SuperTrendResult {
  value: number;
  direction: "up" | "down";
  upperBand: number;
  lowerBand: number;
  atr: number;
}

/**
 * Calculate Average True Range (ATR)
 */
function calculateATR(candles: OHLCV[], period: number): number[] {
  const atr: number[] = [];
  const tr: number[] = [];

  // Calculate True Range
  for (let i = 0; i < candles.length; i++) {
    const high = candles[i].high;
    const low = candles[i].low;
    const prevClose = i > 0 ? candles[i - 1].close : candles[i].close;

    const tr1 = high - low;
    const tr2 = Math.abs(high - prevClose);
    const tr3 = Math.abs(low - prevClose);

    tr.push(Math.max(tr1, tr2, tr3));
  }

  // Calculate ATR using SMA
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += tr[i];
  }
  atr.push(sum / period);

  for (let i = period; i < tr.length; i++) {
    const newATR = (atr[atr.length - 1] * (period - 1) + tr[i]) / period;
    atr.push(newATR);
  }

  return atr;
}

/**
 * Calculate Simple Moving Average (SMA)
 */
function calculateSMA(values: number[], period: number): number[] {
  const sma: number[] = [];
  for (let i = 0; i <= values.length - period; i++) {
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += values[i + j];
    }
    sma.push(sum / period);
  }
  return sma;
}

/**
 * Calculate HL2 (High + Low) / 2
 */
function calculateHL2(candles: OHLCV[]): number[] {
  return candles.map((c) => (c.high + c.low) / 2);
}

/**
 * Calculate SuperTrend indicator
 * 
 * @param candles Array of OHLCV candles (must be sorted by timestamp ascending)
 * @param period Period for ATR calculation (default: 10)
 * @param multiplier Multiplier for ATR bands (default: 3)
 * @returns Array of SuperTrend results
 */
export function calculateSuperTrend(
  candles: OHLCV[],
  period: number = 10,
  multiplier: number = 3
): SuperTrendResult[] {
  if (candles.length < period) {
    throw new Error(`Need at least ${period} candles to calculate SuperTrend`);
  }

  const hl2 = calculateHL2(candles);
  const atr = calculateATR(candles, period);

  const results: SuperTrendResult[] = [];

  // We need to skip the first (period - 1) candles since ATR needs to warm up
  const startIndex = period - 1;

  for (let i = startIndex; i < candles.length; i++) {
    const atrIndex = i - startIndex;
    const currentATR = atr[atrIndex];
    const currentHL2 = hl2[i];

    // Calculate basic bands
    const basicUpperBand = currentHL2 + multiplier * currentATR;
    const basicLowerBand = currentHL2 - multiplier * currentATR;

    // Calculate final bands with previous values
    let finalUpperBand = basicUpperBand;
    let finalLowerBand = basicLowerBand;

    if (results.length > 0) {
      const prevResult = results[results.length - 1];
      finalUpperBand = Math.min(basicUpperBand, prevResult.upperBand);
      finalLowerBand = Math.max(basicLowerBand, prevResult.lowerBand);
    }

    // Determine trend direction
    const close = candles[i].close;
    let direction: "up" | "down";
    let value: number;

    if (results.length === 0) {
      // First candle: determine initial trend
      direction = close <= finalUpperBand ? "down" : "up";
      value = direction === "up" ? finalLowerBand : finalUpperBand;
    } else {
      const prevResult = results[results.length - 1];

      if (prevResult.direction === "up") {
        if (close <= finalLowerBand) {
          direction = "down";
          value = finalUpperBand;
        } else {
          direction = "up";
          value = finalLowerBand;
        }
      } else {
        if (close >= finalUpperBand) {
          direction = "up";
          value = finalLowerBand;
        } else {
          direction = "down";
          value = finalUpperBand;
        }
      }
    }

    results.push({
      value,
      direction,
      upperBand: finalUpperBand,
      lowerBand: finalLowerBand,
      atr: currentATR,
    });
  }

  return results;
}

/**
 * Get the latest SuperTrend signal
 */
export function getLatestSuperTrendSignal(
  candles: OHLCV[],
  period: number = 10,
  multiplier: number = 3
): SuperTrendResult | null {
  const results = calculateSuperTrend(candles, period, multiplier);
  return results.length > 0 ? results[results.length - 1] : null;
}

/**
 * Detect trend change (buy/sell signal)
 */
export function detectTrendChange(
  previousSignal: SuperTrendResult | null,
  currentSignal: SuperTrendResult
): "buy" | "sell" | null {
  if (!previousSignal) {
    return null; // Not enough data for signal
  }

  if (previousSignal.direction === "down" && currentSignal.direction === "up") {
    return "buy";
  }

  if (previousSignal.direction === "up" && currentSignal.direction === "down") {
    return "sell";
  }

  return null; // No trend change
}

