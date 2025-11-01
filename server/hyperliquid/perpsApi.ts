/**
 * Hyperliquid Perpetuals API Integration (API Key Authentication)
 * Handles all Perps trading operations including:
 * - Balance queries
 * - Position management
 * - Order execution
 * - Stop loss management
 */

export interface PerpsPosition {
  coin: string;
  leverage: number;
  szi: string; // size
  positionValue: number;
  unrealizedPnl: number;
  returnOnLeverage: number;
  liquidationPrice: number | null;
}

export interface PerpsBalance {
  accountValue: number;
  totalNotionalUsd: number;
  totalRawUsd: number;
}

export interface PerpsOrder {
  coin: string;
  side: "A" | "B"; // A = long, B = short
  sz: number; // size in contracts
  leverage: number;
  orderType: "Limit" | "Market";
  limitPx: number;
  triggerPx?: number;
  triggerCondition?: "Above" | "Below";
  reduceOnly?: boolean;
  postOnly?: boolean;
  cloid?: string;
}

/**
 * Fetch Perpetuals account balance using API key
 */
export async function fetchPerpsBalance(
  walletAddress: string,
  apiKey?: string
): Promise<PerpsBalance | null> {
  try {
    console.log(`[Perps] Fetching balance for wallet: ${walletAddress}`);

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    // Add API key to headers if provided
    if (apiKey) {
      headers["HYPERLIQUID-API-KEY"] = apiKey;
    }

    const response = await fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers,
      body: JSON.stringify({
        type: "clearinghouseState",
        user: walletAddress.toLowerCase(),
      }),
    });

    if (!response.ok) {
      console.error(
        `[Perps] Hyperliquid API error: ${response.status} ${response.statusText}`
      );
      return null;
    }

    const data = await response.json();
    console.log("[Perps] Clearinghouse state response:", data);

    if (data && data.marginSummary && data.marginSummary.accountValue !== undefined) {
      return {
        accountValue: parseFloat(data.marginSummary.accountValue),
        totalNotionalUsd: parseFloat(data.marginSummary.totalNtlPos || "0"),
        totalRawUsd: parseFloat(data.marginSummary.totalRawUsd || "0"),
      };
    }

    console.warn("[Perps] No account value in response", data);
    return null;
  } catch (error) {
    console.error("[Perps] Error fetching balance:", error);
    return null;
  }
}

/**
 * Fetch open positions
 */
export async function fetchOpenPositions(
  walletAddress: string,
  apiKey?: string
): Promise<PerpsPosition[]> {
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    if (apiKey) {
      headers["HYPERLIQUID-API-KEY"] = apiKey;
    }

    const response = await fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers,
      body: JSON.stringify({
        type: "clearinghouseState",
        user: walletAddress.toLowerCase(),
      }),
    });

    if (!response.ok) {
      return [];
    }

    const data = await response.json();
    console.log("[Perps] Open positions:", data.assetPositions);

    if (data && data.assetPositions) {
      return data.assetPositions.map((pos: any) => ({
        coin: pos.position.coin,
        leverage: parseFloat(pos.position.leverage),
        szi: pos.position.szi,
        positionValue: parseFloat(pos.position.positionValue),
        unrealizedPnl: parseFloat(pos.position.unrealizedPnl),
        returnOnLeverage: parseFloat(pos.position.returnOnLeverage),
        liquidationPrice: pos.position.liquidationPx
          ? parseFloat(pos.position.liquidationPx)
          : null,
      }));
    }

    return [];
  } catch (error) {
    console.error("[Perps] Error fetching positions:", error);
    return [];
  }
}

/**
 * Place a Perps order using API key
 * Note: API key authentication doesn't support order placement yet
 * This is a placeholder for future implementation
 */
export async function placePerpsOrder(
  walletAddress: string,
  apiKey: string,
  order: PerpsOrder
): Promise<any> {
  try {
    console.log("[Perps] Placing order (API key method):", {
      coin: order.coin,
      side: order.side,
      sz: order.sz,
      leverage: order.leverage,
    });

    // For now, log that this requires signature-based auth
    console.warn("[Perps] Order placement requires signature-based authentication");
    console.warn("[Perps] API key can only be used for read operations (balance, positions)");

    return { status: "error", message: "Order placement not supported with API key only" };
  } catch (error) {
    console.error("[Perps] Error placing order:", error);
    return null;
  }
}

/**
 * Close a position
 * Note: Requires signature-based authentication
 */
export async function closePosition(
  walletAddress: string,
  apiKey: string,
  coin: string,
  currentSize: number
): Promise<any> {
  try {
    console.warn("[Perps] Position closing requires signature-based authentication");
    return { status: "error", message: "Position closing not supported with API key only" };
  } catch (error) {
    console.error("[Perps] Error closing position:", error);
    return null;
  }
}

/**
 * Fetch current SOL price
 */
export async function fetchCurrentPrice(apiKey?: string): Promise<number> {
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    if (apiKey) {
      headers["HYPERLIQUID-API-KEY"] = apiKey;
    }

    const response = await fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers,
      body: JSON.stringify({
        type: "allMids",
      }),
    });

    if (!response.ok) {
      console.error(
        `[Perps] Price API error: ${response.status} ${response.statusText}`
      );
      return 0;
    }

    const data = await response.json();
    console.log("[Perps] Current prices:", data);

    // Look for SOL price
    if (data["SOL"]) {
      const price = parseFloat(data["SOL"]);
      console.log(`[Perps] SOL price: $${price}`);
      return price;
    }

    console.warn("[Perps] SOL price not found in response");
    return 0;
  } catch (error) {
    console.error("[Perps] Error fetching price:", error);
    return 0;
  }
}
