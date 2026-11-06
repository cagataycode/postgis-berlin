# 6. Cost of the GIN index on bulk load

Insert 50k street-tree rows into two copies of the partition: all indexes vs the same without GIN on `attrs`. Times are wall-clock for the INSERT.

50,000 rows: with GIN 14.6 s, without 8.4 s (1.7x).

## Summary (warm execution time)

| Case | ms |
| --- | ---: |
| with GIN (7 indexes) | 14583.3 |
| without GIN (6 indexes) | 8424.0 |
