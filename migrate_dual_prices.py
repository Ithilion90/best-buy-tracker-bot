"""Migration: Add dual-mode price tracking columns"""
import sqlite3
import sys

print("="*80)
print("DATABASE MIGRATION: DUAL-MODE PRICE TRACKING")
print("="*80)

conn = sqlite3.connect('tracker.db')
cursor = conn.cursor()

# Verifica colonne esistenti
cursor.execute("PRAGMA table_info(items)")
existing_cols = [col[1] for col in cursor.fetchall()]

migrations = [
    ('min_price_new', 'REAL', 'Minimo storico SOLO NUOVO'),
    ('max_price_new', 'REAL', 'Massimo storico SOLO NUOVO'),
    ('min_price_all', 'REAL', 'Minimo storico NUOVO+USATO'),
    ('max_price_all', 'REAL', 'Massimo storico NUOVO+USATO'),
]

print("\n📋 Colonne da aggiungere:")
print("-"*80)

applied = 0
skipped = 0

for col_name, col_type, description in migrations:
    if col_name in existing_cols:
        print(f"⏭️  {col_name:20s} - già presente, skip")
        skipped += 1
    else:
        print(f"➕ {col_name:20s} - aggiunta ({description})")
        cursor.execute(f"ALTER TABLE items ADD COLUMN {col_name} {col_type}")
        applied += 1

conn.commit()

print("\n" + "="*80)
print("MIGRATION COMPLETATA")
print("="*80)
print(f"\n✅ Colonne aggiunte: {applied}")
print(f"⏭️  Colonne esistenti: {skipped}")

if applied > 0:
    print("\n📊 Prossimi passi:")
    print("1. Aggiorna cmd_add() per salvare entrambi i prezzi")
    print("2. Aggiorna handle_toggle_new_only() per usare dati dal DB")
    print("3. Aggiorna refresh_prices_and_notify() per aggiornare tutte le colonne")

# Verifica struttura finale
print("\n" + "="*80)
print("STRUTTURA FINALE TABELLA items (colonne prezzi)")
print("="*80)

cursor.execute("PRAGMA table_info(items)")
price_cols = [col for col in cursor.fetchall() if 'price' in col[1]]

print("\nColonne prezzi:")
print("-"*80)
for col in price_cols:
    cid, name, col_type, notnull, default, pk = col
    print(f"{name:20s} {col_type:15s}")

conn.close()

print("\n✅ Migration completata con successo!")
