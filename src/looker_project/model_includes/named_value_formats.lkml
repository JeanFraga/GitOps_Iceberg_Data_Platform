####################################################################
# Reusable value formats.
#
# Defined once here so unit rendering is consistent across every
# measure rather than repeated as inline value_format strings.
#
# Currency is NOT defined here on purpose: Looker ships built-in
# `usd` and `usd_0` formats, and declaring a named_value_format with a
# built-in's name shadows it. The measures reference the built-ins
# directly; only units Looker has no built-in for live below.
####################################################################

named_value_format: miles {
  value_format: "#,##0.00\" mi\""
}

named_value_format: minutes {
  value_format: "#,##0.0\" min\""
}

named_value_format: mph {
  value_format: "#,##0.0\" mph\""
}
