# FEATURE: UI Uniforme e Pulsante Track NEW Only dopo /add

## Data
5 Ottobre 2025

## Richiesta Utente
1. Rendere i riquadri dei prodotti in `/list` tutti con la **stessa dimensione (massima possibile)**
2. Aggiungere il **pulsante "Track NEW Only"** al messaggio che appare dopo aver condiviso un prodotto

## Implementazione

### 1. Riquadri Uniformi in `/list`

**Problema precedente:**
- Riquadri con altezze diverse (alcuni prodotti avevano Status, altri no)
- Nessun separatore visivo tra i prodotti
- Difficile confrontare rapidamente le informazioni

**Soluzione:**
```python
# Separatore visivo
separator = "─" * 40

# Struttura fissa per ogni prodotto:
product_lines = [
    separator,
    f"<b>{i}.</b> {clickable}",
    (NEW ONLY indicator se presente),
    separator,
    f"🌍 <b>Domain:</b> {dom or 'n/a'}",
    f"📦 <b>Status:</b> {stock_line}",  # SEMPRE presente
    f"💰 <b>Current:</b> {format_price(cur_p, curr_row)}",  # SEMPRE presente (con '—' se non disponibile)
    f"📉 <b>Historical Min:</b> {format_price(min_p, curr_row)}",
    f"📈 <b>Historical Max:</b> {format_price(max_p, curr_row)}",
    separator
]
```

**Caratteristiche:**
- ✅ **Separatori visivi**: Linee `────` sopra e sotto ogni prodotto
- ✅ **Altezza uniforme**: Status **sempre** presente (anche se "✅ In stock")
- ✅ **Current price sempre visualizzato**: Con fallback `—` se non disponibile
- ✅ **NEW ONLY indicator separato**: Su riga dedicata per chiarezza
- ✅ **Titolo più lungo**: 45 caratteri invece di 40 per sfruttare larghezza massima

**Esempio Output:**
```
────────────────────────────────────────
1. Apple AirPods Pro (2nd generation)
     🆕 NEW ONLY
────────────────────────────────────────
🌍 Domain: com
📦 Status: ✅ In stock
💰 Current: $84.99
📉 Historical Min: $79.99
📈 Historical Max: $94.99
────────────────────────────────────────
[❌ Track ALL]
```

### 2. Pulsante Track NEW Only dopo `/add`

**Problema precedente:**
- Dopo aver aggiunto un prodotto, l'utente doveva fare `/list` per attivare "Track NEW Only"
- Due passaggi invece di uno

**Soluzione:**
```python
# Create button for Track NEW Only toggle
keyboard = InlineKeyboardMarkup([[
    InlineKeyboardButton("🆕 Track NEW Only", callback_data=f"toggle_new_{item_id}")
]])

# Apply to both photo and text messages
if image_url:
    await context.bot.send_photo(
        chat_id=user.id, 
        photo=image_url, 
        caption=response, 
        parse_mode="HTML",
        reply_markup=keyboard  # ← Aggiunto
    )
else:
    await msg.edit_text(
        response, 
        parse_mode="HTML", 
        disable_web_page_preview=True,
        reply_markup=keyboard  # ← Aggiunto
    )
```

**Caratteristiche:**
- ✅ **Pulsante immediatamente disponibile** dopo `/add`
- ✅ **Stesso callback handler**: Usa `toggle_new_{item_id}` come `/list`
- ✅ **Aggiornamento immediato**: Fetch Keepa istantaneo quando cliccato
- ✅ **Funziona con foto**: Applicato sia a `send_photo` (caption) che `edit_text`
- ✅ **Un solo step**: Utente può attivare NEW tracking senza `/list`

**Esempio Output:**
```
✅ Product Added!

📦 Apple AirPods Pro (2nd generation)
💰 Current Price: $84.99
📉 Historical Min: $79.99
📈 Historical Max: $94.99

📢 You'll be notified when the price change!

[🆕 Track NEW Only]  ← Click per attivare subito!
```

## Files Modificati

### `src/bot.py`

**1. Funzione `cmd_list()` (linee ~690-745)**

Modifiche:
- Aggiunto `separator = "─" * 40`
- Aumentato titolo da 40 a 45 caratteri
- Status **sempre** presente con fallback "✅ In stock"
- Current price **sempre** presente con fallback "—"
- NEW ONLY indicator su riga separata
- Separatori all'inizio e fine di ogni riquadro

**2. Funzione `handle_message()` (linee ~600-625)**

Modifiche:
- Creato `InlineKeyboardMarkup` con pulsante "🆕 Track NEW Only"
- Aggiunto `reply_markup=keyboard` a `send_photo()`
- Aggiunto `reply_markup=keyboard` a `edit_text()`

## Testing

### Test Manuale
1. ✅ Condividere link Amazon → Verificare pulsante "Track NEW Only" presente
2. ✅ Cliccare pulsante → Verificare "🔄 Updating prices..."
3. ✅ Eseguire `/list` → Verificare riquadri uniformi con separatori
4. ✅ Verificare Status sempre presente (anche per "In stock")
5. ✅ Verificare Current price sempre presente (anche con "—")
6. ✅ Toggle vari prodotti → Verificare funzionamento corretto

### Test File
`test_new_layout.py` - Documentazione visiva delle modifiche

## Vantaggi

### UI Uniforme
- 📐 **Consistenza visiva**: Tutti i riquadri stessa altezza
- 👁️ **Più facile leggere**: Separatori chiari tra prodotti
- 📊 **Confronto rapido**: Informazioni allineate
- 📱 **Migliore su mobile**: Messaggi separati più leggibili

### Pulsante dopo /add
- ⚡ **Più veloce**: Un solo step invece di due (`/add` → click invece di `/add` → `/list` → click)
- 🎯 **Intuitivo**: Opzione disponibile subito
- 🔄 **Immediato**: Fetch Keepa istantaneo
- 👍 **Migliore UX**: Meno friction per l'utente

## Backward Compatibility

✅ Tutte le funzionalità esistenti preservate:
- Toggle callback handler invariato
- Immediate refresh funziona
- DB queries invariate
- Nessun breaking change

## Note Tecniche

### Separatori
- Usa carattere Unicode `─` (U+2500) per compatibilità Telegram
- Lunghezza 40 caratteri = larghezza massima leggibile su mobile

### Status Placeholder
```python
# Se stock_line è vuoto, usa "In stock" come default
if stock_line:
    product_lines.append(f"📦 <b>Status:</b> {stock_line}")
else:
    product_lines.append(f"📦 <b>Status:</b> ✅ In stock")
```

### Current Price Placeholder
```python
# Sempre presente, anche se non disponibile
if avail == 'unavailable':
    product_lines.append(f"💰 <b>Current:</b> —")
elif avail == 'preorder' and not show_preorder_price:
    product_lines.append(f"💰 <b>Current:</b> —")
else:
    product_lines.append(f"💰 <b>Current:</b> {format_price(cur_p, curr_row)}")
```

## Screenshots / Examples

### Prima (altezza variabile)
```
1. Prodotto A 🆕 NEW ONLY
🌍 Domain: com
✅ In stock
💰 Current: $84.99
📉 Historical Min: $79.99
📈 Historical Max: $94.99

2. Prodotto B
🌍 Domain: com
💰 Current: $68.77
📉 Historical Min: $60.00
📈 Historical Max: $150.00
```

### Dopo (altezza uniforme)
```
────────────────────────────────────────
1. Prodotto A
     🆕 NEW ONLY
────────────────────────────────────────
🌍 Domain: com
📦 Status: ✅ In stock
💰 Current: $84.99
📉 Historical Min: $79.99
📈 Historical Max: $94.99
────────────────────────────────────────

────────────────────────────────────────
2. Prodotto B
────────────────────────────────────────
🌍 Domain: com
📦 Status: ✅ In stock
💰 Current: $68.77
📉 Historical Min: $60.00
📈 Historical Max: $150.00
────────────────────────────────────────
```

---

**Status**: ✅ Implementato e testato
**Data**: 5 Ottobre 2025
