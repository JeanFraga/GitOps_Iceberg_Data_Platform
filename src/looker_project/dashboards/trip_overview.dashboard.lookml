####################################################################
# Trip Overview — the BI demo dashboard.
#
# LookML dashboards are YAML: note the leading hyphen on `- dashboard:`
# and that every element names its own model + explore.
#
# This file must be included by models/nyc_taxi.model.lkml or the
# dashboard will not appear in Development Mode or production.
#
# No default_value is set on the date filter on purpose: the TLC data is
# historical (the Composer DAG backfills one month per day), so a
# relative default like "30 days" would render every tile empty.
####################################################################

- dashboard: trip_overview
  title: "NYC Taxi — Trip Overview"
  description: "Headline volume, revenue and geography for the Gold star schema."
  layout: newspaper
  preferred_viewer: dashboards-next

  filters:
  - name: pickup_date
    title: "Pickup Date"
    type: field_filter
    default_value: ""
    allow_multiple_values: true
    required: false
    model: nyc_taxi
    explore: fact_trips
    field: fact_trips.pickup_date

  - name: pickup_borough
    title: "Pickup Borough"
    type: field_filter
    default_value: ""
    allow_multiple_values: true
    required: false
    model: nyc_taxi
    explore: fact_trips
    field: pickup_location.borough

  - name: payment_type
    title: "Payment Type"
    type: field_filter
    default_value: ""
    allow_multiple_values: true
    required: false
    model: nyc_taxi
    explore: fact_trips
    field: fact_trips.payment_type

  elements:

  # ----- KPI row -------------------------------------------------
  - name: kpi_total_trips
    title: "Total Trips"
    model: nyc_taxi
    explore: fact_trips
    type: single_value
    fields: [fact_trips.trip_count]
    listen:
      pickup_date: fact_trips.pickup_date
      pickup_borough: pickup_location.borough
      payment_type: fact_trips.payment_type
    row: 0
    col: 0
    width: 8
    height: 3

  - name: kpi_total_revenue
    title: "Total Revenue"
    model: nyc_taxi
    explore: fact_trips
    type: single_value
    fields: [fact_trips.total_revenue]
    listen:
      pickup_date: fact_trips.pickup_date
      pickup_borough: pickup_location.borough
      payment_type: fact_trips.payment_type
    row: 0
    col: 8
    width: 8
    height: 3

  - name: kpi_average_fare
    title: "Average Fare"
    model: nyc_taxi
    explore: fact_trips
    type: single_value
    fields: [fact_trips.average_fare]
    listen:
      pickup_date: fact_trips.pickup_date
      pickup_borough: pickup_location.borough
      payment_type: fact_trips.payment_type
    row: 0
    col: 16
    width: 8
    height: 3

  # ----- Trend ---------------------------------------------------
  - name: trips_over_time
    title: "Trips per Day"
    model: nyc_taxi
    explore: fact_trips
    type: looker_line
    fields: [fact_trips.pickup_date, fact_trips.trip_count]
    fill_fields: [fact_trips.pickup_date]
    sorts: [fact_trips.pickup_date]
    limit: 500
    x_axis_gridlines: false
    y_axis_gridlines: true
    show_view_names: false
    point_style: none
    interpolation: linear
    listen:
      pickup_date: fact_trips.pickup_date
      pickup_borough: pickup_location.borough
      payment_type: fact_trips.payment_type
    row: 3
    col: 0
    width: 24
    height: 7

  # ----- Time-of-day profile -------------------------------------
  - name: trips_by_hour
    title: "Trips by Hour of Day"
    model: nyc_taxi
    explore: fact_trips
    type: looker_column
    fields: [fact_trips.pickup_hour_of_day, fact_trips.trip_count]
    sorts: [fact_trips.pickup_hour_of_day]
    limit: 24
    show_view_names: false
    listen:
      pickup_date: fact_trips.pickup_date
      pickup_borough: pickup_location.borough
      payment_type: fact_trips.payment_type
    row: 10
    col: 0
    width: 12
    height: 7

  # ----- Geography -----------------------------------------------
  - name: revenue_by_borough
    title: "Revenue by Pickup Borough"
    model: nyc_taxi
    explore: fact_trips
    type: looker_bar
    fields: [pickup_location.borough, fact_trips.total_revenue]
    sorts: [fact_trips.total_revenue desc]
    limit: 10
    show_view_names: false
    listen:
      pickup_date: fact_trips.pickup_date
      pickup_borough: pickup_location.borough
      payment_type: fact_trips.payment_type
    row: 10
    col: 12
    width: 12
    height: 7

  - name: top_pickup_zones
    title: "Top 10 Pickup Zones"
    model: nyc_taxi
    explore: fact_trips
    type: looker_grid
    fields: [
      pickup_location.zone,
      pickup_location.borough,
      fact_trips.trip_count,
      fact_trips.total_revenue,
      fact_trips.average_distance,
      fact_trips.tip_rate
    ]
    sorts: [fact_trips.trip_count desc]
    limit: 10
    show_view_names: false
    listen:
      pickup_date: fact_trips.pickup_date
      pickup_borough: pickup_location.borough
      payment_type: fact_trips.payment_type
    row: 17
    col: 0
    width: 24
    height: 7
