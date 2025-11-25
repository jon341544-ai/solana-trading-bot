# Solana Trading Bot (MACD Strategy)

This is an automated trading bot for the Solana ecosystem, utilizing the **MACD (Moving Average Convergence Divergence)** technical indicator to trade **SOL/USDC** on decentralized exchanges (DEXs) via the **Jupiter Aggregator API**.

**NOTE ON DEX TRADING:**
Unlike centralized exchange (CEX) bots, this bot does not execute trades directly through a simple API call. Instead, it uses the Jupiter API to get a swap quote and a serialized transaction. **A full, secure implementation requires a Solana wallet integration (e.g., using `solana-py` and a secure way to sign transactions with your private key).**

For the purpose of this conversion, the `execute_swap` function contains a **SIMULATION** of the transaction signing and sending process. **DO NOT USE THIS CODE FOR LIVE TRADING WITHOUT IMPLEMENTING THE SECURE TRANSACTION LOGIC.**

## Configuration

The bot requires the following environment variables to be set:

| Variable | Description |
| :--- | :--- |
| `SOLANA_PRIVATE_KEY` | The **Base58 encoded private key** of your Solana wallet. This wallet must hold the USDC and SOL tokens you wish to trade. **WARNING: Treat this key as highly sensitive.** |
| `SOLANA_RPC_URL` | (Optional) The URL of a Solana RPC node. Defaults to `https://api.mainnet-beta.solana.com`. |
| `PORT` | (Optional) The port for the web server. Defaults to `5000`. |

## Strategy

The bot implements a simple MACD crossover strategy:

*   **BUY Signal:** MACD line crosses above the Signal line, and the Histogram is positive and increasing. The bot swaps **USDC for SOL**.
*   **SELL Signal:** MACD line crosses below the Signal line, and the Histogram is negative and decreasing. The bot swaps **SOL for USDC**.

The bot uses a fixed trade amount of **$10 USDC equivalent** per trade, which can be adjusted in the `solana_bot.py` file.

## Dependencies

This project requires Python 3.x and the following libraries:

*   `flask`
*   `pandas`
*   `numpy`
*   `requests`
*   `gunicorn`
*   `solana-py`
*   `jupiter-python-sdk`

Install them using:
\`\`\`bash
pip install -r requirements.txt
\`\`\`

## Running the Bot

1.  **Set Environment Variables:**
    \`\`\`bash
    export SOLANA_PRIVATE_KEY="YOUR_PRIVATE_KEY_HERE"
    # Optional: export SOLANA_RPC_URL="YOUR_RPC_URL"
    \`\`\`

2.  **Run the application:**
    \`\`\`bash
    gunicorn solana_bot:app
    \`\`\`

3.  **Access the Dashboard:**
    The bot runs a simple web dashboard (usually on port 5000) to view status, balances, and trade history.
    \`\`\`
    http://localhost:5000
    \`\`\`
