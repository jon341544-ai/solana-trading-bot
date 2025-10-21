/**
 * Bot Manager - Manages persistent bot instances
 * 
 * Keeps track of running bots and ensures they continue running
 * even when the web page is closed. Bots are stored in memory
 * and their state is persisted to the database.
 */

import { TradingBotEngine } from "./botEngine";
import { getDb, tradingConfigs } from "../db";
import { BotConfig } from "./botEngine";
import { eq } from "drizzle-orm";

// Global map of running bots (userId -> bot instance)
const activeBots = new Map<string, TradingBotEngine>();

/**
 * Start a bot for a user
 */
export async function startBotForUser(userId: string, config: BotConfig): Promise<boolean> {
  try {
    // Check if bot is already running
    if (activeBots.has(userId)) {
      console.log(`[BotManager] Bot already running for user ${userId}`);
      return true;
    }

    // Create and start new bot
    const bot = new TradingBotEngine(config);
    await bot.start();

    // Store in active bots map
    activeBots.set(userId, bot);

    // Update database to mark bot as active
    const db = await getDb();
    if (db) {
      await db
        .update(tradingConfigs)
        .set({ isActive: true })
        .where(eq(tradingConfigs.id, config.configId));
    }

    console.log(`[BotManager] Started bot for user ${userId}`);
    return true;
  } catch (error) {
    console.error(`[BotManager] Failed to start bot for user ${userId}:`, error);
    return false;
  }
}

/**
 * Stop a bot for a user
 */
export async function stopBotForUser(userId: string): Promise<boolean> {
  try {
    const bot = activeBots.get(userId);
    if (!bot) {
      console.log(`[BotManager] No bot running for user ${userId}`);
      return true;
    }

    // Stop the bot
    await bot.stop();

    // Remove from active bots map
    activeBots.delete(userId);

    // Update database to mark bot as inactive
    const db = await getDb();
    if (db) {
      const config = await db
        .select()
        .from(tradingConfigs)
        .where(eq(tradingConfigs.userId, userId))
        .limit(1);

      if (config.length > 0) {
        await db
          .update(tradingConfigs)
          .set({ isActive: false })
          .where(eq(tradingConfigs.id, config[0].id));
      }
    }

    console.log(`[BotManager] Stopped bot for user ${userId}`);
    return true;
  } catch (error) {
    console.error(`[BotManager] Failed to stop bot for user ${userId}:`, error);
    return false;
  }
}

/**
 * Get bot status for a user
 */
export function getBotStatus(userId: string) {
  const bot = activeBots.get(userId);
  if (!bot) {
    return { isRunning: false };
  }
  return bot.getStatus();
}

/**
 * Check if bot is running for a user
 */
export function isBotRunning(userId: string): boolean {
  return activeBots.has(userId);
}

/**
 * Get all active bots
 */
export function getActiveBots(): Map<string, TradingBotEngine> {
  return activeBots;
}

/**
 * Restore bots from database on server startup
 * This ensures bots continue running if the server restarts
 */
export async function restoreBotsFromDatabase(): Promise<void> {
  try {
    const db = await getDb();
    if (!db) {
      console.warn("[BotManager] Database not available, skipping bot restoration");
      return;
    }

    // Get all active bot configurations
    const activeConfigs = await db
      .select()
      .from(tradingConfigs)
      .where(eq(tradingConfigs.isActive, true));

    console.log(`[BotManager] Found ${activeConfigs.length} active bots to restore`);

    // Start each bot
    for (const config of activeConfigs) {
      const botConfig: BotConfig = {
        userId: config.userId,
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

      const success = await startBotForUser(config.userId, botConfig);
      if (success) {
        console.log(`[BotManager] Restored bot for user ${config.userId}`);
      } else {
        console.error(`[BotManager] Failed to restore bot for user ${config.userId}`);
      }
    }
  } catch (error) {
    console.error("[BotManager] Failed to restore bots from database:", error);
  }
}

/**
 * Shutdown all bots gracefully
 */
export async function shutdownAllBots(): Promise<void> {
  console.log(`[BotManager] Shutting down ${activeBots.size} bots...`);

  const botEntries = Array.from(activeBots.entries());
  for (const [userId, bot] of botEntries) {
    try {
      await bot.stop();
      console.log(`[BotManager] Stopped bot for user ${userId}`);
    } catch (error) {
      console.error(`[BotManager] Error stopping bot for user ${userId}:`, error);
    }
  }

  activeBots.clear();
  console.log("[BotManager] All bots shut down");
}

