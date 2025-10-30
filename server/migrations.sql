-- Create trading_configs table
CREATE TABLE IF NOT EXISTS trading_configs (
  id VARCHAR(255) PRIMARY KEY,
  userId VARCHAR(255) NOT NULL,
  solanaPrivateKey TEXT,
  rpcUrl VARCHAR(500),
  walletAddress VARCHAR(255),
  period INT DEFAULT 10,
  multiplier VARCHAR(50),
  tradeAmountPercent INT DEFAULT 50,
  slippageTolerance VARCHAR(50),
  isActive BOOLEAN DEFAULT false,
  autoTrade BOOLEAN DEFAULT false,
  createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_userId (userId)
);

-- Create bot_logs table
CREATE TABLE IF NOT EXISTS bot_logs (
  id VARCHAR(255) PRIMARY KEY,
  configId VARCHAR(255) NOT NULL,
  level VARCHAR(50),
  message TEXT,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_configId (configId)
);

-- Create trades table
CREATE TABLE IF NOT EXISTS trades (
  id VARCHAR(255) PRIMARY KEY,
  userId VARCHAR(255) NOT NULL,
  configId VARCHAR(255) NOT NULL,
  type VARCHAR(50),
  amount DECIMAL(20, 8),
  price DECIMAL(20, 8),
  status VARCHAR(50),
  txHash VARCHAR(255),
  inputAmount DECIMAL(20, 8),
  outputAmount DECIMAL(20, 8),
  priceImpact DECIMAL(10, 6),
  superTrendValue DECIMAL(20, 8),
  macdValue DECIMAL(20, 8),
  bixordValue DECIMAL(20, 8),
  createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_userId (userId),
  INDEX idx_configId (configId)
);

-- Create market_data table
CREATE TABLE IF NOT EXISTS market_data (
  id VARCHAR(255) PRIMARY KEY,
  configId VARCHAR(255) NOT NULL,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  price DECIMAL(20, 8),
  volume DECIMAL(20, 8),
  superTrendValue DECIMAL(20, 8),
  macdValue DECIMAL(20, 8),
  bixordValue DECIMAL(20, 8),
  trend VARCHAR(50),
  INDEX idx_configId (configId),
  INDEX idx_timestamp (timestamp)
);

-- Create users table
CREATE TABLE IF NOT EXISTS users (
  id VARCHAR(64) PRIMARY KEY,
  name TEXT,
  email VARCHAR(320),
  loginMethod VARCHAR(64),
  role ENUM('user', 'admin') DEFAULT 'user' NOT NULL,
  createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  lastSignedIn TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
