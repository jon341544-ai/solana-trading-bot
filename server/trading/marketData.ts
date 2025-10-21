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

// Cache for price data
let priceCache: { data: PriceData; timestamp: number } | null = null;
const PRICE_CACHE_TTL = 30000; // 30 seconds

/**
 * Fetch current SOL/USD price from CoinGecko API with retry logic and fallback
 */
export async function fetchSOLPrice(): Promise<PriceData> {
  // Check cache first
  if (priceCache && Date.now() - priceCache.timestamp < PRICE_CACHE_TTL) {
    return priceCache.data;
  }

  // Try multiple sources with retry logic
  const sources = [
    {
      name: "coingecko",
      url: "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
      parser: (data: any) => data.solana?.usd,
    },
    {
      name: "coingecko-alt",
      url: "https://api.coingecko.com/api/v3/coins/solana?localization=false",
      parser: (data: any) => data.market_data?.current_price?.usd,
    },
  ];

  for (const source of sources) {
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const response = await fetch(source.url, {
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        const price = source.parser(data);

        if (!price || typeof price !== "number") {
          throw new Error("Invalid price data");
        }

        const priceData: PriceData = {
          timestamp: Date.now(),
          price,
          source: source.name,
        };

        // Cache the result
        priceCache = { data: priceData, timestamp: Date.now() };
        console.log(`Successfully fetched SOL price: $${price} from ${source.name}`);
        return priceData;
      } catch (error) {
        console.warn(
          `Attempt ${attempt + 1} failed for ${source.name}:`,
          error
        );
        if (attempt < 2) {
          // Wait before retry with exponential backoff
          await new Promise((resolve) =>
            setTimeout(resolve, Math.pow(2, attempt) * 1000)
          );
        }
      }
    }
  }

  // If all sources failed, use cached price if available
  if (priceCache) {
    console.warn("All price sources failed, using cached price");
    return priceCache.data;
  }

  // Last resort: throw error
  throw new Error("Failed to fetch SOL price from all sources");
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

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    const response = await fetch(url, {
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

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

