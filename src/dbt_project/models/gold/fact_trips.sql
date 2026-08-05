SELECT
    FARM_FINGERPRINT(
        CONCAT(
            CAST(t.vendor_id AS STRING),
            CAST(t.tpep_pickup_datetime AS STRING)
        )
    )                        AS trip_id,
    t.vendor_id,
    t.pu_location_id         AS pickup_location_id,
    t.do_location_id         AS dropoff_location_id,
    t.tpep_pickup_datetime,
    t.tpep_dropoff_datetime,
    t.passenger_count,
    t.trip_distance,
    t.fare_amount,
    t.extra,
    t.mta_tax,
    t.tip_amount,
    t.tolls_amount,
    t.improvement_surcharge,
    t.congestion_surcharge,
    t.airport_fee,
    t.total_amount,
    t.payment_type,
    t.ratecode_id,
    t.store_and_fwd_flag
FROM {{ source('silver', 'yellow_trips') }} t
