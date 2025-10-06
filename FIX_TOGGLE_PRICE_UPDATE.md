# Fix: Toggle NEW ONLY - Prezzi Non Si Aggiornano

## 🚨 Problema

**Prodotto:** B0D2MK6NML  
**Sintomo:** Toggle tra "Solo Nuovo" ↔ "Nuovo + Usato" non aggiorna i prezzi

**Keepa Data:**
- NEW ONLY: Max €137.92
- NEW+USED: Max €104.99

**Comportamento errato:** Dopo toggle, il massimo non cambiava.

## 🔧 Root Cause

Ordine esecuzione errato + fallback a vecchi valori DB:

```python
# ❌ PRIMA
item = db.list_items()[...]  # Vecchi prezzi
keepa_data = fetch_keepa(new_only=new_state)
if error:
    min_p = item.get('min_price')  # ❌ Usa vecchi!
```

## ✅ Fix

```python
# ✅ DOPO
item_before = db.list_items()[...]  # Solo per ASIN
keepa_data = fetch_keepa(new_only=new_state)
if error:
    show_error_to_user()  # ✅ Nessun fallback
    return
db.update_prices(...)
item = db.list_items()[...]  # ✅ Nuovi prezzi
```

**Modifiche:**
1. Re-fetch item DOPO aggiornamento DB
2. Eliminati fallback silenziosi ai vecchi prezzi
3. Mostra errori espliciti all'utente

## 📊 Verifica

✅ Toggle NEW ONLY → NEW+USED: Max €137.92 → €104.99  
✅ Toggle NEW+USED → NEW ONLY: Max €104.99 → €137.92  

**File:** `src/bot.py` - `handle_toggle_new_only()`  
**Status:** ✅ RISOLTO (2025-10-05)
