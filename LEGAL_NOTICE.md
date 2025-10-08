# Legal Notice - Amazon Price Tracker Bot

## Data Collection & Usage

This bot uses **100% legal methods** to access Amazon product information:

### 1. Amazon Product Advertising API (PA API 5.0)

**LEGAL - Official Amazon API**

- **What it does:** Fetches current product prices, titles, images, and availability
- **Authorization:** Requires Amazon Associates Program approval
- **Documentation:** https://webservices.amazon.com/paapi5/documentation/
- **License Agreement:** https://affiliate-program.amazon.com/help/operating/agreement
- **Rate Limits:** 1 request/second (8,640 requests/day) on free tier
- **Compliance:** Fully compliant with Amazon Terms of Service

**Legal Basis:**
- Licensed use under Amazon Associates Program Operating Agreement
- Proper API credentials (Access Key + Secret Key)
- Affiliate tag attribution in all product links

### 2. Keepa API (Price History Data)

**SEMI-LEGAL - Third-party service in grey area**

- **What it does:** Provides historical min/max prices for products
- **Status:** Commercial service that Amazon tolerates but doesn't officially endorse
- **Documentation:** https://keepa.com/#!api
- **Rate Limits:** Varies by subscription tier
- **Usage in this bot:** ONLY for historical price data (min/max bounds)

**Legal Considerations:**
- Keepa operates in a grey area (not official Amazon partner)
- Widely used by price tracking services (CamelCamelCamel, etc.)
- No known legal action by Amazon against Keepa users
- **Risk level:** LOW - Amazon has not pursued Keepa or its users

**Note:** If Amazon objects to Keepa usage, bot can be modified to use ONLY PA API for all data.

---

## What This Bot Does NOT Do

### ❌ Web Scraping (REMOVED)

**Previous version of this bot used web scraping - THIS HAS BEEN REMOVED**

- ❌ NO direct HTTP requests to Amazon product pages
- ❌ NO HTML parsing of Amazon content
- ❌ NO user-agent spoofing
- ❌ NO evasion of Amazon's anti-bot measures

**File removed:** `src/price_fetcher.py` (scraping module)

**Reason:** Web scraping violates Amazon Terms of Service and is illegal in many jurisdictions.

---

## User Privacy

### Data We Collect

1. **Telegram User Data:**
   - User ID (required for bot functionality)
   - Username, first name, last name (optional, for display)
   - NOT stored: phone number, email, or personal messages

2. **Tracked Products:**
   - Amazon ASIN (product identifier)
   - Domain (amazon.com, amazon.it, etc.)
   - Historical prices (min/max/current)
   - User's custom settings (none currently)

3. **Logs:**
   - Error logs (for debugging)
   - API call logs (for rate limit monitoring)
   - NOT logged: message content, personal information

### Data Retention

- **User data:** Stored until user removes product or deletes account
- **Logs:** Rotated periodically (default: 30 days)
- **No data sharing:** Your data is NEVER sold or shared with third parties

### GDPR Compliance (EU Users)

If you're in the EU, you have the right to:
- **Access:** Request copy of your data
- **Deletion:** Request deletion of your data (use `/remove all`)
- **Portability:** Export your tracked products
- **Rectification:** Correct inaccurate data

Contact: [Your contact email/Telegram]

---

## Affiliate Disclosure

### Amazon Associates Program

This bot participates in the Amazon Associates Program:

**What this means:**
- Product links include an affiliate tag
- If you purchase through bot links, we may earn a small commission
- **NO extra cost to you** - prices are identical
- Commission helps cover bot hosting costs

**Transparency:**
- All product links clearly show `tag=YOUR_AFFILIATE_TAG`
- You can remove the tag manually if preferred
- Bot functionality works the same with or without purchases

**Compliance:**
- Proper disclosure in bot messages
- Affiliate tag in all product URLs
- No deceptive pricing or false scarcity claims

---

## Terms of Use

### User Responsibilities

By using this bot, you agree to:

1. **Legal Use Only**
   - Use bot for personal price tracking only
   - DO NOT use for commercial scraping or resale
   - DO NOT abuse API rate limits

2. **Accuracy Disclaimer**
   - Prices shown are informational only
   - **ALWAYS verify prices on Amazon before purchasing**
   - Bot is not liable for price discrepancies

3. **No Warranty**
   - Bot provided "AS IS" without warranty
   - No guarantee of uptime or accuracy
   - Use at your own risk

4. **Compliance**
   - You must comply with Amazon's Terms of Service
   - You must comply with your local laws
   - Bot owner not responsible for user misuse

### Bot Owner Responsibilities

We commit to:

1. **Legal Compliance**
   - Use ONLY authorized Amazon APIs
   - Respect rate limits and API terms
   - Remove illegal features if identified

2. **Data Protection**
   - Secure storage of user data
   - No sale or sharing of user data
   - Proper deletion on user request

3. **Transparency**
   - Clear disclosure of affiliate relationships
   - Open source code (if public repo)
   - Prompt response to legal concerns

---

## Legal Disclaimers

### Amazon Relationship

**NOT AFFILIATED:** This bot is NOT affiliated with, endorsed by, or sponsored by Amazon.com, Inc. or its affiliates.

**Trademarks:** "Amazon" and the Amazon logo are trademarks of Amazon.com, Inc. or its affiliates.

### Liability Limitations

**Price Accuracy:**
> Prices and availability are subject to change. This bot displays cached data that may be outdated. Always verify current prices on Amazon.com before making a purchase.

**Service Availability:**
> We do not guarantee uninterrupted service. The bot may be offline due to maintenance, API outages, or other technical issues.

**Data Loss:**
> We are not responsible for loss of tracked products or historical data. Backup your important product lists.

**Purchase Decisions:**
> This bot provides information only. You are solely responsible for purchase decisions. We are not liable for any damages arising from your use of this bot.

---

## API Credentials & Security

### Required Credentials

To run this bot, you need:

1. **Telegram Bot Token**
   - Obtain from: @BotFather on Telegram
   - Scope: Full bot functionality
   - Keep SECRET - do not share publicly

2. **Amazon PA API Credentials**
   - Obtain from: https://webservices.amazon.com/paapi5/documentation/register-for-pa-api.html
   - Requires: Amazon Associates account approval
   - Credentials: Access Key + Secret Key
   - Keep SECRET - do not commit to public repos

3. **Keepa API Key** (Optional)
   - Obtain from: https://keepa.com/#!api
   - Cost: ~€30/month (varies by plan)
   - Alternative: Use ONLY PA API (less historical data)

### Security Best Practices

**Environment Variables:**
```bash
# .env file (DO NOT commit to git)
BOT_TOKEN=your_telegram_bot_token
AMAZON_ACCESS_KEY=your_pa_api_access_key
AMAZON_SECRET_KEY=your_pa_api_secret_key
AFFILIATE_TAG=your_affiliate_tag
KEEPA_API_KEY=your_keepa_key  # optional
```

**Git Ignore:**
```gitignore
# .gitignore
.env
*.db
__pycache__/
```

**Production Deployment:**
- Use environment variables (NOT hardcoded credentials)
- Enable HTTPS for webhooks
- Rotate credentials periodically
- Monitor API usage for suspicious activity

---

## Compliance Checklist

### Before Public Release

- [x] Remove all web scraping code
- [x] Use ONLY official Amazon PA API
- [x] Add affiliate disclosure to bot messages
- [x] Create this LEGAL_NOTICE.md
- [x] Add disclaimer to `/start` and `/help` commands
- [ ] Obtain Amazon Associates approval
- [ ] Test with valid PA API credentials
- [ ] Add privacy policy link to bot
- [ ] Set up GDPR data export/deletion
- [ ] Monitor API rate limits
- [ ] Set up error alerting

### Ongoing Compliance

- [ ] Review Amazon PA API Terms quarterly
- [ ] Update affiliate disclosure if program changes
- [ ] Respond to GDPR requests within 30 days
- [ ] Monitor for Amazon ToS changes
- [ ] Keep dependencies updated (security patches)

---

## Contact & Support

**Bot Operator:** [Your name/handle]  
**Email:** [Your contact email]  
**Telegram:** [Your Telegram handle]  
**GitHub:** [Repo link if public]

**For Legal Inquiries:**
- DMCA takedown requests: [email]
- Data deletion requests: [email]
- Terms of Service questions: [email]

**For Technical Support:**
- Bug reports: [GitHub Issues or email]
- Feature requests: [GitHub or contact]

---

## Updates to This Notice

**Last Updated:** January 2025

We may update this legal notice periodically. Changes will be:
- Announced in bot update messages
- Posted to GitHub (if public)
- Emailed to active users (if applicable)

**Your Continued Use:** By continuing to use the bot after updates, you agree to the revised terms.

---

## Conclusion

This bot is designed to be **100% legal** and **transparent**:

✅ **Official Amazon API** - No scraping  
✅ **Clear affiliate disclosure** - No deception  
✅ **User privacy** - No data selling  
✅ **Open communication** - Prompt legal response  

If you have any legal concerns, please contact us immediately.

---

*This bot is provided for informational purposes only. Prices and availability are subject to change without notice. Always verify on Amazon.com before purchasing.*
