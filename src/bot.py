from typing import Optional
import re
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Imports
try:
    from src import db
    from src.config import config, validate_config
    from src.logger import logger
    from src.keepa_client import fetch_lifetime_min_max, fetch_lifetime_min_max_current
    from src.utils import extract_asin, with_affiliate, truncate, resolve_and_normalize_amazon_url
    from src.price_fetcher import fetch_price_and_title
    from src.cache import keepa_cache  # added
except ImportError:
    import db
    from config import config, validate_config
    from logger import logger
    from keepa_client import fetch_lifetime_min_max, fetch_lifetime_min_max_current
    from utils import extract_asin, with_affiliate, truncate, resolve_and_normalize_amazon_url
    from price_fetcher import fetch_price_and_title
    from cache import keepa_cache  # added

AMAZON_URL_RE = re.compile(
    r'(https?://(?:www\.)?(?:amzn\.to|amzn\.eu|amzn\.in|amazon\.(?:com|co\.uk|de|fr|it|es|ca|co\.jp|in|com\.mx))/[^\s]+)',
    re.IGNORECASE,
)

def validate_amazon_url(url: str) -> bool:
    """Validate Amazon URL"""
    supported_domains = ['amazon.com', 'amazon.co.uk', 'amazon.de', 'amazon.fr', 'amazon.it', 'amazon.es', 'amazon.ca', 'amazon.co.jp', 'amazon.in', 'amazon.com.mx', 'amzn.to', 'amzn.eu', 'amzn.in']
    return any(domain in url.lower() for domain in supported_domains)

def validate_price_consistency(current_price: float, min_price: float, max_price: float) -> tuple[float, float]:
    """
    Validate price consistency. Current price is never changed, adjust min/max if needed.
    Returns corrected (min_price, max_price)
    """
    corrected_min = min_price
    corrected_max = max_price
    
    # If current price is lower than recorded min, update min
    if current_price < min_price:
        corrected_min = current_price
        logger.info("Adjusted min price", old_min=min_price, new_min=current_price, current=current_price)
    
    # If current price is higher than recorded max, update max
    if current_price > max_price:
        corrected_max = current_price
        logger.info("Adjusted max price", old_max=max_price, new_max=current_price, current=current_price)
    
    return corrected_min, corrected_max

async def ensure_user_in_db(update: Update) -> None:
    """Ensure user exists in database"""
    user = update.effective_user
    if user:
        db.ensure_user(user.id, user.username, user.first_name, user.last_name)

async def send_price_notification(user_id: int, asin: str, title: str, old_price: float, new_price: float, min_price: float, app: Application) -> None:
    """Send price notification to user"""
    try:
        aff_url = with_affiliate(f"https://amazon.it/dp/{asin}")
        title_display = truncate(title, 40)
        clickable_title = f"<a href=\"{aff_url}\">{title_display}</a>"
        
        # Check if it's a historical minimum
        is_historical_min = abs(new_price - min_price) < 0.01
        
        hist_line = f"🏷️ <b>Historical Min:</b> €{min_price:.2f}" if min_price is not None else ""
        if is_historical_min:
            # Historical minimum notification (include explicit min line)
            message = (
                f"🔥 <b>HISTORICAL MINIMUM!</b> 🔥\n\n"
                f"📦 {clickable_title}\n\n"
                f"💰 <b>New Price:</b> €{new_price:.2f}\n"
                f"📉 <b>Previous:</b> €{old_price:.2f}\n"
                f"💡 <b>Savings:</b> €{old_price - new_price:.2f}\n"
                f"{hist_line}\n\n"
                f"🎯 <b>This is the lowest price ever recorded!</b>"
            )
        else:
            # Regular price drop notification (append historical min line)
            message = (
                f"📉 <b>Price Drop Alert!</b>\n\n"
                f"📦 {clickable_title}\n\n"
                f"💰 <b>New Price:</b> €{new_price:.2f}\n"
                f"📈 <b>Previous:</b> €{old_price:.2f}\n"
                f"💡 <b>Savings:</b> €{old_price - new_price:.2f}\n"
                f"{hist_line}"
            )
        
        await app.bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
        logger.info("Price notification sent", user_id=user_id, asin=asin, old_price=old_price, new_price=new_price, is_historical_min=is_historical_min)
        
    except Exception as e:
        logger.error("Error sending notification", error=str(e), user_id=user_id, asin=asin)

async def check_price_changes(app: Application) -> None:
    """Check for price changes and send notifications"""
    try:
        # Get all tracked items
        all_items = db.get_all_items()
        if not all_items: 
            return
        # Grouping logic remains
        asin_to_items = {}
        for item in all_items:
            asin = item.get('asin')
            if asin:
                asin_to_items.setdefault(asin, []).append(item)
        if not asin_to_items:
            return
        asins = list(asin_to_items.keys())
        keepa_data = fetch_lifetime_min_max_current(asins)
        # Scrape tasks
        scrape_tasks = {}
        for asin, items in asin_to_items.items():
            sample_url = items[0].get('url')
            if sample_url:
                scrape_tasks[asin] = asyncio.create_task(fetch_price_and_title(sample_url))
        scrape_results = {}
        if scrape_tasks:
            for asin, task in scrape_tasks.items():
                try:
                    title_s, scraped_price, _currency = await task
                    scrape_results[asin] = (title_s, scraped_price)
                except Exception as e:
                    logger.warning("Scrape failed", asin=asin, error=str(e))
        cache_updates = {}  # new
        for asin, items in asin_to_items.items():
            keepa_entry = keepa_data.get(asin)
            if not keepa_entry:
                continue
            min_price, max_price, keepa_current = keepa_entry
            if not min_price or not max_price:
                continue
            scraped_title, scraped_price = scrape_results.get(asin, (None, None))
            if scraped_price:
                current_price = scraped_price
                source = "scrape"
            elif keepa_current:
                current_price = keepa_current
                source = "keepa"
            else:
                current_price = (min_price + max_price) / 2
                source = "avg"
            logger.info("Resolved current price", asin=asin, source=source, current=current_price)
            adj_min, adj_max = validate_price_consistency(current_price, min_price, max_price)
            cache_updates[asin] = (min_price, max_price, current_price)  # record authoritative current
            for item in items:
                old_price = item.get('last_price')
                if not isinstance(old_price, (int, float)):
                    continue
                price_drop = old_price - current_price
                if price_drop > 1.0 or (price_drop / old_price) > 0.05:
                    await send_price_notification(
                        user_id=item['user_id'],
                        asin=asin,
                        title=item['title'] or (scraped_title or f"Product {asin}"),
                        old_price=old_price,
                        new_price=current_price,
                        min_price=adj_min,
                        app=app
                    )
                    try:
                        db.update_price(item['id'], current_price)
                    except Exception as e:
                        logger.warning("DB update failed", item_id=item['id'], error=str(e))
        if cache_updates:
            try:
                keepa_cache.set_lifetime_minmax_current(list(cache_updates.keys()), cache_updates)
            except Exception as e:
                logger.warning("Failed to update keepa cache after price check", error=str(e))
        logger.info("Price check completed", items_checked=len(all_items), asins_checked=len(asins), cache_updates=len(cache_updates))
    except Exception as e:
        logger.error("Error in price check", error=str(e))

async def periodic_price_check(app: Application) -> None:
    """Run periodic price checks every hour"""
    while True:
        await asyncio.sleep(10)  # Check every hour
        await check_price_changes(app)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command - automatically shows help"""
    await ensure_user_in_db(update)
    # Automatically call help command
    await cmd_help(update, context)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command"""
    await update.message.reply_text(
        "🤖 <b>Available Commands</b>\n\n"
        "/list — Show tracked products with prices\n"
        "/remove &lt;number&gt; — Remove specific product\n"
        "/remove all — Remove all tracked products\n"
        "/help — Show this guide\n\n"
        "💡 <b>Tip:</b> Share an Amazon link to add it automatically!\n"
        "📢 <b>Notifications:</b> You'll be alerted when prices drop!",
        parse_mode="HTML"
    )

async def handle_shared_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle shared Amazon links - MAIN FUNCTIONALITY"""
    await ensure_user_in_db(update)
    user = update.effective_user
    text = update.message.text
    
    m = AMAZON_URL_RE.search(text)
    if not m:
        # If message contains a URL but not an Amazon link, notify user once
        lowered = text.lower()
        if ("http://" in lowered or "https://" in lowered or "www." in lowered):
            await update.message.reply_text(
                "❌ Unsupported link. Please send a valid Amazon product link (amazon.* or amzn.to)."
            )
        return
    
    url = m.group(1)
    
    if not validate_amazon_url(url):
        return

    # Expand short link and normalize (/dp/ASIN) form
    try:
        url = await resolve_and_normalize_amazon_url(url)
    except Exception:
        pass
    
    msg = await update.message.reply_text("🔍 Processing Amazon link...")
    
    try:
        # Extract ASIN (after resolution/normalization)
        asin = extract_asin(url)
        if not asin:
            await msg.edit_text("❌ Cannot extract ASIN from this link")
            return

        # Check if product already tracked by this user
        try:
            existing = db.get_item_by_user_and_asin(user.id, asin)
        except Exception:
            existing = None
        if existing:
            # Fetch latest Keepa (maybe cached) to show up-to-date data
            keepa_existing = fetch_lifetime_min_max_current([asin]) or {}
            k_min, k_max, k_current = keepa_existing.get(asin, (existing.get('min_price'), existing.get('max_price'), existing.get('last_price')))
            current_display = k_current or existing.get('last_price') or existing.get('min_price') or 0
            min_display = k_min or existing.get('min_price') or current_display
            max_display = k_max or existing.get('max_price') or current_display
            title_display_full = existing.get('title') or f"Amazon Product {asin}"
            aff_url_existing = with_affiliate(existing.get('url'))
            title_display = truncate(title_display_full, 60)
            clickable_title_existing = f"<a href=\"{aff_url_existing}\">{title_display}</a>"
            await msg.edit_text(
                "ℹ️ <b>Already Tracked</b>\n\n"
                f"📦 {clickable_title_existing}\n"
                f"💰 <b>Current Price:</b> €{current_display:.2f}\n"
                f"📉 <b>Min Price:</b> €{min_display:.2f}\n"
                f"📈 <b>Max Price:</b> €{max_display:.2f}\n\n"
                "Use /list to view all your products.",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            logger.info("Duplicate add prevented", asin=asin, user_id=user.id)
            return

        # Get product title and current price (use resolved URL)
        title, current_price, currency = await fetch_price_and_title(url)
        if not title:
            title = f"Amazon Product {asin}"

        if not current_price:
            await msg.edit_text("❌ Cannot fetch current price for this product")
            return

        # Get Keepa data
        keepa_data = fetch_lifetime_min_max_current([asin])
        min_price, max_price, current_price_from_keepa = keepa_data.get(asin, (None, None, None))

        if not min_price or not max_price:
            await msg.edit_text("❌ No price data found for this product")
            return

        # Use current price if available, otherwise fallback to current_price_from_keepa 
        if not current_price:
            current_price = current_price_from_keepa

        # Validate price consistency - adjust min/max if needed but keep current price
        corrected_min, corrected_max = validate_price_consistency(current_price, min_price, max_price)

        # Add to database with current price and corrected min/max
        item_id = db.add_item(
            user_id=user.id,
            url=url,
            asin=asin,
            title=title,
            currency=currency or "EUR",
            price=current_price  # Use actual current price
        )

        # Create affiliate link for display
        aff_url = with_affiliate(url)
        title_display = truncate(title, 60)
        clickable_title = f"<a href=\"{aff_url}\">{title_display}</a>"
        
        response = (
            f"✅ <b>Product Added!</b>\n\n"
            f"📦 {clickable_title}\n"
            f"💰 <b>Current Price:</b> €{current_price:.2f}\n"
            f"📉 <b>Min Price:</b> €{corrected_min:.2f}\n"
            f"📈 <b>Max Price:</b> €{corrected_max:.2f}\n\n"
            f"📢 <b>You'll be notified when the price change!</b>"
        )
        
        await msg.edit_text(response, parse_mode="HTML", disable_web_page_preview=True)
        logger.info("Product added via shared link", asin=asin, title=title[:30], current_price=current_price, min_price=corrected_min, max_price=corrected_max)
        try:
            keepa_cache.set_lifetime_minmax_current([asin], {asin: (corrected_min, corrected_max, current_price)})
        except Exception as e:
            logger.warning("Failed to update keepa cache on add", asin=asin, error=str(e))
        
    except Exception as e:
        logger.error("Error processing shared link", error=str(e))
        await msg.edit_text("❌ Error processing the link")

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List tracked products with fresh Keepa data - MAIN FUNCTIONALITY"""
    await ensure_user_in_db(update)
    user = update.effective_user
    
    rows = db.list_items(user.id)
    if not rows:
        await update.message.reply_text(
            "📦 <b>No products tracked yet!</b>\n\n"
            "Share an Amazon link to start! 🛒",
            parse_mode="HTML"
        )
        return
    
    msg = await update.message.reply_text("🔍 Fetching updated data...")
    
    try:
        # Get all ASINs for fresh Keepa lookup
        asins = [r['asin'] for r in rows if r.get('asin')]

        if not asins:
            await msg.edit_text("❌ No valid ASINs found in tracked products")
            return

        # Fetch Keepa data (min/max + maybe current)
        keepa_data = fetch_lifetime_min_max_current(asins)
        logger.info("Fetched Keepa data for list view", asins_requested=len(asins), data_received=len(keepa_data))

        lines = ["🛒 <b>Your Tracked Products:</b>\n"]
        
        for i, r in enumerate(rows, 1):
            asin = r.get('asin')
            if not asin:
                continue
                
            # Get fresh Keepa data
            if asin in keepa_data:
                min_price, max_price, current_price = keepa_data[asin]
                
                if min_price and max_price:
                    # Use current price from Keepa if available, otherwise fallback to average
                    if not current_price:
                        current_price = (min_price + max_price) / 2
                    
                    # Create clickable affiliate link with product title
                    title = truncate(r['title'] or f"Product {asin}", 40)
                    aff_url = with_affiliate(r['url'])
                    clickable_title = f"<a href=\"{aff_url}\">{title}</a>"
                    
                    # Apply price consistency validation using Keepa current price
                    if current_price:
                        corrected_min, corrected_max = validate_price_consistency(current_price, min_price, max_price)
                        
                        # Update database if corrections were made
                        if corrected_min != min_price or corrected_max != max_price:
                            # Update min/max in database
                            try:
                                db.update_price_bounds(r['id'], corrected_min, corrected_max)
                                logger.info("Updated price consistency in list", 
                                          item_id=r['id'], 
                                          old_min=min_price, new_min=corrected_min,
                                          old_max=max_price, new_max=corrected_max,
                                          current=current_price)
                            except Exception as e:
                                logger.warning("Failed to update price consistency", error=str(e), item_id=r['id'])
                        
                        # Use corrected values for display
                        display_min, display_max = corrected_min, corrected_max
                    else:
                        display_min, display_max = min_price, max_price
                    
                    line = f"{i}. {clickable_title}\n"
                    line += f"   💰 <b>Current:</b> €{current_price:.2f}\n"
                    line += f"   📉 <b>Min:</b> €{display_min:.2f}\n"
                    line += f"   📈 <b>Max:</b> €{display_max:.2f}"
                    
                    lines.append(line)
                else:
                    title = truncate(r['title'] or f"Product {clickable_title}", 40)
                    lines.append(f"{i}. {title} - ❌ Data unavailable")
            else:
                title = truncate(r['title'] or f"Product {clickable_title}", 40)
                lines.append(f"{i}. {title} - ❌ Product not found")

        if len(lines) == 1:  # Only header
            await msg.edit_text("❌ No data available for tracked products")
            return
        
        await msg.edit_text("\n\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
        
    except Exception as e:
        logger.error("Error in list command", error=str(e))
        await msg.edit_text("❌ Error fetching data")

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove tracked product(s)"""
    await ensure_user_in_db(update)
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ <b>Usage:</b>\n"
            "/remove &lt;number&gt; — Remove specific product\n"
            "/remove all — Remove all products\n\n"
            "Use /list to see product numbers",
            parse_mode="HTML"
        )
        return
    
    arg = context.args[0].lower()
    
    # Handle "remove all" command
    if arg == "all":
        rows = db.list_items(user.id)
        if not rows:
            await update.message.reply_text(
                "📦 <b>No products to remove!</b>\n\n"
                "Your tracking list is already empty.",
                parse_mode="HTML"
            )
            return
        
        # Remove all items directly
        count = len(rows)
        removed_count = 0
        for item in rows:
            if db.remove_item(user.id, item['id']):
                removed_count += 1
                asin_for_cache = item.get('asin')
                if asin_for_cache:
                    try:
                        # Remove possible single-ASIN cache variants
                        keepa_cache.cache.delete(f"minmax_current:{asin_for_cache}")
                        keepa_cache.cache.delete(f"product:{asin_for_cache}")
                    except Exception:
                        pass
        
        if removed_count > 0:
            await update.message.reply_text(
                f"✅ <b>Successfully removed {removed_count} products!</b>\n\n"
                f"Your tracking list is now empty.",
                parse_mode="HTML"
            )
            logger.info("Removed all products", user_id=user.id, count=removed_count)
        else:
            await update.message.reply_text(
                "❌ Error removing products. Please try again.",
                parse_mode="HTML"
            )
        return
    
    # Handle single product removal by number
    if not arg.isdigit():
        await update.message.reply_text(
            "❌ <b>Invalid argument!</b>\n\n"
            "<b>Usage:</b>\n"
            "/remove &lt;number&gt; — Remove specific product\n"
            "/remove all — Remove all products\n\n"
            "Use /list to see product numbers",
            parse_mode="HTML"
        )
        return
    
    index = int(arg) - 1
    rows = db.list_items(user.id)
    
    if index < 0 or index >= len(rows):
        await update.message.reply_text(
            "❌ Invalid product number. Use /list to see available products.",
            parse_mode="HTML"
        )
        return
    
    item = rows[index]
    success = db.remove_item(user.id, item['id'])
    
    if success:
        title = truncate(item['title'] or f"Product {item.get('asin', 'N/A')}", 30)
        await update.message.reply_text(
            f"✅ Removed: <b>{title}</b>",
            parse_mode="HTML"
        )
        logger.info("Removed single product", user_id=user.id, item_id=item['id'], title=title)
        asin_for_cache = item.get('asin')
        if asin_for_cache:
            try:
                keepa_cache.cache.delete(f"minmax_current:{asin_for_cache}")
                keepa_cache.cache.delete(f"product:{asin_for_cache}")
            except Exception:
                pass
    else:
        await update.message.reply_text(
            "❌ Error removing product. Please try again.",
            parse_mode="HTML"
        )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors"""
    logger.error("Bot error", error=str(context.error))

def main() -> None:
    validate_config()
    db.init_db()
    
    logger.info("Starting Amazon Keepa Price Tracker Bot with notifications")
    
    app = Application.builder().token(config.bot_token).build()
    
    # Essential handlers only
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_shared_link))
    
    # Unknown command handler (must be after known commands)
    async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("❌ Unknown command. Use /help to see the available commands.")
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    app.add_error_handler(error_handler)
    
    # Start periodic price checking in a separate task after the app starts
    async def post_init(application: Application) -> None:
        asyncio.create_task(periodic_price_check(application))
    
    app.post_init = post_init
    
    logger.info("Bot started successfully - Price tracking and notifications active")
    app.run_polling()

if __name__ == "__main__":
    main()
