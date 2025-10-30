import { eq, desc } from "drizzle-orm";
import mysql from "mysql2/promise";
import { drizzle } from "drizzle-orm/mysql2";
import { InsertUser, users, tradingConfigs, TradingConfig, botLogs, trades } from "../drizzle/schema";
import { ENV } from './_core/env';

// Export schema tables for use in other modules
export { tradingConfigs, botLogs, trades } from "../drizzle/schema";

let _db: ReturnType<typeof drizzle> | null = null;
let _tablesCreated = false;

// Lazily create the drizzle instance so local tooling can run without a DB.
export async function getDb() {
  if (!_db && process.env.DATABASE_URL) {
    try {
      _db = drizzle(process.env.DATABASE_URL);
      
      // Create tables if they don't exist
      if (!_tablesCreated) {
        await initializeTables();
        _tablesCreated = true;
      }
    } catch (error) {
      console.warn("[Database] Failed to connect:", error);
      _db = null;
    }
  }
  return _db;
}

// Initialize database tables
async function initializeTables() {
  if (!process.env.DATABASE_URL) return;
  
  try {
    const connection = await mysql.createConnection(process.env.DATABASE_URL);
    
    // Create trading_configs table
    await connection.execute(`CREATE TABLE IF NOT EXISTS trading_configs (id VARCHAR(255) PRIMARY KEY, userId VARCHAR(255) NOT NULL, solanaPrivateKey TEXT, rpcUrl VARCHAR(500), walletAddress VARCHAR(255), period INT DEFAULT 10, multiplier VARCHAR(50), tradeAmountPercent INT DEFAULT 50, slippageTolerance VARCHAR(50), isActive BOOLEAN DEFAULT false, autoTrade BOOLEAN DEFAULT false, createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, INDEX idx_userId (userId))`);
    
    // Create bot_logs table
    await connection.execute(`CREATE TABLE IF NOT EXISTS bot_logs (id VARCHAR(255) PRIMARY KEY, configId VARCHAR(255) NOT NULL, level VARCHAR(50), message TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, INDEX idx_configId (configId))`);
    
    // Create trades table
    await connection.execute(`CREATE TABLE IF NOT EXISTS trades (id VARCHAR(255) PRIMARY KEY, userId VARCHAR(255) NOT NULL, configId VARCHAR(255) NOT NULL, type VARCHAR(50), amount DECIMAL(20, 8), price DECIMAL(20, 8), status VARCHAR(50), txHash VARCHAR(255), inputAmount DECIMAL(20, 8), outputAmount DECIMAL(20, 8), priceImpact DECIMAL(10, 6), superTrendValue DECIMAL(20, 8), macdValue DECIMAL(20, 8), bixordValue DECIMAL(20, 8), createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP, INDEX idx_userId (userId), INDEX idx_configId (configId))`);
    
    // Create market_data table
    await connection.execute(`CREATE TABLE IF NOT EXISTS market_data (id VARCHAR(255) PRIMARY KEY, configId VARCHAR(255) NOT NULL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, price DECIMAL(20, 8), volume DECIMAL(20, 8), superTrendValue DECIMAL(20, 8), macdValue DECIMAL(20, 8), bixordValue DECIMAL(20, 8), trend VARCHAR(50), INDEX idx_configId (configId), INDEX idx_timestamp (timestamp))`);
    
    // Create users table
    await connection.execute(`CREATE TABLE IF NOT EXISTS users (id VARCHAR(64) PRIMARY KEY, name TEXT, email VARCHAR(320), loginMethod VARCHAR(64), role ENUM('user', 'admin') DEFAULT 'user' NOT NULL, createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP, lastSignedIn TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)`);
    
    await connection.end();
    console.log("[Database] Tables initialized successfully");
  } catch (error) {
    console.error("[Database] Failed to initialize tables:", error);
  }
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
    .orderBy((t) => desc(t.createdAt))
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

