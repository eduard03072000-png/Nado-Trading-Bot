# 🤖 NADO DEX Trading Bot

Multi-wallet automated trading bot for NADO DEX perpetual futures with Telegram interface.

## ✨ Features

### 📊 Multi-Wallet Support
- **Wallet 1** (0x45E293D6...): Direct trading without subaccount
- **Wallet 2** (0x5F62E505...): Trading through subaccount
- Independent position tracking per wallet
- Separate trade history for each wallet

### 🎯 Trading Modes
- **Manual Trading**: Open LONG/SHORT positions via Telegram
- **Grid Auto-Trader**: Automated grid trading with take-profit levels
- **ML Auto-Trader**: Machine learning-based predictions (58% accuracy)

### 🛡️ Risk Management
- Automatic TP/SL placement (+0.03% TP)
- Leverage control (default 10x)
- Position size validation
- Balance monitoring

### 📱 Telegram Interface
- Real-time position monitoring
- One-click position opening
- Auto-trader start/stop controls
- Balance & PnL tracking

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- NADO DEX account with funded wallet
- Telegram Bot Token

### Installation

1. **Clone repository**
```bash
git clone https://github.com/eduard03072000-png/Nado-Trading-Bot.git
cd Nado-Trading-Bot
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure `.env`**
```env
# Wallet 1 (Direct Trading)
BOT_PRIVATE_KEY=0x...
NADO_WALLET_ADDRESS=0x45E293D6F82b6f94F8657A15daB479dcbE034b39

# Wallet 2 (Subaccount Trading)
BOT_PRIVATE_KEY_2=0x...
NADO_WALLET_ADDRESS_2=0x5F62E505D28B583A396c58fE72227abfc2815549
NADO_SUBACCOUNT_ID_2=0x5f62e505...

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

4. **Run bot**
```bash
python telegram_trading_bot.py
```

Or use Windows batch file:
```bash
RUN_BOT.bat
```

## 📖 Usage

### Start Bot
Send `/start` in Telegram to initialize the bot

### Manual Trading
1. Click **"📈 Open Position"**
2. Select LONG 🟢 or SHORT 🔴
3. Choose wallet (Wallet 1 or Wallet 2)
4. Select trading pair (ETH-PERP, SOL-PERP, etc.)
5. Enter position size
6. Confirm order

### Grid Auto-Trader
1. Click **"🤖 Auto Grid"**
2. Select wallet
3. Choose trading pair
4. Enter position size
5. Auto-trader will:
   - Open position
   - Place TP orders at +0.03%
   - Monitor and execute TPs
   - Re-enter positions automatically

### ML Auto-Trader
1. Click **"🧠 ML Auto"**
2. Select wallet and pair
3. ML model predicts:
   - Direction (UP/DOWN/HOLD)
   - Confidence level
   - Suggested position size
4. Auto-executes trades based on predictions

## 🏗️ Architecture

```
telegram_trading_bot.py       # Main Telegram interface
├── multi_wallet_dashboard.py # Multi-wallet management
├── trading_dashboard_v2.py   # Core trading logic
├── grid_autotrader.py        # Grid trading automation
├── ml_autotrader.py          # ML-based trading
├── historical_data_provider.py # Market data fetching
└── tp_sl_calculator.py       # TP/SL calculations
```

## 📊 Data Files

- `positions_data_wallet1.json` - Wallet 1 positions
- `positions_data_wallet2.json` - Wallet 2 positions
- `trade_history_wallet1.json` - Wallet 1 history
- `trade_history_wallet2.json` - Wallet 2 history
- `traders_status.json` - Auto-trader states
- `ml_model_trained.pkl` - Trained ML model

## 🔧 Configuration

### Leverage Settings
Default: 10x (adjustable via Telegram)

### Trading Pairs Supported
- ETH-PERP (Product ID: 2)
- SOL-PERP (Product ID: 3)
- BTC-PERP (Product ID: 1)
- And more...

### Auto TP Settings
- Default: +0.03% above entry
- Automatically placed on position open

## ⚠️ Important Notes

### Wallet Configuration
- **Wallet 1**: Trades DIRECTLY from wallet address (no subaccount)
- **Wallet 2**: Trades through SUBACCOUNT (requires setup)

### Subaccount vs Direct Trading
- **Direct**: Positions editable on DEX interface ✅
- **Subaccount**: May have editing restrictions ⚠️

### First-Time Setup
Ensure wallets have:
1. Funded USDC balance
2. Previous deposits on NADO DEX
3. Proper network connection

## 🐛 Troubleshooting

### "No previous deposits" Error
- Make at least one deposit on NADO DEX
- Verify wallet address in `.env`

### Positions Not Visible on DEX
- Check if using correct wallet mode (direct vs subaccount)
- Verify sender_hex configuration

### Balance Shows None
- Ensure subaccount_hex is set correctly
- Check wallet has sufficient funds

## 📝 Development

### Adding New Features
1. Create feature branch
2. Test thoroughly with small positions
3. Update documentation
4. Submit PR

### Training ML Model
```bash
python train_ml_model.py
```

### Testing
```bash
python test_ml_auto.py
```

## 🤝 Contributing

Contributions welcome! Please:
1. Fork repository
2. Create feature branch
3. Test changes
4. Submit pull request

## 📄 License

MIT License - See LICENSE file

## ⚠️ Disclaimer

**Trading cryptocurrency perpetual futures involves substantial risk of loss.**

- This bot is for educational purposes
- No guarantee of profits
- Use at your own risk
- Start with small positions
- Never risk more than you can afford to lose

## 🔗 Links

- [NADO DEX](https://www.nado.fun/)
- [Telegram Bot API](https://core.telegram.org/bots)
- [NADO Protocol Docs](https://docs.nado.fun/)

---

**Made with ❤️ by eduard03072000**

Last Updated: February 12, 2026
