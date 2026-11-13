"""G-num: numeric questions generated from XBRL facts, with answers computed in code.

`candidates` (values, fiscal-period traps, growth), `ratios` and `peers` turn one split's
latest facts (E2) into every question they can ask; `generate` picks a seeded, stratified
quota per split and question type; `source` reads facts from Postgres.
"""
