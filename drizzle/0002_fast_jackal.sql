CREATE TABLE `bot_status` (
	`id` varchar(64) NOT NULL,
	`userId` varchar(64) NOT NULL,
	`isRunning` boolean DEFAULT false,
	`balance` decimal(30,8) DEFAULT '0',
	`usdcBalance` decimal(30,8) DEFAULT '0',
	`currentPrice` decimal(20,8) DEFAULT '0',
	`trend` enum('up','down','neutral') DEFAULT 'neutral',
	`lastSignal` varchar(64),
	`lastTradeTime` timestamp,
	`createdAt` timestamp DEFAULT (now()),
	`updatedAt` timestamp DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT `bot_status_id` PRIMARY KEY(`id`),
	CONSTRAINT `bot_status_userId_unique` UNIQUE(`userId`)
);
