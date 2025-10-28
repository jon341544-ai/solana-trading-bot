/**
 * Bixord FantailVMA (FVMA) Indicator
 * 
 * Variable Moving Average that adapts based on ADX (Average Directional Index) strength
 * - Uses ADX to determine trend strength
 * - Adapts moving average sensitivity based on ADX value
 * - More responsive in strong trends, smoother in weak trends
 */

export interface FVMAResult {
  fvma: number;
  adx: number;
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
 * Calculate ADX (Average Directional Index)
 */
function calculateADX(
  ohlcv: OHLCV[],
  adxLength: number = 2,
  weighting: number = 10
): number {
  if (ohlcv.length < 2) return 0;

  let sPDI = 0;
  let sMDI = 0;
  let str = 0;
  let adx = 0;

  for (let i = 1; i < ohlcv.length; i++) {
    const hi = ohlcv[i].high;
    const hi1 = ohlcv[i - 1].high;
    const lo = ohlcv[i].low;
    const lo1 = ohlcv[i - 1].low;
    const close1 = ohlcv[i - 1].close;

    // Calculate Bulls and Bears
    const bulls1 = 0.5 * (Math.abs(hi - hi1) + (hi - hi1));
    const bears1 = 0.5 * (Math.abs(lo1 - lo) + (lo1 - lo));

    const bulls = bulls1 < bears1 ? 0 : bulls1 === bears1 ? 0 : bulls1;
    const bears = bulls1 > bears1 ? 0 : bulls1 === bears1 ? 0 : bears1;

    // Update PDI and MDI with weighting
    sPDI = (weighting * sPDI + bulls) / (weighting + 1);
    sMDI = (weighting * sMDI + bears) / (weighting + 1);

    // Calculate True Range
    const tr = Math.max(hi - lo, hi - close1);
    str = (weighting * str + tr) / (weighting + 1);

    // Calculate PDI, MDI, DX
    const pdi = str > 0 ? sPDI / str : 0;
    const mdi = str > 0 ? sMDI / str : 0;
    const dx = pdi + mdi > 0 ? Math.abs(pdi - mdi) / (pdi + mdi) : 0;

    // Update ADX
    adx = (weighting * adx + dx) / (weighting + 1);
  }

  return Math.min(1, Math.max(0, adx));
}

/**
 * Calculate Bixord FVMA
 */
export function calculateFVMA(
  ohlcv: OHLCV[],
  adxLength: number = 2,
  weighting: number = 10,
  maLength: number = 6
): FVMAResult | null {
  if (ohlcv.length < Math.max(adxLength, maLength)) {
    console.log("[FVMA] Not enough data to calculate FVMA");
    return null;
  }

  // Calculate ADX
  const adx = calculateADX(ohlcv, adxLength, weighting);

  // Get ADX range for normalization
  let adxMin = adx;
  let adxMax = adx;

  const lookbackLength = Math.min(adxLength, ohlcv.length);
  for (let i = Math.max(0, ohlcv.length - lookbackLength); i < ohlcv.length; i++) {
    const tempAdx = calculateADX(ohlcv.slice(0, i + 1), adxLength, weighting);
    adxMin = Math.min(adxMin, tempAdx);
    adxMax = Math.max(adxMax, tempAdx);
  }

  // Normalize ADX
  const diff = adxMax - adxMin;
  const normalizedADX = diff > 0 ? (adx - adxMin) / diff : 0;

  // Calculate Variable Moving Average
  let varMA = ohlcv[0].close;

  for (let i = 1; i < ohlcv.length; i++) {
    const tempAdx = calculateADX(ohlcv.slice(0, i + 1), adxLength, weighting);
    const tempDiff = adxMax - adxMin;
    const tempNormalized = tempDiff > 0 ? (tempAdx - adxMin) / tempDiff : 0;
    const const_val = Math.min(1, Math.max(0, tempNormalized));

    varMA = ((2 - const_val) * varMA + const_val * ohlcv[i].close) / 2;
  }

  // Calculate SMA of VarMA
  let fvma = varMA;
  if (maLength > 1) {
    let sum = 0;
    const startIdx = Math.max(0, ohlcv.length - maLength);
    for (let i = startIdx; i < ohlcv.length; i++) {
      sum += ohlcv[i].close;
    }
    fvma = sum / Math.min(maLength, ohlcv.length);
  }

  // Determine signal based on price vs FVMA
  const currentPrice = ohlcv[ohlcv.length - 1].close;
  let signal: "bullish" | "bearish" | "neutral" = "neutral";

  if (currentPrice > fvma) {
    signal = "bullish";
  } else if (currentPrice < fvma) {
    signal = "bearish";
  }

  console.log(`[FVMA] FVMA: ${fvma.toFixed(6)}, ADX: ${adx.toFixed(6)}, Price: ${currentPrice.toFixed(6)}, Signal: ${signal}`);

  return {
    fvma,
    adx,
    signal,
  };
}

/**
 * Get FVMA buy/sell signal
 * Buy when price crosses above FVMA
 * Sell when price crosses below FVMA
 */
export function getFVMASignal(ohlcv: OHLCV[]): "buy" | "sell" | "hold" {
  const fvma = calculateFVMA(ohlcv);

  if (!fvma) {
    return "hold";
  }

  if (fvma.signal === "bullish") {
    return "buy";
  } else if (fvma.signal === "bearish") {
    return "sell";
  }

  return "hold";
}

