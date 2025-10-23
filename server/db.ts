import { eq } from "drizzle-orm";
import { drizzle } from "drizzle-orm/mysql2";
import { InsertUser, users, tradingConfigs, TradingConfig, botLogs, trades } from "../drizzle/schema";
import { ENV } from './_core/env';

// Export schema tables for use in other modules
export { tradingConfigs, botLogs, trades } from "../drizzle/schema";

let _db: ReturnType<typeof drizzle> | null = null;

// Lazily create the drizzle instance so local tooling can run without a DB.
export async function getDb() {
  if (!_db && process.env.DATABASE_URL) {
    try {
      _db = drizzle(process.env.DATABASE_URL);
    } catch (error) {
      console.warn("[Database] Failed to connect:", error);
      _db = null;
    }
  }
  return _db;
}

export async function upsertUser(user: InsertUser): Promise<void> {
  if (!user.id) {
    throw new Error("User ID is required for upsert");
  }

  const db = await getDb();
  if (!db) {
    console.warn("[Database] Cannot upsert user: database not available");
    return;
  }

  try {
    const values: InsertUser = {
      id: user.id,
    };
    const updateSet: Record<string, unknown> = {};

    const textFields = ["name", "email", "loginMethod"] as const;
    type TextField = (typeof textFields)[number];

    const assignNullable = (field: TextField) => {
      const value = user[field];
      if (value === undefined) return;
      const normalized = value ?? null;
      values[field] = normalized;
      updateSet[field] = normalized;
    };

    textFields.forEach(assignNullable);

    if (user.lastSignedIn !== undefined) {
      values.lastSignedIn = user.lastSignedIn;
      updateSet.lastSignedIn = user.lastSignedIn;
    }
    if (user.role === undefined) {
      if (user.id === ENV.ownerId) {
        user.role = 'admin';
        values.role = 'admin';
        updateSet.role = 'admin';
      }
    }

    if (Object.keys(updateSet).length === 0) {
      updateSet.lastSignedIn = new Date();
    }

    await db.insert(users).values(values).onDuplicateKeyUpdate({
      set: updateSet,
    });
  } catch (error) {
    console.error("[Database] Failed to upsert user:", error);
    throw error;
  }
}

export async function getUser(id: string) {
  const db = await getDb();
  if (!db) {
    console.warn("[Database] Cannot get user: database not available");
    return undefined;
  }

  const result = await db.select().from(users).where(eq(users.id, id)).limit(1);

  return result.length > 0 ? result[0] : undefined;
}

/**
 * Trading Config operations
 */
export async function getTradingConfig(userId: string): Promise<TradingConfig | undefined> {
  const db = await getDb();
  if (!db) return undefined;

  const result = await db
    .select()
    .from(tradingConfigs)
    .where(eq(tradingConfigs.userId, userId))
    .limit(1);

  return result.length > 0 ? result[0] : undefined;
}

export async function createTradingConfig(config: typeof tradingConfigs.$inferInsert) {
  const db = await getDb();
  if (!db) throw new Error("Database not available");

  await db.insert(tradingConfigs).values(config);
}

export async function updateTradingConfig(configId: string, updates: Partial<typeof tradingConfigs.$inferInsert>) {
  const db = await getDb();
  if (!db) throw new Error("Database not available");

  await db.update(tradingConfigs).set(updates).where(eq(tradingConfigs.id, configId));
}

/**
 * Bot logs operations
 */
export async function getBotLogs(configId: string, limit: number = 100) {
  const db = await getDb();
  if (!db) return [];

  const { desc } = await import('drizzle-orm');
  const result = await db
    .select()
    .from(botLogs)
    .where(eq(botLogs.configId, configId))
    .orderBy(desc(botLogs.createdAt))
    .limit(limit);

  return result;
}

/**
 * Trade history operations
 */
export async function getTradeHistory(userId: string, limit: number = 50) {
  const db = await getDb();
  if (!db) return [];

  const result = await db
    .select()
    .from(trades)
    .where(eq(trades.userId, userId))
    .orderBy((t) => t.createdAt)
    .limit(limit);

  return result;
}

export async function getTradeStats(userId: string) {
  const db = await getDb();
  if (!db) return null;

  const tradeHistory = await getTradeHistory(userId, 1000);

  if (tradeHistory.length === 0) {
    return {
      totalTrades: 0,
      buyTrades: 0,
      sellTrades: 0,
      successfulTrades: 0,
      failedTrades: 0,
      totalProfit: 0,
    };
  }

  const buyTrades = tradeHistory.filter((t) => t.tradeType === "buy").length;
  const sellTrades = tradeHistory.filter((t) => t.tradeType === "sell").length;
  const successfulTrades = tradeHistory.filter((t) => t.status === "success").length;
  const failedTrades = tradeHistory.filter((t) => t.status === "failed").length;

  return {
    totalTrades: tradeHistory.length,
    buyTrades,
    sellTrades,
    successfulTrades,
    failedTrades,
    totalProfit: 0, // Would need more complex calculation
  };
}

