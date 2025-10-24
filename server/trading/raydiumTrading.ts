/**
 * Raydium Trading Module
 * 
 * Alternative DEX for executing USDC/SOL swaps
 * Uses Raydium API for better reliability
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

export interface RaydiumSwapParams {
  inputMint: string;
  outputMint: string;
  amount: number;
  slippageBps?: number;
}

export interface RaydiumSwapResult {
  txHash: string;
  inputAmount: number;
  outputAmount: number;
  status: "success" | "failed";
}

/**
 * Get Raydium swap instructions
 */
export async function getRaydiumSwapInstructions(
  connection: Connection,
  params: RaydiumSwapParams,
  walletAddress: string
): Promise<any> {
  try {
    console.log(`[Raydium] Getting swap instructions...`);
    console.log(`[Raydium] Input: ${params.inputMint}`);
    console.log(`[Raydium] Output: ${params.outputMint}`);
    console.log(`[Raydium] Amount: ${params.amount}`);

    const slippageBps = params.slippageBps || 150; // 1.5% default

    // Get swap route from Raydium API
    const routeUrl = `https://api.raydium.io/v2/swap/route`;
    
    const routeResponse = await fetchWithRetry(routeUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        inputMint: params.inputMint,
        outputMint: params.outputMint,
        amount: params.amount.toString(),
        slippageBps: slippageBps,
        wallet: walletAddress,
      }),
      maxRetries: 3,
      timeoutMs: 15000,
    });

    if (!routeResponse.ok) {
      throw new Error(`Failed to get Raydium route: ${routeResponse.statusText}`);
    }

    const route = await routeResponse.json();
    console.log(`[Raydium] Route received`);
    console.log(`[Raydium] Out amount: ${route.outAmount}`);

    if (!route.outAmount) {
      throw new Error("Invalid route response: no outAmount");
    }

    // Get swap transaction from Raydium
    const swapUrl = `https://api.raydium.io/v2/swap/transaction`;
    
    const swapResponse = await fetchWithRetry(swapUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        route: route,
        wallet: walletAddress,
        wrapSol: true,
        unwrapSol: true,
      }),
      maxRetries: 3,
      timeoutMs: 15000,
    });

    if (!swapResponse.ok) {
      throw new Error(`Failed to get swap transaction: ${swapResponse.statusText}`);
    }

    const swapData = await swapResponse.json();
    console.log(`[Raydium] Swap transaction received`);

    return {
      transaction: swapData.transaction,
      outAmount: route.outAmount,
    };
  } catch (error) {
    console.error(`[Raydium] Error getting swap instructions:`, error);
    throw error;
  }
}

/**
 * Execute Raydium swap
 */
export async function executeRaydiumSwap(
  connection: Connection,
  keypair: Keypair,
  params: RaydiumSwapParams
): Promise<RaydiumSwapResult> {
  const startTime = Date.now();

  try {
    console.log(`[Raydium] ===== STARTING RAYDIUM SWAP =====`);
    console.log(`[Raydium] Wallet: ${keypair.publicKey.toBase58()}`);

    // Get swap instructions
    const swapData = await getRaydiumSwapInstructions(
      connection,
      params,
      keypair.publicKey.toBase58()
    );

    // Deserialize transaction
    console.log(`[Raydium] Deserializing transaction...`);
    const txBuf = Buffer.from(swapData.transaction, "base64");
    const transaction = VersionedTransaction.deserialize(txBuf);

    // Sign transaction
    console.log(`[Raydium] Signing transaction...`);
    transaction.sign([keypair]);

    // Send transaction
    console.log(`[Raydium] Sending transaction...`);
    const txHash = await connection.sendTransaction(transaction, {
      skipPreflight: false,
      maxRetries: 3,
    });

    console.log(`[Raydium] ✅ Transaction sent: ${txHash}`);

    // Wait for confirmation
    console.log(`[Raydium] Waiting for confirmation...`);
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
      console.error(`[Raydium] ❌ Transaction failed:`, confirmation.value.err);
      throw new Error(`Transaction failed: ${JSON.stringify(confirmation.value.err)}`);
    }

    console.log(`[Raydium] ✅ Transaction confirmed!`);
    console.log(`[Raydium] Execution time: ${Date.now() - startTime}ms`);
    console.log(`[Raydium] ===== SWAP COMPLETED SUCCESSFULLY =====`);

    return {
      txHash,
      inputAmount: params.amount,
      outputAmount: parseInt(swapData.outAmount),
      status: "success",
    };
  } catch (error) {
    const errorMsg = String(error);
    console.error(`[Raydium] ❌ SWAP FAILED:`, error);
    console.error(`[Raydium] Error message: ${errorMsg}`);
    console.error(`[Raydium] Execution time: ${Date.now() - startTime}ms`);
    console.error(`[Raydium] ===== SWAP FAILED =====`);

    return {
      txHash: "",
      inputAmount: params.amount,
      outputAmount: 0,
      status: "failed",
    };
  }
}

