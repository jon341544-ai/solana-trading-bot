/**
 * Hyperliquid Spot Trading Module
 * 
 * Integrates with Hyperliquid's spot trading API for SOL/USDC trades
 * Uses signature-based authentication with private key
 */

import { ethers } from "ethers";
import { fetchWithRetry } from "./networkResilience";

const HYPERLIQUID_API_URL = "https://api.hyperliquid.xyz";
const SOL_ASSET_ID = 10000; // SOL spot asset ID on Hyperliquid
const USDC_ASSET_ID = 10001; // USDC spot asset ID on Hyperliquid

export interface HyperliquidSpotTradeParams {
  asset: number; // Asset ID (10000 for SOL, 10001 for USDC)
  isBuy: boolean; // true for buy, false for sell
  price: string; // Price as string
  size: string; // Size as string
  reduceOnly?: boolean; // For spot, usually false
}

export interface HyperliquidSpotTradeResult {
  txHash: string;
  status: "success" | "failed";
  message: string;
  orderId?: string;
}

/**
 * Sign a Hyperliquid request using private key
 */
function signHyperliquidRequest(
  privateKey: string,
  action: any,
  nonce: number,
  vaultAddress?: string
): string {
  try {
    // Create wallet from private key
    const wallet = new ethers.Wallet(privateKey);

    // Prepare the message to sign
    const actionHash = ethers.keccak256(ethers.toUtf8Bytes(JSON.stringify(action)));
    const nonceHash = ethers.toBeHex(nonce, 32);
    const vaultAddressHash = vaultAddress
      ? ethers.toBeHex(vaultAddress, 32)
      : ethers.toBeHex("0x0000000000000000000000000000000000000000", 32);

    // Combine hashes
    const messageHash = ethers.keccak256(
      ethers.solidityPacked(["bytes32", "bytes32", "bytes32"], [actionHash, nonceHash, vaultAddressHash])
    );

    // Sign the message
    const signature = wallet.signingKey.sign(messageHash);
    return signature.serialized;
  } catch (error) {
    console.error("[HyperliquidSpot] Error signing request:", error);
    throw error;
  }
}

/**
 * Get spot metadata (asset IDs, etc.)
 */
export async function getSpotMetadata(): Promise<any> {
  try {
    console.log("[HyperliquidSpot] Fetching spot metadata...");

    const response = await fetchWithRetry(`${HYPERLIQUID_API_URL}/info`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "spotMeta" }),
      maxRetries: 3,
      timeoutMs: 10000,
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch spot metadata: ${response.statusText}`);
    }

    const metadata = await response.json();
    console.log("[HyperliquidSpot] Spot metadata fetched successfully");
    return metadata;
  } catch (error) {
    console.error("[HyperliquidSpot] Error fetching spot metadata:", error);
    throw error;
  }
}

/**
 * Get spot user state (balances, open orders, etc.)
 */
export async function getSpotUserState(userAddress: string): Promise<any> {
  try {
    console.log(`[HyperliquidSpot] Fetching spot user state for ${userAddress}...`);

    const response = await fetchWithRetry(`${HYPERLIQUID_API_URL}/info`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "spotUserState", user: userAddress }),
      maxRetries: 3,
      timeoutMs: 10000,
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch spot user state: ${response.statusText}`);
    }

    const userState = await response.json();
    console.log("[HyperliquidSpot] Spot user state fetched successfully");
    return userState;
  } catch (error) {
    console.error("[HyperliquidSpot] Error fetching spot user state:", error);
    throw error;
  }
}

/**
 * Get current spot prices
 */
export async function getSpotPrices(): Promise<any> {
  try {
    console.log("[HyperliquidSpot] Fetching spot prices...");

    const response = await fetchWithRetry(`${HYPERLIQUID_API_URL}/info`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "spotMetaAndAssetCtxs" }),
      maxRetries: 3,
      timeoutMs: 10000,
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch spot prices: ${response.statusText}`);
    }

    const data = await response.json();
    console.log("[HyperliquidSpot] Spot prices fetched successfully");
    return data;
  } catch (error) {
    console.error("[HyperliquidSpot] Error fetching spot prices:", error);
    throw error;
  }
}

/**
 * Execute a spot trade on Hyperliquid
 */
export async function executeHyperliquidSpotTrade(
  privateKey: string,
  userAddress: string,
  params: HyperliquidSpotTradeParams
): Promise<HyperliquidSpotTradeResult> {
  const startTime = Date.now();

  try {
    console.log(`[HyperliquidSpot] ===== STARTING SPOT TRADE =====`);
    console.log(`[HyperliquidSpot] User: ${userAddress}`);
    console.log(`[HyperliquidSpot] Asset: ${params.asset}, IsBuy: ${params.isBuy}`);
    console.log(`[HyperliquidSpot] Price: ${params.price}, Size: ${params.size}`);

    // Get current nonce (timestamp in milliseconds)
    const nonce = Date.now();

    // Prepare the order action
    const action = {
      type: "order",
      orders: [
        {
          a: params.asset,
          b: params.isBuy,
          p: params.price,
          s: params.size,
          r: params.reduceOnly || false,
          t: { limit: { tif: "Gtc" } }, // Good-till-canceled
        },
      ],
      grouping: "na",
    };

    // Sign the request
    console.log("[HyperliquidSpot] Signing request...");
    const signature = signHyperliquidRequest(privateKey, action, nonce, userAddress);

    // Prepare the full request
    const request = {
      action: action,
      nonce: nonce,
      signature: signature,
      vaultAddress: userAddress,
    };

    // Send the trade request
    console.log("[HyperliquidSpot] Sending trade request...");
    const response = await fetchWithRetry(`${HYPERLIQUID_API_URL}/exchange`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      maxRetries: 2,
      timeoutMs: 15000,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Trade request failed: ${response.statusText} - ${errorText}`);
    }

    const result = await response.json();
    console.log("[HyperliquidSpot] Trade response:", result);

    // Check if trade was successful
    if (result.status === "ok" || result.success) {
      console.log(`[HyperliquidSpot] ✅ Trade executed successfully!`);
      console.log(`[HyperliquidSpot] Execution time: ${Date.now() - startTime}ms`);
      console.log(`[HyperliquidSpot] ===== TRADE COMPLETED =====`);

      return {
        txHash: result.response?.data?.orderId || `hl_${nonce}`,
        status: "success",
        message: "Trade executed successfully",
        orderId: result.response?.data?.orderId,
      };
    } else {
      const errorMsg = result.response?.error || result.error || "Unknown error";
      throw new Error(`Trade failed: ${errorMsg}`);
    }
  } catch (error) {
    const errorMsg = String(error);
    console.error(`[HyperliquidSpot] ❌ TRADE FAILED:`, error);
    console.error(`[HyperliquidSpot] Error message: ${errorMsg}`);
    console.error(`[HyperliquidSpot] Execution time: ${Date.now() - startTime}ms`);
    console.error(`[HyperliquidSpot] ===== TRADE FAILED =====`);

    return {
      txHash: "",
      status: "failed",
      message: errorMsg,
    };
  }
}

/**
 * Get SOL/USDC spot price
 */
export async function getSolUsdcPrice(): Promise<number> {
  try {
    const prices = await getSpotPrices();

    // Extract SOL price from the response
    // The response structure depends on Hyperliquid's API format
    if (prices && prices.assetCtxs) {
      const solCtx = prices.assetCtxs.find((ctx: any) => ctx.name === "SOL");
      if (solCtx && solCtx.markPx) {
        const price = parseFloat(solCtx.markPx);
        console.log(`[HyperliquidSpot] SOL/USDC Price: $${price.toFixed(2)}`);
        return price;
      }
    }

    // Fallback: return 0 if price not found
    console.warn("[HyperliquidSpot] Could not extract SOL price from response");
    return 0;
  } catch (error) {
    console.error("[HyperliquidSpot] Error getting SOL/USDC price:", error);
    return 0;
  }
}

