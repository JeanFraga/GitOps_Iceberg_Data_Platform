####################################################################
# dim_date — calendar dimension.
#
# Source: src/dbt_project/models/gold/dim_date.sql
# Grain:  one row per calendar date observed in the trip data.
#
# The dbt model already materialises year / month / day_name / quarter /
# is_weekend, so this view exposes those physical columns directly
# instead of re-deriving them with a dimension_group. That keeps the
# Gold layer the single source of calendar logic — Looker renders what
# dbt computed rather than computing a second, divergent version.
####################################################################

view: dim_date {
  sql_table_name: `@{gcp_project_id}.@{gold_dataset}.dim_date` ;;

  dimension: date_day {
    primary_key: yes
    type: date
    datatype: date
    sql: ${TABLE}.date_day ;;
    description: "Calendar date of the trip pickup."
  }

  dimension: year {
    type: number
    value_format_name: id
    sql: ${TABLE}.year ;;
  }

  dimension: quarter {
    type: number
    sql: ${TABLE}.quarter ;;
  }

  dimension: month_number {
    type: number
    sql: ${TABLE}.month ;;
    description: "Calendar month as 1-12."
  }

  dimension: month_name {
    type: string
    sql: ${TABLE}.month_name ;;
    # Without this, Looker sorts month names alphabetically (April first).
    order_by_field: month_number
  }

  dimension: day_of_month {
    type: number
    sql: ${TABLE}.day ;;
  }

  dimension: day_of_week_number {
    type: number
    sql: ${TABLE}.day_of_week ;;
    description: "BigQuery DAYOFWEEK: 1 = Sunday through 7 = Saturday."
  }

  dimension: day_name {
    type: string
    sql: ${TABLE}.day_name ;;
    order_by_field: day_of_week_number
  }

  dimension: is_weekend {
    type: yesno
    sql: ${TABLE}.is_weekend ;;
  }

  # count_distinct, not count: this view is always joined many_to_one from
  # fact_trips, where `type: count` would count trips rather than days.
  measure: day_count {
    type: count_distinct
    sql: ${date_day} ;;
    description: "Number of distinct calendar days present in the current result set."
  }
}
