## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
from cloudflare import Cloudflare
from datetime import datetime, timedelta
from os import environ as env

# Since we aren't bundling this script, we can dynamically import src/ modules.
import sys; sys.path.append('src')

from nbac import fetch_archetypes, train_nbac, encode_meta, blob_to_db_value
from nbac.postgres import start_pool, hash_bytes

FORMATS = [
  'standard',
  'modern',
  'pioneer',
  'vintage',
  'legacy',
  'pauper',
]

MIN_DATE = (TIMESTAMP := datetime.now()) - timedelta(days=90)

# Start a PostgreSQL connection pool for the MTGO database.
start_pool()

# Setup a connection to the Cloudflare D1 API.
if api_token := env.get("CLOUDFLARE_API_TOKEN"):
  client = Cloudflare(api_token=api_token)
elif (api_key := env.get("CLOUDFLARE_API_KEY")) and (api_email := env.get("CLOUDFLARE_EMAIL")):
  client = Cloudflare(default_headers={
    "X-Auth-Key": api_key,
    "X-Auth-Email": api_email,
  })
else:
  raise RuntimeError(
    "CLOUDFLARE_API_TOKEN or CLOUDFLARE_API_KEY/CLOUDFLARE_EMAIL is required."
  )

db = lambda query, **kwargs: client.d1.database.raw(
  database_id=env["CLOUDFLARE_DATABASE_ID"],
  account_id=env["CLOUDFLARE_ACCOUNT_ID"],
  sql=query,
  **kwargs
)

for format in FORMATS:
  cards_table = f"{format}_nbac_cards"
  meta_table = f"{format}_nbac_meta"

  # Create NBAC tables if they do not exist.
  db(f"""
    CREATE TABLE IF NOT EXISTS {cards_table} (
      card TEXT PRIMARY KEY,
      entry BLOB,
      hash TEXT,
      updated_at DEFAULT CURRENT_TIMESTAMP
    );
  """)

  db(f"""
    CREATE TABLE IF NOT EXISTS {meta_table} (
      key TEXT PRIMARY KEY,
      entry BLOB,
      hash TEXT,
      updated_at DEFAULT CURRENT_TIMESTAMP
    );
  """)

  corpus = fetch_archetypes(format, MIN_DATE)
  artifacts = train_nbac(corpus)

  meta_blob = encode_meta(artifacts.meta)
  meta_hash = hash_bytes(meta_blob)

  # The Cloudflare Python SDK sends params as JSON, so raw bytes aren't supported.
  # Always base64-encode blobs for the build script; the Worker decodes them.
  force_b64 = True
  meta_value = blob_to_db_value(meta_blob, force_base64=True)

  # Upsert meta row.
  db(f"""
    INSERT INTO {meta_table} (key, entry, hash, updated_at)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(key) DO UPDATE SET
      entry = excluded.entry,
      hash = excluded.hash,
      updated_at = CURRENT_TIMESTAMP
    WHERE excluded.hash != {meta_table}.hash;
  """, params=["meta", meta_value, meta_hash])

  # Batch insert/update card entries.
  batch_size = 25
  keys = list(sorted(artifacts.cards.keys()))
  for i in range(0, len(keys), batch_size):
    batch_keys = keys[i:i + batch_size]
    params = []
    for card in batch_keys:
      blob = artifacts.cards[card]
      params.extend([card, blob_to_db_value(blob, force_base64=force_b64), hash_bytes(blob)])

    db(f"""
      INSERT INTO {cards_table} (card, entry, hash, updated_at)
      VALUES
        {','.join(['(?, ?, ?, CURRENT_TIMESTAMP)'] * len(batch_keys))}
      ON CONFLICT(card) DO UPDATE SET
        entry = excluded.entry,
        hash = excluded.hash,
        updated_at = CURRENT_TIMESTAMP
      WHERE excluded.hash != {cards_table}.hash;
    """, params=params)

  # Indexes for faster checks and maintenance.
  db(f"CREATE INDEX IF NOT EXISTS {cards_table}_hash ON {cards_table} (hash)")
  db(f"CREATE INDEX IF NOT EXISTS {cards_table}_updated_at ON {cards_table} (updated_at)")
  db(f"CREATE INDEX IF NOT EXISTS {meta_table}_hash ON {meta_table} (hash)")
  db(f"CREATE INDEX IF NOT EXISTS {meta_table}_updated_at ON {meta_table} (updated_at)")

  # Delete old entries from the database (older than a month).
  db(f"DELETE FROM {cards_table} WHERE updated_at < datetime('now', '-1 month')")
  db(f"DELETE FROM {meta_table} WHERE updated_at < datetime('now', '-1 month')")
