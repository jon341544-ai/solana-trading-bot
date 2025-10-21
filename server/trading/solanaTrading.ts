/**
 * Solana Trading Module
 * 
 * Handles trade execution on Solana blockchain using Jupiter aggregator
 */

import {
  Connection,
  Keypair,
  PublicKey,
  Transaction,
  VersionedTransaction,
  sendAndConfirmTransaction,
} from "@solana/web3.js";
import bs58 from "bs58";
import { fetchWithRetry, getJupiterEndpoint } from "./networkResilience";

export interface TradeParams {
  inputMint: string; // Token to sell (SOL or USDC)
  outputMint: string; // Token to buy
  amount: number; // Amount in smallest units (lamports for SOL, smallest unit for USDC)
  slippageBps: number; // Slippage in basis points (e.g., 150 = 1.5%)
}

export interface TradeResult {
  txHash: string;
  inputAmount: number;
  outputAmount: number;
  priceImpact: number;
  status: "success" | "failed";
  error?: string;
}

/**
 * Initialize Solana connection
 */
export function createConnection(rpcUrl: string): Connection {
  return new Connection(rpcUrl, {
    commitment: "confirmed",
    fetch: ((url: any, options: any) => {
      return fetch(url, {
        ...options,
        mode: "cors",
        credentials: "omit",
        cache: "no-cache",
      });
    }) as any,
  });
}

/**
 * Create keypair from base58 private key
 */
export function createKeypairFromBase58(privateKeyBase58: string): Keypair {
  try {
    const decoded = bs58.decode(privateKeyBase58);
    return Keypair.fromSecretKey(decoded);
  } catch (error) {
    throw new Error(`Invalid private key format: ${error}`);
  }
}

/**
 * Get wallet balance
 */
export async function getWalletBalance(
  connection: Connection,
  publicKey: PublicKey
): Promise<number> {
  try {
    const balance = await connection.getBalance(publicKey);
    return balance;
  } catch (error) {
    console.error("Failed to get wallet balance:", error);
    throw new Error(`Failed to get wallet balance: ${error}`);
  }
}

/**
 * Get token balance for a specific mint
 */
export async function getTokenBalance(
  connection: Connection,
  walletAddress: PublicKey,
  tokenMint: PublicKey
): Promise<number> {
  try {
    const accounts = await connection.getParsedTokenAccountsByOwner(walletAddress, {
      mint: tokenMint,
    });

    if (accounts.value.length === 0) {
      return 0;
    }

    const balance = accounts.value[0].account.data.parsed.info.tokenAmount.amount;
    return parseInt(balance);
  } catch (error) {
    console.error("Failed to get token balance:", error);
    return 0;
  }
}

/**
 * Execute a trade using Jupiter API with retry logic
 * 
 * Jupiter is the leading DEX aggregator on Solana
 * This function gets a quote and executes the swap with automatic retries
 */
export async function executeTrade(
  connection: Connection,
  keypair: Keypair,
  params: TradeParams
): Promise<TradeResult> {
  try {
    // Step 1: Get quote from Jupiter with retry logic
    const jupiterEndpoint = await getJupiterEndpoint();
    const quoteUrl = new URL(`${jupiterEndpoint}/quote`);
    quoteUrl.searchParams.append("inputMint", params.inputMint);
    quoteUrl.searchParams.append("outputMint", params.outputMint);
    quoteUrl.searchParams.append("amount", params.amount.toString());
    quoteUrl.searchParams.append("slippageBps", params.slippageBps.toString());

    console.log(`[Trade] Getting quote from ${jupiterEndpoint}...`);
    const quoteResponse = await fetchWithRetry(quoteUrl.toString(), {
      maxRetries: 3,
      timeoutMs: 15000,
    });
    const quoteData = await quoteResponse.json();

    if (!quoteData.data) {
      throw new Error("No quote data received from Jupiter");
    }

    const quote = quoteData.data[0];
    const inputAmount = parseInt(quote.inAmount);
    const outputAmount = parseInt(quote.outAmount);
    const priceImpact = parseFloat(quote.priceImpactPct);

    console.log(`Quote received: ${inputAmount} -> ${outputAmount}`);
    console.log(`Price impact: ${priceImpact}%`);

    // Step 2: Get swap transaction from Jupiter with retry logic
    console.log(`[Trade] Getting swap transaction from ${jupiterEndpoint}...`);
    const swapResponse = await fetchWithRetry(`${jupiterEndpoint}/swap`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        quoteResponse: quote,
        userPublicKey: keypair.publicKey.toString(),
        wrapAndUnwrapSol: true,
      }),
      maxRetries: 3,
      timeoutMs: 15000,
    });

    const swapData = await swapResponse.json();

    if (!swapData.swapTransaction) {
      throw new Error("No swap transaction received from Jupiter");
    }

    // Step 3: Deserialize and sign the transaction
    const swapTransactionBuf = Buffer.from(swapData.swapTransaction, "base64");
    const transaction = VersionedTransaction.deserialize(swapTransactionBuf);

    transaction.sign([keypair]);

    // Step 4: Send transaction
    const txHash = await connection.sendTransaction(transaction, {
      skipPreflight: false,
      maxRetries: 2,
    });

    console.log(`Transaction sent: ${txHash}`);

    // Step 5: Wait for confirmation
    const confirmation = await connection.confirmTransaction(txHash, "confirmed");

    if (confirmation.value.err) {
      throw new Error(`Transaction failed: ${confirmation.value.err}`);
    }

    return {
      txHash,
      inputAmount,
      outputAmount,
      priceImpact,
      status: "success",
    };
  } catch (error) {
    console.error("Trade execution failed:", error);
    return {
      txHash: "",
      inputAmount: 0,
      outputAmount: 0,
      priceImpact: 0,
      status: "failed",
      error: `${error}`,
    };
  }
}

/**
 * Simulate a trade (for testing without executing on blockchain)
 */
export function simulateTrade(
  params: TradeParams,
  currentPrice: number,
  slippagePercent: number = 1.5
): TradeResult {
  const slippageMultiplier = 1 - slippagePercent / 100;
  const outputAmount = Math.floor(
    (params.amount / currentPrice) * slippageMultiplier
  );
  const priceImpact = (slippagePercent * 0.5) / 100; // Simplified price impact

  return {
    txHash: `sim_${Date.now()}_${Math.random().toString(36).substring(7)}`,
    inputAmount: params.amount,
    outputAmount,
    priceImpact,
    status: "success",
  };
}

/**
 * Calculate trade amount based on wallet balance and percentage
 */
export function calculateTradeAmount(
  walletBalance: number,
  tradePercentage: number
): number {
  return Math.floor((walletBalance * tradePercentage) / 100);
}

/**
 * Validate trade parameters
 */
export function validateTradeParams(
  params: TradeParams,
  minAmount: number = 1000
): { valid: boolean; error?: string } {
  if (params.amount < minAmount) {
    return {
      valid: false,
      error: `Amount must be at least ${minAmount} lamports`,
    };
  }

  if (params.slippageBps < 0 || params.slippageBps > 10000) {
    return {
      valid: false,
      error: "Slippage must be between 0 and 10000 basis points",
    };
  }

  return { valid: true };
}

