# Fix: Riquadri Uniformi nel Comando /list

**Problema**: I riquadri dei prodotti nel comando `/list` avevano dimensioni diverse perché alcuni campi venivano omessi condizionalmente.

**Soluzione**: Tutti i prodotti ora mostrano **esattamente 7 righe**, garantendo dimensioni perfettamente uniformi.

## Struttura Uniforme dei Riquadri

Ogni prodotto mostra sempre queste righe nell'ordine esatto:

```
Riga 1: [Numero]. [Titolo cliccabile]
Riga 2: [NEW ONLY indicator o riga vuota]
Riga 3: 🌍 Domain: [dominio]
Riga 4: 📦 Status: [status o placeholder]
Riga 5: 💰 Current: [prezzo o —]
Riga 6: 📉 Historical Min: [prezzo minimo]
Riga 7: 📈 Historical Max: [prezzo massimo]
```

## Esempio Output

### Prodotto con Track NEW Only Attivo

```
1. Amazon Fire TV Stick 4K
     🆕 NEW ONLY
🌍 Domain: amazon.it
📦 Status: ✅ In stock
💰 Current: €54.99
📉 Historical Min: €34.99
📈 Historical Max: €59.99
[🔄 Track ALL (New + Used)]
```

### Prodotto con Track ALL (Default)

```
2. PlayStation 5 Console
     
🌍 Domain: amazon.it
📦 Status: ✅ In stock
💰 Current: €549.99
📉 Historical Min: €449.99
📈 Historical Max: €599.99
[🆕 Track NEW Only]
```

### Prodotto Non Disponibile

```
3. Nintendo Switch OLED
     
🌍 Domain: amazon.it
📦 Status: ❌ Not available
💰 Current: —
📉 Historical Min: €299.99
📈 Historical Max: €349.99
[🆕 Track NEW Only]
```

## Modifiche Implementate

### 1. cmd_list() (linee ~735-765)

**Prima**:
```python
# Comportamento condizionale - dimensioni variabili
product_lines = [f"<b>{i}.</b> {clickable}"]
if new_only_indicator:  # ⚠️ A volte c'è, a volte no
    product_lines.append(f"     {new_only_indicator}")

product_lines.append(f"🌍 <b>Domain:</b> {dom or 'n/a'}")

if stock_line:  # ⚠️ Condizionale
    product_lines.append(f"📦 <b>Status:</b> {stock_line}")
else:
    product_lines.append(f"📦 <b>Status:</b> ✅ In stock")
```

**Dopo**:
```python
# Sempre 7 righe - dimensioni uniformi
product_lines = [f"<b>{i}.</b> {clickable}"]

# Line 2: NEW ONLY indicator o riga vuota (SEMPRE presente)
product_lines.append(f"     {new_only_indicator}" if new_only_indicator else "")

# Line 3: Domain (SEMPRE presente)
product_lines.append(f"🌍 <b>Domain:</b> {dom or 'n/a'}")

# Line 4: Status (SEMPRE presente con placeholder)
product_lines.append(f"📦 <b>Status:</b> {stock_line}" if stock_line else "📦 <b>Status:</b> ✅ In stock")

# Line 5: Current Price (SEMPRE presente con — se unavailable)
# ...

# Line 6: Historical Min (SEMPRE presente)
product_lines.append(f"📉 <b>Historical Min:</b> {format_price(min_p, curr_row)}")

# Line 7: Historical Max (SEMPRE presente)
product_lines.append(f"📈 <b>Historical Max:</b> {format_price(max_p, curr_row)}")
```

### 2. handle_toggle_new_only() (linee ~1025-1050)

Stessa logica applicata al callback handler per mantenere consistenza quando si toggli tra NEW e ALL.

## Vantaggi

✅ **Dimensioni perfettamente uniformi**: Tutti i riquadri hanno la stessa altezza  
✅ **UI più pulita**: Layout prevedibile e ordinato  
✅ **Nessun separatore**: Rimossi i separatori tra prodotti (come richiesto)  
✅ **Sempre 7 righe**: Struttura fissa e consistente  
✅ **Placeholder intelligenti**: Riga vuota per NEW ONLY, "—" per prezzi non disponibili  

## Test

Per testare:

1. Aggiungi almeno 3 prodotti:
   - Uno con Track NEW Only attivo
   - Uno con Track ALL (default)
   - Uno che sia unavailable o preorder

2. Esegui `/list`

3. Verifica che:
   - Tutti i riquadri abbiano la stessa altezza
   - Nessuna linea separatrice tra prodotti
   - Tutti i riquadri abbiano esattamente 7 righe (+ pulsante)
   - La riga 2 sia vuota nei prodotti senza NEW ONLY
   - I prodotti unavailable mostrino "—" invece del prezzo

## File Modificati

- **src/bot.py**:
  - Funzione `cmd_list()` (linee ~735-765)
  - Funzione `handle_toggle_new_only()` (linee ~1025-1050)

## Riferimenti

- Issue: "nel comando list voglio che ogni prodotto abbia il riquadro della stessa dimensione, quello massimo, senza separatori"
- Soluzione precedente: FEATURE_UNIFORM_UI.md (rimozione separatori)
- Questa fix: Garantisce dimensioni uniformi con righe fisse
