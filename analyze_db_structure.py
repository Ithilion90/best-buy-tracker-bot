"""Analizza struttura DB e propone modifiche"""
import sqlite3

conn = sqlite3.connect('tracker.db')
cursor = conn.cursor()

print("="*80)
print("STRUTTURA ATTUALE TABELLA items")
print("="*80)

cursor.execute("PRAGMA table_info(items)")
cols = cursor.fetchall()

print("\nColonne esistenti:")
print("-"*80)
for col in cols:
    cid, name, col_type, notnull, default, pk = col
    print(f"{cid:2d}. {name:20s} {col_type:15s} {'NOT NULL' if notnull else '        '} {f'DEFAULT {default}' if default else ''} {'PK' if pk else ''}")

print("\n" + "="*80)
print("COLONNE DA AGGIUNGERE PER DUAL-MODE TRACKING")
print("="*80)

needed_cols = {
    'new_only': ('BOOLEAN', '0', 'Flag: track solo nuovo (1) o nuovo+usato (0)'),
    'min_price_new': ('DOUBLE PRECISION', 'NULL', 'Minimo storico SOLO NUOVO'),
    'max_price_new': ('DOUBLE PRECISION', 'NULL', 'Massimo storico SOLO NUOVO'),
    'min_price_all': ('DOUBLE PRECISION', 'NULL', 'Minimo storico NUOVO+USATO'),
    'max_price_all': ('DOUBLE PRECISION', 'NULL', 'Massimo storico NUOVO+USATO'),
}

existing_col_names = [col[1] for col in cols]
missing_cols = []

print("\nVerifica colonne:")
print("-"*80)
for col_name, (col_type, default, description) in needed_cols.items():
    if col_name in existing_col_names:
        print(f"✅ {col_name:20s} - già presente")
    else:
        print(f"❌ {col_name:20s} - MANCANTE")
        missing_cols.append((col_name, col_type, default, description))

if missing_cols:
    print("\n" + "="*80)
    print("MIGRATION SCRIPT")
    print("="*80)
    print("\nAggiungi queste colonne al database:\n")
    
    for col_name, col_type, default, description in missing_cols:
        if default == 'NULL':
            print(f"ALTER TABLE items ADD COLUMN {col_name} {col_type};")
        else:
            print(f"ALTER TABLE items ADD COLUMN {col_name} {col_type} DEFAULT {default};")
    
    print("\n-- Descrizioni:")
    for col_name, col_type, default, description in missing_cols:
        print(f"-- {col_name}: {description}")
    
    print("\n" + "="*80)
    print("LOGICA TOGGLE MIGLIORATA")
    print("="*80)
    print("""
Con queste colonne, il toggle funzionerà così:

1. Al primo /add:
   - Fetch Keepa NEW ONLY → salva in min_price_new, max_price_new
   - Fetch Keepa NEW+USED → salva in min_price_all, max_price_all
   - Salva current price in last_price
   - Se new_only=True: min_price = min_price_new, max_price = max_price_new
   - Se new_only=False: min_price = min_price_all, max_price = max_price_all

2. Al toggle button:
   - NON serve rifare fetch Keepa!
   - Cambia solo new_only flag
   - Se new_only=True: min_price = min_price_new, max_price = max_price_new
   - Se new_only=False: min_price = min_price_all, max_price = max_price_all
   - Aggiorna messaggio con nuovi valori dal DB

3. Al refresh cycle:
   - Fetch SEMPRE entrambi i dati (NEW e ALL)
   - Aggiorna tutte e 4 le colonne
   - Applica anomaly validation su min_price_new
   - Usa min_price/max_price secondo new_only flag

VANTAGGI:
✅ Toggle istantaneo (no API calls)
✅ Dati sempre disponibili per entrambe le modalità
✅ Storico prezzi separato NEW vs ALL
✅ Possibilità di comparare le due modalità
""")
else:
    print("\n✅ Tutte le colonne necessarie sono già presenti!")

conn.close()
