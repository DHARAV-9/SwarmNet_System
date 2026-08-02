import configparser
import os

# Locate config.ini relative to the project root (two levels up from this file)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir))
_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config.ini")

_cfg = configparser.ConfigParser()
if not os.path.exists(_CONFIG_PATH):
    raise FileNotFoundError(f"config.ini not found at {_CONFIG_PATH}")
_cfg.read(_CONFIG_PATH)

# [NETWORK]

BASE_PORT: int = _cfg.getint("NETWORK", "BASE_PORT")
BASE_PORT = int(os.environ.get("SWARMNET_BASE_PORT", BASE_PORT))
DASHBOARD_PORT: int = _cfg.getint("NETWORK", "DASHBOARD_PORT")
RPC_TIMEOUT_MS: int = _cfg.getint("NETWORK", "RPC_TIMEOUT_MS")
PACKET_LOSS_RATE: float = _cfg.getfloat("NETWORK", "PACKET_LOSS_RATE")

# [RAFT]

HEARTBEAT_INTERVAL_MS: int = _cfg.getint("RAFT", "HEARTBEAT_INTERVAL_MS")
ELECTION_TIMEOUT_MIN_MS: int = _cfg.getint("RAFT", "ELECTION_TIMEOUT_MIN_MS")
ELECTION_TIMEOUT_MAX_MS: int = _cfg.getint("RAFT", "ELECTION_TIMEOUT_MAX_MS")

# [GOSSIP]

GOSSIP_INTERVAL_MS: int = _cfg.getint("GOSSIP", "GOSSIP_INTERVAL_MS")
GOSSIP_FANOUT: int = _cfg.getint("GOSSIP", "GOSSIP_FANOUT")

# [FLOCKING]

NEIGHBOR_RADIUS: float = _cfg.getfloat("FLOCKING", "NEIGHBOR_RADIUS")
MIN_SEP_DIST: float = _cfg.getfloat("FLOCKING", "MIN_SEP_DIST")
MAX_SPEED: float = _cfg.getfloat("FLOCKING", "MAX_SPEED")
W_SEP: float = _cfg.getfloat("FLOCKING", "W_SEP")
W_ALI: float = _cfg.getfloat("FLOCKING", "W_ALI")
W_COH: float = _cfg.getfloat("FLOCKING", "W_COH")
W_WAY: float = _cfg.getfloat("FLOCKING", "W_WAY")
FLOCKING_TICK_MS: int = _cfg.getint("FLOCKING", "FLOCKING_TICK_MS")

# [SIMULATION]

WORLD_WIDTH: int = _cfg.getint("SIMULATION", "WORLD_WIDTH")
WORLD_HEIGHT: int = _cfg.getint("SIMULATION", "WORLD_HEIGHT")
BATTERY_DRAIN_RATE: float = _cfg.getfloat("SIMULATION", "BATTERY_DRAIN_RATE")
FPS: int = _cfg.getint("SIMULATION", "FPS")
DEFAULT_N: int = _cfg.getint("SIMULATION", "DEFAULT_N")

# [TASKS]

BID_WINDOW_MS: int = _cfg.getint("TASKS", "BID_WINDOW_MS")
TASK_FAILURE_TIMEOUT_MS: int = _cfg.getint("TASKS", "FAILURE_TIMEOUT_MS")

# [METRICS]

METRICS_DIR: str = _cfg.get("METRICS", "METRICS_DIR")
EXPORT_CSV: bool = _cfg.getboolean("METRICS", "EXPORT_CSV")
LOG_LEVEL: str = _cfg.get("METRICS", "LOG_LEVEL")
