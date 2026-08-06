####################################################################
# fact_trips — trip fact table.
#
# Source: src/dbt_project/models/gold/fact_trips.sql
# Grain:  one row per taxi trip (trip_id is enforced unique + not_null
#         by the dbt tests in models/gold/schema.yml).
#
# Column types mirror the physical BigQuery schema exactly:
#   trip_id, vendor_id, *_location_id, payment_type  INT64
#   ratecode_id and every amount/count column        FLOAT64
#   tpep_pickup_datetime / tpep_dropoff_datetime     TIMESTAMP
####################################################################

view: fact_trips {
  sql_table_name: `@{gcp_project_id}.@{gold_dataset}.fact_trips` ;;

  # ---------------------------------------------------------------
  # Keys
  # ---------------------------------------------------------------

  dimension: trip_id {
    primary_key: yes
    type: number
    value_format_name: id
    sql: ${TABLE}.trip_id ;;
    description: "Surrogate key: FARM_FINGERPRINT of the Silver business key (vendor, pickup ts, dropoff ts, pickup zone, dropoff zone)."
  }

  dimension: pickup_location_id {
    type: number
    hidden: yes
    sql: ${TABLE}.pickup_location_id ;;
  }

  dimension: dropoff_location_id {
    type: number
    hidden: yes
    sql: ${TABLE}.dropoff_location_id ;;
  }

  # ---------------------------------------------------------------
  # Time
  # ---------------------------------------------------------------

  dimension_group: pickup {
    type: time
    datatype: timestamp
    timeframes: [raw, time, hour_of_day, date, day_of_week, week, month, month_name, quarter, year]
    sql: ${TABLE}.tpep_pickup_datetime ;;
    description: "When the meter was engaged."
  }

  dimension_group: dropoff {
    type: time
    datatype: timestamp
    timeframes: [raw, time, hour_of_day, date, week, month, year]
    sql: ${TABLE}.tpep_dropoff_datetime ;;
    description: "When the meter was disengaged."
  }

  dimension: trip_duration_minutes {
    type: number
    value_format_name: minutes
    sql: TIMESTAMP_DIFF(${TABLE}.tpep_dropoff_datetime, ${TABLE}.tpep_pickup_datetime, SECOND) / 60.0 ;;
    description: "Wall-clock trip length. Negative values indicate bad source rows."
  }

  dimension: is_valid_duration {
    type: yesno
    sql: ${trip_duration_minutes} > 0 AND ${trip_duration_minutes} < 240 ;;
    description: "Filters out the zero/negative and multi-day durations present in raw TLC data."
  }

  # ---------------------------------------------------------------
  # Trip attributes
  # ---------------------------------------------------------------

  dimension: vendor_id {
    type: number
    hidden: yes
    sql: ${TABLE}.vendor_id ;;
  }

  dimension: vendor {
    type: string
    sql: CASE ${vendor_id}
           WHEN 1 THEN 'Creative Mobile Technologies'
           WHEN 2 THEN 'VeriFone'
           ELSE 'Unknown'
         END ;;
    description: "TLC-assigned provider that supplied the record."
  }

  dimension: payment_type_id {
    type: number
    hidden: yes
    sql: ${TABLE}.payment_type ;;
  }

  dimension: payment_type {
    type: string
    sql: CASE ${payment_type_id}
           WHEN 1 THEN 'Credit card'
           WHEN 2 THEN 'Cash'
           WHEN 3 THEN 'No charge'
           WHEN 4 THEN 'Dispute'
           WHEN 5 THEN 'Unknown'
           WHEN 6 THEN 'Voided trip'
           ELSE 'Unknown'
         END ;;
    description: "TLC payment_type code, decoded."
  }

  dimension: rate_code {
    type: string
    # ratecode_id is FLOAT64 in BigQuery, so compare against float literals.
    sql: CASE ${TABLE}.ratecode_id
           WHEN 1.0  THEN 'Standard rate'
           WHEN 2.0  THEN 'JFK'
           WHEN 3.0  THEN 'Newark'
           WHEN 4.0  THEN 'Nassau or Westchester'
           WHEN 5.0  THEN 'Negotiated fare'
           WHEN 6.0  THEN 'Group ride'
           WHEN 99.0 THEN 'Unknown'
           ELSE 'Unknown'
         END ;;
    description: "TLC RatecodeID, decoded."
  }

  dimension: store_and_fwd_flag {
    type: yesno
    sql: ${TABLE}.store_and_fwd_flag = 'Y' ;;
    description: "Trip was held in vehicle memory before transmission (no live connection to the server)."
  }

  dimension: passenger_count {
    type: number
    sql: ${TABLE}.passenger_count ;;
  }

  dimension: trip_distance {
    type: number
    value_format_name: miles
    sql: ${TABLE}.trip_distance ;;
    description: "Meter-reported distance in miles."
  }

  dimension: trip_distance_tier {
    type: tier
    tiers: [0, 1, 2, 5, 10, 20]
    style: integer
    sql: ${trip_distance} ;;
    description: "Distance buckets in miles."
  }

  # ---------------------------------------------------------------
  # Money. The fare components are hidden and surfaced through
  # measures — row-level currency columns clutter the field picker
  # without being much use on their own.
  #
  # total_amount is the exception and stays visible: it is the single
  # headline per-trip value, and it appears in the `detail` drill set
  # below where a user clicking into a measure expects to see it.
  # ---------------------------------------------------------------

  dimension: total_amount {
    type: number
    value_format_name: usd
    sql: ${TABLE}.total_amount ;;
    description: "Total charged to the passenger, including surcharges and tip."
  }

  dimension: fare_amount {
    type: number
    hidden: yes
    sql: ${TABLE}.fare_amount ;;
  }

  dimension: tip_amount {
    type: number
    hidden: yes
    sql: ${TABLE}.tip_amount ;;
  }

  dimension: tolls_amount {
    type: number
    hidden: yes
    sql: ${TABLE}.tolls_amount ;;
  }

  dimension: extra {
    type: number
    hidden: yes
    sql: ${TABLE}.extra ;;
  }

  dimension: mta_tax {
    type: number
    hidden: yes
    sql: ${TABLE}.mta_tax ;;
  }

  dimension: improvement_surcharge {
    type: number
    hidden: yes
    sql: ${TABLE}.improvement_surcharge ;;
  }

  dimension: congestion_surcharge {
    type: number
    hidden: yes
    sql: ${TABLE}.congestion_surcharge ;;
  }

  dimension: airport_fee {
    type: number
    hidden: yes
    sql: ${TABLE}.airport_fee ;;
  }

  # ---------------------------------------------------------------
  # Measures
  # ---------------------------------------------------------------

  measure: trip_count {
    type: count
    description: "Number of trips."
    drill_fields: [detail*]
  }

  measure: total_revenue {
    type: sum
    sql: ${total_amount} ;;
    value_format_name: usd
    description: "Sum of total_amount."
    drill_fields: [detail*]
  }

  measure: average_fare {
    type: average
    sql: ${total_amount} ;;
    value_format_name: usd
    description: "Average total_amount per trip."
  }

  measure: total_fare {
    type: sum
    sql: ${fare_amount} ;;
    value_format_name: usd
    description: "Sum of the metered fare, excluding tips, tolls and surcharges."
  }

  measure: total_tips {
    type: sum
    sql: ${tip_amount} ;;
    value_format_name: usd
  }

  measure: average_tip {
    type: average
    sql: ${tip_amount} ;;
    value_format_name: usd
  }

  measure: tip_rate {
    type: number
    # SAFE_DIVIDE avoids a divide-by-zero when every trip in the group is
    # a $0 fare (voided trips and disputes both occur in the raw data).
    sql: SAFE_DIVIDE(${total_tips}, ${total_fare}) ;;
    value_format_name: percent_1
    description: "Total tips as a share of total metered fare. Cash tips are not recorded by TLC, so this understates true tipping."
  }

  measure: total_distance {
    type: sum
    sql: ${trip_distance} ;;
    value_format_name: miles
  }

  measure: average_distance {
    type: average
    sql: ${trip_distance} ;;
    value_format_name: miles
  }

  measure: average_duration_minutes {
    type: average
    sql: ${trip_duration_minutes} ;;
    value_format_name: minutes
  }

  measure: average_speed_mph {
    type: number
    sql: SAFE_DIVIDE(SUM(${trip_distance}), SUM(${trip_duration_minutes}) / 60.0) ;;
    value_format_name: mph
    description: "Total distance divided by total duration. Aggregate ratio, not the mean of per-trip speeds."
  }

  measure: total_passengers {
    type: sum
    sql: ${passenger_count} ;;
    value_format_name: decimal_0
  }

  measure: average_passengers {
    type: average
    sql: ${passenger_count} ;;
    value_format_name: decimal_2
  }

  measure: pickup_zone_count {
    type: count_distinct
    sql: ${pickup_location_id} ;;
    description: "Distinct pickup zones represented in the current result set."
  }

  # ---------------------------------------------------------------
  # Drill set — what a user sees when clicking into a measure.
  # ---------------------------------------------------------------

  set: detail {
    fields: [
      trip_id,
      pickup_time,
      dropoff_time,
      vendor,
      pickup_location.zone,
      dropoff_location.zone,
      trip_distance,
      trip_duration_minutes,
      payment_type,
      total_amount
    ]
  }
}
