####################################################################
# Trips Explore — the star schema wired together.
#
# Kept in its own file rather than inline in the model so that adding a
# second model (a departmental or embed-scoped one) can reuse or refine
# this Explore instead of copying it. Views are included at the model
# level, so no include: is needed here.
#
# dim_locations is joined twice via `from:`, which is why the view
# itself carries no pickup/dropoff wording — the view_label supplies it.
####################################################################

explore: fact_trips {
  label: "NYC Taxi Trips"
  description: "One row per yellow-taxi trip, joined to pickup zone, dropoff zone and calendar date."
  persist_with: nyc_taxi_default

  join: pickup_location {
    from: dim_locations
    view_label: "Pickup Zone"
    type: left_outer
    relationship: many_to_one
    sql_on: ${fact_trips.pickup_location_id} = ${pickup_location.location_id} ;;
  }

  join: dropoff_location {
    from: dim_locations
    view_label: "Dropoff Zone"
    type: left_outer
    relationship: many_to_one
    sql_on: ${fact_trips.dropoff_location_id} = ${dropoff_location.location_id} ;;
  }

  # Joined on the date timeframe of the pickup dimension_group. dim_date is
  # built from pickup datetimes in dbt, so every fact row matches exactly
  # one calendar row; left_outer is defensive rather than expected.
  join: dim_date {
    view_label: "Pickup Date"
    type: left_outer
    relationship: many_to_one
    sql_on: ${fact_trips.pickup_date} = ${dim_date.date_day} ;;
  }
}
