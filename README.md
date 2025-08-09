# Amazon Price Tracker Telegram Bot

🤖 **Advanced Telegram bot for tracking Amazon product prices with automatic notifications and affiliate link support.**

## ✨ Features

### 🎯 Core Functionality
- **Smart Link Detection**: Share any Amazon link to automatically add it for tracking
- **Real-time Price Monitoring**: Integrated with Keepa for accurate price data
- **Automatic Notifications**: Get alerts when prices drop or reach historical minimums
- **Affiliate Link Support**: All product links include your affiliate tag automatically

### 🔧 Advanced Features
- **Price Consistency Validation**: Automatic correction of price data inconsistencies
- **Interactive Commands**: Easy-to-use command interface
- **User-friendly Interface**: Clean HTML formatting with clickable product links
- **Comprehensive Logging**: Detailed logging for debugging and monitoring
- **Database Integration**: SQLite storage with enhanced schema and statistics

### 🤖 Commands
- **Auto-Help**: `/start` automatically shows help and available commands
- **Product Listing**: `/list` - Show all tracked products with current, min, and max prices
- **Product Removal**: `/remove <number>` - Remove specific products from tracking
- **Help**: `/help` - Show detailed command guide

### 📱 Smart Notifications
- **Price Drop Alerts**: Notified when prices drop significantly (>1€ or >5%)
- **Historical Minimum Alerts**: Special notifications for all-time low prices
- **Clickable Links**: All notifications include affiliate links to products

## 🚀 Technical Highlights

- **Keepa Integration**: Professional price tracking data
- **Circuit Breaker Pattern**: Resilient error handling
- **Caching System**: Optimized API calls and performance
- **Price Validation**: Smart price consistency checks
- **Background Monitoring**: Hourly automatic price checks
- **User Statistics**: Track savings and notification history

## 📋 Requirements

- Python 3.11+
- Telegram bot token from @BotFather
- Keepa API access (for price data)

## 🛠️ Setup

### 1️⃣ Environment Setup
```powershell
# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2️⃣ Configuration
```powershell
# Copy example config
Copy-Item .env.example .env

# Edit .env with your settings:
# BOT_TOKEN=your_telegram_bot_token
# AFFILIATE_TAG=your_amazon_affiliate_tag
# KEEPA_API_KEY=your_keepa_api_key
```

### 3️⃣ Run the Bot
```powershell
# Option 1: Direct execution
python src\bot.py

# Option 2: Module execution
python -m src.bot

# Option 3: VS Code task (if available)
# Use "Run Bot" task in VS Code
```

## 📊 Database Schema

The bot uses SQLite with an enhanced schema including:
- **Users**: User information and statistics
- **Items**: Tracked products with price history
- **Price History**: Historical price data
- **User Stats**: Savings tracking and activity metrics
- **System Metrics**: Performance and usage analytics

## 🔄 How It Works

1. **Share a Link**: Send any Amazon product URL to the bot
2. **Automatic Processing**: Bot extracts product info and gets price data from Keepa
3. **Smart Storage**: Saves with price consistency validation
4. **Background Monitoring**: Checks prices every hour automatically
5. **Smart Notifications**: Alerts you when prices drop or hit minimums
6. **Easy Management**: Use `/list` and `/remove` to manage your products

## 📈 Price Tracking Logic

- **Current Price**: Real-time price from Amazon
- **Min/Max Prices**: Historical data from Keepa
- **Consistency Validation**: Automatic correction if current price is outside min/max bounds
- **Smart Notifications**: Only notifies on significant price changes

## 🔒 Security Features

- **User Isolation**: Users can only access their own products
- **Input Validation**: Comprehensive validation of all user inputs
- **Error Handling**: Graceful error handling with user feedback
- **Rate Limiting**: Respectful API usage patterns

## 🎯 Use Cases

- **Deal Hunting**: Track products for the best prices
- **Wishlist Monitoring**: Get notified when wanted items go on sale
- **Affiliate Marketing**: Automatic affiliate link generation
- **Price Research**: Historical price analysis
- **Budget Planning**: Track when products hit your target price

## 📝 Notes

- Respects Amazon's terms of service and rate limits
- Uses Keepa for reliable price data
- Includes comprehensive error handling and logging
- Designed for production use with proper monitoring
- Supports multiple users with individual tracking

## 🤝 Contributing

This is a production-ready bot with clean, documented code. Feel free to contribute improvements or report issues.

## 📄 License

Private project - all rights reserved.
