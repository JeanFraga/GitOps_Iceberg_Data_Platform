/*
  Dimension table for TLC Taxi Zone locations, enriched with the official TLC
  zone lookup (seeds/taxi_zone_lookup.csv). Rows are limited to locations
  actually observed in the trip data.
*/
WITH observed AS (
    SELECT pickup_location_id AS location_id
    FROM {{ ref('stg_yellow_trips') }}
    WHERE pickup_location_id IS NOT NULL

    UNION DISTINCT

    SELECT dropoff_location_id
    FROM {{ ref('stg_yellow_trips') }}
    WHERE dropoff_location_id IS NOT NULL
)
SELECT
    o.location_id,
    z.borough,
    z.zone,
    z.service_zone
FROM observed o
LEFT JOIN {{ ref('taxi_zone_lookup') }} z USING (location_id)
