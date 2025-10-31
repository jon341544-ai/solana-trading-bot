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

    // Just try to query each table - if it fails, the table doesn't exist
    // The database should already have the tables from migrations
    const tableChecks = [
      { name: 'users', query: () => db.select().from(users).limit(1) },
      { name: 'trading_configs', query: () => db.select().from(tradingConfigs).limit(1) },
      { name: 'trades', query: () => db.select().from(trades).limit(1) },
      { name: 'bot_logs', query: () => db.select().from(botLogs).limit(1) },
      { name: 'bot_status', query: () => db.select().from(botStatus).limit(1) },
      { name: 'market_data', query: () => db.select().from(marketData).limit(1) },
    ];

    for (const check of tableChecks) {
      try {
        await check.query();
        console.log(`[DB Init] ✅ ${check.name} table exists`);
      } catch (e) {
        console.warn(`[DB Init] ⚠️ ${check.name} table query failed (may not exist):`, (e as any).message?.split('\n')[0]);
      }
    }

    console.log("[DB Init] ✅ Database check complete");
    return true;
  } catch (error) {
    console.error("[DB Init] ❌ Failed to check database:", error);
    return false;
  }
}

