"""Integration constants; wire values live in microair.protocol."""

DOMAIN = "microair_bt"
CONF_POLL_INTERVAL = "poll_interval"
CONF_ALLOW_RUNNING = "allow_running"
CONF_POLLING_ENABLED = "polling_enabled"
DEFAULT_POLL_INTERVAL = 30
MIN_POLL_INTERVAL = 15
MAX_BACKOFF = 300
# The EEPROM image (~1 KB, ~50 notification frames at MTU 23) changes only
# when the operator writes it; refresh it rarely so a marginal proxy link
# only has to carry the small ReadLive reply on every poll.
EEPROM_REFRESH_INTERVAL = 3600
SERVICE_SET_STARTUP_MODE = "set_startup_mode"
# The EasyStart reports compressor current but no line voltage, so the power
# sensor is an estimate: current x nominal voltage x power factor. Both are
# operator-tunable because they depend on the mains and the compressor.
CONF_NOMINAL_VOLTAGE = "nominal_voltage"
CONF_POWER_FACTOR = "power_factor"
DEFAULT_NOMINAL_VOLTAGE = 240.0
DEFAULT_POWER_FACTOR = 0.9
# Optional "live" mode holds one GATT connection open through a single proxy
# and reads ReadLive on a fast timer (like the OEM app), instead of the default
# connect-per-poll. It trades the reliability of the reconnect-per-read design
# for near-real-time current at the cost of monopolising the one BLE central.
CONF_LIVE_MODE = "live_mode"
CONF_LIVE_INTERVAL = "live_interval"
DEFAULT_LIVE_INTERVAL = 5
MIN_LIVE_INTERVAL = 2
