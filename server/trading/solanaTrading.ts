/**
 * Solana Trading Module
 * 
 * Handles REAL trade execution on Solana blockchain
 * This module executes actual swaps with real fund transfers
 */

import {
  Connection,
  Keypair,
  PublicKey,
  VersionedTransaction,
  TransactionMessage,
  SystemProgram,
} from "@solana/web3.js";
import { AccountLayout } from "@solana/spl-token";
import bs58 from "bs58";
import { fetchWithRetry } from "./networkResilience";
import { executeRaydiumSwap } from "./raydiumTrading";

export interface TradeParams {
  inputMint: string;
  outputMint: string;
  amount: number;
  slippageBps?: number;
}

export interface TradeResult {
  txHash: string;
  inputAmount: number;
  outputAmount: number;
  priceImpact: number;
  status: "success" | "failed" | "pending";
}

const SOL_MINT = "So11111111111111111111111111111111111111112";
const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";

/**
 * Create a Solana connection
 */
export function createConnection(rpcUrl: string): Connection {
  return new Connection(rpcUrl, "confirmed");
}

/**
 * Create a keypair from a base58 encoded private key
 */
export function createKeypairFromBase58(privateKeyStr: string): Keypair {
  const decoded = Buffer.from((bs58 as any).decode(privateKeyStr));
  return Keypair.fromSecretKey(decoded);
}

/**
 * Get wallet balance in lamports
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
  publicKey: PublicKey,
  mint: string
): Promise<number> {
  console.log(`[getTokenBalance] Called for mint: ${mint}, pubkey: ${publicKey.toBase58()}`);
  try {
    // Use getParsedTokenAccountsByOwner for better parsing
    const accounts = await connection.getParsedTokenAccountsByOwner(publicKey, {
      mint: new PublicKey(mint),
    });
    console.log(`[getTokenBalance] Got accounts:`, accounts.value.length);

    if (accounts.value.length === 0) {
      return 0;
    }

    // Sum up all token account balances
    let totalBalance = 0;
    console.log(`[Token] Found ${accounts.value.length} accounts for mint ${mint}`);
    for (const account of accounts.value) {
      try {
        const parsed = account.account.data.parsed;
        console.log(`[Token] Parsed data type: ${parsed?.type}`);
        const parsedInfo = parsed?.info;
        if (parsedInfo && parsedInfo.tokenAmount) {
          const amount = parsedInfo.tokenAmount.amount;
          console.log(`[Token] Balance: ${amount}`);
          totalBalance += amount;
        }
      } catch (error) {
        console.error("Failed to parse token account:", error);
      }
    }
    console.log(`[Token] Total: ${totalBalance}`);

    return Number(totalBalance);
  } catch (error: any) {
    // Handle specific error cases silently
    if (error?.message?.includes("could not find mint") || error?.message?.includes("Invalid param")) {
      // Token account doesn't exist yet - return 0 silently
      return 0;
    }
    console.error("Failed to get token balance:", error);
    return 0;
  }
}

/**
 * Convert SOL to lamports
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
 * Calculate trade amount based on percentage
 */
export function calculateTradeAmount(balance: number, percentage: number): number {
  return Math.floor((balance * percentage) / 100);
}

/**
 * Get SOL price from CoinGecko
 */
async function getSolPrice(): Promise<number> {
  try {
    const response = await fetch(
      "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
    );
    const data = await response.json();
    return data.solana.usd || 190;
  } catch (error) {
    console.error("Failed to fetch SOL price:", error);
  }
  return 190; // Default fallback price
}

/**
 * Execute a REAL trade on Solana using Jupiter DEX
 */
export async function executeTrade(
  connection: Connection,
  keypair: Keypair,
  params: TradeParams
): Promise<TradeResult> {
  const startTime = Date.now();

  try {
    console.log(`[Trade] ===== STARTING REAL TRADE EXECUTION =====`);
    console.log(`[Trade] Wallet: ${keypair.publicKey.toBase58()}`);
    console.log(`[Trade] Input Mint: ${params.inputMint}`);
    console.log(`[Trade] Output Mint: ${params.outputMint}`);
    console.log(`[Trade] Amount: ${params.amount}`);

    // Step 1: Get Jupiter quote
    console.log(`[Trade] Fetching Jupiter swap quote...`);
    
    const slippageBps = params.slippageBps || 150; // 1.5% default slippage
    const quoteUrl = `https://quote-api.jup.ag/v6/quote?inputMint=${params.inputMint}&outputMint=${params.outputMint}&amount=${params.amount}&slippageBps=${slippageBps}`;
    
    console.log(`[Trade] Quote URL: ${quoteUrl}`);
    
    const quoteResponse = await fetchWithRetry(quoteUrl, {
      maxRetries: 3,
      timeoutMs: 20000,
    });
    if (!quoteResponse.ok) {
      throw new Error(`Failed to get Jupiter quote: ${quoteResponse.statusText}`);
    }
    
    const quote = await quoteResponse.json();
    console.log(`[Trade] Quote received. Out amount: ${quote.outAmount}`);
    
    if (!quote.outAmount) {
      throw new Error(`Invalid quote response: no outAmount`);
    }

    // Step 2: Get swap transaction from Jupiter
    console.log(`[Trade] Building Jupiter swap transaction...`);
    
     const swapResponse = await fetchWithRetry('https://quote-api.jup.ag/v6/swap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        quoteResponse: quote,
        userPublicKey: keypair.publicKey.toBase58(),
        wrapAndUnwrapSol: true,
        dynamicComputeUnitLimit: true,
        prioritizationFeeLamports: 'auto',
      }),
      maxRetries: 3,
      timeoutMs: 20000,
    });
    if (!swapResponse.ok) {
      throw new Error(`Failed to get swap transaction: ${swapResponse.statusText}`);
    }
    
    const swapData = await swapResponse.json();
    if (!swapData.swapTransaction) {
      throw new Error(`Invalid swap response: no swapTransaction`);
    }
    
    console.log(`[Trade] Swap transaction received from Jupiter`);

    // Step 3: Deserialize and sign the transaction
    const swapTransactionBuf = Buffer.from(swapData.swapTransaction, 'base64');
    const transaction = VersionedTransaction.deserialize(swapTransactionBuf);
    
    console.log(`[Trade] Signing transaction...`);
    transaction.sign([keypair]);

    // Step 4: Send transaction
    console.log(`[Trade] Sending transaction to blockchain...`);
    const txHash = await connection.sendTransaction(transaction, {
      skipPreflight: false,
      maxRetries: 3,
    });

    console.log(`[Trade] ✅ Transaction sent: ${txHash}`);

    // Step 5: Wait for confirmation
    console.log(`[Trade] Waiting for confirmation...`);
    const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash();
    
    const confirmation = await connection.confirmTransaction(
      {
        signature: txHash,
        blockhash: blockhash,
        lastValidBlockHeight: lastValidBlockHeight,
      },
      "confirmed"
    );

    if (confirmation.value.err) {
      console.error(`[Trade] ❌ Transaction failed:`, confirmation.value.err);
      throw new Error(`Transaction failed: ${JSON.stringify(confirmation.value.err)}`);
    }

    console.log(`[Trade] ✅ Transaction confirmed!`);
    console.log(`[Trade] Execution time: ${Date.now() - startTime}ms`);
    console.log(`[Trade] ===== TRADE COMPLETED SUCCESSFULLY =====`);

    return {
      txHash,
      inputAmount: params.amount,
      outputAmount: parseInt(quote.outAmount),
      priceImpact: quote.priceImpactPct || 0,
      status: "success",
    };
  } catch (jupiterError) {
    console.warn(`[Trade] Jupiter swap failed, trying Raydium...`);
    try {
      const raydiumResult = await executeRaydiumSwap(connection, keypair, params);
      if (raydiumResult.status === "success") {
        return {
          txHash: raydiumResult.txHash,
          inputAmount: raydiumResult.inputAmount,
          outputAmount: raydiumResult.outputAmount,
          priceImpact: 0,
          status: "success",
        };
      }
    } catch (raydiumError) {
      console.error(`[Trade] Raydium fallback failed:`, raydiumError);
    }

    const errorMsg = String(jupiterError);
    console.error(`[Trade] TRADE FAILED:`, jupiterError);
    console.error(`[Trade] Error: ${errorMsg}`);
    console.error(`[Trade] Time: ${Date.now() - startTime}ms`);

    return {
      txHash: "",
      inputAmount: params.amount,
      outputAmount: 0,
      priceImpact: 0,
      status: "failed",
    };
  }
}

