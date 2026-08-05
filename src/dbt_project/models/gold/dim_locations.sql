/*
  Dimension table for TLC Taxi Zone locations.
  In a full implementation this would join the TLC zone lookup CSV
  (https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv).
  Here we derive distinct locations directly from the Silver trips table.
*/
SELECT DISTINCT
    pu_location_id AS location_id,
    CAST(NULL AS STRING) AS borough,
    CAST(NULL AS STRING) AS zone,
    CAST(NULL AS STRING) AS service_zone
FROM {{ source('silver', 'yellow_trips') }}
WHERE pu_location_id IS NOT NULL

UNION DISTINCT

SELECT DISTINCT
    do_location_id AS location_id,
    CAST(NULL AS STRING) AS borough,
    CAST(NULL AS STRING) AS zone,
    CAST(NULL AS STRING) AS service_zone
FROM {{ source('silver', 'yellow_trips') }}
WHERE do_location_id IS NOT NULL
