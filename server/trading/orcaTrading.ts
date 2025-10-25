/**
 * Orca Trading Module
 * 
 * Orca DEX integration for USDC/SOL swaps
 * Orca supports the user's USDC variant (EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v)
 */

import {
  Connection,
  Keypair,
  PublicKey,
  VersionedTransaction,
} from "@solana/web3.js";
import { fetchWithRetry } from "./networkResilience";

const SOL_MINT = "So11111111111111111111111111111111111111112";
const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";

export interface OrcaSwapParams {
  inputMint: string;
  outputMint: string;
  amount: number;
  slippageBps?: number;
}

export interface OrcaSwapResult {
  txHash: string;
  inputAmount: number;
  outputAmount: number;
  status: "success" | "failed";
}

/**
 * Get Orca swap quote
 */
export async function getOrcaSwapQuote(
  params: OrcaSwapParams
): Promise<any> {
  try {
    console.log(`[Orca] Getting swap quote...`);
    console.log(`[Orca] Input: ${params.inputMint}`);
    console.log(`[Orca] Output: ${params.outputMint}`);
    console.log(`[Orca] Amount: ${params.amount}`);

    const slippageBps = params.slippageBps || 150; // 1.5% default

    // Orca API endpoint for quotes
    const quoteUrl = `https://api.mainnet.orca.so/v1/quote?inputMint=${params.inputMint}&outputMint=${params.outputMint}&amount=${params.amount}&slippageBps=${slippageBps}`;
    
    console.log(`[Orca] Quote URL: ${quoteUrl}`);

    const quoteResponse = await fetchWithRetry(quoteUrl, {
      maxRetries: 3,
      timeoutMs: 15000,
    });

    if (!quoteResponse.ok) {
      throw new Error(`Failed to get Orca quote: ${quoteResponse.statusText}`);
    }

    const quote = await quoteResponse.json();
    console.log(`[Orca] Quote received`);
    console.log(`[Orca] Out amount: ${quote.outAmount}`);

    if (!quote.outAmount) {
      throw new Error("Invalid quote response: no outAmount");
    }

    return quote;
  } catch (error) {
    console.error(`[Orca] Error getting quote:`, error);
    throw error;
  }
}

/**
 * Execute Orca swap
 */
export async function executeOrcaSwap(
  connection: Connection,
  keypair: Keypair,
  params: OrcaSwapParams
): Promise<OrcaSwapResult> {
  const startTime = Date.now();

  try {
    console.log(`[Orca] ===== STARTING ORCA SWAP =====`);
    console.log(`[Orca] Wallet: ${keypair.publicKey.toBase58()}`);

    // Get swap quote
    const quote = await getOrcaSwapQuote(params);

    // Get swap transaction from Orca
    console.log(`[Orca] Getting swap transaction...`);
    
    const swapUrl = `https://api.mainnet.orca.so/v1/swap`;
    
    const swapResponse = await fetchWithRetry(swapUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        quoteResponse: quote,
        userPublicKey: keypair.publicKey.toBase58(),
        wrapAndUnwrapSol: true,
        prioritizationFeeLamports: "auto",
      }),
      maxRetries: 3,
      timeoutMs: 15000,
    });

    if (!swapResponse.ok) {
      throw new Error(`Failed to get swap transaction: ${swapResponse.statusText}`);
    }

    const swapData = await swapResponse.json();
    if (!swapData.swapTransaction) {
      throw new Error("Invalid swap response: no swapTransaction");
    }

    console.log(`[Orca] Swap transaction received`);

    // Deserialize transaction
    console.log(`[Orca] Deserializing transaction...`);
    const txBuf = Buffer.from(swapData.swapTransaction, "base64");
    const transaction = VersionedTransaction.deserialize(txBuf);

    // Sign transaction
    console.log(`[Orca] Signing transaction...`);
    transaction.sign([keypair]);

    // Send transaction
    console.log(`[Orca] Sending transaction...`);
    const txHash = await connection.sendTransaction(transaction, {
      skipPreflight: false,
      maxRetries: 3,
    });

    console.log(`[Orca] ✅ Transaction sent: ${txHash}`);

    // Wait for confirmation
    console.log(`[Orca] Waiting for confirmation...`);
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
      console.error(`[Orca] ❌ Transaction failed:`, confirmation.value.err);
      throw new Error(`Transaction failed: ${JSON.stringify(confirmation.value.err)}`);
    }

    console.log(`[Orca] ✅ Transaction confirmed!`);
    console.log(`[Orca] Execution time: ${Date.now() - startTime}ms`);
    console.log(`[Orca] ===== SWAP COMPLETED SUCCESSFULLY =====`);

    return {
      txHash,
      inputAmount: params.amount,
      outputAmount: parseInt(quote.outAmount),
      status: "success",
    };
  } catch (error) {
    const errorMsg = String(error);
    console.error(`[Orca] ❌ SWAP FAILED:`, error);
    console.error(`[Orca] Error message: ${errorMsg}`);
    console.error(`[Orca] Execution time: ${Date.now() - startTime}ms`);
    console.error(`[Orca] ===== SWAP FAILED =====`);

    return {
      txHash: "",
      inputAmount: params.amount,
      outputAmount: 0,
      status: "failed",
    };
  }
}

