# ⚡ Nado DEX Trading Bot

Automated trading bot for [Nado DEX](https://app.nado.xyz/perpetuals) — perpetual futures on Ink Network (Nado Protocol).  
Full Telegram control + Mini App WebUI for trading from your phone.

---

## 📱 Features

- **Telegram Bot** — full trading control via inline keyboard
- **Telegram Mini App** — mobile trading dashboard (balance, positions, LONG/SHORT)
- **Multi-wallet** — 2 wallets simultaneously, isolated strategies
- **Grid Auto-Trader** — automated grid trading strategy
- **Candle Restart / Risk Stop** — smart strategy activation logic
- **TP/SL** — automatic take profit & stop loss orders
- **Trade History** — full history with PnL tracking
- **Server deployment** — runs 24/7 on VPS via systemd

---

## 🖥️ Mini App Preview

The Telegram Mini App opens directly inside Telegram and provides:
- 💰 Real-time balance (Total Equity, Available Margin, Unrealized PnL)
- 📊 Open positions with close button
- 📈 Live market prices (BTC, ETH, SOL)
- ⚡ One-tap LONG/SHORT with leverage slider, TP/SL inputs
- 🔄 Switch between Wallet 1 and Wallet 2

---

## 🚀 Quick Start

### 1. Clone & install
```bash
git clone https://github.com/eduard03072000-png/Nado-Trading-Bot.git
cd Nado-Trading-Bot
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
# Fill in your keys in .env
```

### 3. Run locally
```bash
python telegram_trading_bot.py
```

### 4. Deploy to server (systemd)
```bash
# Copy files to server, then:
systemctl enable trading-bot trading-webapp
systemctl start trading-bot trading-webapp
```

---

## ⚙️ Configuration (.env)

```env
# Wallet 1
BOT_PRIVATE_KEY=0x...
NADO_WALLET_ADDRESS=0x...
NADO_SUBACCOUNT_ID=0x...

# Wallet 2 (optional)
BOT_PRIVATE_KEY_2=0x...
NADO_WALLET_ADDRESS_2=0x...
NADO_SUBACCOUNT_ID_2=0x...

# Telegram Bot 1
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Telegram Bot 2 (optional)
TELEGRAM_BOT_TOKEN_2=...
TELEGRAM_CHAT_ID_2=...

# Network
NADO_NETWORK=mainnet
NADO_RPC_URL=https://rpc-gel.inkonchain.com/
```

---

## 📁 Project Structure

```
Nado-Trading-Bot/
├── telegram_trading_bot.py      # Main Telegram bot
├── trading_dashboard_v2.py      # Core trading engine (Nado API)
├── multi_wallet_dashboard.py    # Multi-wallet manager
├── webapp_server.py             # Flask API server for Mini App
├── webapp/
│   └── index.html               # Telegram Mini App UI
├── config/
│   ├── config.json              # Trading settings
│   └── strategies.json          # Strategy configs
├── historical_data_provider.py  # Historical price data
├── trade_history_manager.py     # Trade history & PnL
├── tp_sl_calculator.py          # TP/SL calculator
├── history_handlers.py          # History display handlers
├── config.py                    # Config loader
└── .env.example                 # Environment template
```

---

## 🔧 Tech Stack

- **Python 3.12**
- **nado-protocol** — Nado DEX SDK
- **python-telegram-bot 22** — Telegram Bot API
- **Flask** — Mini App API server
- **nginx + Let's Encrypt** — HTTPS for Mini App
- **systemd** — process management on VPS

---

## 🌐 Supported Markets

| Symbol | Product ID |
|--------|-----------|
| BTC-PERP | 2 |
| ETH-PERP | 4 |
| SOL-PERP | 8 |

---

## ⚠️ Disclaimer

This bot trades real funds on a live DEX. Use at your own risk.  
Always test with small amounts first. The authors are not responsible for any financial losses.

---

## 📄 License

MIT
