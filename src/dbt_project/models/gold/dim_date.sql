{{
  config(
    materialized='external',
    options={
      'format': 'ICEBERG',
      'uris': ['gs://' ~ env_var('GCP_PROJECT_ID') ~ '-iceberg-warehouse/warehouse/gold/dim_date/metadata/v1.metadata.json'],
      'connection_id': 'us-central1.iceberg-gcs-conn'
    }
  )
}}

SELECT DISTINCT
    DATE(tpep_pickup_datetime)                            AS date_day,
    EXTRACT(YEAR  FROM tpep_pickup_datetime)              AS year,
    EXTRACT(MONTH FROM tpep_pickup_datetime)              AS month,
    EXTRACT(DAY   FROM tpep_pickup_datetime)              AS day,
    EXTRACT(DAYOFWEEK FROM tpep_pickup_datetime)          AS day_of_week,
    FORMAT_DATE('%A', DATE(tpep_pickup_datetime))         AS day_name,
    FORMAT_DATE('%B', DATE(tpep_pickup_datetime))         AS month_name,
    EXTRACT(QUARTER FROM tpep_pickup_datetime)            AS quarter,
    CASE
        WHEN EXTRACT(DAYOFWEEK FROM tpep_pickup_datetime) IN (1, 7)
        THEN TRUE ELSE FALSE
    END                                                   AS is_weekend
FROM {{ source('silver', 'yellow_trips') }}
WHERE tpep_pickup_datetime IS NOT NULL
