# Feature: Unavailable Product Handling

## Implementation Summary

### Objective
The bot now properly handles products that are not available on Amazon by:
1. **Hiding current price** when product is unavailable
2. **Showing clear status indicators** (✅ In stock, ❌ Not available, 🕒 Pre-order)
3. **Skipping price drop notifications** for unavailable products
4. **Displaying availability status** in all relevant views

This prevents confusing users with stale price data for products they cannot purchase.

---

## Changes Made

### 1. Enhanced `/list` Command Display

**Location:** `src/bot.py` - `cmd_list()` function (lines ~635-655)

**Behavior:**
```python
# Determine availability status
avail = (r.get('availability') or '').lower()

# Show appropriate status icon
if avail == 'unavailable':
    stock_line = "❌ Not available"
elif avail == 'preorder':
    stock_line = "🕒 Pre-order"
elif avail == 'in_stock':
    stock_line = "✅ In stock"

# Hide current price for unavailable products
if avail == 'unavailable':
    pass  # Don't show "💰 Current:" line
else:
    line += f"   💰 <b>Current:</b> {format_price(cur_p, curr_row)}\n"
```

**Example Output:**
```
1. Corsair VENGEANCE LPX DDR4 RAM
   🌍 Domain: amazon.it
   📦 Status: ❌ Not available
   📉 Historical Min: €99.58
   📈 Historical Max: €145.00
```

**Note:** Current price is NOT shown, preventing confusion about stale data.

---

### 2. Enhanced "Product Already Tracked" Message

**Location:** `src/bot.py` - `handle_shared_link()` function (lines ~431-470)

**Behavior:**
```python
# Check availability status
avail_existing = (existing.get('availability') or '').lower()

# Determine status line
if avail_existing == 'unavailable':
    status_line = "📦 <b>Status:</b> ❌ Not available\n"
elif avail_existing == 'preorder':
    status_line = "📦 <b>Status:</b> 🕒 Pre-order\n"
elif avail_existing == 'in_stock':
    status_line = "📦 <b>Status:</b> ✅ In stock\n"

# Show current price only if not unavailable
if avail_existing != 'unavailable':
    message_parts.append(f"💰 <b>Current:</b> {format_price(current_display, curr)}\n")
```

**Example Output (Unavailable):**
```
📦 Product Already Tracked

Corsair VENGEANCE LPX DDR4 RAM
🌍 Domain: amazon.it
📦 Status: ❌ Not available
📉 Historical Min: €99.58
📈 Historical Max: €145.00

Use /list to view all products.
```

**Example Output (Available):**
```
📦 Product Already Tracked

Corsair VENGEANCE LPX DDR4 RAM
🌍 Domain: amazon.it
📦 Status: ✅ In stock
💰 Current: €109.99
📉 Historical Min: €99.58
📈 Historical Max: €145.00

Use /list to view all products.
```

---

### 3. Skip Notifications for Unavailable Products

**Location:** `src/bot.py` - `send_price_notification()` function (lines ~113-125)

**Behavior:**
```python
async def send_price_notification(..., availability: str | None = None) -> None:
    """Send price notification to user.
    
    Args:
        availability: Product availability status. If 'unavailable', notification is skipped.
    """
    try:
        # Skip notification if product is unavailable
        if availability and availability.lower() == 'unavailable':
            logger.info("Skipping notification for unavailable product", 
                       user_id=user_id, asin=asin, domain=domain)
            return
        
        # ... rest of notification logic
```

**Rationale:**
- Prevents sending "Price Drop!" notifications for products users cannot buy
- Avoids creating false urgency for unavailable items
- Reduces notification spam when products go out of stock

**Updated Call Site (refresh_prices_and_notify):**
```python
await send_price_notification(
    item['user_id'],
    asin,
    item.get('title') or (scraped_title or f"Product {asin}"),
    old_price,
    current_price,
    adj_min,
    adj_max,
    app,
    domain=dom,
    availability=to_avail,  # NEW: Pass availability status
)
```

---

## Availability Status Values

### Recognized Statuses

| Status        | Display          | Show Price? | Send Notifications? | Notes                           |
|---------------|------------------|-------------|---------------------|---------------------------------|
| `in_stock`    | ✅ In stock      | Yes         | Yes                 | Product available for purchase  |
| `unavailable` | ❌ Not available | **No**      | **No**              | Product out of stock            |
| `preorder`    | 🕒 Pre-order     | Configurable | Yes                | Available for pre-order         |
| `null/empty`  | *(no status)*    | Yes         | Yes                 | Availability unknown            |

### Pre-order Price Display

**Environment Variable:** `SHOW_PRICE_WHEN_PREORDER`

**Default:** `true` (show price for pre-orders)

**Options:**
- `true`, `1`, `yes`, `y` → Show current price for pre-orders
- `false`, `0`, `no`, `n` → Hide current price for pre-orders

**Example:**
```bash
# .env file
SHOW_PRICE_WHEN_PREORDER=false
```

---

## Database Schema

### Items Table

**Column:** `availability` (TEXT, nullable)

**Purpose:** Stores current availability status of tracked product

**Values:** `'in_stock'`, `'unavailable'`, `'preorder'`, or `NULL`

**Updated By:**
- `update_price()` - when scraper provides availability
- `update_item_availability()` - dedicated availability update

**Migration:** Column added via `ALTER TABLE` in `_migrate_existing_schema()` (already implemented)

---

## Price History Tracking

### Price History Table

**Column:** `availability` (TEXT, nullable)

**Purpose:** Track availability changes over time alongside price changes

**Example Data:**
```
| timestamp           | price  | availability |
|---------------------|--------|--------------|
| 2025-01-01 10:00:00 | 99.58  | in_stock     |
| 2025-01-02 10:00:00 | 109.99 | in_stock     |
| 2025-01-03 10:00:00 | 109.99 | unavailable  |
| 2025-01-04 10:00:00 | 99.58  | in_stock     |
```

**Use Cases:**
- Analyze stock-out patterns
- Detect price changes coinciding with availability changes
- Historical availability trends

---

## Testing

### Test Script: `test_unavailable_handling.py`

**Run:**
```bash
python test_unavailable_handling.py
```

**Test Coverage:**

1. **Price Display Logic** (4 test cases)
   - ✅ In stock: Shows current price
   - ✅ Unavailable: Hides current price
   - ✅ Pre-order: Shows/hides based on env var
   - ✅ No status: Shows current price

2. **Notification Skip Logic** (4 test cases)
   - ✅ In stock: Sends notifications
   - ✅ Unavailable: Skips notifications
   - ✅ Pre-order: Sends notifications
   - ✅ No status: Sends notifications

3. **"Already Tracked" Display** (2 test cases)
   - ✅ Available: Shows status + current price
   - ✅ Unavailable: Shows status, hides current price

**All tests PASSED** ✅

---

## User Experience Impact

### Before Implementation

**Problem:** Users saw stale prices for unavailable products
```
1. Corsair RAM
   💰 Current: €99.58      ← Product is unavailable, price is stale
   📉 Historical Min: €99.58
   📈 Historical Max: €145.00
```

**Issues:**
- Confusing: Price shown but cannot purchase
- False urgency: "Historical minimum!" but product unavailable
- Wasted notifications: Alerts for products users can't buy

### After Implementation

**Solution:** Clear status, no misleading price info
```
1. Corsair RAM
   📦 Status: ❌ Not available   ← Clear indication
   📉 Historical Min: €99.58      ← Historical data still shown
   📈 Historical Max: €145.00
```

**Benefits:**
- ✅ No confusion about availability
- ✅ No false urgency notifications
- ✅ Historical data still accessible
- ✅ Clear visual indicators (✅ ❌ 🕒)

---

## Implementation Details

### Availability Data Flow

```
1. Price Scraper (price_fetcher.py)
   ↓
   Returns: (title, price, currency, availability)
   
2. Refresh Cycle (bot.py - refresh_prices_and_notify)
   ↓
   Validates: scraped_avail in ('unavailable', 'preorder', 'in_stock')
   ↓
   Updates: db.update_price(item_id, price, availability=to_avail)
   
3. Database (db.py - update_price)
   ↓
   Persists: items.availability = to_avail
   ↓
   Records: price_history.availability = to_avail
   
4. Display Logic (bot.py - cmd_list, handle_shared_link)
   ↓
   Reads: item.get('availability')
   ↓
   Decides: Show/hide current price based on status
   
5. Notification Logic (bot.py - send_price_notification)
   ↓
   Checks: if availability == 'unavailable' → skip
   ↓
   Sends: Only if product is available/preorder
```

### Logging

**Unavailable Product Detection:**
```python
logger.info("Skipping notification for unavailable product", 
           user_id=user_id, asin=asin, domain=domain)
```

**Already Tracked with Status:**
```python
logger.info("Duplicate link relayed (already tracked)", 
           asin=asin, user_id=user.id, domain=existing_domain, 
           availability=avail_existing)
```

---

## Edge Cases Handled

### 1. Availability Data Missing
**Scenario:** Scraper returns `None` or empty string for availability  
**Behavior:** Treat as "unknown" → show price, allow notifications  
**Rationale:** Conservative approach - don't hide data unless explicitly unavailable

### 2. Availability Changes
**Scenario:** Product goes from `in_stock` → `unavailable` → `in_stock`  
**Behavior:**
- First change: Notification sent (last was in_stock)
- Second change (to unavailable): Price updated, no notification
- Third change (back to in_stock): Notification sent if price dropped

**Example:**
```
Day 1: €109.99, in_stock → Notification sent (initial tracking)
Day 2: €109.99, unavailable → No notification (same price, now unavailable)
Day 3: €99.58, in_stock → Notification sent (price dropped + available again)
```

### 3. Pre-order Price Display
**Scenario:** Product is available for pre-order with known price  
**Default:** Show price (helps users decide if pre-order is worth it)  
**Configurable:** Can hide via `SHOW_PRICE_WHEN_PREORDER=false`

### 4. Historical Data Display
**Scenario:** Product unavailable but has historical min/max  
**Behavior:** Always show historical min/max (helps users know typical pricing)  
**Rationale:** Historical context useful even when currently unavailable

---

## Future Enhancements

### 1. Availability Change Notifications
**Idea:** Notify when product becomes available again
```
🎉 Back in Stock!

Corsair VENGEANCE LPX DDR4 RAM
💰 Current: €99.58
📉 Historical Min: €99.58

This product is available again at the historical minimum price!
```

### 2. Availability Trends
**Idea:** Show stock-out frequency
```
📊 Availability Pattern
✅ In stock: 80% of time
❌ Out of stock: 15% of time
🕒 Pre-order: 5% of time
```

### 3. Restock Alerts
**Idea:** User can enable "notify me when back in stock"
```
/notify_restock 123

✅ You'll be notified when this product is back in stock
```

### 4. Price While Unavailable Tracking
**Idea:** Continue tracking Keepa data even when unavailable
- Shows if price changes while out of stock
- Helps predict restocking price point

---

## Conclusion

### Implementation Status

✅ **Unavailable products handled correctly**  
✅ **Current price hidden when unavailable**  
✅ **Clear status indicators shown**  
✅ **Notifications skipped for unavailable products**  
✅ **Historical data still accessible**  
✅ **Tested and validated**

### User Benefits

- 🎯 **No confusion** about product availability
- 💡 **Clear status** at a glance (✅ ❌ 🕒)
- 📊 **Historical context** preserved
- 🔕 **No spam** from unavailable product alerts
- ✨ **Better user experience** overall

---

*Last updated: January 2025 - Unavailable product handling implementation*
