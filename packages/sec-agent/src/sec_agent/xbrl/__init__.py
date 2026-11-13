"""SEC XBRL companyfacts -> the `facts` table.

companyfacts (one JSON per company) -> typed entries (`companyfacts`) -> canonical
concepts (`concepts`), duration classes (`periods`) and fiscal labels (`calendar`) ->
one `Fact` per concept, unit, period and filing (`normalize`) -> Postgres (`store`).
Every filed version is kept; `versions` and the `facts_latest` view pick the latest (E2).
"""
