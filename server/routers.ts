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
import { startBotForUser, stopBotForUser, getBotStatus as getBotStatusFromManager, isBotRunning } from "./trading/botManager";

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
    getConfig: protectedProcedure.query(async ({ ctx }) => {
      const config = await getTradingConfig(ctx.user.id);
      return config || null;
    }),

    /**
     * Update trading configuration
     */
    updateConfig: protectedProcedure
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
        let config = await getTradingConfig(ctx.user.id);

        if (!config) {
          // Create new config
          const configId = `config_${ctx.user.id}_${Date.now()}`;
          const newConfig = {
            id: configId,
            userId: ctx.user.id,
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
    startBot: protectedProcedure.mutation(async ({ ctx }) => {
      const config = await getTradingConfig(ctx.user.id);

      if (!config) {
        throw new Error("Trading configuration not found. Please set up your configuration first.");
      }

      if (!config.solanaPrivateKey) {
        throw new Error("Private key not configured");
      }

      // Check if bot is already running
      if (isBotRunning(ctx.user.id)) {
        return { success: true, message: "Bot is already running" };
      }

      // Create and start bot using the bot manager
      const botConfig: BotConfig = {
        userId: ctx.user.id,
        configId: config.id,
        privateKey: config.solanaPrivateKey,
        rpcUrl: config.rpcUrl || "https://api.mainnet-beta.solana.com",
        walletAddress: config.walletAddress || "",
        period: config.period || 10,
        multiplier: parseFloat((config.multiplier || "3.0").toString()),
        tradeAmountPercent: config.tradeAmountPercent || 50,
        slippageTolerance: parseFloat((config.slippageTolerance || "1.5").toString()),
        autoTrade: config.autoTrade || false,
      };

      const success = await startBotForUser(ctx.user.id, botConfig);

      return { success, message: success ? "Bot started successfully" : "Failed to start bot" };
    }),

    /**
     * Stop the trading bot
     */
    stopBot: protectedProcedure.mutation(async ({ ctx }) => {
      const success = await stopBotForUser(ctx.user.id);
      return { success, message: success ? "Bot stopped successfully" : "Failed to stop bot" };
    }),

    /**
     * Get bot status
     */
    getBotStatus: protectedProcedure.query(async ({ ctx }) => {
      const botStatus = getBotStatusFromManager(ctx.user.id);

      if (!botStatus || !botStatus.isRunning) {
        return {
          isRunning: false,
          balance: 0,
          lastPrice: 0,
          lastSignal: null,
          lastTradeTime: null,
        };
      }
      return botStatus as any;
    }),

    /**
     * Get bot logs
     */
    getLogs: protectedProcedure
      .input(
        z.object({
          limit: z.number().min(1).max(500).default(100),
        })
      )
      .query(async ({ ctx, input }) => {
        const config = await getTradingConfig(ctx.user.id);
        if (!config) return [];

        return await getBotLogs(config.id, input.limit);
      }),

    /**
     * Get trade history
     */
    getTradeHistory: protectedProcedure
      .input(
        z.object({
          limit: z.number().min(1).max(500).default(50),
        })
      )
      .query(async ({ ctx, input }) => {
        return await getTradeHistory(ctx.user.id, input.limit);
      }),

    /**
     * Get trade statistics
     */
    getTradeStats: protectedProcedure.query(async ({ ctx }) => {
      return await getTradeStats(ctx.user.id);
    }),
  }),
});

export type AppRouter = typeof appRouter;

