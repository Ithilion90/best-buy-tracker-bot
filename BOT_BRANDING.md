# Amazon Price Tracker - Bot Branding

## Nome Bot
**Amazon Price Tracker** 🛒

Il bot è stato rinominato da "Best Buy Tracker" a "Amazon Price Tracker" per riflettere meglio la sua funzionalità principale.

## Logo del Bot

### Immagine Corrente
L'immagine del bot viene mostrata nei comandi `/start` e `/help`.

**URL attuale**: `https://i.imgur.com/8KxQzBP.png`

Questa è un'immagine placeholder. Per personalizzarla:

### Come Cambiare l'Immagine

1. **Crea o trova un'immagine adatta**:
   - Dimensioni consigliate: 512x512 px o 1024x1024 px
   - Formato: PNG o JPG
   - Tema: Amazon, shopping, prezzi, tracking
   - Esempi di temi:
     - Logo Amazon con tag prezzo
     - Carrello della spesa con grafico prezzi
     - Icona di notifica con simbolo €/$
     - Box Amazon con freccia verso il basso (sconto)

2. **Carica l'immagine**:
   - **Opzione A - Imgur**: Carica su https://imgur.com e copia il link diretto
   - **Opzione B - GitHub**: Aggiungi al repository in `assets/bot-logo.png`
   - **Opzione C - Server proprio**: Carica sul tuo server

3. **Aggiorna il codice**:
   Modifica `src/bot.py` nella funzione `cmd_help()`:
   ```python
   # Cambia questo URL con il tuo
   logo_url = "https://i.imgur.com/8KxQzBP.png"
   ```

### Raccomandazioni Design

✅ **Cosa includere**:
- Colori Amazon (arancione #FF9900, nero, bianco)
- Simboli di prezzo (€, $, ₤)
- Icone di notifica/campanello
- Freccia verso il basso (indicatore di sconto)
- Carrello della spesa

❌ **Da evitare**:
- Logo Amazon ufficiale esatto (copyright)
- Immagini troppo complesse o cariche
- Testo troppo piccolo
- Colori troppo scuri (leggibilità su Telegram)

### Alternative Già Pronte

Se non vuoi creare un'immagine personalizzata, ecco alcune opzioni:

1. **Emoji grande**: Usa un emoji come 🛒📉 o 💰📊
2. **Icon Libraries**: 
   - Font Awesome
   - Material Icons
   - Flaticon (con licenza)

### Impostazione BotFather

Oltre all'immagine nel messaggio `/help`, puoi impostare:

1. **Foto profilo del bot** (botpic):
   ```
   /mybots → Seleziona bot → Edit Bot → Edit Botpic
   ```

2. **Descrizione** (description):
   ```
   Track Amazon product prices and get instant notifications when they drop!
   
   Share any Amazon product link and I'll monitor it for you 24/7.
   Never miss a deal again! 🛒💰
   ```

3. **About** (short description):
   ```
   Track Amazon prices and get notified of discounts 📉
   ```

4. **Comandi** (commands):
   ```
   start - Start the bot and see help
   help - Show available commands
   list - Show tracked products
   remove - Remove a product
   ```

## Messaggi del Bot

Il branding è stato aggiornato anche in:

- ✅ Comando `/start` - Mostra logo e nome "Amazon Price Tracker"
- ✅ Comando `/help` - Mostra logo e descrizione completa
- ✅ Log di avvio - "Starting Amazon Price Tracker Bot"
- ✅ Log finale - "Amazon Price Tracker Bot started successfully"

## File Modificati

- `src/bot.py`:
  - Funzione `cmd_help()` - Aggiunto logo e nuovo nome
  - Funzione `main()` - Aggiornati messaggi di log

## Prossimi Passi

1. [ ] Caricare un'immagine personalizzata
2. [ ] Aggiornare l'URL in `cmd_help()`
3. [ ] Configurare BotFather con foto profilo
4. [ ] Aggiornare descrizione su BotFather
5. [ ] Testare il comando `/start` per verificare l'immagine

## Note

- L'immagine viene scaricata da Telegram ogni volta che un utente esegue `/help`
- Se l'immagine non si carica (errore), il bot mostra solo il testo
- Assicurati che l'URL sia sempre accessibile (non usare link temporanei)
