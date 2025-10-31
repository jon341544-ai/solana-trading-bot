import { getDb } from "./db";
import { users, tradingConfigs, trades, botLogs, botStatus, marketData } from "../drizzle/schema";

export async function initializeDatabase() {
  const db = await getDb();
  if (!db) {
    console.error("[DB Init] Database connection not available");
    return false;
  }

  try {
    console.log("[DB Init] Checking if tables exist...");

    // Try to query each table to see if it exists
    try {
      const userCount = await db.select().from(users).limit(1);
      console.log("[DB Init] ✅ users table exists");
    } catch (e) {
      console.log("[DB Init] ⚠️ users table doesn't exist, creating...");
      await db.execute(`
        CREATE TABLE IF NOT EXISTS users (
          id VARCHAR(64) PRIMARY KEY,
          name TEXT,
          email VARCHAR(320),
          loginMethod VARCHAR(64),
          role ENUM('user', 'admin') NOT NULL DEFAULT 'user',
          createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          lastSignedIn TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
      `);
      console.log("[DB Init] ✅ users table created");
    }

    try {
      const configCount = await db.select().from(tradingConfigs).limit(1);
      console.log("[DB Init] ✅ trading_configs table exists");
    } catch (e) {
      console.log("[DB Init] ⚠️ trading_configs table doesn't exist, creating...");
      await db.execute(`
        CREATE TABLE IF NOT EXISTS trading_configs (
          id VARCHAR(255) PRIMARY KEY,
          userId VARCHAR(64) NOT NULL,
          solanaPrivateKey TEXT,
          rpcUrl VARCHAR(500),
          walletAddress VARCHAR(255),
          hyperliquidPrivateKey TEXT,
          hyperliquidWalletAddress VARCHAR(255),
          isActive BOOLEAN DEFAULT true,
          createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          KEY userId (userId)
        )
      `);
      console.log("[DB Init] ✅ trading_configs table created");
    }

    try {
      const tradeCount = await db.select().from(trades).limit(1);
      console.log("[DB Init] ✅ trades table exists");
    } catch (e) {
      console.log("[DB Init] ⚠️ trades table doesn't exist, creating...");
      await db.execute(`
        CREATE TABLE IF NOT EXISTS trades (
          id VARCHAR(255) PRIMARY KEY,
          userId VARCHAR(64) NOT NULL,
          configId VARCHAR(255),
          tradeType ENUM('BUY', 'SELL'),
          tokenIn VARCHAR(50),
          tokenOut VARCHAR(50),
          amountIn DECIMAL(20, 8),
          amountOut DECIMAL(20, 8),
          priceAtExecution DECIMAL(20, 8),
          superTrendSignal VARCHAR(50),
          superTrendValue DECIMAL(20, 8),
          txHash VARCHAR(255),
          status VARCHAR(50),
          createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          KEY userId (userId),
          KEY configId (configId)
        )
      `);
      console.log("[DB Init] ✅ trades table created");
    }

    try {
      const logCount = await db.select().from(botLogs).limit(1);
      console.log("[DB Init] ✅ bot_logs table exists");
    } catch (e) {
      console.log("[DB Init] ⚠️ bot_logs table doesn't exist, creating...");
      await db.execute(`
        CREATE TABLE IF NOT EXISTS bot_logs (
          id VARCHAR(255) PRIMARY KEY,
          userId VARCHAR(64) NOT NULL,
          configId VARCHAR(255),
          logType VARCHAR(50),
          message TEXT,
          createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          KEY configId (configId)
        )
      `);
      console.log("[DB Init] ✅ bot_logs table created");
    }

    try {
      const statusCount = await db.select().from(botStatus).limit(1);
      console.log("[DB Init] ✅ bot_status table exists");
    } catch (e) {
      console.log("[DB Init] ⚠️ bot_status table doesn't exist, creating...");
      await db.execute(`
        CREATE TABLE IF NOT EXISTS bot_status (
          id VARCHAR(255) PRIMARY KEY,
          userId VARCHAR(64) NOT NULL UNIQUE,
          isRunning BOOLEAN DEFAULT false,
          balance DECIMAL(20, 8) DEFAULT 0,
          usdcBalance DECIMAL(20, 8) DEFAULT 0,
          currentPrice DECIMAL(20, 8) DEFAULT 0,
          trend VARCHAR(50),
          lastSignal VARCHAR(50),
          lastTradeTime TIMESTAMP,
          createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
      `);
      console.log("[DB Init] ✅ bot_status table created");
    }

    try {
      const marketCount = await db.select().from(marketData).limit(1);
      console.log("[DB Init] ✅ market_data table exists");
    } catch (e) {
      console.log("[DB Init] ⚠️ market_data table doesn't exist, creating...");
      await db.execute(`
        CREATE TABLE IF NOT EXISTS market_data (
          id VARCHAR(255) PRIMARY KEY,
          symbol VARCHAR(50),
          price DECIMAL(20, 8),
          volume DECIMAL(20, 8),
          high DECIMAL(20, 8),
          low DECIMAL(20, 8),
          change24h DECIMAL(10, 2),
          timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          KEY symbol (symbol)
        )
      `);
      console.log("[DB Init] ✅ market_data table created");
    }

    console.log("[DB Init] ✅ All tables initialized successfully");
    return true;
  } catch (error) {
    console.error("[DB Init] ❌ Failed to initialize database:", error);
    return false;
  }
}

