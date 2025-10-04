# Fix per Notifica B0DS6S98ZF - Prezzo Incongruente

## Problema Originale

**ASIN**: B0DS6S98ZF  
**Notifica ricevuta**: Minimo storico a $511.07  
**Prezzo reale sul sito**: $599.99  

## Analisi Root Cause

### Diagnostica Eseguita

```
Scraped Price (1st fetch): $599.99 USD ✅ CORRETTO
Scraped Price (2nd fetch): EUR511.07 ❌ REDIRECT EU

Keepa Data:
- Min: $549.00
- Max: $739.99  
- Current: $599.99 ✅ CORRETTO
```

### Causa Identificata

Amazon mostra prezzi diversi in base a:
- Geolocalizzazione IP
- Cookie/sessione utente
- Redirect automatici a store EU

Durante il refresh periodico (ogni 30 minuti), lo scraping ha:
1. Fatto richiesta a `amazon.com/dp/B0DS6S98ZF`
2. Ricevuto redirect a versione EU con prezzo EUR511.07
3. Parsato correttamente: `price=511.07, currency='EUR'`
4. **SALVATO 511.07 senza validare la currency** ❌

Il bot non verificava se la currency scrapata corrispondeva al domain atteso!

## Soluzione Implementata

### Modifiche a `src/bot.py`

1. **Cattura currency dallo scraping**:
```python
# Prima:
title_s, price_s, _c, _img, avail = await fetch_price_title_image_and_availability(url)
return asin, title_s, price_s, avail

# Dopo:
title_s, price_s, currency_s, _img, avail = await fetch_price_title_image_and_availability(url)
return asin, title_s, price_s, currency_s, avail
```

2. **Validazione currency nel refresh**:
```python
scraped_title, scraped_price, scraped_currency, scraped_avail = scrape_results.get(asin, (None, None, None, None))

# Valida che currency scrapata corrisponda al domain
expected_currency = domain_to_currency(dom)
if scraped_price is not None and scraped_currency and scraped_currency != expected_currency:
    logger.warning(
        "Scraped currency mismatch - discarding scraped price",
        asin=asin,
        domain=dom,
        expected=expected_currency,
        got=scraped_currency,
        price=scraped_price
    )
    # Scarta il prezzo scrapato se la currency è sbagliata
    scraped_price = None
```

### Logica di Fallback

Dopo la validazione:
```python
current_price = scraped_price if scraped_price is not None else (k_cur if k_cur is not None else (k_min + k_max) / 2)
```

Se lo scraping viene scartato (currency mismatch), usa Keepa:
- Preferenza 1: `scraped_price` (se valido)
- Preferenza 2: `k_cur` (Keepa current)
- Preferenza 3: `(k_min + k_max) / 2` (media storica)

## Test di Verifica

### Test Cases Validati

| Domain | Scraped | Expected | Result |
|--------|---------|----------|--------|
| amazon.com | EUR511.07 | USD | ❌ REJECT → use Keepa $599.99 ✅ |
| amazon.com | USD599.99 | USD | ✅ ACCEPT scraped |
| amazon.it | EUR511.07 | EUR | ✅ ACCEPT scraped |
| amazon.co.uk | EUR450.00 | GBP | ❌ REJECT → use Keepa |

Tutti i test passano correttamente!

## Comportamento Atteso Post-Fix

### Per B0DS6S98ZF (amazon.com):

**Durante refresh ogni 30 min:**
1. Scraping tenta fetch da `amazon.com/dp/B0DS6S98ZF`
2. Se riceve redirect EU con EUR511.07:
   - ⚠️ Logger avvisa: "Scraped currency mismatch"
   - ❌ Scarta il prezzo scrapato
   - ✅ Usa Keepa current: $599.99
3. Se riceve risposta US corretta con USD599.99:
   - ✅ Valida currency match
   - ✅ Usa il prezzo scrapato: $599.99

**Notifiche:**
- Prezzo salvato: $599.99 (Keepa o scraping valido)
- Minimo storico: $549.00 (Keepa min)
- Notifica mostrerà i valori corretti in USD

## Impatto Generale

### Protezioni Aggiunte
- ✅ Valida currency per tutti i domini
- ✅ Previene salvaggi di prezzi con currency errata
- ✅ Fallback automatico a Keepa quando scraping redirect
- ✅ Log di warning per diagnostica futura

### Domini Protetti
- amazon.com → USD
- amazon.it → EUR
- amazon.co.uk → GBP
- amazon.de → EUR
- amazon.fr → EUR
- amazon.es → EUR
- amazon.ca → CAD
- amazon.com.mx → MXN
- amazon.co.jp → JPY

## Files Modificati

- ✅ `src/bot.py` - Validazione currency nel refresh
- ✅ Test suite creata per validazione

## Note Tecniche

### Perché Amazon Redirecta?

Amazon può redirectare in base a:
- IP geolocalizzato (EU → store EU)
- Accept-Language header
- Cookie di sessione precedenti
- User-Agent mobile/desktop

### Perché Keepa È Affidabile?

Keepa:
- Usa API ufficiali Amazon
- Tiene conto del domain specifico
- Non subisce redirect
- Cache aggiornata regolarmente

### Quando Preferire Scraping vs Keepa?

**Scraping** (più real-time):
- Quando currency valida
- Per prezzi flash/lampo
- Aggiornamenti frequenti

**Keepa** (più stabile):
- Currency mismatch (redirect)
- Scraping fallito/timeout
- Fallback affidabile
