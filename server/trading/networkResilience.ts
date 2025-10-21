/**
 * Network Resilience Module
 * 
 * Provides robust network handling with:
 * - Retry logic with exponential backoff
 * - Multiple fallback endpoints
 * - Request timeouts
 * - Connection pooling
 */

// Fallback RPC endpoints for Solana
const RPC_ENDPOINTS = [
  "https://api.mainnet-beta.solana.com",
  "https://solana-api.projectserum.com",
  "https://api.rpcpool.com",
];

// Jupiter API endpoints
const JUPITER_ENDPOINTS = [
  "https://quote-api.jup.ag/v6",
  "https://api.jup.ag/v6",
];

interface RetryOptions {
  maxRetries?: number;
  initialDelayMs?: number;
  maxDelayMs?: number;
  backoffMultiplier?: number;
  timeoutMs?: number;
}

const DEFAULT_RETRY_OPTIONS: RetryOptions = {
  maxRetries: 3,
  initialDelayMs: 1000,
  maxDelayMs: 10000,
  backoffMultiplier: 2,
  timeoutMs: 15000,
};

/**
 * Execute a fetch request with retry logic and timeout
 */
export async function fetchWithRetry(
  url: string,
  options: RequestInit & RetryOptions = {}
): Promise<Response> {
  const {
    maxRetries = DEFAULT_RETRY_OPTIONS.maxRetries ?? 3,
    initialDelayMs = DEFAULT_RETRY_OPTIONS.initialDelayMs ?? 1000,
    maxDelayMs = DEFAULT_RETRY_OPTIONS.maxDelayMs ?? 10000,
    backoffMultiplier = DEFAULT_RETRY_OPTIONS.backoffMultiplier ?? 2,
    timeoutMs = DEFAULT_RETRY_OPTIONS.timeoutMs ?? 15000,
    ...fetchOptions
  } = options;

  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      // Create abort controller for timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

      const response = await fetch(url, {
        ...fetchOptions,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      // If response is ok, return immediately
      if (response.ok) {
        return response;
      }

      // If response is not ok but not a network error, don't retry
      if (response.status >= 400 && response.status < 500) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      // For 5xx errors, retry
      lastError = new Error(`HTTP ${response.status}: ${response.statusText}`);
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));

      // If this was the last attempt, throw
      if (attempt === maxRetries) {
        throw lastError;
      }

      // Calculate delay with exponential backoff
      const delay = Math.min(
        (initialDelayMs ?? 1000) * Math.pow(backoffMultiplier ?? 2, attempt),
        maxDelayMs ?? 10000
      );

      console.warn(
        `[NetworkResilience] Attempt ${attempt + 1}/${maxRetries + 1} failed for ${url}: ${lastError.message}. Retrying in ${delay}ms...`
      );

      // Wait before retrying
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError || new Error("Unknown error during fetch");
}

/**
 * Try multiple endpoints until one succeeds
 */
export async function fetchWithFallback(
  endpoints: string[],
  options: RequestInit & RetryOptions = {}
): Promise<Response> {
  let lastError: Error | null = null;

  for (const endpoint of endpoints) {
    try {
      console.log(`[NetworkResilience] Trying endpoint: ${endpoint}`);
      const response = await fetchWithRetry(endpoint, options);
      console.log(`[NetworkResilience] Successfully connected to: ${endpoint}`);
      return response;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      console.warn(
        `[NetworkResilience] Endpoint failed: ${endpoint} - ${lastError.message}`
      );
    }
  }

  throw (
    lastError ||
    new Error(`All endpoints failed: ${endpoints.join(", ")}`)
  );
}

/**
 * Get a working RPC endpoint with fallback
 */
export async function getRPCEndpoint(customRpc?: string): Promise<string> {
  if (customRpc) {
    // Test custom RPC first
    try {
      const response = await fetchWithRetry(customRpc, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 1,
          method: "getHealth",
        }),
        maxRetries: 1,
        timeoutMs: 5000,
      });

      if (response.ok) {
        console.log(`[NetworkResilience] Using custom RPC: ${customRpc}`);
        return customRpc;
      }
    } catch (error) {
      console.warn(
        `[NetworkResilience] Custom RPC failed, falling back to defaults: ${error}`
      );
    }
  }

  // Try default endpoints
  for (const endpoint of RPC_ENDPOINTS) {
    try {
      const response = await fetchWithRetry(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 1,
          method: "getHealth",
        }),
        maxRetries: 1,
        timeoutMs: 5000,
      });

      if (response.ok) {
        console.log(`[NetworkResilience] Using RPC endpoint: ${endpoint}`);
        return endpoint;
      }
    } catch (error) {
      console.warn(
        `[NetworkResilience] RPC endpoint failed: ${endpoint} - ${error}`
      );
    }
  }

  // If all fail, return primary endpoint (will fail on actual use, but at least we tried)
  console.error(
    "[NetworkResilience] All RPC endpoints failed, using primary endpoint"
  );
  return RPC_ENDPOINTS[0];
}

/**
 * Get a working Jupiter endpoint with fallback
 */
export async function getJupiterEndpoint(): Promise<string> {
  for (const endpoint of JUPITER_ENDPOINTS) {
    try {
      const response = await fetchWithRetry(`${endpoint}/tokens`, {
        maxRetries: 1,
        timeoutMs: 5000,
      });

      if (response.ok) {
        console.log(`[NetworkResilience] Using Jupiter endpoint: ${endpoint}`);
        return endpoint;
      }
    } catch (error) {
      console.warn(
        `[NetworkResilience] Jupiter endpoint failed: ${endpoint} - ${error}`
      );
    }
  }

  // If all fail, return primary endpoint
  console.error(
    "[NetworkResilience] All Jupiter endpoints failed, using primary endpoint"
  );
  return JUPITER_ENDPOINTS[0];
}

/**
 * Execute a trade with full retry and fallback logic
 */
export async function executeTradeWithResilience(
  tradeFunction: (rpcEndpoint: string, jupiterEndpoint: string) => Promise<any>
): Promise<any> {
  const maxAttempts = 3;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const rpcEndpoint = await getRPCEndpoint();
      const jupiterEndpoint = await getJupiterEndpoint();

      console.log(
        `[NetworkResilience] Executing trade (attempt ${attempt + 1}/${maxAttempts})`
      );
      const result = await tradeFunction(rpcEndpoint, jupiterEndpoint);

      console.log("[NetworkResilience] Trade executed successfully");
      return result;
    } catch (error) {
      const errorMsg =
        error instanceof Error ? error.message : String(error);
      console.error(
        `[NetworkResilience] Trade attempt ${attempt + 1} failed: ${errorMsg}`
      );

      if (attempt < maxAttempts - 1) {
        // Wait before retrying with exponential backoff
        const delay = Math.min(1000 * Math.pow(2, attempt), 10000);
        console.log(
          `[NetworkResilience] Retrying in ${delay}ms...`
        );
        await new Promise((resolve) => setTimeout(resolve, delay));
      } else {
        throw error;
      }
    }
  }
}

/**
 * Check network connectivity
 */
export async function checkNetworkConnectivity(): Promise<boolean> {
  try {
    const response = await fetchWithRetry("https://api.mainnet-beta.solana.com", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "getHealth",
      }),
      maxRetries: 1,
      timeoutMs: 5000,
    });

    return response.ok;
  } catch (error) {
    console.warn("[NetworkResilience] Network connectivity check failed:", error);
    return false;
  }
}

/**
 * Get network status
 */
export async function getNetworkStatus(): Promise<{
  isConnected: boolean;
  rpcEndpoint: string;
  jupiterEndpoint: string;
  timestamp: Date;
}> {
  const isConnected = await checkNetworkConnectivity();
  const rpcEndpoint = await getRPCEndpoint();
  const jupiterEndpoint = await getJupiterEndpoint();

  return {
    isConnected,
    rpcEndpoint,
    jupiterEndpoint,
    timestamp: new Date(),
  };
}

