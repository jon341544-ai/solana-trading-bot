/**
 * MACD (Moving Average Convergence Divergence) Indicator
 * 
 * Momentum indicator that shows the relationship between two moving averages
 * MACD = 12-period EMA - 26-period EMA
 * Signal Line = 9-period EMA of MACD
 * Histogram = MACD - Signal Line
 */

export interface MACDResult {
  macd: number;
  signalLine: number;
  histogram: number;
  signal: "bullish" | "bearish" | "neutral";
}

export interface OHLCV {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/**
 * Calculate Exponential Moving Average (EMA)
 */
function calculateEMA(data: number[], period: number): number[] {
  if (data.length < period) return [];

  const ema: number[] = [];
  const multiplier = 2 / (period + 1);

  // Calculate SMA for first EMA value
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += data[i];
  }
  ema[period - 1] = sum / period;

  // Calculate EMA for remaining values
  for (let i = period; i < data.length; i++) {
    ema[i] = (data[i] - ema[i - 1]) * multiplier + ema[i - 1];
  }

  return ema;
}

/**
 * Calculate MACD
 */
export function calculateMACD(ohlcv: OHLCV[]): MACDResult | null {
  if (ohlcv.length < 26) {
    console.log("[MACD] Not enough data to calculate MACD (need at least 26 candles)");
    return null;
  }

  // Extract close prices
  const closes = ohlcv.map((candle) => candle.close);

  // Calculate EMAs
  const ema12 = calculateEMA(closes, 12);
  const ema26 = calculateEMA(closes, 26);

  // Calculate MACD line (12-EMA - 26-EMA)
  const macdLine: number[] = [];
  for (let i = 25; i < closes.length; i++) {
    macdLine.push(ema12[i] - ema26[i]);
  }

  if (macdLine.length < 9) {
    console.log("[MACD] Not enough MACD values to calculate signal line");
    return null;
  }

  // Calculate Signal line (9-EMA of MACD)
  const signalLine = calculateEMA(macdLine, 9);

  // Get latest values
  const latestMACD = macdLine[macdLine.length - 1];
  const latestSignal = signalLine[signalLine.length - 1];
  const latestHistogram = latestMACD - latestSignal;

  // Determine signal
  let signal: "bullish" | "bearish" | "neutral" = "neutral";
  if (latestHistogram > 0) {
    signal = "bullish";
  } else if (latestHistogram < 0) {
    signal = "bearish";
  }

  console.log(`[MACD] MACD: ${latestMACD.toFixed(6)}, SignalLine: ${latestSignal.toFixed(6)}, Histogram: ${latestHistogram.toFixed(6)}, Signal: ${signal}`);

  return {
    macd: latestMACD,
    signalLine: latestSignal,
    histogram: latestHistogram,
    signal,
  };
}

/**
 * Get MACD buy/sell signal
 * Buy when MACD crosses above signal line (histogram > 0)
 * Sell when MACD crosses below signal line (histogram < 0)
 */
export function getMACDSignal(ohlcv: OHLCV[]): "buy" | "sell" | "hold" {
  const macd = calculateMACD(ohlcv);

  if (!macd) {
    return "hold";
  }

  if (macd.histogram > 0) {
    return "buy";
  } else if (macd.histogram < 0) {
    return "sell";
  }

  return "hold";
}

