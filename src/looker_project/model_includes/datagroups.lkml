####################################################################
# Cache policies shared by every Explore in the project.
#
# The Composer DAG (src/composer/dags/nyc_taxi_incremental.py) loads one
# TLC month per day, so a 24-hour ceiling matches the real refresh
# cadence. The trigger query is deliberately cheap: COUNT(*) and MAX()
# over a clustered column, concatenated into a single scalar because
# sql_trigger compares one value between runs.
####################################################################

datagroup: nyc_taxi_default {
  label: "NYC Taxi daily load"
  description: "Invalidates when fact_trips gains rows or its latest pickup timestamp advances."

  sql_trigger:
    SELECT CONCAT(
      CAST(COUNT(*) AS STRING), '|',
      CAST(MAX(tpep_pickup_datetime) AS STRING)
    )
    FROM `@{gcp_project_id}.@{gold_dataset}.fact_trips` ;;

  max_cache_age: "24 hours"
}
