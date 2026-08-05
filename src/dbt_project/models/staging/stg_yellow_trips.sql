/*
  Staging layer over the Silver BigLake external table: renames columns to
  analytics-friendly names in one place so gold models never touch the source
  directly.
*/
SELECT
    vendor_id,
    tpep_pickup_datetime,
    tpep_dropoff_datetime,
    passenger_count,
    trip_distance,
    ratecode_id,
    store_and_fwd_flag,
    pu_location_id  AS pickup_location_id,
    do_location_id  AS dropoff_location_id,
    payment_type,
    fare_amount,
    extra,
    mta_tax,
    tip_amount,
    tolls_amount,
    improvement_surcharge,
    total_amount,
    congestion_surcharge,
    airport_fee
FROM {{ source('silver', 'yellow_trips') }}
