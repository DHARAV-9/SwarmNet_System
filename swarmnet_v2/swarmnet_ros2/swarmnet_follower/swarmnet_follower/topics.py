"""ROS2-compatible per-vehicle topic names."""


def state_topic(drone_id: int) -> str:
    """Return the state topic, keeping every name token nonnumeric."""
    if isinstance(drone_id, bool) or not isinstance(drone_id, int) or drone_id < 1:
        raise ValueError("drone_id must be a positive integer")
    return f"/swarm/drone_{drone_id}/state"
