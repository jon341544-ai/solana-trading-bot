/**
 * Hyperliquid Perpetuals API Integration
 * Handles all Perps trading operations including:
 * - Balance queries
 * - Position management
 * - Order execution
 * - Stop loss management
 */

import crypto from "crypto";

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
 * Sign request for Hyperliquid API
 */
function signRequest(
  action: any,
  nonce: number,
  privateKey: string
): string {
  const message = JSON.stringify(action);
  const toSign = crypto
    .createHash("sha256")
    .update(message)
    .digest("hex");

  const signature = crypto
    .createPrivateKey({
      key: Buffer.from(privateKey, "hex"),
      format: "raw",
      type: "ed25519",
    })
    .sign(Buffer.from(toSign, "hex"));

  return signature.toString("hex");
}

/**
 * Fetch Perpetuals account balance
 */
export async function fetchPerpsBalance(
  walletAddress: string
): Promise<PerpsBalance | null> {
  try {
    console.log(`[Perps] Fetching balance for wallet: ${walletAddress}`);

    const response = await fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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

    if (data && data.accountValue !== undefined) {
      return {
        accountValue: parseFloat(data.accountValue),
        totalNotionalUsd: parseFloat(data.totalNotionalUsd || "0"),
        totalRawUsd: parseFloat(data.totalRawUsd || "0"),
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
  walletAddress: string
): Promise<PerpsPosition[]> {
  try {
    const response = await fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
 * Place a Perps order
 */
export async function placePerpsOrder(
  walletAddress: string,
  privateKey: string,
  order: PerpsOrder
): Promise<any> {
  try {
    const nonce = Date.now();

    const action = {
      type: "order",
      orders: [
        {
          coin: order.coin,
          side: order.side,
          sz: order.sz,
          leverage: {
            type: "cross",
            value: order.leverage,
          },
          orderType: order.orderType,
          limitPx: order.limitPx,
          triggerPx: order.triggerPx,
          triggerCondition: order.triggerCondition,
          reduceOnly: order.reduceOnly || false,
          postOnly: order.postOnly || false,
          cloid: order.cloid || null,
        },
      ],
      grouping: "na",
      nonce: nonce,
      signature: "", // Will be filled below
    };

    // Sign the request
    action.signature = signRequest(action, nonce, privateKey);

    console.log("[Perps] Placing order:", {
      coin: order.coin,
      side: order.side,
      sz: order.sz,
      leverage: order.leverage,
    });

    const response = await fetch("https://api.hyperliquid.xyz/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(action),
    });

    if (!response.ok) {
      console.error(
        `[Perps] Order API error: ${response.status} ${response.statusText}`
      );
      return null;
    }

    const result = await response.json();
    console.log("[Perps] Order result:", result);

    return result;
  } catch (error) {
    console.error("[Perps] Error placing order:", error);
    return null;
  }
}

/**
 * Close a position
 */
export async function closePosition(
  walletAddress: string,
  privateKey: string,
  coin: string,
  currentSize: number
): Promise<any> {
  try {
    // Determine the opposite side to close the position
    const side = currentSize > 0 ? "B" : "A"; // B = short to close long, A = long to close short

    return await placePerpsOrder(walletAddress, privateKey, {
      coin: coin,
      side: side,
      sz: Math.abs(currentSize),
      leverage: 1, // Use 1x leverage for closing
      orderType: "Market",
      limitPx: 0,
      reduceOnly: true,
    });
  } catch (error) {
    console.error("[Perps] Error closing position:", error);
    return null;
  }
}

/**
 * Fetch current SOL price
 */
export async function fetchCurrentPrice(): Promise<number> {
  try {
    const response = await fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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

