# Solana Trading Bot - Railway.app Deployment Guide

## Overview
This guide walks you through deploying the Solana Trading Bot to Railway.app from your phone.

## Prerequisites
- GitHub account (jon341544-ai) ✅
- Railway.app account (free)
- Hyperliquid API credentials
- Solana RPC URL

## Step-by-Step Deployment (From Your Phone)

### Step 1: Create Railway.app Account
1. Open https://railway.app on your phone
2. Click "Sign up"
3. Choose "Sign up with GitHub"
4. Authorize Railway to access your GitHub account
5. Complete the setup

### Step 2: Create New Project
1. In Railway dashboard, click "New Project"
2. Select "Deploy from GitHub repo"
3. Search for "solana-trading-bot" in your repositories
4. Click to select it
5. Click "Deploy"

### Step 3: Add Environment Variables
Railway will ask you to configure environment variables. Add these:

```
DATABASE_URL=postgresql://user:password@localhost:5432/trading_bot
HYPERLIQUID_PRIVATE_KEY=0x5e5f206eb897a0cadbe48611c9b2f46c93e8983d725ef6886a5b5e7ae645acb1
HYPERLIQUID_WALLET_ADDRESS=0x0838db67976dfbd2b25fcc6b3a1a705e65ea9b9f
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_PRIVATE_KEY=your_solana_private_key_here
JWT_SECRET=your_jwt_secret_here
```

### Step 4: Add PostgreSQL Database
1. In your Railway project, click "Add Service"
2. Select "PostgreSQL"
3. Railway will automatically set DATABASE_URL
4. Click "Deploy"

### Step 5: Deploy
1. Click "Deploy" button
2. Wait for deployment to complete (2-5 minutes)
3. Once deployed, you'll get a public URL

### Step 6: Access Your Bot
1. Open the public URL in your browser
2. You should see the Solana Trading Bot dashboard
3. Configure your bot settings
4. Enable "Automatic Trading"
5. Click "Save Configuration"

## Monitoring

### View Logs
1. In Railway dashboard, click your project
2. Click "Logs" tab
3. Watch real-time bot activity

### Check Bot Status
1. Open the bot dashboard URL
2. View "Bot Status" section
3. Check "Logs" and "Trades" tabs

## Troubleshooting

### Bot not starting?
- Check logs for errors
- Verify all environment variables are set correctly
- Ensure DATABASE_URL is correct

### Trades not executing?
- Check Hyperliquid API key is correct
- Verify Hyperliquid wallet has funds
- Check bot logs for error messages

### Database connection failed?
- Wait 1-2 minutes for PostgreSQL to initialize
- Verify DATABASE_URL environment variable
- Restart the service

## Support
If you encounter issues, check the logs in Railway dashboard for detailed error messages.
