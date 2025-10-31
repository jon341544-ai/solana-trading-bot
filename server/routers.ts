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
import { startBotForUser, stopBotForUser, getBotStatus as getBotStatusFromManager, getAllBotUserIds } from "./trading/botManager";

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
        let config = await getTradingConfig(userId);
        console.log("[Router] Found config:", config ? "yes" : "no");
        
        if (!config) {
          const hyperliquidPrivateKey = process.env.HYPERLIQUID_PRIVATE_KEY;
          const hyperliquidWalletAddress = process.env.HYPERLIQUID_WALLET_ADDRESS;
          console.log("[Router] Creating config, creds available:", !!(hyperliquidPrivateKey && hyperliquidWalletAddress));
          
          if (!hyperliquidPrivateKey || !hyperliquidWalletAddress) {
            throw new Error("No trading configuration found and Hyperliquid credentials not available");
          }
          
          const configId = `config_${userId}_${Date.now()}`;
          const newConfig = {
            id: configId,
            userId: userId,
            solanaPrivateKey: "",
            rpcUrl: "https://api.mainnet-beta.solana.com",
            walletAddress: hyperliquidWalletAddress,
            period: 10,
            multiplier: "3.0",
            tradeAmountPercent: 50,
            slippageTolerance: "1.5",
            isActive: true,
            autoTrade: true,
          };
          console.log("[Router] Creating new config:", configId);
          await createTradingConfig(newConfig);
          config = newConfig as any;
        }
        
        const hyperliquidPrivateKey = process.env.HYPERLIQUID_PRIVATE_KEY;
        const hyperliquidWalletAddress = process.env.HYPERLIQUID_WALLET_ADDRESS;
        
        if (!config) {
          throw new Error("Trading configuration not found");
        }
        
        const botConfig: BotConfig = {
          userId: config.userId,
          configId: config.id,
          privateKey: config.solanaPrivateKey || "",
          rpcUrl: config.rpcUrl || "https://api.mainnet-beta.solana.com",
          walletAddress: config.walletAddress || "",
          period: config.period || 10,
          multiplier: parseFloat((config.multiplier || "3.0").toString()),
          tradeAmountPercent: config.tradeAmountPercent || 50,
          slippageTolerance: parseFloat((config.slippageTolerance || "1.5").toString()),
          autoTrade: config.autoTrade || false,
          hyperliquidPrivateKey: hyperliquidPrivateKey || undefined,
          hyperliquidWalletAddress: hyperliquidWalletAddress || undefined,
          useHyperliquid: !!(hyperliquidPrivateKey && hyperliquidWalletAddress),
        };
        
        console.log("[Router] Starting bot, useHyperliquid:", botConfig.useHyperliquid);
        const success = await startBotForUser(userId, botConfig);
        console.log("[Router] Bot start result:", success);
        
        return { success };
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
      const success = await stopBotForUser(userId);
      return { success };
    }),

    /**
     * Get bot status
     */
    getBotStatus: publicProcedure.query(async ({ ctx }) => {
      const userId = ctx.user?.id || "default_user";
      console.log("[Router] getBotStatus called, userId:", userId);
      console.log("[Router] All active bot userIds:", getAllBotUserIds());
      // Always check the bot manager first - this is the source of truth
      const botStatus = getBotStatusFromManager(userId);
      if (botStatus && botStatus.isRunning) {
        return botStatus;
      }
      // If bot is not running, return default stopped status
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
     * Execute a manual test transaction
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
        const config = await getTradingConfig(userId);
        if (!config) {
          throw new Error("No trading configuration found");
        }

        if (!config.solanaPrivateKey) {
          throw new Error("Private key not configured");
        }

        const { createConnection, createKeypairFromBase58, executeTrade } = await import("./trading/solanaTrading");
        try {
          const connection = createConnection(config.rpcUrl || "https://api.mainnet-beta.solana.com");
          const keypair = createKeypairFromBase58(config.solanaPrivateKey);

          const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
          const SOL_MINT = "So11111111111111111111111111111111111111112";
          
          let tradeAmount: number;
          if (input.transactionType === "buy") {
            tradeAmount = Math.floor(input.amount * 1e6);
          } else {
            tradeAmount = Math.floor(input.amount * 1e9);
          }
          
          const slippageBps = Math.floor((config.slippageTolerance ? parseFloat(config.slippageTolerance.toString()) : 1.5) * 100);

          const result = await executeTrade(
            connection,
            keypair,
            {
              inputMint: input.transactionType === "buy" ? USDC_MINT : SOL_MINT,
              outputMint: input.transactionType === "buy" ? SOL_MINT : USDC_MINT,
              amount: tradeAmount,
              slippageBps: slippageBps,
            }
          );

          return {
            success: result.status === "success",
            txHash: result.txHash,
            error: result.status === "failed" ? "Trade execution failed" : undefined,
            inputAmount: result.inputAmount,
            outputAmount: result.outputAmount,
            priceImpact: result.priceImpact,
          };
        } catch (error) {
          console.error("Test transaction error:", error);
          throw new Error(`Test transaction failed: ${error}`);
        }
      }),
  }),
});

export type AppRouter = typeof appRouter;

