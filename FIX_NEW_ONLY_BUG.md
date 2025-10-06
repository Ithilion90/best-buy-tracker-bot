# FIX: Bug NEW ONLY - Prezzi USED nelle notifiche

## 🐛 Problema Identificato

**Data:** 5 Ottobre 2025
**Prodotto affetto:** B0D2MK6NML (e potenzialmente tutti i prodotti con `new_only=True`)

### Descrizione del Bug

Nonostante un prodotto fosse impostato su **NEW ONLY**, il sistema:
1. ❌ Inviava notifiche con prezzi USED
2. ❌ Aggiornava il `current_price` nel DB con prezzi USED
3. ❌ Mostrava minimi storici basati su prezzi USED

### Causa Root

Nel file `src/bot.py`, funzione `refresh_prices_and_notify()`, alla linea ~280:

```python
# CODICE BUGGY (PRIMA DELLA FIX)
current_price = scraped_price if scraped_price is not None else (k_cur if k_cur is not None else (k_min + k_max) / 2)
```

**Il problema:** 
- `scraped_price` proviene dallo scraping diretto della pagina Amazon
- Amazon mostra il prezzo **più basso disponibile** (che può essere USED/Ricondizionato)
- Lo scraper **non filtra per condizione NEW**
- Il codice usava sempre `scraped_price` se disponibile, **ignorando il flag `new_only`**

### Esempio Concreto (B0D2MK6NML)

| Fonte | Prezzo | Note |
|-------|--------|------|
| Scraping pagina | €68.77 | Prezzo USED (il più basso visibile) ❌ |
| Keepa NEW ONLY | €84.90 | Prezzo NEW corretto ✅ |

Con il bug, il sistema usava €68.77 anche se il prodotto era `new_only=True`.

---

## ✅ Soluzione Implementata

### Codice Modificato

```python
# CODICE FIXED (DOPO LA FIX)
if new_only:
    # For NEW ONLY products, use only Keepa data (filtered for NEW condition)
    current_price = k_cur if k_cur is not None else (k_min + k_max) / 2
    logger.debug("Using Keepa price for NEW ONLY product", asin=asin, keepa_current=k_cur, scraped_ignored=scraped_price)
else:
    # For NEW+USED products, prefer scraped price (most current), fallback to Keepa
    current_price = scraped_price if scraped_price is not None else (k_cur if k_cur is not None else (k_min + k_max) / 2)
```

### Logica della Fix

1. **Se `new_only=True`:**
   - ✅ Usa **solo Keepa** (`k_cur`) che è filtrato per condizione NEW
   - ✅ Ignora completamente `scraped_price` (può contenere prezzi USED)
   - ✅ Fallback a `(k_min + k_max) / 2` se Keepa current non disponibile

2. **Se `new_only=False`:**
   - ✅ Usa `scraped_price` (più aggiornato)
   - ✅ Fallback a Keepa se scraping fallisce
   - ✅ Comportamento originale mantenuto

### Benefici

- 🎯 **Accuratezza:** Prezzi NEW ONLY ora rispecchiano solo offerte nuove
- 🔔 **Notifiche corrette:** Niente più alert su prezzi USED per prodotti NEW ONLY
- 📊 **Dati affidabili:** Minimi/massimi storici basati sulla condizione corretta
- 🐛 **Bug risolto:** B0D2MK6NML ora mostra €84.90 invece di €68.77

---

## 🧪 Test di Verifica

Eseguire: `python test_new_only_fix.py`

**Output atteso:**
```
VECCHIO COMPORTAMENTO (BUGGY):
   current_price = 68.77 ❌ (usa il prezzo USED!)

NUOVO COMPORTAMENTO (FIXED):
   current_price = 84.9 ✅ (usa solo Keepa NEW ONLY!)

Differenza: €68.77 (USED) vs €84.9 (NEW)
Risparmio evitato: €16.13
```

---

## 📝 Note Tecniche

### Architettura del Sistema di Prezzi

1. **Keepa API:**
   - Supporta filtro `new_only` nel parametro `stats`
   - Stats index 0 = Amazon (ALL conditions)
   - Stats index 1 = NEW offers only
   - Dati storici affidabili e filtrati

2. **Web Scraping:**
   - Estrae il prezzo **visibile sulla pagina**
   - **NON filtra per condizione** (mostra il più basso)
   - Utile per NEW+USED (prezzo reale di mercato)
   - **Da ignorare per NEW ONLY**

3. **Grouping Logic:**
   - Prodotti raggruppati per `(domain, new_only)`
   - Query Keepa separate per NEW e ALL
   - ✅ Questo era già corretto
   - ❌ Il bug era nell'uso del `scraped_price`

### Logging Aggiunto

Nuovo log di debug per troubleshooting:
```python
logger.debug("Using Keepa price for NEW ONLY product", 
             asin=asin, 
             keepa_current=k_cur, 
             scraped_ignored=scraped_price)
```

Visibile nei log quando un prodotto NEW ONLY ignora uno scraped price USED.

---

## 🔄 Migrazione Dati Esistenti

I prodotti già in DB con prezzi USED errati verranno corretti automaticamente:
- Al prossimo **refresh cycle** (ogni 30 minuti)
- O al prossimo **toggle** del pulsante NEW ONLY
- O al **riavvio del bot**

**Nessuna azione manuale richiesta.**

---

## ✅ Checklist Post-Fix

- [x] Codice modificato in `refresh_prices_and_notify()`
- [x] Logging aggiunto per debugging
- [x] Test script creato (`test_new_only_fix.py`)
- [x] Documentazione scritta
- [x] Verificato che non ci siano errori di sintassi
- [ ] Test in produzione con B0D2MK6NML
- [ ] Monitorare log per confermare fix funzionante

---

**Autore:** GitHub Copilot  
**Data Fix:** 5 Ottobre 2025  
**Commit:** (da determinare)
