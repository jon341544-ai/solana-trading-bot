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
  getBotStatus as getDbBotStatus,
  upsertBotStatus,
} from "./db";
import { TradingBotEngine, BotConfig } from "./trading/botEngine";
import { startBotForUser, stopBotForUser } from "./trading/botManager";
import { PerpsTradingEngine, PerpsTradingConfig } from "./trading/perpsTradingEngine";
import { fetchPerpsBalance, fetchCurrentPrice as fetchPerpPrice } from "./hyperliquid/perpsApi";


// Simple bot storage - one bot per user
const activeBots = new Map<string, { isRunning: boolean; balance: number; usdcBalance: number; currentPrice: number; lastSignal: any; lastTradeTime: Date; trend: string }>();

// Perps trading engines - one per user
const perpsTradingEngines = new Map<string, PerpsTradingEngine>();

// Bot update loop timers
const botInstances = new Map<string, ReturnType<typeof setInterval>>();

// Fetch Hyperliquid balance
async function fetchHyperliquidBalance(walletAddress: string) {
  try {
    if (!walletAddress) {
      console.warn("[Bot] ⚠️ No wallet address provided for balance fetch");
      return { solBalance: 0, usdcBalance: 0 };
    }
    
    console.log(`[Bot] 🔍 Fetching balance for wallet: ${walletAddress}`);
    
    const requestBody = {
      type: "spotClearinghouseState",
      user: walletAddress.toLowerCase(),
    };
    console.log("[Bot] 📤 Request body:", JSON.stringify(requestBody));
    
    const response = await fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    });
    
    console.log(`[Bot] 📨 Response status: ${response.status} ${response.statusText}`);
    
    if (!response.ok) {
      console.error(`[Bot] ❌ Hyperliquid API error: ${response.status} ${response.statusText}`);
      const errorText = await response.text();
      console.error("[Bot] Error response body:", errorText);
      return { solBalance: 0, usdcBalance: 0 };
    }
    
    const data = await response.json();
    console.log("[Bot] 📥 Hyperliquid balance response:", JSON.stringify(data));
    
    if (data && data.balances && Array.isArray(data.balances)) {
      let solBalance = 0;
      let usdcBalance = 0;
      
      console.log(`[Bot] Found ${data.balances.length} balance entries`);
      
      for (const balance of data.balances) {
        console.log(`[Bot] Processing balance: coin=${balance.coin}, total=${balance.total}`);
        if (balance.coin === "SOL" || balance.coin === "USOL") {
          solBalance = parseFloat(balance.total);
          console.log(`[Bot] ✅ Found ${balance.coin} balance: ${solBalance}`);
        }
        if (balance.coin === "USDC") {
          usdcBalance = parseFloat(balance.total);
          console.log(`[Bot] ✅ Found USDC balance: ${usdcBalance}`);
        }
      }
      
      console.log(`[Bot] ✅ Final balances - SOL: ${solBalance}, USDC: ${usdcBalance}`);
      return { solBalance, usdcBalance };
    } else {
      console.warn("[Bot] ⚠️ No balances in Hyperliquid response", JSON.stringify(data));
    }
  } catch (error) {
    console.error("[Bot] ❌ Error fetching Hyperliquid balance:", error);
  }
  return { solBalance: 0, usdcBalance: 0 };
}

// Fetch SOL price from Hyperliquid
async function fetchSOLPrice() {
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
    console.log(`[Bot] updateBotStatus called for userId=${userId}, wallet=${walletAddress}`);
    const { solBalance, usdcBalance } = await fetchHyperliquidBalance(walletAddress);
    const currentPrice = await fetchCurrentPrice();
    
    console.log(`[Bot] Fetched data: SOL=${solBalance}, USDC=${usdcBalance}, Price=$${currentPrice}`);
    
    const botStatus = activeBots.get(userId);
    console.log(`[Bot] Bot status exists: ${!!botStatus}`);
    
    if (botStatus) {
      botStatus.balance = solBalance;
      botStatus.usdcBalance = usdcBalance;
      botStatus.currentPrice = currentPrice;
      botStatus.lastTradeTime = new Date();
      
      // Also save to database (with error handling)
      try {
        await upsertBotStatus(userId, {
          balance: solBalance.toString(),
          usdcBalance: usdcBalance.toString(),
          currentPrice: currentPrice.toString(),
        });
      } catch (dbError) {
        console.warn("[Bot] Database save failed, but in-memory state is updated:", (dbError as any).message?.split('\n')[0]);
      }
      
      console.log(`[Bot] ✅ Updated status for ${userId}: SOL=${solBalance}, USDC=${usdcBalance}, Price=$${currentPrice}`);
    } else {
      console.warn(`[Bot] ⚠️ Bot status not found for userId=${userId}`);
    }
  } catch (error) {
    console.error("[Bot] ❌ Error updating bot status:", error);
  }
}

// Start bot update loop
function startBotUpdateLoop(userId: string, walletAddress: string) {
  console.log("[Bot] Starting update loop for user:", userId);
  
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
  console.log("[Bot] Update loop started");
}

// Stop bot update loop
function stopBotUpdateLoop(userId: string) {
  if (botInstances.has(userId)) {
    clearInterval(botInstances.get(userId));
    botInstances.delete(userId);
  }
}


// Perps bot update loop
function startPerpsBotUpdateLoop(userId: string, walletAddress: string, perpEngine: PerpsTradingEngine) {
  // Clear any existing timer
  if (botInstances.has(userId)) {
    clearInterval(botInstances.get(userId));
  }
  
  // Update immediately
  updatePerpsBotStatus(userId, perpEngine);
  
  // Then update every 30 seconds
  const timer = setInterval(() => {
    updatePerpsBotStatus(userId, perpEngine);
  }, 30000);
  
  botInstances.set(userId, timer);
}

// Update Perps bot status
async function updatePerpsBotStatus(userId: string, perpEngine: PerpsTradingEngine) {
  try {
    const currentPrice = await fetchPerpPrice();
    const stats = perpEngine.getStats();
    const position = perpEngine.getCurrentPosition();
    
    // Update in-memory state
    const botState = activeBots.get(userId);
    if (botState) {
      botState.currentPrice = currentPrice;
      botState.balance = stats.currentBalance;
      botState.lastTradeTime = new Date();
      
      // Determine trend based on position
      if (position) {
        botState.trend = position.side === "long" ? "up" : "down";
      }
    }
    
    console.log(`[Perps] Updated bot status - Price: $${currentPrice.toFixed(2)}, Balance: $${stats.currentBalance.toFixed(2)}`);
  } catch (error) {
    console.error("[Perps] Error updating bot status:", error);
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
     * Start the trading bot (Hyperliquid Spot trading)
     */
    startBot: publicProcedure.mutation(async ({ ctx }) => {
      const userId = ctx.user?.id || "default_user";
      const walletAddress = "0xf8a97533ced45b00ea479dd3e3b0e3602eb0e433";
      
      console.log("[Bot] Starting Spot trading bot for user:", userId);
      console.log("[Bot] Using wallet:", walletAddress);
      
      try {
        // Fetch initial balance from Spot account
        const { solBalance, usdcBalance } = await fetchHyperliquidBalance(walletAddress);
        const currentPrice = await fetchSOLPrice();
        
        console.log(`[Bot] Spot balance: SOL=${solBalance.toFixed(4)}, USDC=${usdcBalance.toFixed(2)}, Price=$${currentPrice.toFixed(2)}`);
        
        // Update bot status
        activeBots.set(userId, {
          isRunning: true,
          balance: solBalance,
          usdcBalance: usdcBalance,
          currentPrice: currentPrice,
          lastSignal: null,
          lastTradeTime: new Date(),
          trend: "down",
        });
        
        console.log("[Bot] Spot trading bot started successfully!");
        return { success: true };
      } catch (error) {
        console.error("[Bot] Error starting bot:", error);
        throw error;
      }
    }),


  stopBot: publicProcedure.mutation(async ({ ctx }) => {
      const userId = ctx.user?.id || "default_user";
      console.log("[Bot] Stopping bot for user:", userId);
      
      try {
        // Stop the update loop
        stopBotUpdateLoop(userId);
        console.log("[Bot] Update loop stopped");
        
        // Remove from active bots
        activeBots.delete(userId);
        console.log("[Bot] Removed from active bots");
        
        // Clean up any Perps engines if they exist
        const perpEngine = perpsTradingEngines.get(userId);
        if (perpEngine) {
          perpsTradingEngines.delete(userId);
          console.log("[Bot] Cleaned up Perps engine");
        }
        
        console.log("[Bot] Bot stopped successfully for user:", userId);
        return { success: true };
      } catch (error) {
        console.error("[Bot] Error stopping bot:", error);
        throw error;
      }
    }),

    /**
     * Manually refresh bot balance and price
     */
    refreshBalance: publicProcedure.mutation(async ({ ctx }) => {
      const userId = ctx.user?.id || "default_user";
      const walletAddress = "0xf8a97533ced45b00ea479dd3e3b0e3602eb0e433";
      
      console.log("[Router] refreshBalance called for user:", userId);
      
      try {
        // Fetch balance directly from Hyperliquid
        const { solBalance, usdcBalance } = await fetchHyperliquidBalance(walletAddress);
        const currentPrice = await fetchSOLPrice();
        
        console.log(`[Router] Fetched balance: SOL=${solBalance}, USDC=${usdcBalance}, Price=$${currentPrice}`);
        
        // Update in-memory state if bot exists
        let botStatus = activeBots.get(userId);
        if (!botStatus) {
          // Create a new bot status if it doesn't exist
          botStatus = {
            isRunning: false,
            balance: solBalance,
            usdcBalance: usdcBalance,
            currentPrice: currentPrice,
            lastSignal: null,
            lastTradeTime: new Date(),
            trend: "down",
          };
          activeBots.set(userId, botStatus);
        } else {
          // Update existing bot status
          botStatus.balance = solBalance;
          botStatus.usdcBalance = usdcBalance;
          botStatus.currentPrice = currentPrice;
          botStatus.lastTradeTime = new Date();
        }
        
        console.log("[Router] Returning refreshed balance:", botStatus);
        return botStatus;
      } catch (error) {
        console.error("[Router] Error refreshing balance:", error);
        return { isRunning: false, balance: 0, usdcBalance: 0, currentPrice: 0, lastSignal: null, lastTradeTime: new Date(), trend: "down" };
      }
    }),

    /**
     * Get bot status
     */
    getBotStatus: publicProcedure.query(async ({ ctx }) => {
      const userId = ctx.user?.id || "default_user";
      console.log("[Router] getBotStatus called, userId:", userId);
      
      // Try to get from database first
      try {
        const dbStatus = await getDbBotStatus(userId);
        if (dbStatus) {
          console.log("[Router] Found bot status in DB for user:", userId, "balance:", dbStatus.balance);
          return {
            isRunning: dbStatus.isRunning,
            currentPrice: parseFloat(dbStatus.currentPrice?.toString() || "0"),
            balance: parseFloat(dbStatus.balance?.toString() || "0"),
            usdcBalance: parseFloat(dbStatus.usdcBalance?.toString() || "0"),
            trend: dbStatus.trend || "neutral",
            lastSignal: dbStatus.lastSignal,
            lastTradeTime: dbStatus.lastTradeTime,
          };
        }
      } catch (dbError) {
        console.warn("[Router] Database query failed, falling back to in-memory state");
      }
      
      // Fallback to in-memory state
      const botState = activeBots.get(userId);
      if (botState) {
        console.log("[Router] Using in-memory bot state for user:", userId, "balance:", botState.balance);
        return {
          isRunning: botState.isRunning,
          currentPrice: botState.currentPrice,
          balance: botState.balance,
          usdcBalance: botState.usdcBalance,
          trend: botState.trend,
          lastSignal: botState.lastSignal,
          lastTradeTime: botState.lastTradeTime,
        };
      }
      
      // If bot is not found anywhere, return default stopped status
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
        try {
          // Import Hyperliquid trading module
          const { getSolUsdcPrice } = await import("./trading/hyperliquidSpot");
          
          // Get current SOL price
          const solPrice = await getSolUsdcPrice();
          if (solPrice === 0) {
            throw new Error("Could not fetch SOL price");
          }
          
          // Calculate order value
          const orderValue = input.amount * solPrice;
          
          return {
            success: true,
            message: `Test ${input.transactionType.toUpperCase()} order: ${input.amount} SOL @ $${solPrice.toFixed(2)} = $${orderValue.toFixed(2)}`,
            price: solPrice,
            amount: input.amount,
            total: orderValue,
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

