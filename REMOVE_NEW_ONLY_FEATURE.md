# Rimozione Feature "NEW ONLY / NEW+USED Toggle"

## 📋 Modifiche Effettuate

### Contesto
Su richiesta dell'utente, è stata completamente rimossa la funzionalità di toggle tra "Solo Nuovo" e "Nuovo + Usato". Il bot ora traccia **sempre e solo i prezzi NEW+USED** (tutti i venditori) per ogni prodotto.

### File Modificato: `src/bot.py`

#### 1. **Rimosso Import CallbackQueryHandler**
```python
# PRIMA:
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# DOPO:
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
```

#### 2. **Rimosso Pulsante Toggle in `handle_shared_link()`**
- **Rimosso:** Creazione pulsante "Track NEW Only"
- **Rimosso:** `InlineKeyboardMarkup` con pulsante toggle
- **Risultato:** Quando si aggiunge un prodotto, non viene più mostrato alcun pulsante

**Codice rimosso:**
```python
# Create button for Track NEW Only toggle
keyboard = InlineKeyboardMarkup([[
    InlineKeyboardButton("🆕 Track NEW Only", callback_data=f"toggle_new_{item_id}")
]])
```

#### 3. **Rimosso Indicatore e Pulsante in `cmd_list()`**
- **Rimosso:** Lettura flag `new_only` dal database
- **Rimosso:** Indicatore "🔍 Tracking: 🆕 NEW ONLY / 🔄 NEW + USED"
- **Rimosso:** Pulsante toggle per ogni prodotto
- **Risultato:** Lista prodotti mostra solo: Dominio, Status, Prezzi (6 righe invece di 7)

**Righe rimosse dalla lista:**
```python
# Rimosso indicatore modalità tracking
new_only = r.get('new_only', 0)
new_only_indicator = "🆕 NEW ONLY" if new_only else "🔄 NEW + USED"
product_lines.append(f"🔍 <b>Tracking:</b> {new_only_indicator}")

# Rimosso pulsante toggle
button_text = "🔄 Track ALL (New + Used)" if new_only else "🆕 Track NEW Only"
keyboard = InlineKeyboardMarkup([[
    InlineKeyboardButton(button_text, callback_data=f"toggle_new_{item_id}")
]])
```

#### 4. **Rimossa Funzione Completa `handle_toggle_new_only()`**
- **Rimosso:** Intera funzione async (circa 150 righe)
- **Funzionalità eliminate:**
  - Parsing callback data
  - Toggle flag `new_only` nel DB
  - Fetch prezzi Keepa con filtro nuovo/usato
  - Aggiornamento prezzi nel DB
  - Ricostruzione messaggio con nuovi prezzi
  - Aggiornamento pulsante

#### 5. **Rimosso Handler Callback in `main()`**
```python
# RIMOSSO:
app.add_handler(CallbackQueryHandler(handle_toggle_new_only, pattern=r'^toggle_new_\d+$'))
```

#### 6. **Semplificato Raggruppamento in `refresh_prices_and_notify()`**
- **Prima:** Raggruppamento per `(domain, new_only)` - chiamate Keepa separate per NEW e ALL
- **Dopo:** Raggruppamento solo per `domain` - una sola chiamata Keepa per dominio

**Codice modificato:**
```python
# PRIMA:
domain_group: dict[tuple[str, bool], dict[str, list[dict]]] = {}
for it in items:
    # ...
    new_only = bool(it.get('new_only', 0))
    domain_group.setdefault((dom, new_only), {}).setdefault(asin, []).append(it)

for (dom, new_only), asin_map in domain_group.items():
    keepa_bounds_dom = fetch_lifetime_min_max_current(asins_dom, domain=dom, new_only=new_only)

# DOPO:
domain_group: dict[str, dict[str, list[dict]]] = {}
for it in items:
    # ...
    domain_group.setdefault(dom, {}).setdefault(asin, []).append(it)

for dom, asin_map in domain_group.items():
    keepa_bounds_dom = fetch_lifetime_min_max_current(asins_dom, domain=dom, new_only=False)
```

### Comportamento Attuale

#### Aggiunta Prodotto
1. Utente condivide link Amazon
2. Bot estrae ASIN e dati prodotto
3. Bot chiama Keepa con `new_only=False` (NEW+USED)
4. Mostra messaggio di conferma **senza pulsante toggle**

#### Lista Prodotti (`/list`)
Ogni prodotto mostra:
1. **Titolo** (con link affiliato)
2. **🌍 Domain:** amazon.it
3. **📦 Status:** ✅ In stock / ❌ Not available / 🕒 Pre-order
4. **💰 Current:** Prezzo attuale
5. **📉 Historical Min:** Minimo storico
6. **📈 Historical Max:** Massimo storico

**Nessun pulsante, nessun indicatore modalità tracking**

#### Refresh Periodico
- Chiamata Keepa **sempre con `new_only=False`**
- Traccia prezzi da **tutti i venditori** (nuovo + usato)
- Notifiche basate su cali di prezzo NEW+USED

### Database

**⚠️ NOTA IMPORTANTE:** 
Le colonne `new_only`, `min_price_new`, `max_price_new`, `min_price_all`, `max_price_all` **esistono ancora** nel database ma **non vengono più utilizzate** dal codice.

**Opzioni:**
1. **Lasciare le colonne** (scelta attuale) - Non causano problemi, semplicemente inutilizzate
2. **Rimuoverle con migration** - Richiede script SQL separato se si vuole pulizia completa

### Vantaggi della Rimozione

#### Performance
- ✅ **-50% chiamate Keepa** durante refresh (una sola chiamata per dominio invece di due)
- ✅ **UI più semplice** - Lista prodotti con 6 righe invece di 7
- ✅ **Nessuna latenza** per operazioni di toggle (funzione eliminata)

#### UX
- ✅ **Interfaccia più pulita** - Nessun pulsante, nessuna confusione
- ✅ **Comportamento consistente** - Sempre tracking NEW+USED per tutti
- ✅ **Prezzi affidabili** - Include offerte da tutti i venditori

#### Codice
- ✅ **-200 righe di codice** (handle_toggle_new_only + UI toggle)
- ✅ **Logica semplificata** - Nessun raggruppamento dual-mode
- ✅ **Meno complessità** - Un solo flusso di prezzi da gestire

### File NON Modificati

I seguenti file **mantengono** le funzionalità dual-mode ma **non vengono chiamati** dal bot:

- `src/db.py`:
  - `toggle_new_only()` - Esiste ma non viene chiamata
  - `update_dual_price_bounds()` - Esiste ma non viene chiamata
  - Colonne DB `new_only`, `*_new`, `*_all` - Esistono ma non usate

**Questi file possono essere:**
- Lasciati così (nessun impatto funzionale)
- Rimossi in futuro se si desidera pulizia completa

### Migrazione Dati

**NON NECESSARIA** - Il codice funziona con lo schema DB esistente:
- Colonne dual-mode semplicemente ignorate
- `new_only` flag ignorato (tutti i prodotti trattati come NEW+USED)
- Nessun errore, nessun problema di compatibilità

### Testing

#### Test Manuale
1. ✅ Aggiungi prodotto → Nessun pulsante toggle
2. ✅ `/list` → 6 righe per prodotto, nessun pulsante
3. ✅ Refresh prezzi → Una sola chiamata Keepa per dominio
4. ✅ Notifiche → Basate su prezzi NEW+USED

#### Verifica Errori
```bash
python -m pylint src/bot.py  # No errors
```

### Rollback (se necessario)

Per ripristinare la funzionalità dual-mode:
```bash
git checkout HEAD~1 -- src/bot.py
```

Oppure ripristinare da backup la versione precedente di `bot.py`.

---

**Data rimozione:** 2025-10-05  
**Versione bot:** Semplificata (solo NEW+USED tracking)  
**Stato:** ✅ COMPLETO - Pronto per deploy
