# Nado-Trading-Bot

Telegram-based trading bot for NADO DEX with ML prediction and automated trading strategies.

## Features

- 🤖 **Telegram Interface** - Full control via Telegram bot
- 📊 **Manual Trading** - Open LONG/SHORT positions with custom TP/SL
- 🎯 **Grid Auto-Trader** - Automated grid trading strategy
- 🧠 **ML Auto-Trader** - Machine learning-based position opening
- 📈 **TP/SL Calculator** - Calculate risk/reward scenarios
- 💰 **Real-time Balance** - Monitor equity and health

## Requirements

- Python 3.10+
- NADO DEX account with API access
- Telegram Bot Token

## Installation

1. Clone the repository:
```bash
git clone https://github.com/eduard03072000-png/Nado-Trading-Bot.git
cd Nado-Trading-Bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your credentials
```

4. Run the bot:
```bash
python telegram_trading_bot.py
```

## Configuration

Edit `.env` file:
```env
# NADO DEX Credentials
NADO_PRIVATE_KEY=your_private_key
NADO_SUBACCOUNT_ID=your_subaccount_id

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_USER_ID=your_telegram_id

# Trading Settings
DEFAULT_LEVERAGE=10
NETWORK=mainnet
```

## Project Structure

```
├── telegram_trading_bot.py    # Main Telegram bot
├── trading_dashboard.py       # Trading logic
├── grid_autotrader.py         # Grid trading strategy
├── ml_autotrader.py           # ML-based trading
├── tp_sl_calculator.py        # TP/SL calculations
├── config.py                  # Configuration loader
├── src/                       # Source modules
│   ├── ml/                    # ML prediction models
│   ├── dex/                   # DEX interaction
│   └── utils/                 # Utilities
└── config/                    # Config files
    ├── config.json
    └── strategies.json
```

## Usage

### Start the Bot
```bash
python telegram_trading_bot.py
```

### Telegram Commands
- `/start` - Main menu
- Use buttons to navigate

### Trading Features

**Manual Trading:**
- Open LONG/SHORT positions
- Set custom TP/SL levels
- Close positions manually

**Grid Auto-Trader:**
- Automated grid orders
- Configurable grid spacing
- 24/7 operation

**ML Auto-Trader:**
- ML-based entry signals
- Configurable confidence threshold
- Automatic TP/SL monitoring

## Safety Features

- ✅ Access control whitelist
- ✅ Minimum notional validation
- ✅ Leverage limits
- ✅ Position size checks
- ✅ Error handling

## 📱 Features Overview

### Main Menu
Full control through intuitive Telegram interface:
- 🟢 **LONG** / 🔴 **SHORT** - Quick position opening
- 📊 **Positions** - Monitor active trades with real-time P&L
- 💰 **Balance** - Check equity and account health
- 📈 **Prices** - View current market prices
- 🎯 **TP/SL Calculator** - Calculate risk/reward scenarios

### 🤖 Grid Auto-Trader
Automated grid trading strategy:
- Places LONG and SHORT orders automatically
- Configurable grid spacing and offset
- Automatic TP/SL execution
- 24/7 unattended operation
- Supports: BTC-PERP, ETH-PERP, SOL-PERP, INK-PERP

### 🧠 ML Auto-Trader
Machine learning-based trading:
- Analyzes market indicators (RSI, MACD, Moving Averages, Volatility)
- Configurable confidence threshold (50-70%)
- Opens positions only on strong ML signals
- Automatic TP/SL monitoring and execution
- Real-time prediction updates (UP/DOWN/SIDEWAYS)

### 📊 Position Management
- Real-time P&L tracking with color coding
- Entry price, current price, and position value
- Automatic TP/SL price display
- One-click position closing
- Support for multiple simultaneous positions

## 🎯 How It Works

1. **Manual Trading**
   - Select LONG or SHORT
   - Choose trading pair
   - Set position size
   - Configure TP/SL levels
   - Confirm and execute

2. **Grid Auto**
   - Select trading pair
   - Set grid offset from current price
   - Bot places orders automatically
   - Closes at TP/SL and repeats

3. **ML Auto**
   - Select trading pair and size
   - Set minimum ML confidence (e.g., 55%)
   - Choose TP/SL scenario
   - Bot analyzes market every minute
   - Opens positions on strong signals
   - Monitors and closes at TP/SL

## License

MIT License

## Disclaimer

⚠️ **Trading cryptocurrencies carries risk. Use at your own risk.**
This bot is for educational purposes. Always test with small amounts first.

## Support

For issues or questions, open an issue on GitHub.
