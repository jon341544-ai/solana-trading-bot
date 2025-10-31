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

    // Create new bot
    const bot = new TradingBotEngine(config);
    
    // Store in active bots map BEFORE starting (so we can query it even if start fails)
    activeBots.set(userId, bot);
    console.log(`[BotManager] Created bot for user ${userId}`);
    
    // Start the bot
    await bot.start();
    console.log(`[BotManager] Started bot for user ${userId}`);
    
    // Update database to mark bot as active
    const db = await getDb();
    if (db) {
      await db
        .update(tradingConfigs)
        .set({ isActive: true })
        .where(eq(tradingConfigs.id, config.configId));
    }
    
    return true;
  } catch (error) {
    console.error(`[BotManager] Failed to start bot for user ${userId}:`, error);
    // Keep the bot in the map so we can see its error state
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
      // Find the config for this user
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
    return {
      isRunning: false,
      balance: 0,
      usdcBalance: 0,
      currentPrice: 0,
      lastSignal: null,
      lastTradeTime: new Date(),
      trend: "down",
    };
  }
  return bot.getStatus();
}

/**
 * Get all active bots
 */
export function getActiveBots() {
  return Array.from(activeBots.entries()).map(([userId, bot]) => ({
    userId,
    status: bot.getStatus(),
  }));
}

/**
 * Restore bots from database (called on server startup)
 */
export async function restoreBotsFromDatabase(): Promise<void> {
  try {
    const db = await getDb();
    if (!db) return;
    
    // Get all active configs
    const configs = await db
      .select()
      .from(tradingConfigs)
      .where(eq(tradingConfigs.isActive, true));
    
    console.log(`[BotManager] Restoring ${configs.length} bots from database`);
    
    // Start each bot
    for (const config of configs) {
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
        hyperliquidPrivateKey: process.env.HYPERLIQUID_PRIVATE_KEY,
        hyperliquidWalletAddress: process.env.HYPERLIQUID_WALLET_ADDRESS,
        useHyperliquid: !!(process.env.HYPERLIQUID_PRIVATE_KEY && process.env.HYPERLIQUID_WALLET_ADDRESS),
      };
      
      await startBotForUser(config.userId, botConfig);
    }
  } catch (error) {
    console.error("[BotManager] Failed to restore bots:", error);
  }
}

/**
 * Shutdown all bots (called on server shutdown)
 */
export async function shutdownAllBots(): Promise<void> {
  try {
    const bots = Array.from(activeBots.keys());
    console.log(`[BotManager] Shutting down ${bots.length} bots`);
    
    for (const userId of bots) {
      await stopBotForUser(userId);
    }
  } catch (error) {
    console.error("[BotManager] Error shutting down bots:", error);
  }
}
