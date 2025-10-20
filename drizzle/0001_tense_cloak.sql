CREATE TABLE `bot_logs` (
	`id` varchar(64) NOT NULL,
	`userId` varchar(64) NOT NULL,
	`configId` varchar(64) NOT NULL,
	`logType` enum('info','success','error','warning','trade') NOT NULL,
	`message` text NOT NULL,
	`createdAt` timestamp DEFAULT (now()),
	CONSTRAINT `bot_logs_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `market_data` (
	`id` varchar(64) NOT NULL,
	`timestamp` timestamp NOT NULL,
	`solPrice` decimal(20,8) NOT NULL,
	`high` decimal(20,8) NOT NULL,
	`low` decimal(20,8) NOT NULL,
	`close` decimal(20,8) NOT NULL,
	`volume` decimal(30,8) NOT NULL,
	`superTrendValue` decimal(20,8),
	`trendDirection` enum('up','down'),
	`createdAt` timestamp DEFAULT (now()),
	CONSTRAINT `market_data_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `trades` (
	`id` varchar(64) NOT NULL,
	`userId` varchar(64) NOT NULL,
	`configId` varchar(64) NOT NULL,
	`tradeType` enum('buy','sell') NOT NULL,
	`tokenIn` varchar(64) NOT NULL,
	`tokenOut` varchar(64) NOT NULL,
	`amountIn` decimal(30,8) NOT NULL,
	`amountOut` decimal(30,8) NOT NULL,
	`priceAtExecution` decimal(20,8) NOT NULL,
	`superTrendSignal` enum('buy','sell') NOT NULL,
	`superTrendValue` decimal(20,8),
	`txHash` varchar(256),
	`status` enum('pending','success','failed') DEFAULT 'pending',
	`createdAt` timestamp DEFAULT (now()),
	`updatedAt` timestamp DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT `trades_id` PRIMARY KEY(`id`)
);
--> statement-breakpoint
CREATE TABLE `trading_configs` (
	`id` varchar(64) NOT NULL,
	`userId` varchar(64) NOT NULL,
	`solanaPrivateKey` text NOT NULL,
	`rpcUrl` varchar(512) DEFAULT 'https://api.mainnet-beta.solana.com',
	`walletAddress` varchar(128) NOT NULL,
	`period` int DEFAULT 10,
	`multiplier` decimal(5,2) DEFAULT '3.0',
	`tradeAmountPercent` int DEFAULT 50,
	`slippageTolerance` decimal(5,2) DEFAULT '1.5',
	`isActive` boolean DEFAULT false,
	`autoTrade` boolean DEFAULT false,
	`createdAt` timestamp DEFAULT (now()),
	`updatedAt` timestamp DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT `trading_configs_id` PRIMARY KEY(`id`)
);
