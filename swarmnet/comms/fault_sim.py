from __future__ import annotations

import logging
import random

logger = logging.getLogger(__name__)


class FaultSimulator:
    """Simulates unreliable network by randomly dropping messages.

    Attributes:
        loss_rate:       Probability in [0.0, 1.0] that any single message
                         is silently dropped.
        dropped_count:   Running total of messages dropped so far.
        sent_count:      Running total of messages that were actually sent.
        _rng:            Seeded random generator for reproducibility.
    """

    def __init__(self, loss_rate: float = 0.0, seed: int | None = None) -> None:
        if not 0.0 <= loss_rate <= 1.0:
            raise ValueError(f"loss_rate must be in [0, 1], got {loss_rate}")
        self.loss_rate = loss_rate
        self.dropped_count = 0
        self.sent_count = 0
        self._rng = random.Random(seed)

    def should_drop(self) -> bool:
        """Return ``True`` if the next message should be dropped.

        Side-effects:
            Increments ``dropped_count`` or ``sent_count`` accordingly.
        """
        if self.loss_rate <= 0.0:
            self.sent_count += 1
            return False
        if self._rng.random() < self.loss_rate:
            self.dropped_count += 1
            logger.debug(
                "FaultSim: dropped message (total dropped: %d)", self.dropped_count
            )
            return True
        self.sent_count += 1
        return False

    def set_loss_rate(self, rate: float) -> None:
        """Update the loss rate at runtime (e.g., from the dashboard)."""
        if not 0.0 <= rate <= 1.0:
            raise ValueError(f"loss_rate must be in [0, 1], got {rate}")
        self.loss_rate = rate
        logger.info("FaultSim: packet loss rate set to %.1f%%", rate * 100)
