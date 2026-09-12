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
