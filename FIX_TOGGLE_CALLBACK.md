# Fix: Toggle Callback Query Answer

**Problema**: Il toggle del pulsante "Track NEW Only" / "Track ALL" non funzionava correttamente.

**Causa**: Chiamata duplicata di `query.answer()` nella funzione `handle_toggle_new_only()`.

## Dettagli del Bug

Nel codice originale:

```python
async def handle_toggle_new_only(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # ❌ Prima chiamata (vuota)
    
    # ... codice intermedio ...
    
    # Show loading indicator
    await query.answer("🔄 Updating prices...")  # ❌ Seconda chiamata - FALLISCE
```

**Problema**: L'API di Telegram permette di chiamare `query.answer()` **una sola volta** per ogni callback query. La seconda chiamata fallisce silenziosamente, causando:
- Nessun feedback visivo all'utente ("🔄 Updating prices..." non viene mostrato)
- Possibili problemi nel completamento dell'operazione di toggle

## Soluzione

Rimossa la prima chiamata vuota e spostato il messaggio di feedback all'inizio:

```python
async def handle_toggle_new_only(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    
    user = update.effective_user
    if not user:
        await query.answer("❌ User not found", show_alert=True)  # ✅ Answer con messaggio di errore
        return
    
    # Parse callback data
    try:
        item_id = int(query.data.split('_')[-1])
    except (ValueError, IndexError):
        await query.answer("❌ Invalid callback data", show_alert=True)  # ✅ Answer con messaggio di errore
        return
    
    # Show loading indicator immediately - UNICA chiamata a query.answer()
    await query.answer("🔄 Updating prices...")  # ✅ Chiamata unica con feedback
    
    # ... resto del codice di toggle ...
```

## Vantaggi del Fix

1. ✅ **Feedback visivo immediato**: L'utente vede "🔄 Updating prices..." quando clicca il pulsante
2. ✅ **Nessuna chiamata API fallita**: Una sola chiamata a `query.answer()`, come richiesto dall'API Telegram
3. ✅ **Gestione errori migliorata**: Gli errori precoci (user not found, invalid data) mostrano alert invece di modificare il messaggio
4. ✅ **Codice più pulito**: Flusso lineare senza chiamate duplicate

## Test

Per testare il fix:

1. Aggiungi un prodotto Amazon al bot
2. Clicca sul pulsante "🆕 Track NEW Only"
3. Dovresti vedere:
   - Notifica "🔄 Updating prices..." in alto
   - Il messaggio si aggiorna con i nuovi prezzi (solo NEW)
   - Il pulsante cambia in "🔄 Track ALL (New + Used)"
4. Clicca nuovamente per tornare a Track ALL
5. Verifica che i prezzi si aggiornino correttamente

## Riferimenti

- **File modificato**: `src/bot.py`
- **Funzione**: `handle_toggle_new_only()` (linee ~898-1090)
- **Issue correlato**: "nel comando list non cambia più correttamente tra solo nuovo e nuovo + usato"
