# 🤖 Amazon Price Tracker Bot - Eseguibile

## 📋 **Requisiti per l'Installazione**

1. **Sistema Operativo**: Windows 10/11 (64-bit)
2. **File di configurazione**: `.env` file con il token del bot Telegram

## 🚀 **Installazione e Configurazione**

### Passo 1: Configurazione Bot Telegram
1. Apri Telegram e cerca `@BotFather`
2. Digita `/newbot` e segui le istruzioni
3. Salva il **token** del bot che ricevi

### Passo 2: Configurazione File .env
1. Crea un file chiamato `.env` nella stessa cartella dell'eseguibile
2. Aggiungi il contenuto seguente:

```
# Configurazione Bot Telegram
BOT_TOKEN=il_tuo_token_qui

# Configurazione Database
DATABASE_PATH=tracker.db

# Configurazione Keepa (opzionale)
KEEPA_ACCESS_KEY=la_tua_chiave_keepa_opzionale

# Configurazione Amazon Affiliazione (opzionale)
AMAZON_AFFILIATE_TAG=il_tuo_tag_affiliazione

# Configurazione Log
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log
```

### Passo 3: Avvio del Bot
1. Clicca doppio su `BestBuyTrackerBot.exe`
2. Se tutto è configurato correttamente, vedrai:
   ```
   INFO: Database initialized successfully
   INFO: Starting Amazon Price Tracker Bot
   INFO: Bot started successfully - Price tracking and notifications active
   ```

## 📱 **Come Usare il Bot**

### Comandi Disponibili:
- `/start` - Avvia il bot e mostra la guida
- `/help` - Mostra tutti i comandi disponibili
- `/list` - Mostra i prodotti tracciati con prezzi aggiornati
- `/remove <numero>` - Rimuove un prodotto dalla lista

### Aggiungere Prodotti:
1. Vai su Amazon e trova un prodotto
2. Copia il link del prodotto
3. Invia il link al bot su Telegram
4. Il bot inizierà automaticamente a tracciare il prezzo

### Notifiche Automatiche:
- **Calo Prezzo**: Quando un prodotto scende di prezzo significativamente
- **Minimo Storico**: Quando un prodotto raggiunge il prezzo più basso mai registrato

## 🔧 **Risoluzione Problemi**

### Il bot non si avvia:
1. Verifica che il file `.env` sia presente e corretto
2. Controlla che il BOT_TOKEN sia valido
3. Assicurati che non ci siano altri bot con lo stesso token in esecuzione

### Il bot non risponde:
1. Verifica la connessione internet
2. Controlla che il token del bot sia ancora valido
3. Riavvia l'eseguibile

### I prezzi non si aggiornano:
1. Il bot controlla automaticamente ogni ora
2. Usa `/list` per forzare un aggiornamento manuale

## 📂 **File Generati**
- `tracker.db` - Database con i prodotti tracciati
- `logs/bot.log` - File di log per debug
- `cache/` - Cache per ottimizzare le richieste

## 🔒 **Sicurezza**
- Non condividere mai il tuo BOT_TOKEN
- Il database è locale e sicuro
- Tutti i dati rimangono sul tuo computer

## 📞 **Supporto**
In caso di problemi, controlla i log in `logs/bot.log` per messaggi di errore dettagliati.

---
**Versione**: 2.0  
**Ultima Modifica**: Agosto 2025  
**Compatibilità**: Windows 10/11 64-bit
