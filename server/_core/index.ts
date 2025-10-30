import express from "express";
import { createServer } from "http";
import net from "net";
import { createExpressMiddleware } from "@trpc/server/adapters/express";
import { registerOAuthRoutes } from "./oauth";
import { appRouter } from "../routers";
import { createContext } from "./context";
import { serveStatic, setupVite } from "./vite";
import { restoreBotsFromDatabase, shutdownAllBots } from "../trading/botManager";
import { startHealthMonitor, stopHealthMonitor } from "../trading/botHealthMonitor";

function isPortAvailable(port: number): Promise<boolean> {
  return new Promise(resolve => {
    const server = net.createServer();
    server.listen(port, () => {
      server.close(() => resolve(true));
    });
    server.on("error", () => resolve(false));
  });
}

async function findAvailablePort(startPort: number = 3000): Promise<number> {
  for (let port = startPort; port < startPort + 20; port++) {
    if (await isPortAvailable(port)) {
      return port;
    }
  }
  throw new Error(`No available port found starting from ${startPort}`);
}

async function startServer() {
  const app = express();
  const server = createServer(app);
  // Configure body parser with larger size limit for file uploads
  app.use(express.json({ limit: "50mb" }));
  app.use(express.urlencoded({ limit: "50mb", extended: true }));
  // OAuth callback under /api/oauth/callback
  registerOAuthRoutes(app);
  // tRPC API
  app.use(
    "/api/trpc",
    createExpressMiddleware({
      router: appRouter,
      createContext,
    })
  );
  // development mode uses Vite, production mode uses static files
  if (process.env.NODE_ENV === "development") {
    await setupVite(app, server);
  } else {
    serveStatic(app);
  }

  const preferredPort = parseInt(process.env.PORT || "3000");
  const port = await findAvailablePort(preferredPort);

  if (port !== preferredPort) {
    console.log(`Port ${preferredPort} is busy, using port ${port} instead`);
  }

  server.listen(port, () => {
    console.log(`Server running on http://localhost:${port}/`);
  });

  // Restore bots from database on startup
  console.log("[Server] Restoring bots from database...");
  try {
    await restoreBotsFromDatabase();
    console.log("[Server] Bot restoration complete");
  } catch (error) {
    console.error("[Server] Failed to restore bots:", error);
  }

  // Initialize bot with Hyperliquid credentials from environment variables
  const hyperliquidPrivateKey = process.env.HYPERLIQUID_PRIVATE_KEY;
  const hyperliquidWalletAddress = process.env.HYPERLIQUID_WALLET_ADDRESS;
  
  if (hyperliquidPrivateKey && hyperliquidWalletAddress) {
    console.log("[Server] Hyperliquid credentials found in environment");
    
    // Delay initialization to ensure database is ready
    setTimeout(async () => {
      console.log("[Server] Initializing Hyperliquid bot...");
      try {
        const { getTradingConfig, createTradingConfig } = await import("../db");
        const { startBotForUser } = await import("../trading/botManager");
        
        const userId = "default_user";
        let config = await getTradingConfig(userId);
        
        if (!config) {
          console.log("[Server] Creating default trading configuration...");
          // Create default config with Hyperliquid credentials
          const configId = `config_${userId}_${Date.now()}`;
          const newConfig = {
            id: configId,
            userId: userId,
            solanaPrivateKey: "", // Not needed for Hyperliquid
            rpcUrl: "https://api.mainnet-beta.solana.com",
            walletAddress: hyperliquidWalletAddress,
            period: 10,
            multiplier: "3.0",
            tradeAmountPercent: 50,
            slippageTolerance: "1.5",
            isActive: true,
            autoTrade: true,
          };
          
          try {
            await createTradingConfig(newConfig);
            config = newConfig as any;
            console.log("[Server] Trading configuration created successfully");
          } catch (dbError) {
            console.error("[Server] Failed to create trading configuration:", dbError);
            return;
          }
        }
        
        // Start bot with Hyperliquid credentials
        if (config) {
          const botConfig = {
            userId: config.userId,
            configId: config.id,
            privateKey: "",
            rpcUrl: config.rpcUrl || "https://api.mainnet-beta.solana.com",
            walletAddress: hyperliquidWalletAddress,
            hyperliquidPrivateKey: hyperliquidPrivateKey,
            hyperliquidWalletAddress: hyperliquidWalletAddress,
            period: config.period || 10,
            multiplier: parseFloat((config.multiplier || "3.0").toString()),
            tradeAmountPercent: config.tradeAmountPercent || 50,
            slippageTolerance: parseFloat((config.slippageTolerance || "1.5").toString()),
            autoTrade: true,
            useHyperliquid: true,
          };
          
          const success = await startBotForUser(userId, botConfig);
          if (success) {
            console.log("[Server] ✅ Hyperliquid bot initialized and started");
          } else {
            console.error("[Server] Failed to start Hyperliquid bot");
          }
        }
      } catch (error) {
        console.error("[Server] Failed to initialize Hyperliquid bot:", error);
      }
    }, 3000); // Wait 3 seconds for database to be ready
  } else {
    console.log("[Server] Hyperliquid credentials not found in environment");
  }

  // Start health monitor to keep bots running
  startHealthMonitor(60000); // Check every 60 seconds

  // Handle graceful shutdown
  process.on("SIGTERM", async () => {
    console.log("[Server] SIGTERM received, shutting down gracefully...");
    stopHealthMonitor();
    await shutdownAllBots();
    server.close(() => {
      console.log("[Server] Server closed");
      process.exit(0);
    });
  });

  process.on("SIGINT", async () => {
    console.log("[Server] SIGINT received, shutting down gracefully...");
    stopHealthMonitor();
    await shutdownAllBots();
    server.close(() => {
      console.log("[Server] Server closed");
      process.exit(0);
    });
  });
}

startServer().catch(console.error);

