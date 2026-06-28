## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""Archetype/label utilities and corpus fetching for NBAC."""

from __future__ import annotations

from collections import Counter, OrderedDict
from datetime import datetime
import re


ARCHETYPE_COLORS = [
  # 1-color combinations
  'Mono-White', 'Mono-Blue', 'Mono-Black', 'Mono-Red', 'Mono-Green',
  'White',      'Blue',      'Black',      'Red',      'Green',
  'W',          'U',         'B',          'R',        'G',
  # 2-color combinations
  'Azorius', 'Orzhov', 'Boros', 'Selesnya', 'Dimir', 'Izzet', 'Rakdos',
  'WU',      'WB',     'WR',    'WG',       'UB',    'UR',    'BR',
  'Golgari', 'Gruul', 'Simic',
  'BG',      'RG',    'UG',
  # 3-color combinations
  'Jeskai', 'Grixis', 'Jund', 'Naya', 'Bant', 'Abzan', 'Sultai', 'Mardu',
  'WUR',    'UBR',    'BRG',  'WRG',  'GWU',  'WBG',   'UBG',    'WBR',
  'Temur', 'Esper', 'Bant',
  'URG',   'WUB',   'WUG',
  # 4/5-color combinations
  'WBRG', 'WURG', 'WUBG', 'WUBR', 'UBRG', 'WUBRG', '4c', '5c', '4/5c',
  # Specialty
  'Colorless', 'Snow',
  'C',         'S',
]

MACRO_ARCHETYPES = [
  'Aggro',
  'Control',
  'Midrange',
  'Combo',
  # Specialty
  'Prison',
  'Tempo',
  'Ramp',
  'GenericBlink',
]


def remove_colors(name: str | None) -> str | None:
  if name is None:
    return None

  for color in ARCHETYPE_COLORS:
    if color in name:
      name = re.sub(rf'^{color}\b', '', name, flags=re.IGNORECASE)
  return name.strip()


def fetch_archetypes(format: str, date: datetime) -> list[tuple]:
  """Fetch labeled decks from the Videre Project MTGO database."""

  from .postgres import get_cursor, parse_decklist

  cur = get_cursor()
  cur.execute(f"""
    SELECT
      a.id,
      a.name,
      a.archetype,
      e.format,
      e.date,
      d.mainboard,
      d.sideboard
    FROM
      archetypes a
      INNER JOIN decks d ON a.deck_id = d.id
      INNER JOIN events e ON d.event_id = e.id
    WHERE
      a.id IS NOT NULL
      AND e.format = '{format.capitalize()}'
      AND e.date >= '{date.strftime('%Y-%m-%d')}'
  """)

  archetypes = cur.fetchall()
  if len(archetypes) == 0:
    raise ValueError(f'No archetypes found for {format} on or after {date}.')

  for i, archetype in enumerate(archetypes):
    mainboard = parse_decklist(archetype[5])
    sideboard = parse_decklist(archetype[6])
    archetypes[i] = archetype[:5] + (mainboard, sideboard)

  return archetypes


def analyze_archetypes(archetypes: list[tuple]):
  analyzed = {}
  for archetype in archetypes:
    _, name, archetype_name, *_ = archetype
    if archetype_name is None:
      continue
    elif name in ARCHETYPE_COLORS:
      assert len(remove_colors(name) or '') == 0
      continue
    elif (base_name := remove_colors(archetype_name)) not in MACRO_ARCHETYPES:
      archetype_name = base_name

    if archetype_name not in analyzed:
      analyzed[archetype_name] = {
        'name': Counter(),
        'count': 0
      }
    analyzed[archetype_name]['name'][name] += 1
    analyzed[archetype_name]['count'] += 1

  for archetype_name, counters in analyzed.items():
    analyzed[archetype_name]['name'] = dict(counters['name'])

  analyzed = OrderedDict(sorted(analyzed.items(),
                               key=lambda item: item[1]['count'], reverse=True))
  return analyzed


def normalize_label(entry: tuple, allowed: set[str]) -> str | None:
  """Normalize a raw row to the archetype label used for training."""
  # entry fields: (id, name, archetype, format, date, mainboard, sideboard)
  base_name = remove_colors(entry[2])
  label = base_name if base_name in allowed and base_name not in MACRO_ARCHETYPES else entry[2]
  if not isinstance(label, str) or label not in allowed:
    return None
  return label


__all__ = [
  'ARCHETYPE_COLORS',
  'MACRO_ARCHETYPES',
  'remove_colors',
  'fetch_archetypes',
  'analyze_archetypes',
  'normalize_label',
]
