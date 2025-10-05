# FIX: Errore "There is no text in the message to edit" sul Toggle dopo /add

## Data
5 Ottobre 2025

## Problema

Quando l'utente cliccava il pulsante "Track NEW Only" subito dopo aver aggiunto un prodotto (con foto), appariva l'errore:

```
"error": "There is no text in the message to edit"
```

Il bot crashava e il toggle non funzionava.

## Causa

Due problemi nel callback handler `handle_toggle_new_only()`:

### 1. Tipo di Messaggio Sbagliato
- Dopo `/add` con immagine prodotto, il messaggio contiene una **foto con caption**
- Il callback usava sempre `edit_message_text()` che funziona solo con messaggi testuali
- Per messaggi con foto serve `edit_message_caption()`

### 2. Formato Messaggio Incompatibile
- Il messaggio dopo `/add` ha formato "Product Added":
  ```
  ✅ Product Added!
  📦 Title
  💰 Current Price: ...
  ```
- Il callback ricostruiva sempre nel formato `/list`:
  ```
  ────────────────────────────────────────
  1. Title
  🌍 Domain: ...
  ```
- Risultato: formato completamente sbagliato dopo il toggle

## Soluzione

### 1. Detect e Gestione Foto vs Testo

```python
# Detect if message has photo (caption) or text
if query.message.photo:
    # Message has photo, update caption
    await query.edit_message_caption(
        caption=message_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
else:
    # Message is text only
    await query.edit_message_text(
        message_text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=keyboard
    )
```

Con **fallback** per tentativi alternativi in caso di errore.

### 2. Detect e Preserva Formato Originale

```python
# Detect message format: "Product Added" vs "/list" format
original_text = query.message.caption if query.message.photo else query.message.text
is_product_added = original_text and "Product Added" in original_text

if is_product_added:
    # Build message in "Product Added" format
    product_lines = [
        "✅ <b>Product Added!</b>",
        "",
        f"📦 {clickable_title}"
    ]
    if new_only_indicator:
        product_lines.append(f"     {new_only_indicator}")
    
    product_lines.extend([
        f"💰 <b>Current Price:</b> {format_price(cur_p, curr_row)}",
        f"📉 <b>Historical Min:</b> {format_price(min_p, curr_row)}",
        f"📈 <b>Historical Max:</b> {format_price(max_p, curr_row)}",
        "",
        "📢 <b>You'll be notified when the price change!</b>"
    ])
else:
    # Build message in "/list" format with separators
    separator = "─" * 40
    product_lines = [
        separator,
        f"<b>{product_num}.</b> {clickable}"
    ]
    # ... resto del formato /list
```

## Comportamento Dopo il Fix

### Scenario 1: Toggle dopo /add (con foto)

**PRIMA:**
1. User condivide link Amazon
2. Bot invia foto con caption "Product Added" e pulsante "Track NEW Only"
3. User clicca pulsante
4. ❌ **ERRORE**: "There is no text in the message to edit"
5. Pulsante non funziona

**DOPO:**
1. User condivide link Amazon
2. Bot invia foto con caption "Product Added" e pulsante "Track NEW Only"
3. User clicca pulsante
4. ✅ Caption aggiornata con `edit_message_caption()`
5. Formato "Product Added" **preservato**
6. Indicatore "🆕 NEW ONLY" aggiunto
7. Prezzi aggiornati da Keepa
8. Pulsante cambia in "❌ Track ALL"

**Output:**
```
✅ Product Added!

📦 NZXT H5 Flow - Case per PC
     🆕 NEW ONLY
💰 Current Price: €84.90
📉 Historical Min: €68.77
📈 Historical Max: €104.99

📢 You'll be notified when the price change!

[❌ Track ALL]
```

### Scenario 2: Toggle da /list (senza foto)

**COMPORTAMENTO:**
- Usa `edit_message_text()`
- Formato `/list` con separatori
- Funziona come prima

**Output:**
```
────────────────────────────────────────
1. NZXT H5 Flow - Case per PC
     🆕 NEW ONLY
────────────────────────────────────────
🌍 Domain: amazon.it
📦 Status: ✅ In stock
💰 Current: €84.90
📉 Historical Min: €68.77
📈 Historical Max: €104.99
────────────────────────────────────────
[❌ Track ALL]
```

## Files Modificati

### `src/bot.py`

**Funzione: `handle_toggle_new_only()`** (linee ~1000-1070)

**Modifiche:**

1. **Detect tipo messaggio** (linea ~1003):
   ```python
   original_text = query.message.caption if query.message.photo else query.message.text
   is_product_added = original_text and "Product Added" in original_text
   ```

2. **Formato condizionale** (linee ~1005-1045):
   - `if is_product_added:` → Formato "Product Added"
   - `else:` → Formato `/list` con separatori

3. **Edit condizionale** (linee ~1050-1070):
   ```python
   if query.message.photo:
       await query.edit_message_caption(...)
   else:
       await query.edit_message_text(...)
   ```

4. **Fallback robusto**:
   - Try entrambi i metodi in caso di errore
   - Error handling migliorato con `query.answer()` invece di `edit_message_text()`

## Testing

### Test Caso 1: Toggle dopo /add con foto
1. ✅ Condividi link Amazon (prodotto con immagine)
2. ✅ Clicca "Track NEW Only" → Caption aggiornata
3. ✅ Verifica formato "Product Added" preservato
4. ✅ Verifica indicatore "🆕 NEW ONLY" visibile
5. ✅ Verifica prezzi aggiornati (NEW invece di ALL)
6. ✅ Clicca "Track ALL" → Caption aggiornata senza errori

### Test Caso 2: Toggle da /list senza foto
1. ✅ Esegui `/list`
2. ✅ Clicca "Track NEW Only" → Testo aggiornato
3. ✅ Verifica formato `/list` con separatori preservato
4. ✅ Verifica funzionamento come prima

### Test Caso 3: Edge cases
1. ✅ Prodotto senza foto dopo /add → Usa `edit_message_text()`
2. ✅ Prodotto con foto e NEW già attivo → Toggle OFF funziona
3. ✅ Errori Keepa → Fallback a prezzi esistenti senza crash

## Log dell'Errore (PRIMA del fix)

```
2025-10-05 02:50:04,741 - BestBuyTracker - ERROR - {
  "message": "Error toggling new_only", 
  "error": "There is no text in the message to edit", 
  "item_id": 37, 
  "user_id": 1352312450
}
```

## Log Atteso (DOPO il fix)

```
2025-10-05 HH:MM:SS - BestBuyTracker - INFO - {
  "message": "Toggled new_only via callback", 
  "item_id": 37, 
  "user_id": 1352312450, 
  "new_state": true
}
```

## Vantaggi del Fix

1. ✅ **Nessun errore** con foto dopo /add
2. ✅ **Formato preservato** (Product Added vs /list)
3. ✅ **UX coerente** - ogni messaggio mantiene il suo stile
4. ✅ **Fallback robusto** - try/except multipli per resilienza
5. ✅ **Backward compatible** - /list funziona come prima

## Note Tecniche

### Detect Foto
```python
if query.message.photo:
    # List[PhotoSize] - message has photos
```

Telegram ritorna una lista di `PhotoSize` se il messaggio contiene foto.

### Detect Formato Messaggio
```python
original_text = query.message.caption if query.message.photo else query.message.text
```

Se c'è foto, legge caption; altrimenti legge text.

### Fallback Chain
```python
try:
    await query.edit_message_caption(...)
except:
    try:
        await query.edit_message_text(...)
    except:
        # Ultimate fallback
        await query.answer("Error", show_alert=True)
```

Prova caption → text → alert utente.

---

**Status**: ✅ FIXED
**Testato**: Manualmente con B0D2MK6NML (foto + caption)
**Compatibilità**: Preservata al 100%
