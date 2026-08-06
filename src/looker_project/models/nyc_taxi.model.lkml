####################################################################
# nyc_taxi — primary model.
#
# All includes are declared here (once) rather than scattered across
# explore files, so there is a single place to see everything the model
# pulls in. Order is deliberate: shared config, then views, then the
# explores that reference those views.
####################################################################

connection: "@{connection_name}"

include: "/model_includes/*.lkml"
include: "/views/*.view.lkml"
include: "/explores/*.explore.lkml"
include: "/dashboards/*.dashboard.lookml"

label: "NYC Taxi (Gold)"

# TLC data is calendar-based; no fiscal offset applies.
week_start_day: monday
fiscal_month_offset: 0

# Default cache policy for every Explore that does not override it.
persist_with: nyc_taxi_default
