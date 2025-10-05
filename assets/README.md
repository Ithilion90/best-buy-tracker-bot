# Bot Assets

## Logo del Bot

Questa directory contiene le risorse grafiche del bot.

### bot-logo.png

**Dimensioni raccomandate**: 512x512 px o 1024x1024 px  
**Formato**: PNG con sfondo trasparente  
**Uso**: Mostrato nei comandi `/start` e `/help`

### Come Creare il Logo

#### Opzione 1: Emoji Combinate (Semplice)
Usa uno strumento online come:
- https://emojicombos.com
- https://getemoji.com

Emoji suggerite:
- 🛒📉 (Carrello + Grafico in discesa)
- 💰📊 (Denaro + Grafico)
- 🏷️📱 (Tag prezzo + Telefono)

#### Opzione 2: Canva (Gratuito)
1. Vai su https://www.canva.com
2. Crea nuovo design → 512 x 512 px
3. Elementi da includere:
   - Sfondo: Gradiente arancione-bianco (colori Amazon)
   - Icona: Carrello della spesa o box
   - Simbolo: Freccia ⬇️ o tag prezzo 🏷️
   - Testo (opzionale): "APT" o "Amazon Price Tracker"
4. Esporta come PNG trasparente

#### Opzione 3: Figma (Professionale)
Template consigliati:
- Bot icon design
- E-commerce app icon
- Shopping tracker logo

#### Opzione 4: AI Generator
Usa DALL-E, Midjourney, o Leonardo.ai con prompt:
```
"E-commerce price tracker app logo, shopping cart with downward arrow, 
orange and white colors, minimalist style, flat design, 512x512, 
icon for telegram bot"
```

### Colori Amazon Ufficiali

- **Arancione**: #FF9900
- **Nero**: #232F3E
- **Bianco**: #FFFFFF
- **Grigio scuro**: #37475A

### Template Suggerito

```
┌─────────────────┐
│   🛒            │  ← Carrello shopping
│                 │
│   📉            │  ← Grafico prezzi
│                 │
│   Amazon        │  ← Testo (opzionale)
│   Price         │
│   Tracker       │
└─────────────────┘
```

### Dopo Aver Creato il Logo

1. Salva il file come `bot-logo.png` in questa directory
2. Commit e push su GitHub
3. L'URL sarà disponibile automaticamente in:
   ```
   https://raw.githubusercontent.com/Ithilion90/best-buy-tracker-bot/main/assets/bot-logo.png
   ```
4. Il bot caricherà automaticamente l'immagine quando l'utente esegue `/start` o `/help`

### Alternative Temporanee

Se non hai ancora creato un logo personalizzato, puoi usare:

**Emoji grande**: Modifica `cmd_help()` in `src/bot.py`:
```python
# Rimuovi la parte try/except con reply_photo
# Usa solo:
await update.message.reply_text(
    "🛒📉 <b>Amazon Price Tracker</b>\n\n" + help_text,
    parse_mode="HTML"
)
```

**URL temporaneo**: Usa un servizio di hosting immagini:
- Imgur: https://imgur.com (upload gratis)
- ImgBB: https://imgbb.com
- Cloudinary: https://cloudinary.com

### Checklist

- [ ] Logo creato (512x512 px, PNG)
- [ ] File salvato come `assets/bot-logo.png`
- [ ] Push su GitHub
- [ ] Testato comando `/help`
- [ ] Immagine si carica correttamente
- [ ] Logo del bot su BotFather aggiornato

---

**Nota**: Assicurati di non usare il logo ufficiale Amazon per evitare problemi di copyright. Crea un design ispirato ma originale.
