# NEW Condition Tracking Feature

## Overview
Users can now track prices for **NEW condition products only** on a per-product basis. This allows filtering out used, refurbished, or other condition offers from price tracking and notifications.

## User Experience

### Toggle Button in /list
Each product in `/list` is now displayed as a **separate message** with its own inline keyboard button directly below the price information:
- **"🆕 Track NEW Only"** - When clicked, filters tracking to NEW condition only
- **"❌ Track ALL"** - When clicked, reverts to tracking all conditions (default)

When NEW tracking is enabled, products show a `🆕 NEW ONLY` indicator next to the title.

### Example Layout
```
🛒 Your Tracked Products:

┌─────────────────────────────────────┐
│ 1. Corsair Vengeance LPX 16GB      │
│ 🌍 Domain: amazon.com               │
│ 📦 Status: ✅ In stock             │
│ 💰 Current: $79.99                  │
│ 📉 Historical Min: $69.99           │
│ 📈 Historical Max: $99.99           │
│                                     │
│ [🆕 Track NEW Only]  ← Click here  │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 2. AMD Ryzen 7 5800X 🆕 NEW ONLY   │
│ 🌍 Domain: amazon.com               │
│ 📦 Status: ✅ In stock             │
│ 💰 Current: $299.99                 │
│ 📉 Historical Min: $279.99          │
│ 📈 Historical Max: $449.99          │
│                                     │
│ [❌ Track ALL]  ← Click to disable │
└─────────────────────────────────────┘
```

### Benefits
- ✅ **Immediate visibility**: Button appears right below product info
- ✅ **Clean organization**: Each product is self-contained
- ✅ **Fast updates**: Only the specific product message refreshes on toggle
- ✅ **Better mobile UX**: Easier to tap on individual products
- ✅ **Standard size**: Telegram inline buttons are automatically optimized

## Technical Implementation

### Database Schema
Added `new_only` column to `items` table:
```sql
-- SQLite
new_only INTEGER DEFAULT 0

-- PostgreSQL  
new_only BOOLEAN DEFAULT FALSE
```

Migration is automatic via `init_db()` function.

### Toggle Function
`db.toggle_new_only(item_id: int, user_id: int) -> bool`
- Gets current state
- Toggles boolean value
- Updates database
- Returns new state (True/False)
- Logs action

### Keepa Integration

#### Stats Array Structure
Keepa API returns stats with multiple indices:
- `stats[0]` = Amazon price (direct from Amazon)
- `stats[1]` = **NEW** offers price (marketplace sellers - NEW condition only)
- `stats[2]` = **USED** offers price (used/refurbished condition)
- `stats[3]` = (varies)
- `stats[4]` = Sales rank
- `stats[5]` = List price
- Keepa uses `-1` to indicate "no data available"

**IMPORTANT**: Index 1 is NEW, not index 2! This was corrected after initial implementation.
See `FIX_INVERTED_NEW_USED.md` for details.

#### Modified Functions

**`fetch_lifetime_min_max_current()`**
```python
fetch_lifetime_min_max_current(
    asin_list: List[str],
    domain: Optional[str] = None,
    force: bool = False,
    new_only: bool = False  # ← NEW parameter
) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]]
```

**`_pick_amazon_stat()`**
```python
def _pick_amazon_stat(stats: dict, key: str, new_only: bool = False) -> Optional[float]:
    # When new_only=True:
    #   - Extracts from stats[1] (NEW offers)
    #   - Returns None if data is -1 or missing (no fallback to Amazon/Used)
    # When new_only=False:
    #   - Extracts from stats[0] (Amazon/all conditions)
    #   - Falls back to scanning array if index 0 unavailable
```

### Refresh Logic

Products are now grouped by `(domain, new_only)` instead of just `domain`:
```python
domain_group: dict[tuple[str, bool], dict[str, list[dict]]] = {}
for item in items:
    dom = item.get('domain')
    new_only = bool(item.get('new_only', 0))
    domain_group.setdefault((dom, new_only), {}).setdefault(asin, []).append(item)
```

This ensures:
- Separate Keepa API calls for NEW vs ALL tracking
- Correct stats index used per product preference
- Notifications respect NEW condition setting

### Callback Handler
```python
async def handle_toggle_new_only(update, context):
    # Pattern: r'^toggle_new_\d+$'
    # Callback data: 'toggle_new_{item_id}'
    
    # 1. Parse item_id from callback data
    # 2. Call db.toggle_new_only(item_id, user_id) → new_state
    # 3. Show loading: "🔄 Updating prices..."
    # 4. Fetch FRESH prices from Keepa with new_only=new_state
    # 5. Update DB with new prices immediately
    # 6. Rebuild product message with updated prices
    # 7. Update the single message with new button state
```

**Key Features:**
- ✅ **Immediate refresh**: Fetches new prices from Keepa instantly (no 30-min wait)
- ✅ **Price consistency**: Displayed prices always match the tracking mode
- ✅ **Loading indicator**: Shows "🔄 Updating prices..." during fetch
- ✅ **Error handling**: Falls back to existing prices if Keepa fails
- ✅ **DB update**: New prices persisted for future notifications

**Example Flow (B0D2MK6NML):**
```
BEFORE toggle (Amazon/All):
   Current: $84.99
   [🆕 Track NEW Only]

↓ User clicks button ↓
   "🔄 Updating prices..."

AFTER toggle (NEW only):
   🆕 NEW ONLY
   Current: $84.99  ← Updated from Keepa stats[1]!
   [❌ Track ALL]
```

## Testing

### Unit Tests
`test_new_condition_tracking.py` validates:
1. **DB Toggle**: `toggle_new_only()` changes and persists state
2. **Stats Extraction**: `_pick_amazon_stat()` uses correct index (0 vs 1)
3. **Parsing**: `_parse_keepa_products_with_current()` returns different prices
4. **Real API**: (Optional) Actual Keepa API call with both flags

All tests pass ✅

### Test Results
```
=== Test 1: DB toggle_new_only() ===
✓ Item 25 initial new_only: True
✓ After toggle: False
✓ DB shows new_only: False
✓ After second toggle: True
✅ DB toggle test PASSED

=== Test 2: _pick_amazon_stat() with new_only ===
✓ Amazon current (new_only=False): 1500.0 (expected 1500)
✓ NEW current (new_only=True): 1800.0 (expected 1800)
✓ Amazon min: 1200.0, NEW min: 1500.0
✓ Amazon max: 2000.0, NEW max: 2500.0
✅ _pick_amazon_stat test PASSED

=== Test 3: _parse_keepa_products_with_current() ===
✓ Amazon results: {'TEST123': (12.0, 20.0, 15.0)}
✓ NEW results: {'TEST123': (15.0, 25.0, 18.0)}
✅ _parse_keepa_products_with_current test PASSED
```

## Edge Cases Handled

1. **Toggling During Refresh**
   - Refresh groups by `(domain, new_only)` snapshot at start
   - Toggle updates DB immediately
   - Next refresh cycle uses new setting

2. **Mixed Products**
   - User can have some products with NEW tracking, others without
   - Each tracked independently with correct Keepa stats

3. **Missing NEW Data**
   - If stats[18] is None/missing, fallback to stats[0]
   - Prevents price tracking failure

4. **Notification Logic**
   - Price drops calculated from correct condition (NEW vs ALL)
   - Threshold checks respect per-product setting

## Benefits

- **Precision**: Track only NEW prices, ignore used/refurbished fluctuations
- **Flexibility**: Per-product toggle (not global setting)
- **Transparency**: Clear UI indicator when NEW tracking active
- **Performance**: Efficient Keepa grouping minimizes API calls

## Future Enhancements

Possible improvements:
- Add more condition filters (Used, Refurbished, etc.)
- Show condition breakdown in price history
- Bulk toggle for all products
- Condition preference in user settings (default for new products)

## Migration Notes

### For Existing Databases
- PostgreSQL: `ALTER TABLE items ADD COLUMN IF NOT EXISTS new_only BOOLEAN DEFAULT FALSE`
- SQLite: Migration via `_migrate_existing_schema()` adds `new_only INTEGER DEFAULT 0`
- All existing products default to `new_only=False` (track all conditions)

### For Users
- Existing tracked products unchanged (track all conditions)
- Must explicitly toggle NEW tracking per product
- No data loss or breaking changes

## Files Modified

1. **src/db.py**
   - Added `new_only` column to schema
   - Added `toggle_new_only()` function
   - Updated PostgreSQL init for new column

2. **src/bot.py**
   - Modified `cmd_list()` for toggle buttons
   - Added `handle_toggle_new_only()` callback handler
   - Updated `refresh_prices_and_notify()` grouping logic
   - Registered CallbackQueryHandler

3. **src/keepa_client.py**
   - Added `new_only` parameter to `fetch_lifetime_min_max_current()`
   - Modified `_pick_amazon_stat()` for stats[18] extraction
   - Updated `_parse_keepa_products_with_current()` signature
   - Updated all fetch helpers (_fetch_from_keepa_package_with_current, etc.)

4. **test_new_condition_tracking.py** (new)
   - Comprehensive test suite for feature
