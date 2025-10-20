/**
 * Market Data Fetching Module
 * 
 * Fetches real-time market data from various sources and stores it for analysis
 */

import { OHLCV } from "./supertrend";

export interface PriceData {
  timestamp: number;
  price: number;
  source: string;
}

/**
 * Fetch current SOL/USD price from CoinGecko API
 */
export async function fetchSOLPrice(): Promise<PriceData> {
  try {
    const response = await fetch(
      "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true"
    );
    const data = await response.json();

    if (!data.solana || !data.solana.usd) {
      throw new Error("Invalid response from CoinGecko");
    }

    return {
      timestamp: Date.now(),
      price: data.solana.usd,
      source: "coingecko",
    };
  } catch (error) {
    console.error("Failed to fetch SOL price:", error);
    throw new Error(`Failed to fetch SOL price: ${error}`);
  }
}

/**
 * Fetch USDC/USD price
 */
export async function fetchUSDCPrice(): Promise<PriceData> {
  try {
    const response = await fetch(
      "https://api.coingecko.com/api/v3/simple/price?ids=usd-coin&vs_currencies=usd"
    );
    const data = await response.json();

    if (!data["usd-coin"] || !data["usd-coin"].usd) {
      throw new Error("Invalid response from CoinGecko");
    }

    return {
      timestamp: Date.now(),
      price: data["usd-coin"].usd,
      source: "coingecko",
    };
  } catch (error) {
    console.error("Failed to fetch USDC price:", error);
    throw new Error(`Failed to fetch USDC price: ${error}`);
  }
}

/**
 * Fetch historical OHLCV data from CoinGecko
 * Note: CoinGecko free tier has limited historical data
 */
export async function fetchHistoricalOHLCV(
  days: number = 30,
  interval: "daily" | "hourly" = "daily"
): Promise<OHLCV[]> {
  try {
    const url =
      interval === "daily"
        ? `https://api.coingecko.com/api/v3/coins/solana/ohlc?vs_currency=usd&days=${days}`
        : `https://api.coingecko.com/api/v3/coins/solana/ohlc?vs_currency=usd&days=${days}`;

    const response = await fetch(url);
    const data = await response.json();

    if (!Array.isArray(data)) {
      throw new Error("Invalid response format from CoinGecko");
    }

    // CoinGecko returns [timestamp, open, high, low, close]
    return data.map((candle: number[]) => ({
      timestamp: candle[0],
      open: candle[1],
      high: candle[2],
      low: candle[3],
      close: candle[4],
      volume: 0, // CoinGecko OHLC endpoint doesn't provide volume
    }));
  } catch (error) {
    console.error("Failed to fetch historical OHLCV:", error);
    throw new Error(`Failed to fetch historical OHLCV: ${error}`);
  }
}

/**
 * Simulate OHLCV data for demonstration (when real data is unavailable)
 */
export function generateSimulatedOHLCV(
  basePrice: number,
  count: number = 50,
  volatility: number = 0.02
): OHLCV[] {
  const candles: OHLCV[] = [];
  let currentPrice = basePrice;
  const now = Date.now();
  const intervalMs = 60 * 60 * 1000; // 1 hour

  for (let i = 0; i < count; i++) {
    const change = (Math.random() - 0.5) * volatility * currentPrice;
    const open = currentPrice;
    const close = currentPrice + change;
    const high = Math.max(open, close) * (1 + Math.random() * 0.005);
    const low = Math.min(open, close) * (1 - Math.random() * 0.005);

    candles.push({
      timestamp: now - (count - i) * intervalMs,
      open,
      high,
      low,
      close,
      volume: Math.random() * 1000000,
    });

    currentPrice = close;
  }

  return candles;
}

/**
 * Convert price to lamports (SOL's smallest unit: 1 SOL = 1e9 lamports)
 */
export function solToLamports(sol: number): number {
  return Math.floor(sol * 1e9);
}

/**
 * Convert lamports to SOL
 */
export function lamportsToSol(lamports: number): number {
  return lamports / 1e9;
}

/**
 * Format price for display
 */
export function formatPrice(price: number, decimals: number = 2): string {
  return price.toFixed(decimals);
}

