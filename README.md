# CoinCatch Solana Trading Bot (MACD Strategy)

This is an automated trading bot for the **CoinCatch centralized exchange (CEX)**, utilizing the **MACD (Moving Average Convergence Divergence)** technical indicator to trade **SOL/USDT** on the spot market.

## Configuration

The bot requires the following environment variables to be set in your Railway project:

| Variable | Description |
| :--- | :--- |
| `COINCATCH_API_KEY` | Your CoinCatch API Key. |
| `COINCATCH_API_SECRET` | Your CoinCatch API Secret. |
| `COINCATCH_PASSPHRASE` | Your CoinCatch API Passphrase. |
| `PORT` | (Optional) The port for the web server. Defaults to `5000`. |

## Strategy

The bot implements a simple MACD crossover strategy:

*   **BUY Signal:** MACD line crosses above the Signal line. The bot attempts to buy a fixed amount of **SOL** using **USDT**.
*   **SELL Signal:** MACD line crosses below the Signal line. The bot attempts to sell a fixed amount of **SOL** for **USDT**.

The bot uses a fixed trade amount of **0.1 SOL** per trade, which can be adjusted in the `solana_bot.py` file or via the dashboard.

## Dependencies

This project requires Python 3.x and the following libraries:

*   `flask`
*   `pandas`
*   `numpy`
*   `requests`
*   `gunicorn`

Install them using:
\`\`\`bash
pip install -r requirements.txt
\`\`\`

## Running the Bot

1.  **Set Environment Variables:** Ensure the three `COINCATCH_` variables are set in your Railway project.
2.  **Run the application:** Railway will automatically run the application using the `Procfile`.
3.  **Access the Dashboard:** The bot runs a simple web dashboard (usually on port 5000) to view status, balances, and trade history.
    \`\`\`
    http://<YOUR_RAILWAY_DOMAIN>
    \`\`\`
