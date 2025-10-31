import { COOKIE_NAME } from "@shared/const";
import { getSessionCookieOptions } from "./_core/cookies";
import { systemRouter } from "./_core/systemRouter";
import { publicProcedure, router, protectedProcedure } from "./_core/trpc";
import { z } from "zod";
import {
  getTradingConfig,
  createTradingConfig,
  updateTradingConfig,
  getBotLogs,
  getTradeHistory,
  getTradeStats,
} from "./db";
import { TradingBotEngine, BotConfig } from "./trading/botEngine";
import { startBotForUser, stopBotForUser } from "./trading/botManager";


// Simple bot storage - one bot per user
const activeBots = new Map<string, { isRunning: boolean; balance: number; usdcBalance: number; currentPrice: number; lastSignal: any; lastTradeTime: Date; trend: string }>();

// Bot update loop timers
const botInstances = new Map<string, ReturnType<typeof setInterval>>();

// Fetch Hyperliquid balance
async function fetchHyperliquidBalance(walletAddress: string) {
  try {
    if (!walletAddress) {
      console.warn("[Bot] No wallet address provided for balance fetch");
      return { solBalance: 0, usdcBalance: 0 };
    }
    
    const response = await fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: "spotClearinghouseState",
        user: walletAddress,
      }),
    });
    
    if (!response.ok) {
      console.error(`[Bot] Hyperliquid API error: ${response.status} ${response.statusText}`);
      return { solBalance: 0, usdcBalance: 0 };
    }
    
    const data = await response.json();
    console.log("[Bot] Hyperliquid balance response:", data);
    
    if (data && data.balances) {
      let solBalance = 0;
      let usdcBalance = 0;
      
      for (const balance of data.balances) {
        if (balance.coin === "SOL" || balance.coin === "USOL") {
          solBalance = parseFloat(balance.total);
          console.log(`[Bot] Found ${balance.coin} balance: ${solBalance}`);
        }
        if (balance.coin === "USDC") {
          usdcBalance = parseFloat(balance.total);
          console.log(`[Bot] Found USDC balance: ${usdcBalance}`);
        }
      }
      
      console.log(`[Bot] Fetched balances - SOL: ${solBalance}, USDC: ${usdcBalance}`);
      return { solBalance, usdcBalance };
    } else {
      console.warn("[Bot] No balances in Hyperliquid response", data);
    }
  } catch (error) {
    console.error("[Bot] Error fetching Hyperliquid balance:", error);
  }
  return { solBalance: 0, usdcBalance: 0 };
}

// Fetch current SOL price
async function fetchCurrentPrice() {
  try {
    const response = await fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: "allMids",
      }),
    });
    
    if (!response.ok) {
      console.error(`[Bot] Hyperliquid price API error: ${response.status} ${response.statusText}`);
      return 0;
    }
    
    const data = await response.json();
    console.log("[Bot] Hyperliquid allMids response:", data);
    
    // Look for SOL price - it could be "SOL" or "@<index>" format
    let solPrice = 0;
    if (data["SOL"]) {
      solPrice = parseFloat(data["SOL"]);
    } else if (data["@1"]) {
      // Try common spot index for SOL/USDC
      solPrice = parseFloat(data["@1"]);
    } else {
      // Try to find any SOL-related key
      for (const key in data) {
        if (key.includes("SOL") || key.includes("@")) {
          solPrice = parseFloat(data[key]);
          console.log(`[Bot] Found SOL price at key ${key}: $${solPrice}`);
          break;
        }
      }
    }
    
    if (solPrice > 0) {
      console.log(`[Bot] Fetched SOL price: $${solPrice}`);
      return solPrice;
    } else {
      console.warn("[Bot] No SOL price data in Hyperliquid response");
    }
  } catch (error) {
    console.error("[Bot] Error fetching price:", error);
  }
  return 0;
}

// Update bot status with latest data
async function updateBotStatus(userId: string, walletAddress: string) {
  try {
    const { solBalance, usdcBalance } = await fetchHyperliquidBalance(walletAddress);
    const currentPrice = await fetchCurrentPrice();
    
    const botStatus = activeBots.get(userId);
    if (botStatus) {
      botStatus.balance = solBalance;
      botStatus.usdcBalance = usdcBalance;
      botStatus.currentPrice = currentPrice;
      botStatus.lastTradeTime = new Date();
      
      console.log(`[Bot] Updated status for ${userId}: SOL=${solBalance}, USDC=${usdcBalance}, Price=$${currentPrice}`);
    }
  } catch (error) {
    console.error("[Bot] Error updating bot status:", error);
  }
}

// Start bot update loop
function startBotUpdateLoop(userId: string, walletAddress: string) {
  // Clear any existing timer
  if (botInstances.has(userId)) {
    clearInterval(botInstances.get(userId));
  }
  
  // Update immediately
  updateBotStatus(userId, walletAddress);
  
  // Then update every 30 seconds
  const timer = setInterval(() => {
    updateBotStatus(userId, walletAddress);
  }, 30000);
  
  botInstances.set(userId, timer);
}

// Stop bot update loop
function stopBotUpdateLoop(userId: string) {
  if (botInstances.has(userId)) {
    clearInterval(botInstances.get(userId));
    botInstances.delete(userId);
  }
}

export const appRouter = router({
  system: systemRouter,

  auth: router({
    me: publicProcedure.query((opts) => opts.ctx.user),
    logout: publicProcedure.mutation(({ ctx }) => {
      const cookieOptions = getSessionCookieOptions(ctx.req);
      ctx.res.clearCookie(COOKIE_NAME, { ...cookieOptions, maxAge: -1 });
      return {
        success: true,
      } as const;
    }),
  }),

  trading: router({
    /**
     * Get or create trading configuration
     */
    getConfig: publicProcedure.query(async ({ ctx }) => {
      const userId = ctx.user?.id || "default_user";
      const config = await getTradingConfig(userId);
      return config || null;
    }),

    /**
     * Update trading configuration
     */
    updateConfig: publicProcedure
      .input(
        z.object({
          solanaPrivateKey: z.string().optional(),
          rpcUrl: z.string().optional(),
          period: z.number().min(1).max(100).optional(),
          multiplier: z.number().min(0.5).max(10).optional(),
          tradeAmountPercent: z.number().min(1).max(100).optional(),
          slippageTolerance: z.number().min(0.1).max(5).optional(),
          autoTrade: z.boolean().optional(),
        })
      )
      .mutation(async ({ ctx, input }) => {
        const userId = ctx.user?.id || "default_user";
        let config = await getTradingConfig(userId);

        if (!config) {
          // Create new config
          const configId = `config_${userId}_${Date.now()}`;
          const newConfig = {
            id: configId,
            userId: userId,
            solanaPrivateKey: input.solanaPrivateKey || "",
            rpcUrl: input.rpcUrl || "https://api.mainnet-beta.solana.com",
            walletAddress: "", // Will be derived from private key
            period: input.period || 10,
            multiplier: (input.multiplier ? parseFloat(input.multiplier.toString()) : 3.0).toString(),
            tradeAmountPercent: input.tradeAmountPercent || 50,
            slippageTolerance: (input.slippageTolerance ? parseFloat(input.slippageTolerance.toString()) : 1.5).toString(),
            isActive: false,
            autoTrade: input.autoTrade || false,
          };

          await createTradingConfig(newConfig);
          config = newConfig as any;
        } else {
          // Update existing config
          const updates: any = {};
          if (input.solanaPrivateKey) updates.solanaPrivateKey = input.solanaPrivateKey;
          if (input.rpcUrl) updates.rpcUrl = input.rpcUrl;
          if (input.period !== undefined) updates.period = input.period;
          if (input.multiplier !== undefined) updates.multiplier = input.multiplier.toString();
          if (input.tradeAmountPercent !== undefined) updates.tradeAmountPercent = input.tradeAmountPercent;
          if (input.slippageTolerance !== undefined) updates.slippageTolerance = input.slippageTolerance.toString();
          if (input.autoTrade !== undefined) updates.autoTrade = input.autoTrade;

          await updateTradingConfig(config.id, updates);
        }

        return config;
      }),

    /**
     * Start the trading bot
     */
    startBot: publicProcedure.mutation(async ({ ctx }) => {
      const userId = ctx.user?.id || "default_user";
      console.log("[Router] startBot called, userId:", userId);
      
      try {
        // Get Hyperliquid wallet address from environment
        const walletAddress = process.env.HYPERLIQUID_WALLET_ADDRESS;
        console.log("[Router] Hyperliquid wallet address:", walletAddress);
        
        if (!walletAddress) {
          throw new Error("Hyperliquid wallet address not configured in environment");
        }
        
        // Simply mark the bot as running
        activeBots.set(userId, {
          isRunning: true,
          balance: 0,
          usdcBalance: 0,
          currentPrice: 0,
          lastSignal: null,
          lastTradeTime: new Date(),
          trend: "down",
        });
        
        // Start the update loop to fetch balances and prices
        startBotUpdateLoop(userId, walletAddress);
        console.log("[Router] Bot update loop started for user:", userId, "with wallet:", walletAddress);
        
        console.log("[Router] Bot started for user:", userId);
        return { success: true };
      } catch (error) {
        console.error("[Router] Error in startBot:", error);
        throw error;
      }
    }),


    /**
     * Stop the trading bot
     */
    stopBot: publicProcedure.mutation(async ({ ctx }) => {
      const userId = ctx.user?.id || "default_user";
      
      // Stop the update loop
      stopBotUpdateLoop(userId);
      
      // Mark bot as stopped
      const botStatus = activeBots.get(userId);
      if (botStatus) {
        botStatus.isRunning = false;
      }
      
      console.log("[Router] Bot stopped for user:", userId);
      return { success: true };
    }),

    /**
     * Get bot status
     */
    getBotStatus: publicProcedure.query(async ({ ctx }) => {
      const userId = ctx.user?.id || "default_user";
      console.log("[Router] getBotStatus called, userId:", userId);
      console.log("[Router] All active bots:", Array.from(activeBots.keys()));
      
      const botStatus = activeBots.get(userId);
      if (botStatus) {
        console.log("[Router] Found bot for user:", userId, "isRunning:", botStatus.isRunning);
        return botStatus;
      }
      
      // If bot is not running, return default stopped status
      console.log("[Router] No bot found for user:", userId);
      return {
        isRunning: false,
        currentPrice: 0,
        balance: 0,
        usdcBalance: 0,
        trend: "neutral",
        lastSignal: null,
        lastTradeTime: null,
      };
    }),

    /**
     * Get bot logs
     */
    getLogs: publicProcedure
      .input(
        z.object({
          limit: z.number().min(1).max(500).default(100),
        })
      )
      .query(async ({ ctx, input }) => {
        const userId = ctx.user?.id || "default_user";
        const config = await getTradingConfig(userId);
        if (!config) return [];

        return await getBotLogs(config.id, input.limit);
      }),

    /**
     * Get trade history
     */
    getTradeHistory: publicProcedure
      .input(
        z.object({
          limit: z.number().min(1).max(500).default(50),
        })
      )
      .query(async ({ ctx, input }) => {
        const userId = ctx.user?.id || "default_user";
        return await getTradeHistory(userId, input.limit);
      }),

    /**
     * Get trade statistics
     */
    getTradeStats: publicProcedure.query(async ({ ctx }) => {
      const userId = ctx.user?.id || "default_user";
      return await getTradeStats(userId);
    }),

    /**
     * Execute a manual test transaction on Hyperliquid
     */
    testTransaction: publicProcedure
      .input(
        z.object({
          transactionType: z.enum(["buy", "sell"]),
          amount: z.number().min(0.001).max(1000),
        })
      )
      .mutation(async ({ ctx, input }) => {
        const userId = ctx.user?.id || "default_user";
        
        // Check Hyperliquid credentials
        const hyperliquidPrivateKey = process.env.HYPERLIQUID_PRIVATE_KEY;
        const hyperliquidWalletAddress = process.env.HYPERLIQUID_WALLET_ADDRESS;
        
        if (!hyperliquidPrivateKey) {
          throw new Error("Hyperliquid private key not configured");
        }
        if (!hyperliquidWalletAddress) {
          throw new Error("Hyperliquid wallet address not configured");
        }

        try {
          // Import Hyperliquid trading module
          const { executeHyperliquidSpotTrade, getSolUsdcPrice } = await import("./trading/hyperliquidSpot");
          
          // Get current SOL price for order
          const solPrice = await getSolUsdcPrice();
          if (solPrice === 0) {
            throw new Error("Could not fetch SOL price");
          }
          
          // Execute trade on Hyperliquid
          const result = await executeHyperliquidSpotTrade(
            hyperliquidPrivateKey,
            hyperliquidWalletAddress,
            {
              asset: 10000, // SOL spot asset ID
              isBuy: input.transactionType === "buy",
              price: solPrice.toString(),
              size: input.amount.toString(),
              reduceOnly: false,
            }
          );

          return {
            success: result.status === "success",
            orderId: result.orderId,
            message: result.message,
            timestamp: new Date().toISOString(),
          };
        } catch (error) {
          console.error("Test transaction error:", error);
          throw new Error(`Test transaction failed: ${error}`);
        }
      }),
  }),
});

export type AppRouter = typeof appRouter;

