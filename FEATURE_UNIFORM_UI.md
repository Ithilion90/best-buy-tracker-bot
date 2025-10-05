# FEATURE: UI Pulita con Pulsanti Chiari
**Esempio Output:**
```
1. Apple AirPods Pro (2nd generation)
     🆕 NEW ONLY
🌍 Domain: amazon.com
📦 Status: ✅ In stock
💰 Current: $84.99
📉 Historical Min: $79.99
📈 Historical Max: $94.99
[🔄 Track ALL (New + Used)]
```

### 2. Pulsanti Chiari e Descrittivi

**Evoluzione:**
- **V1**: `❌ Track ALL` ← Icona confusa (sembra "cancella")
- **V2 FINALE**: `🔄 Track ALL (New + Used)` ← Icona chiara + testo esplicativo!

**Caratteristiche:**
- ✅ **Icona 🔄** (frecce circolari) → Indica "switch/cambio modalità"
- ✅ **Testo "(New + Used)"** → Chiarisce che traccia anche usato
- ✅ **Inglese** → Standard internazionale
- ✅ **Immediata comprensione** dell'azionetobre 2025

## Versione Finale
Dopo iterazioni con l'utente, la UI è stata ottimizzata per massima chiarezza e pulizia.

## Richieste Utente (Iterazioni)

**Iterazione 1:**
1. Rendere i riquadri dei prodotti in `/list` tutti con la **stessa dimensione (massima possibile)**
2. Aggiungere il **pulsante "Track NEW Only"** al messaggio che appare dopo aver condiviso un prodotto

**Iterazione 2 (FINALE):**
1. **Rimuovere separatori** (────) tra le righe in `/list`
2. Cambiare **icona da ❌ a 🔄** per il pulsante "Track ALL"
3. Aggiungere **testo esplicativo in inglese**: "Track ALL (New + Used)"

## Implementazione

### 1. UI Pulita in `/list`

**Versione Finale:**
```python
# NO separatori - UI più pulita
product_lines = [f"<b>{i}.</b> {clickable}"]
if new_only_indicator:
    product_lines.append(f"     {new_only_indicator}")

product_lines.append(f"🌍 <b>Domain:</b> {dom or 'n/a'}")
product_lines.append(f"📦 <b>Status:</b> {stock_line or '✅ In stock'}")
product_lines.append(f"💰 <b>Current:</b> {format_price(cur_p, curr_row)}")
product_lines.append(f"📉 <b>Historical Min:</b> {format_price(min_p, curr_row)}")
product_lines.append(f"📈 <b>Historical Max:</b> {format_price(max_p, curr_row)}")
```

**Caratteristiche:**
- ❌ **RIMOSSI separatori** `────` (troppo cluttering)
- ✅ **Altezza uniforme** preservata (Status sempre presente)
- ✅ **Current price sempre presente** (con `—` se non disponibile)
- ✅ **Layout compatto** e leggibile

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

### 3. Pulsante Track NEW Only dopo `/add`

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
