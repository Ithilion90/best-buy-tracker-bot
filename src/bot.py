from typing import Optional
import time
import re
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Imports
try:
    from src import db
    from src.config import config, validate_config
    from src.logger import logger
    from src.keepa_client import fetch_lifetime_min_max, fetch_lifetime_min_max_current
    from src.amazon_api import fetch_product_data_legal
    from src.utils import (
        extract_asin,
        with_affiliate,
        build_product_url,
        truncate,
        resolve_and_normalize_amazon_url,
        domain_to_currency,
        format_price,
    )
except ImportError:
    from db import db
    from config import config, validate_config
    from logger import logger
    from keepa_client import fetch_lifetime_min_max, fetch_lifetime_min_max_current
    from amazon_api import fetch_product_data_legal
    from utils import (
        extract_asin,
        with_affiliate,
        build_product_url,
        truncate,
        resolve_and_normalize_amazon_url,
        domain_to_currency,
        format_price,
    )

AMAZON_URL_RE = re.compile(
    r'((?:https?://)?(?:www\.|m\.|smile\.)?(?:amzn\.to|amzn\.eu|amzn\.in|a\.co|amzn\.asia|amazon\.(?:com|co\.uk|de|fr|it|es|ca|co\.jp|in|com\.mx))/[^\s]+)',
    re.IGNORECASE,
)

# Shared spinner utility (single implementation used by commands)
async def run_spinner(message, base_text: str, frames: list[str], stop_event: asyncio.Event, interval: float = 0.7):
    i = 0
    last_render = None
    while not stop_event.is_set():
        frame = frames[i % len(frames)]
        text = f"{frame} {base_text}"
        if text != last_render:
            try:
                await message.edit_text(text)
            except Exception:
                pass
            last_render = text
        await asyncio.sleep(interval)
        i += 1


def validate_amazon_url(url: str) -> bool:
    """Validate Amazon URL"""
    supported_domains = ['amazon.com', 'amazon.co.uk', 'amazon.de', 'amazon.fr', 'amazon.it', 'amazon.es', 'amazon.ca', 'amazon.co.jp', 'amazon.in', 'amazon.com.mx', 'amzn.to', 'amzn.eu', 'amzn.in', 'a.co', 'amzn.asia']
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

def extract_domain(url: str) -> Optional[str]:
    """Extract and normalize the Amazon domain (strip www., m., smile.)."""
    try:
        if not url:
            return None
        # Ensure we have a scheme for regex
        tmp = url if url.startswith(('http://', 'https://')) else 'https://' + url
        m = re.search(r'https?://([^/]+)/', tmp + '/')
        if not m:
            return None
        host = m.group(1).lower()
        if 'amazon.' not in host and not host.startswith('amzn.'):
            return None
        # Normalize prefixes
        host = re.sub(r'^(?:www|m|smile)\.', '', host)
        return host
    except Exception:
        return None

async def send_price_notification(user_id: int, asin: str, title: str, old_price: float, new_price: float, min_price: float, max_price: float, app: Application, domain: str | None = None, currency: str | None = None, availability: str | None = None) -> None:
    """Send price notification to user (domain-aware, multi-currency).
    
    Args:
        availability: Product availability status. If 'unavailable', notification is skipped.
    """
    try:
        # Skip notification if product is unavailable
        if availability and availability.lower() == 'unavailable':
            logger.info("Skipping notification for unavailable product", user_id=user_id, asin=asin, domain=domain)
            return
        
        dom = domain or 'amazon.it'
        # Use /dp/ URL with affiliate tag and title for better routing
        aff_url = build_product_url(dom, asin, title)
        title_display = truncate(title, 40)
        clickable_title = f"<a href=\"{aff_url}\">{title_display}</a>"

        # Determine currency (priority: provided currency -> domain mapping)
        curr = currency or domain_to_currency(dom)
        is_historical_min = abs(new_price - min_price) < 0.01 if min_price is not None else False
        hist_line = f"📉 <b>Historical Min:</b> {format_price(min_price, curr)}" if min_price is not None else ""
        # Add hint about checking other sellers for best price
        seller_hint = "\n\n💡 <i>Tip: Check 'Other Sellers' on Amazon for the best price</i>"
        
        if is_historical_min:
            message = (
                f"🔥 <b>HISTORICAL MINIMUM!</b> 🔥\n\n"
                f"📦 {clickable_title}\n\n"
                f"💰 <b>New Price:</b> {format_price(new_price, curr)}\n"
                f"🏷️ <b>Previous:</b> {format_price(old_price, curr)}\n"
                #f"💡 <b>Savings:</b> {format_price(old_price - new_price, curr)}\n"
                f"{hist_line}\n"
                f"📈 <b>Historical Max:</b> {format_price(max_price, curr)}\n\n"
                f"🎯 <b>This is the lowest price ever recorded!</b>"
                f"{seller_hint}"
            )
        else:
            message = (
                f"💡 <b>Price Drop Alert!</b>\n\n"
                f"📦 {clickable_title}\n\n"
                f"💰 <b>New Price:</b> {format_price(new_price, curr)}\n"
                f"🏷️ <b>Previous:</b> {format_price(old_price, curr)}\n"
                #f"💡 <b>Savings:</b> {format_price(old_price - new_price, curr)}\n"
                f"{hist_line}\n"
                f"📈 <b>Historical Max:</b> {format_price(max_price, curr)}"
                f"{seller_hint}"
            )

        # Try to fetch image using Amazon PA API (legal method)
        image_url: Optional[str] = None
        try:
            # Fetch product data from PA API to get image
            _title, _price, _currency, img, _avail = fetch_product_data_legal(asin, dom)
            image_url = img
        except Exception as e:
            logger.warning("Could not fetch image from PA API", error=str(e))
            image_url = None

        def _thumbnail(u: Optional[str]) -> Optional[str]:
            if not u or not isinstance(u, str):
                return None
            # Amazon image URLs often allow size modifiers like ._AC_SX342_. before extension
            import re as _re
            m = _re.search(r'(https://[^\s]+?)(\.[a-zA-Z]{3,4})(?:\?.*)?$', u)
            if not m:
                return u
            base, ext = m.group(1), m.group(2)
            if '._AC_' in base or '._SX' in base:
                return u  # already sized
            # Insert a modest width spec to reduce payload
            return f"{base}._AC_SX342_{ext}"

        image_url = _thumbnail(image_url)

        if image_url:
            try:
                await app.bot.send_photo(chat_id=user_id, photo=image_url, caption=message, parse_mode="HTML")
            except Exception:
                await app.bot.send_message(chat_id=user_id, text=message, parse_mode="HTML", disable_web_page_preview=True)
        else:
            await app.bot.send_message(chat_id=user_id, text=message, parse_mode="HTML", disable_web_page_preview=True)
        logger.info("Price notification sent", user_id=user_id, asin=asin, domain=dom, old_price=old_price, new_price=new_price, is_historical_min=is_historical_min)
    except Exception as e:
        logger.error("Error sending notification", error=str(e), user_id=user_id, asin=asin)

async def refresh_prices_and_notify(app: Application) -> None:
    """Periodic refresh: fetch current price + Keepa bounds and update DB; send notifications."""
    try:
        items = db.get_all_items()
        if not items:
            return
        # Group items by domain only
        domain_group: dict[str, dict[str, list[dict]]] = {}
        for it in items:
            asin = it.get('asin')
            if not asin:
                continue
            dom = it.get('domain') or extract_domain(it.get('url') or '') or (getattr(config, 'keepa_domain', 'amazon.com'))
            domain_group.setdefault(dom, {}).setdefault(asin, []).append(it)
        if not domain_group:
            return

        sem = asyncio.Semaphore(10)

        async def fetch_current_data(asin: str, domain: str):
            """Fetch current product data from Amazon PA API (legal method)"""
            async with sem:
                try:
                    # Use PA API instead of scraping (100% legal)
                    title_s, price_s, currency_s, _img, avail = fetch_product_data_legal(asin, domain)
                    return asin, title_s, price_s, currency_s, avail
                except Exception as e:
                    logger.warning("PA API fetch failed", asin=asin, domain=domain, error=str(e))
                    return asin, None, None, None, None

        updated_items = 0
        for dom, asin_map in domain_group.items():
            asins_dom = list(asin_map.keys())
            # Fetch prices for NEW+USED (all sellers)
            keepa_bounds_dom = fetch_lifetime_min_max_current(asins_dom, domain=dom, new_only=False)
            # Fetch current data from PA API concurrently
            tasks = [fetch_current_data(a, dom) for a in asins_dom]
            api_results: dict[str, tuple[str | None, float | None, str | None, str | None]] = {}
            if tasks:
                for asin, t, p, c, a in await asyncio.gather(*tasks):
                    api_results[asin] = (t, p, c, a)

            for asin, lst in asin_map.items():
                k_min, k_max, k_cur = keepa_bounds_dom.get(asin, (None, None, None)) if keepa_bounds_dom else (None, None, None)
                api_title, api_price, api_currency, api_avail = api_results.get(asin, (None, None, None, None))
                
                # Validate API price currency matches expected domain currency
                expected_currency = domain_to_currency(dom)
                if api_price is not None and api_currency and api_currency != expected_currency:
                    logger.warning(
                        "PA API currency mismatch - discarding price",
                        asin=asin,
                        domain=dom,
                        expected=expected_currency,
                        got=api_currency,
                        price=api_price
                    )
                    # Discard API price if currency doesn't match
                    api_price = None

                # Fallback if keepa missing
                if k_min is None or k_max is None:
                    if api_price is not None:
                        k_min = k_max = api_price
                    elif k_cur is not None:
                        k_min = k_max = k_cur
                    else:
                        lp = lst[0].get('last_price')
                        if isinstance(lp, (int, float)):
                            k_min = k_max = lp
                if k_min is None or k_max is None:
                    continue

                current_price = api_price if api_price is not None else (k_cur if k_cur is not None else (k_min + k_max) / 2)
                adj_min, adj_max = validate_price_consistency(current_price, k_min, k_max)

                for item in lst:
                    old_price = item.get('last_price')
                    # Decide availability to persist with PA API data
                    to_avail = None
                    # Persist only explicit availability from PA API
                    if api_avail in ('unavailable', 'preorder', 'available', 'in_stock'):
                        to_avail = api_avail
                    
                    # Skip notifications if product is unavailable
                    should_notify = to_avail != 'unavailable'
                    
                    try:
                        db.update_price_bounds(item['id'], adj_min, adj_max)
                        db.update_price(item['id'], current_price, availability=to_avail)
                    except Exception as e:
                        logger.warning("Refresh DB update failed", item_id=item['id'], error=str(e))
                    # Notification logic (skip if unavailable)
                    if should_notify and isinstance(old_price, (int, float)):
                        drop = old_price - current_price
                        if drop > 1.0 or (old_price > 0 and drop / old_price > 0.05):
                            if dom and not item.get('domain'):
                                try:
                                    db.update_item_domain(item['id'], dom)
                                except Exception:
                                    pass
                            await send_price_notification(
                                item['user_id'],
                                asin,
                                item.get('title') or (api_title or f"Product {asin}"),
                                old_price,
                                current_price,
                                adj_min,
                                adj_max,
                                app,
                                domain=dom,
                                availability=to_avail,
                            )
                updated_items += 1
        logger.info("Refresh cycle complete", groups=len(domain_group), items_updated=updated_items)
    except Exception as e:
        logger.error("Refresh cycle error", error=str(e))

async def periodic_price_check(app: Application) -> None:
    while True:
        await refresh_prices_and_notify(app)
        # Sleep for 30 minutes between refresh cycles (1800 seconds)
        await asyncio.sleep(1800)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command - automatically shows help"""
    await ensure_user_in_db(update)
    # Automatically call help command
    await cmd_help(update, context)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command with bot logo and legal disclaimer"""
    # Amazon-themed logo URL - Shopping cart with price tag
    # TODO: Replace with your custom logo URL
    logo_url = "https://raw.githubusercontent.com/Ithilion90/best-buy-tracker-bot/main/assets/bot-logo.png"
    
    help_text = (
        "🛒 <b>Amazon Price Tracker</b>\n\n"
        "Track Amazon product prices and get notified when they drop!\n\n"
        "<b>📋 Available Commands</b>\n\n"
        "/list — Show tracked products with prices\n"
        "/remove &lt;number&gt; — Remove specific product\n"
        "/remove all — Remove all tracked products\n"
        "/help — Show this guide\n\n"
        "💡 <b>Tip:</b> Share an Amazon link to add it automatically!\n"
        "📢 <b>Notifications:</b> You'll be alerted when prices drop!\n\n"
        "⚖️ <b>Legal Notice:</b>\n"
        "• Prices shown are informational only\n"
        "• Always verify on Amazon before purchasing\n"
        "• Product links include affiliate tag\n"
        "• We use official Amazon PA API (100% legal)\n"
        "• Not affiliated with Amazon.com, Inc.\n\n"
        "ℹ️ Full legal notice: /legal"
    )
    
    try:
        await update.message.reply_photo(
            photo=logo_url,
            caption=help_text,
            parse_mode="HTML"
        )
    except Exception:
        # Fallback to text-only if image fails
        await update.message.reply_text(help_text, parse_mode="HTML")

async def cmd_legal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Legal notice and compliance information"""
    legal_text = (
        "⚖️ <b>Legal Notice &amp; Compliance</b>\n\n"
        "<b>🔒 100% Legal Data Sources:</b>\n\n"
        "1️⃣ <b>Amazon Product Advertising API</b>\n"
        "   • Official Amazon API (PA API 5.0)\n"
        "   • Authorized under Associates Program\n"
        "   • Used for: current prices, titles, images\n\n"
        "2️⃣ <b>Keepa API</b> (Historical Data)\n"
        "   • Third-party price history service\n"
        "   • Used for: min/max historical prices\n\n"
        "<b>❌ What We DON'T Do:</b>\n"
        "   • NO web scraping\n"
        "   • NO unauthorized data collection\n"
        "   • NO ToS violations\n\n"
        "<b>🔐 Your Privacy:</b>\n"
        "   • User ID stored for bot functionality\n"
        "   • Tracked products and prices\n"
        "   • NO personal data sharing\n"
        "   • GDPR compliant (EU users)\n\n"
        "<b>💰 Affiliate Disclosure:</b>\n"
        "   • Product links include affiliate tag\n"
        "   • We may earn commission on purchases\n"
        "   • NO extra cost to you\n"
        "   • Helps cover hosting costs\n\n"
        "<b>⚠️ Important Disclaimer:</b>\n"
        "   • Prices are informational only\n"
        "   • Always verify on Amazon.com\n"
        "   • Not affiliated with Amazon Inc.\n"
        "   • Use at your own risk\n\n"
        "<b>📄 Full Legal Notice:</b>\n"
        "https://github.com/Ithilion90/best-buy-tracker-bot/blob/main/LEGAL_NOTICE.md\n\n"
        "<b>📧 Contact:</b>\n"
        "For legal inquiries or data deletion requests,\n"
        "contact the bot operator.\n\n"
        "By using this bot, you agree to these terms."
    )
    
    await update.message.reply_text(legal_text, parse_mode="HTML", disable_web_page_preview=True)

async def handle_shared_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle shared Amazon links - MAIN FUNCTIONALITY.

    Modifica: niente placeholder "Reading...". Se il testo non contiene un link Amazon valido
    risponde direttamente con il messaggio di comando non riconosciuto.
    """
    await ensure_user_in_db(update)
    user = update.effective_user
    text = (update.message.text or '').strip()

    # Try primary regex
    m = AMAZON_URL_RE.search(text)
    url = m.group(1) if m else None

    # Fallback: find token that looks like an amazon domain without protocol
    if not url:
        fallback_matches = re.findall(r'((?:www\.|m\.|smile\.)?amazon\.[a-z\.]{2,10}/[^\s]+)', text, re.IGNORECASE)
        if fallback_matches:
            url = fallback_matches[0]
            logger.info("Amazon link matched via domain fallback", raw=text, extracted=url)
    # Still nothing: maybe a plain amzn short form without protocol
    if not url:
        short_matches = re.findall(r'(?:amzn\.to|amzn\.eu|amzn\.in|a\.co|amzn\.asia)/[^\s]+', text, re.IGNORECASE)
        if short_matches:
            url = short_matches[0]
            logger.info("Amazon short link matched via short fallback", raw=text, extracted=url)

    if not url:
        # Nessun URL Amazon riconosciuto: usa stesso messaggio di unknown command
        await update.message.reply_text("❌ Unknown command. Use /help to see the available commands.")
        return

    # Clean trailing punctuation common in chat messages
    url = url.rstrip(').,]\n')

    # Prepend https if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Mostra messaggio di progresso dinamico solo ora che abbiamo un URL plausibile
    msg = await update.message.reply_text("⏳ Processing Amazon link...")

    # spinner handled by shared helper run_spinner

    # Avvia primo spinner (analisi URL / scraping iniziale)
    spinner_stop_1 = asyncio.Event()
    # Hourglass animation (simulate vertical ↔ horizontal by alternating filled/empty variants)
    spinner_task_1 = asyncio.create_task(run_spinner(msg, "Processing Amazon link...", ["⏳", "⌛"], spinner_stop_1, 0.7))

    if not validate_amazon_url(url):
        await msg.edit_text("❌ Link Amazon non supportato")
        return

    # Expand short link and normalize (/dp/ASIN) form
    original_url = url
    try:
        url = await resolve_and_normalize_amazon_url(url)
    except Exception as e:
        logger.warning("URL expansion failed", url=original_url, error=str(e))
    else:
        if url != original_url:
            logger.info("URL expanded/normalized", original=original_url, normalized=url)
    
    # (già mostrato il messaggio di processing sopra)
    
    try:
        # Extract ASIN (after resolution/normalization)
        asin = extract_asin(url)
        if not asin:
            # Second chance: if it's a short domain, try a live fetch to follow redirect (already done in resolver, but safety)
            if any(s in url for s in ("a.co/", "amzn.to", "amzn.eu", "amzn.in", "amzn.asia")):
                try:
                    import httpx
                    from src.config import config as _cfg
                except ImportError:
                    import httpx
                    from config import config as _cfg
                try:
                    async with httpx.AsyncClient(follow_redirects=True, timeout=10, headers={"User-Agent": _cfg.user_agent}) as client:
                        resp = await client.get(url)
                        final_url = str(resp.url)
                        if final_url != url:
                            logger.info("Short link second redirect followed", initial=url, final=final_url)
                        url = final_url
                        asin = extract_asin(url)
                except Exception as _e:
                    logger.warning("Short link secondary expansion failed", url=url, error=str(_e))
        if not asin:
            await msg.edit_text("❌ Cannot extract ASIN from this link")
            return
        domain = extract_domain(url)

        # Check if product already tracked by this user
        try:
            existing = db.get_item_by_user_and_asin(user.id, asin, domain)
        except Exception:
            existing = None
        if existing:
            existing_domain = existing.get('domain') or extract_domain(existing.get('url') or '')
            existing_asin = existing.get('asin') or asin
            current_display = existing.get('last_price') or existing.get('min_price') or 0
            min_display = existing.get('min_price') or current_display
            max_display = existing.get('max_price') or current_display
            title_display_full = existing.get('title') or f"Amazon Product {existing_asin}"
            # Use /dp/ URL with affiliate tag and title for better routing
            dom_existing = existing_domain or 'amazon.it'
            aff_url_existing = build_product_url(dom_existing, existing_asin, title_display_full)
            title_display = truncate(title_display_full, 60)
            clickable_title_existing = f"<a href=\"{aff_url_existing}\">{title_display}</a>"
            domain_disp = existing_domain or 'n/a'
            curr = existing.get('currency') or domain_to_currency(existing_domain)
            
            # Check availability status
            avail_existing = (existing.get('availability') or '').lower()
            status_line = ""
            if avail_existing == 'unavailable':
                status_line = "📦 <b>Status:</b> ❌ Not available\n"
            elif avail_existing == 'preorder':
                status_line = "📦 <b>Status:</b> 🕒 Pre-order\n"
            elif avail_existing == 'in_stock':
                status_line = "📦 <b>Status:</b> ✅ In stock\n"
            elif avail_existing:
                status_line = f"📦 <b>Status:</b> ℹ️ {avail_existing}\n"
            
            # Build message parts
            message_parts = [
                "📦 <b>Product Already Tracked</b>\n\n",
                f"{clickable_title_existing}\n",
                f"🌍 <b>Domain:</b> {domain_disp}\n",
                status_line
            ]
            
            # Show current price only if not unavailable
            if avail_existing != 'unavailable':
                message_parts.append(f"💰 <b>Current:</b> {format_price(current_display, curr)}\n")
            
            message_parts.extend([
                f"📉 <b>Historical Min:</b> {format_price(min_display, curr)}\n",
                f"📈 <b>Historical Max:</b> {format_price(max_display, curr)}\n\n",
                "Use /list to view all products."
            ])
            
            await msg.edit_text(
                "".join(message_parts),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            logger.info("Duplicate link relayed (already tracked)", asin=asin, user_id=user.id, domain=existing_domain, availability=avail_existing)
            return

        # Get product title, current price and image using PA API (legal method)
        title, current_price, currency, image_url, availability = fetch_product_data_legal(asin, domain)
        if not title:
            title = f"Amazon Product {asin}"

        if not current_price:
            await msg.edit_text("❌ Cannot fetch current price for this product")
            return
        
        # Get Keepa data (domain-specific)
        # Ferma il primo spinner e avvia il secondo (storico Keepa)
        spinner_stop_1.set()
        try:
            await asyncio.sleep(0)  # yield to let spinner stop
        except Exception:
            pass
        spinner_stop_2 = asyncio.Event()
        spinner_task_2 = asyncio.create_task(run_spinner(msg, "Fetching price history...", ["⌛", "⏳"], spinner_stop_2, 0.7))
        keepa_data = fetch_lifetime_min_max_current([asin], domain=domain)
        min_price, max_price, current_price_from_keepa = keepa_data.get(asin, (None, None, None))

        # Fallback: if Keepa has no history yet, initialize with current price
        force_refetched = False
        if min_price is None or max_price is None:
            if current_price is not None:
                min_price = max_price = current_price
                logger.info("Initialized min/max from current price (no Keepa history)", asin=asin, current=current_price)
            elif current_price_from_keepa is not None:
                min_price = max_price = current_price_from_keepa
                current_price = current_price or current_price_from_keepa
                logger.info("Initialized min/max from Keepa current (no Keepa history)", asin=asin, current=current_price_from_keepa)
            else:
                # As a last attempt try simpler Keepa call without current
                alt_bounds = fetch_lifetime_min_max([asin], domain=domain)
                alt_min, alt_max = alt_bounds.get(asin, (None, None))
                if alt_min is not None and alt_max is not None:
                    min_price, max_price = alt_min, alt_max
                    logger.info("Recovered min/max via secondary Keepa call", asin=asin, min=min_price, max=max_price)
                else:
                    await msg.edit_text("❌ No price data found for this product (ASIN history empty)")
                    return
            # Try a forced fresh Keepa fetch to see if history becomes available immediately
            if min_price and max_price and current_price and min_price == max_price == current_price:
                try:
                    force_data = fetch_lifetime_min_max_current([asin], domain=domain, force=True)
                    fmin, fmax, fcur = force_data.get(asin, (None, None, None))
                    if fmin and fmax and (fmin != fmax or fmin != current_price):
                        min_price, max_price = fmin, fmax
                        current_price_from_keepa = fcur or current_price_from_keepa
                        force_refetched = True
                        logger.info("Force refetch obtained historical bounds", asin=asin, min=min_price, max=max_price)
                except Exception as fe:
                    logger.warning("Force refetch failed", asin=asin, error=str(fe))

        # Use current price if available, otherwise fallback to current_price_from_keepa 
        if not current_price:
            current_price = current_price_from_keepa

        # Validate price consistency - adjust min/max if needed but keep current price
        corrected_min, corrected_max = validate_price_consistency(current_price, min_price, max_price)

        # Create affiliate link for display with title for better routing
        dom_for_url = domain or 'amazon.it'
        aff_url = build_product_url(dom_for_url, asin, title)
        title_display = truncate(title, 60)
        clickable_title = f"<a href=\"{aff_url}\">{title_display}</a>"
        curr_added = currency or domain_to_currency(domain)
        response = (
            f"✅ <b>Product Added!</b>\n\n"
            f"📦 {clickable_title}\n"
            f"💰 <b>Current Price:</b> {format_price(current_price, curr_added)}\n"
            f"📉 <b>Historical Min:</b> {format_price(corrected_min, curr_added)}\n"
            f"📈 <b>Historical Max:</b> {format_price(corrected_max, curr_added)}\n\n"
            f"📢 <b>You'll be notified when the price change!</b>"
        )

        # Add to database with current price (DB insert sets min/max equal to current)
        item_id = db.add_item(
            user_id=user.id,
            url=url,
            asin=asin,
            domain=domain,
            title=title,
            currency=currency or "EUR",
            price=current_price
        )
        # store availability immediately
        try:
            if availability:
                db.update_item_availability(item_id, availability)
        except Exception:
            pass
        # Immediately correct stored min/max in DB to the historical bounds we just displayed
        try:
            if (corrected_min is not None and corrected_max is not None and
                (corrected_min != current_price or corrected_max != current_price)):
                db.update_price_bounds(item_id, corrected_min, corrected_max)
        except Exception as e:
            logger.warning("Failed to update initial DB bounds", asin=asin, error=str(e))
        
        # Ferma eventuale spinner attivo prima della risposta finale
        try:
            if 'spinner_stop_2' in locals():
                spinner_stop_2.set()
            else:
                spinner_stop_1.set()
        except Exception:
            pass
        
        if image_url:
            try:
                await msg.delete()
                await context.bot.send_photo(
                    chat_id=user.id, 
                    photo=image_url, 
                    caption=response, 
                    parse_mode="HTML"
                )
            except Exception:
                await msg.edit_text(
                    response, 
                    parse_mode="HTML", 
                    disable_web_page_preview=True
                )
        else:
            await msg.edit_text(
                response, 
                parse_mode="HTML", 
                disable_web_page_preview=True
            )
        logger.info("Product added via shared link", asin=asin, domain=domain, title=title[:30], current_price=current_price, min_price=corrected_min, max_price=corrected_max)
        
    except Exception as e:
        try:
            if 'spinner_stop_1' in locals():
                spinner_stop_1.set()
            if 'spinner_stop_2' in locals():
                spinner_stop_2.set()
        except Exception:
            pass
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

    # Spinner while building list
    msg = await update.message.reply_text("⏳ Loading list...")
    spinner_stop = asyncio.Event()

    spinner_task = asyncio.create_task(run_spinner(msg, "Building product list...", ["⏳", "⌛"], spinner_stop, 0.6))

    try:
        # Stop spinner first
        spinner_stop.set()
        try:
            await spinner_task
        except Exception:
            pass
        
        # Delete loading message
        try:
            await msg.delete()
        except Exception:
            pass
        
        # Send header message
        await update.message.reply_text(
            "🛒 <b>Your Tracked Products:</b>",
            parse_mode="HTML"
        )
        
        if not rows:
            await update.message.reply_text("❌ No tracked products")
            return
        
        # Send each product as a separate message with its button
        for i, r in enumerate(rows, 1):
            asin = r.get('asin')
            if not asin:
                continue
            dom = r.get('domain') or extract_domain(r.get('url') or '')
            min_p = r.get('min_price')
            max_p = r.get('max_price')
            cur_p = r.get('last_price') or (min_p and max_p and (min_p + max_p) / 2)
            
            if not (isinstance(min_p, (int, float)) and isinstance(max_p, (int, float)) and isinstance(cur_p, (int, float))):
                title = truncate(r['title'] or f"Product {asin}", 40)
                await update.message.reply_text(
                    f"<b>{i}.</b> {title}\n❌ Data unavailable yet",
                    parse_mode="HTML"
                )
                continue
            
            title_full = r['title'] or f"Product {asin}"
            title_disp = truncate(title_full, 45)  # Increased from 40 to 45 for uniformity
            # Use /dp/ URL with affiliate tag and title for better routing
            dom_for_url = dom or 'amazon.it'
            aff_url = build_product_url(dom_for_url, asin, title_full)
            clickable = f"<a href=\"{aff_url}\">{title_disp}</a>"
            curr_row = r.get('currency') or domain_to_currency(dom)
            avail = (r.get('availability') or '').lower()
            
            if avail == 'unavailable':
                stock_line = "❌ Not available"
            elif avail == 'preorder':
                stock_line = "🕒 Pre-order"
            elif avail == 'in_stock':
                stock_line = "✅ In stock"
            elif avail:
                stock_line = f"ℹ️ {avail}"
            else:
                stock_line = ""
            
            # Build product message with uniform formatting (no separators)
            # ALWAYS show same number of lines for uniform card height
            product_lines = [f"<b>{i}.</b> {clickable}"]
            
            # Line 2: Domain (always shown)
            product_lines.append(f"🌍 <b>Domain:</b> {dom or 'n/a'}")
            
            # Line 3: Status (always shown with placeholder if empty)
            product_lines.append(f"📦 <b>Status:</b> {stock_line}" if stock_line else "📦 <b>Status:</b> ✅ In stock")
            
            # Line 4: Current Price (always shown, with placeholder if unavailable)
            show_preorder_price = os.getenv('SHOW_PRICE_WHEN_PREORDER', 'true').lower() in ('1', 'true', 'yes', 'y')
            if avail == 'unavailable':
                product_lines.append(f"💰 <b>Current:</b> —")
            elif avail == 'preorder' and not show_preorder_price:
                product_lines.append(f"💰 <b>Current:</b> —")
            else:
                product_lines.append(f"💰 <b>Current:</b> {format_price(cur_p, curr_row)}")
            
            # Line 5: Historical Min (always shown)
            product_lines.append(f"📉 <b>Historical Min:</b> {format_price(min_p, curr_row)}")
            
            # Line 6: Historical Max (always shown)
            product_lines.append(f"📈 <b>Historical Max:</b> {format_price(max_p, curr_row)}")
            
            # Send product message
            await update.message.reply_text(
                "\n".join(product_lines),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error("Error in list command", error=str(e))
        spinner_stop.set()
        try:
            await spinner_task
        except Exception:
            pass
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

        msg = await update.message.reply_text("⏳ Removing all products...")
        spinner_stop = asyncio.Event()
        spinner_task = asyncio.create_task(run_spinner(msg, "Deleting products...", ["⏳", "⌛"], spinner_stop, 0.6))

        removed_count = 0
        for item in rows:
            if db.remove_item(user.id, item['id']):
                removed_count += 1

        spinner_stop.set()
        try:
            await spinner_task
        except Exception:
            pass

        if removed_count > 0:
            await msg.edit_text(
                f"✅ <b>Successfully removed {removed_count} products!</b>\n\n"
                f"Your tracking list is now empty.",
                parse_mode="HTML"
            )
            logger.info("Removed all products", user_id=user.id, count=removed_count)
        else:
            await msg.edit_text(
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
    msg = await update.message.reply_text("⏳ Removing product...")
    spinner_stop = asyncio.Event()
    spinner_task = asyncio.create_task(run_spinner(msg, "Deleting...", ["⏳", "⌛"], spinner_stop, 0.6))

    success = db.remove_item(user.id, item['id'])

    spinner_stop.set()
    try:
        await spinner_task
    except Exception:
        pass

    if success:
        title = truncate(item['title'] or f"Product {item.get('asin', 'N/A')}", 30)
        await msg.edit_text(
            f"✅ Removed: <b>{title}</b>",
            parse_mode="HTML"
        )
        logger.info("Removed single product", user_id=user.id, item_id=item['id'], title=title)
        try:
            await cmd_list(update, context)
        except Exception as e:
            logger.warning("Auto list after remove failed", error=str(e))
    else:
        await msg.edit_text(
            "❌ Error removing product. Please try again.",
            parse_mode="HTML"
        )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors"""
    logger.error("Bot error", error=str(context.error))

def main() -> None:
    validate_config()
    db.init_db()
    try:
        backend = 'PostgreSQL' if getattr(db, 'is_postgres', lambda: False)() else 'SQLite'
    except Exception:
        backend = 'unknown'
    logger.info("Starting Amazon Price Tracker Bot", db_backend=backend)
    
    app = Application.builder().token(config.bot_token).build()
    
    # Essential handlers only
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("legal", cmd_legal))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("remove", cmd_remove))
    
    # Set bot commands for autocomplete menu
    async def set_commands(application: Application) -> None:
        from telegram import BotCommand
        commands = [
            BotCommand("start", "Start the bot and see help"),
            BotCommand("help", "Show help and available commands"),
            BotCommand("legal", "Legal notice and compliance info"),
            BotCommand("list", "Show all tracked products"),
            BotCommand("remove", "Remove a tracked product"),
        ]
        await application.bot.set_my_commands(commands)
    
    app.post_init = set_commands
    
    # Debug DB command (temporary) to verify persistence
    async def cmd_debugdb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await ensure_user_in_db(update)
        user = update.effective_user
        try:
            from . import db as _db  # type: ignore
        except Exception:
            import db as _db  # type: ignore
        cnt = _db.count_items_for_user(user.id)
        backend = 'PostgreSQL' if getattr(_db, 'is_postgres', lambda: False)() else 'SQLite'
        await update.message.reply_text(f"🔧 Debug DB\nBackend: {backend}\nActive items for you: {cnt}")
    app.add_handler(CommandHandler("debugdb", cmd_debugdb))

    # /debugasin <ASIN> command to inspect anomalous min/max
    async def cmd_debugasin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await ensure_user_in_db(update)
        if not context.args:
            await update.message.reply_text("Usage: /debugasin <ASIN>")
            return
        asin_arg = context.args[0].strip().upper()
        try:
            from .keepa_client import fetch_keepa_debug_data  # type: ignore
        except Exception:
            from keepa_client import fetch_keepa_debug_data  # type: ignore
        dbg = fetch_keepa_debug_data(asin_arg)
        if dbg.get("error"):
            await update.message.reply_text(f"Error: {dbg.get('error')}")
            return
        msg_lines = [f"🔍 Keepa Debug {asin_arg}"]
        msg_lines.append(f"Domain: {dbg.get('domain')}")
        msg_lines.append(f"Parsed Current: {dbg.get('parsed_current')}")
        msg_lines.append(f"Parsed Min/Max: {dbg.get('parsed_min')} / {dbg.get('parsed_max')}")
        msg_lines.append(f"History Min/Max (raw history): {dbg.get('history_min')} / {dbg.get('history_max')}")
        raw_min = dbg.get('stats_min_raw')
        raw_max = dbg.get('stats_max_raw')
        if isinstance(raw_min, (int, float)):
            msg_lines.append(f"Raw Stats Min (cents): {raw_min}")
        if isinstance(raw_max, (int, float)):
            msg_lines.append(f"Raw Stats Max (cents): {raw_max}")
            # Reasons / samples
            if 'stats_min_reason' in dbg:
                msg_lines.append(f"Min Reason: {dbg.get('stats_min_reason')}")
            if 'stats_max_reason' in dbg:
                msg_lines.append(f"Max Reason: {dbg.get('stats_max_reason')}")
            if 'stats_current_reason' in dbg:
                msg_lines.append(f"Current Reason: {dbg.get('stats_current_reason')}")
            if dbg.get('stats_min_sample'):
                msg_lines.append(f"Min Sample: {dbg.get('stats_min_sample')}")
            if dbg.get('stats_max_sample'):
                msg_lines.append(f"Max Sample: {dbg.get('stats_max_sample')}")
            if dbg.get('stats_current_sample'):
                msg_lines.append(f"Current Sample: {dbg.get('stats_current_sample')}")
            if dbg.get('list_price') is not None:
                msg_lines.append(f"List Price: {dbg.get('list_price')}")
            if dbg.get('buybox_price') is not None:
                msg_lines.append(f"BuyBox Price: {dbg.get('buybox_price')}")
            if dbg.get('anomaly'):
                msg_lines.append(f"Anomaly Classification: {dbg.get('anomaly')}")
        sample = dbg.get('sample_prices') or []
        if sample:
            msg_lines.append("Sample History Prices: " + ", ".join(str(s) for s in sample))
        # Simple anomaly heuristic
        try:
            pmx = dbg.get('parsed_max')
            pcur = dbg.get('parsed_current')
            if isinstance(pmx, (int, float)) and isinstance(pcur, (int, float)) and pmx > pcur * 5:
                msg_lines.append("⚠️ Anomaly: max >> current (possible early MSRP, out-of-stock spike, or misparsed history)")
        except Exception:
            pass
        await update.message.reply_text("\n".join(msg_lines))
    app.add_handler(CommandHandler("debugasin", cmd_debugasin))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_shared_link))
    
    # Unknown command handler (must be after known commands)
    async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("❌ Unknown command. Use /help to see the available commands.")
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    app.add_error_handler(error_handler)
    
    # Start periodic price checking in a separate task after the app starts
    async def post_init_combined(application: Application) -> None:
        from telegram import BotCommand
        commands = [
            BotCommand("start", "Start the bot and see help"),
            BotCommand("help", "Show bot guide and commands"),
            BotCommand("list", "Show all tracked products"),
            BotCommand("remove", "Remove a tracked product"),
        ]
        await application.bot.set_my_commands(commands)
        asyncio.create_task(periodic_price_check(application))
    
    app.post_init = post_init_combined
    
    logger.info("Amazon Price Tracker Bot started successfully - Price tracking and notifications active")
    app.run_polling()

if __name__ == "__main__":
    main()
