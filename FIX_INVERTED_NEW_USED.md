# FIX: Inverted NEW/USED Prices - Correct Keepa Stats Index

## Problem

User reported that prices were inverted when toggling "Track NEW Only":
- **Track ALL**: Showed $84.90 (higher price)
- **Track NEW Only**: Showed $68.77 (lower price)

Expected behavior:
- **Track ALL**: Should show best/lowest price (Amazon price, ~$84.99)
- **Track NEW Only**: Should show NEW condition only price (~$84.99)

## Root Cause

**Wrong Keepa stats index used for NEW condition tracking.**

The code was using:
```python
target_index = 2 if new_only else 0
```

But Keepa stats array structure is:
- `stats[0]` = Amazon price (direct from Amazon)
- `stats[1]` = **NEW** offers (from marketplace sellers - NEW condition)
- `stats[2]` = **USED** offers (used/refurbished condition)
- `stats[3]` = (varies)
- `stats[4]` = Sales rank
- `stats[5]` = List price

So when `new_only=True`, the code was extracting `stats[2]` which is **USED**, not NEW!

## Verification

Created diagnostic test (`test_keepa_raw_data.py`) that confirmed:

```
📊 STATS['CURRENT']:
   stats[0] = 8499 cents → $84.99  (Amazon)
   stats[1] = 8499 cents → $84.99  (NEW)
   stats[2] = 8074 cents → $80.74  (USED)

📦 DATA ARRAYS:
   data['NEW'][-1] = 84.99 $ → 8499 cents
   data['USED'][-1] = 80.74 $ → 8073 cents

🎯 CONCLUSIONE:
   ✅ stats[1] (8499) = data['NEW'] (8499) → stats[1] è NEW
```

## Solution

Changed the index from `2` to `1` in `src/keepa_client.py`:

```python
# Before:
target_index = 2 if new_only else 0  # WRONG! 2 is USED

# After:
target_index = 1 if new_only else 0  # CORRECT! 1 is NEW
```

Updated comment to reflect correct understanding:
```python
# Index 0 = Amazon, Index 1 = NEW offers, Index 2 = USED offers
# Keepa stats array: [Amazon, NEW, Used, ?, Sales, ListPrice, ...]
```

## Test Results

After fix (`test_index_fix.py`):

```
🔵 Track ALL (new_only=False):
   Min: $79.99
   Current: $84.99   ← Amazon price (stats[0])
   Max: $94.99

🟢 Track NEW Only (new_only=True):
   Min: $78.0
   Current: $84.99   ← NEW price (stats[1])
   Max: $132.51

✅ CORRETTO! Entrambi mostrano ~$84.99 (Amazon/NEW)
```

Both modes now correctly show ~$84.99 for B0D2MK6NML.

## Impact

- **Fixed**: NEW condition tracking now uses correct index (stats[1])
- **Behavior**: Track ALL = Amazon price, Track NEW = NEW marketplace price
- **No regressions**: Track ALL still uses stats[0] (Amazon) correctly

## Files Modified

1. `src/keepa_client.py` - Line 377:
   - Changed `target_index = 2 if new_only else 0`
   - To `target_index = 1 if new_only else 0`
   - Updated comment with correct index mapping

## Testing

- ✅ `test_keepa_raw_data.py` - Confirms stats[1] = NEW
- ✅ `test_index_fix.py` - Verifies correct behavior after fix
- ✅ Manual verification with B0D2MK6NML ASIN

## Next Steps

User should:
1. Restart bot to load fixed code
2. Test with real product (B0D2MK6NML)
3. Toggle between Track ALL and Track NEW Only
4. Verify both show similar prices (~$84.99) instead of inverted values

---
**Date**: 2024
**Issue**: Inverted NEW/USED prices
**Status**: ✅ FIXED
