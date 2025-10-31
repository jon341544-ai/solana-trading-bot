/**
 * Bot Health Monitor - Ensures bots stay running
 * 
 * Periodically checks if bots are still running and restarts them if they crash.
 * This provides resilience and ensures 24/7 operation.
 */

import { getActiveBots, startBotForUser } from "./botManager";
import { getDb, tradingConfigs } from "../db";
import { eq } from "drizzle-orm";
import { BotConfig } from "./botEngine";

let healthCheckInterval: ReturnType<typeof setInterval> | null = null;

/**
 * Start the health monitor
 */
export function startHealthMonitor(intervalMs: number = 60000): void {
  if (healthCheckInterval) {
    console.log("[HealthMonitor] Health monitor already running");
    return;
  }

  console.log(`[HealthMonitor] Starting health monitor (check every ${intervalMs}ms)`);

  healthCheckInterval = setInterval(async () => {
    try {
      await checkBotHealth();
    } catch (error) {
      console.error("[HealthMonitor] Error during health check:", error);
    }
  }, intervalMs);

  // Run first check immediately
  checkBotHealth().catch((error) =>
    console.error("[HealthMonitor] Error during initial health check:", error)
  );
}

/**
 * Stop the health monitor
 */
export function stopHealthMonitor(): void {
  if (healthCheckInterval) {
    clearInterval(healthCheckInterval);
    healthCheckInterval = null;
    console.log("[HealthMonitor] Health monitor stopped");
  }
}

/**
 * Check health of all active bots
 */
async function checkBotHealth(): Promise<void> {
  const activeBots = getActiveBots();

  if (activeBots.length === 0) {
    // No bots running, check if any should be running
    await restartInactiveBots();
    return;
  }

  // Check each running bot
  for (const botInfo of activeBots) {
    try {
      const { userId, status } = botInfo;

      if (!status.isRunning) {
        console.warn(`[HealthMonitor] Bot for user ${userId} is not running, restarting...`);
        // Try to restart the bot
        await restartBotForUser(userId);
      }
    } catch (error) {
      console.error(`[HealthMonitor] Error checking bot health:`, error);
    }
  }
}

/**
 * Restart a bot for a user
 */
async function restartBotForUser(userId: string): Promise<void> {
  try {
    // Check if Hyperliquid credentials are configured
    const hyperliquidPrivateKey = process.env.HYPERLIQUID_PRIVATE_KEY;
    const hyperliquidWalletAddress = process.env.HYPERLIQUID_WALLET_ADDRESS;
    
    if (!hyperliquidPrivateKey || !hyperliquidWalletAddress) {
      console.warn(`[HealthMonitor] Hyperliquid credentials not configured in environment`);
      return;
    }

    const db = await getDb();
    if (!db) {
      console.warn("[HealthMonitor] Database not available, cannot restart bot");
      return;
    }

    // Get the user's trading configuration
    const configs = await db
      .select()
      .from(tradingConfigs)
      .where(eq(tradingConfigs.userId, userId))
      .limit(1);

    if (configs.length === 0) {
      console.warn(`[HealthMonitor] No trading config found for user ${userId}`);
      return;
    }

    const config = configs[0];

    // Use Hyperliquid credentials from environment
    const botConfig: BotConfig = {
      userId: config.userId,
      configId: config.id,
      privateKey: config.solanaPrivateKey || "",
      rpcUrl: config.rpcUrl || "https://api.mainnet-beta.solana.com",
      walletAddress: config.walletAddress || "",
      hyperliquidPrivateKey: hyperliquidPrivateKey,
      hyperliquidWalletAddress: hyperliquidWalletAddress,
      period: config.period || 10,
      multiplier: parseFloat((config.multiplier || "3.0").toString()),
      tradeAmountPercent: config.tradeAmountPercent || 50,
      slippageTolerance: parseFloat((config.slippageTolerance || "1.5").toString()),
      autoTrade: config.autoTrade || false,
      useHyperliquid: true,
    };

    const success = await startBotForUser(userId, botConfig);
    if (success) {
      console.log(`[HealthMonitor] Successfully restarted bot for user ${userId}`);
    } else {
      console.error(`[HealthMonitor] Failed to restart bot for user ${userId}`);
    }
  } catch (error) {
    console.error(`[HealthMonitor] Error restarting bot for user ${userId}:`, error);
  }
}

/**
 * Check if there are any inactive bots that should be running
 */
async function restartInactiveBots(): Promise<void> {
  try {
    // Disabled: Users should manually start bots via the dashboard
    // This prevents errors from trying to restart bots without proper configuration
    console.log("[HealthMonitor] Bot auto-restart disabled - users can start bots manually via dashboard");
  } catch (error) {
    console.error("[HealthMonitor] Error checking for inactive bots:", error);
  }
}

/**
 * Get health monitor status
 */
export function getHealthMonitorStatus(): { isRunning: boolean; lastCheck?: Date } {
  return {
    isRunning: healthCheckInterval !== null,
  };
}

