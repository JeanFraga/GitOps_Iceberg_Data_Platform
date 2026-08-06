####################################################################
# dim_locations — TLC Taxi Zone dimension.
#
# Source: src/dbt_project/models/gold/dim_locations.sql
# Grain:  one row per LocationID observed in the trip data.
#
# Joined TWICE into the Explore (pickup + dropoff) via `from:`, so this
# view must not hardcode any pickup/dropoff semantics in its labels.
####################################################################

view: dim_locations {
  sql_table_name: `@{gcp_project_id}.@{gold_dataset}.dim_locations` ;;

  dimension: location_id {
    primary_key: yes
    type: number
    value_format_name: id
    sql: ${TABLE}.location_id ;;
    description: "TLC Taxi Zone ID."
  }

  dimension: borough {
    type: string
    sql: ${TABLE}.borough ;;
    description: "NYC borough. NULL for IDs absent from the TLC lookup seed."
    # No map_layer_name: Looker's built-in layers key on FIPS/ISO codes and
    # TLC boroughs are plain names, so binding one here would silently fail
    # to plot. For true zone-level choropleths add a TopoJSON layer under a
    # /maps folder and reference it here.
  }

  dimension: zone {
    type: string
    sql: ${TABLE}.zone ;;
    description: "TLC zone name, e.g. 'Upper East Side North'."
  }

  dimension: service_zone {
    type: string
    sql: ${TABLE}.service_zone ;;
    description: "TLC service grouping: Yellow Zone, Boro Zone, Airports, EWR."
  }

  dimension: is_airport {
    type: yesno
    sql: ${service_zone} = 'Airports' ;;
    description: "Convenience flag for airport-trip analysis."
  }

  # count_distinct, not count: this view is always joined many_to_one from
  # fact_trips, where `type: count` would count trips rather than zones.
  measure: location_count {
    type: count_distinct
    sql: ${location_id} ;;
    description: "Number of distinct zones present in the current result set."
  }
}
