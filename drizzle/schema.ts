import { mysqlEnum, mysqlTable, text, timestamp, varchar, decimal, int, boolean } from "drizzle-orm/mysql-core";

/**
 * Core user table backing auth flow.
 * Extend this file with additional tables as your product grows.
 * Columns use camelCase to match both database fields and generated types.
 */
export const users = mysqlTable("users", {
  id: varchar("id", { length: 64 }).primaryKey(),
  name: text("name"),
  email: varchar("email", { length: 320 }),
  loginMethod: varchar("loginMethod", { length: 64 }),
  role: mysqlEnum("role", ["user", "admin"]).default("user").notNull(),
  createdAt: timestamp("createdAt").defaultNow(),
  lastSignedIn: timestamp("lastSignedIn").defaultNow(),
});

export type User = typeof users.$inferSelect;
export type InsertUser = typeof users.$inferInsert;

/**
 * Trading configuration table for storing bot settings per user
 */
export const tradingConfigs = mysqlTable("trading_configs", {
  id: varchar("id", { length: 64 }).primaryKey(),
  userId: varchar("userId", { length: 64 }).notNull(),
  solanaPrivateKey: text("solanaPrivateKey").notNull(), // Encrypted in production
  rpcUrl: varchar("rpcUrl", { length: 512 }).default("https://api.mainnet-beta.solana.com"),
  walletAddress: varchar("walletAddress", { length: 128 }).notNull(),
  
  // SuperTrend parameters
  period: int("period").default(10),
  multiplier: decimal("multiplier", { precision: 5, scale: 2 }).default("3.0"),
  
  // Trading parameters
  tradeAmountPercent: int("tradeAmountPercent").default(50), // 50% of wallet
  slippageTolerance: decimal("slippageTolerance", { precision: 5, scale: 2 }).default("1.5"),
  
  // Bot control
  isActive: boolean("isActive").default(false),
  autoTrade: boolean("autoTrade").default(false),
  
  createdAt: timestamp("createdAt").defaultNow(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow(),
});

export type TradingConfig = typeof tradingConfigs.$inferSelect;
export type InsertTradingConfig = typeof tradingConfigs.$inferInsert;

/**
 * Market data table for storing historical price data
 */
export const marketData = mysqlTable("market_data", {
  id: varchar("id", { length: 64 }).primaryKey(),
  timestamp: timestamp("timestamp").notNull(),
  solPrice: decimal("solPrice", { precision: 20, scale: 8 }).notNull(),
  high: decimal("high", { precision: 20, scale: 8 }).notNull(),
  low: decimal("low", { precision: 20, scale: 8 }).notNull(),
  close: decimal("close", { precision: 20, scale: 8 }).notNull(),
  volume: decimal("volume", { precision: 30, scale: 8 }).notNull(),
  
  // SuperTrend values
  superTrendValue: decimal("superTrendValue", { precision: 20, scale: 8 }),
  trendDirection: mysqlEnum("trendDirection", ["up", "down"]),
  
  createdAt: timestamp("createdAt").defaultNow(),
});

export type MarketData = typeof marketData.$inferSelect;
export type InsertMarketData = typeof marketData.$inferInsert;

/**
 * Trade history table for logging all executed trades
 */
export const trades = mysqlTable("trades", {
  id: varchar("id", { length: 64 }).primaryKey(),
  userId: varchar("userId", { length: 64 }).notNull(),
  configId: varchar("configId", { length: 64 }).notNull(),
  
  tradeType: mysqlEnum("tradeType", ["buy", "sell"]).notNull(),
  tokenIn: varchar("tokenIn", { length: 64 }).notNull(), // SOL or USDC
  tokenOut: varchar("tokenOut", { length: 64 }).notNull(),
  
  amountIn: decimal("amountIn", { precision: 30, scale: 8 }).notNull(),
  amountOut: decimal("amountOut", { precision: 30, scale: 8 }).notNull(),
  priceAtExecution: decimal("priceAtExecution", { precision: 20, scale: 8 }).notNull(),
  
  // Supertrend signal
  superTrendSignal: mysqlEnum("superTrendSignal", ["buy", "sell"]).notNull(),
  superTrendValue: decimal("superTrendValue", { precision: 20, scale: 8 }),
  
  // Transaction details
  txHash: varchar("txHash", { length: 256 }),
  status: mysqlEnum("status", ["pending", "success", "failed"]).default("pending"),
  
  createdAt: timestamp("createdAt").defaultNow(),
  updatedAt: timestamp("updatedAt").defaultNow().onUpdateNow(),
});

export type Trade = typeof trades.$inferSelect;
export type InsertTrade = typeof trades.$inferInsert;

/**
 * Bot activity log table
 */
export const botLogs = mysqlTable("bot_logs", {
  id: varchar("id", { length: 64 }).primaryKey(),
  userId: varchar("userId", { length: 64 }).notNull(),
  configId: varchar("configId", { length: 64 }).notNull(),
  
  logType: mysqlEnum("logType", ["info", "success", "error", "warning", "trade"]).notNull(),
  message: text("message").notNull(),
  
  createdAt: timestamp("createdAt").defaultNow(),
});

export type BotLog = typeof botLogs.$inferSelect;
export type InsertBotLog = typeof botLogs.$inferInsert;

