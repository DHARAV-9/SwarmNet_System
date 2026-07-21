"""
heartbeat.py — Raft heartbeat sender and receiver.

The leader sends empty AppendEntries RPCs (heartbeats) every
``HEARTBEAT_INTERVAL_MS`` to prevent followers from starting elections.
Followers reset their election timer on receiving a valid heartbeat.
"""

from __future__ import annotations

import logging
import time

from swarmnet.comms.messenger import Messenger
from swarmnet.core.state import DroneState

logger = logging.getLogger(__name__)


def send_heartbeat(state: DroneState, messenger: Messenger) -> None:
    """Leader broadcasts a heartbeat (empty AppendEntries) to all peers.

    Per Raft spec, the heartbeat carries the leader's term, ID, and commit
    index so followers can update their own commit state.
    """
    msg = {
        "type": "append_entries",
        "term": state.current_term,
        "leader_id": state.drone_id,
        "prev_log_index": len(state.log),
        "prev_log_term": state.log[-1]["term"] if state.log else 0,
        "entries": [],  # empty = heartbeat
        "leader_commit": state.commit_index,
    }
    sent = messenger.send_to_all(msg)
    logger.debug(
        "[DRONE %d] Heartbeat sent to %d/%d peers (term=%d)",
        state.drone_id,
        sent,
        len(state.peers),
        state.current_term,
    )


def handle_append_entries(
    msg: dict,
    state: DroneState,
    messenger: Messenger,
) -> None:
    """Process an AppendEntries RPC (heartbeat or log replication).

    Actions:
      1. If the leader's term is lower, reject.
      2. If the leader's term is >= ours, step down to follower and reset
         the election timer.
      3. For actual log entries (non-empty ``entries``), append them and
         respond with success.
    """
    leader_term = msg["term"]
    leader_id = msg["leader_id"]
    entries = msg.get("entries", [])
    leader_commit = msg.get("leader_commit", 0)

    # Reject if stale term
    if leader_term < state.current_term:
        response = {
            "type": "append_entries_response",
            "term": state.current_term,
            "success": False,
            "follower_id": state.drone_id,
            "match_index": len(state.log),
        }
        messenger.send_to(leader_id, response)
        return

    # Accept heartbeat — update our state
    if leader_term > state.current_term or state.raft_state != "follower":
        state.become_follower(leader_term)

    state.leader_id = leader_id
    state.last_heartbeat = time.monotonic()

    # --- Log replication (Phase 1: basic append) --------------------------
    if entries:
        prev_log_index = msg.get("prev_log_index", 0)
        prev_log_term = msg.get("prev_log_term", 0)

        # Consistency check: verify prev entry matches
        if prev_log_index > 0:
            if prev_log_index > len(state.log):
                # We're missing entries — reject
                response = {
                    "type": "append_entries_response",
                    "term": state.current_term,
                    "success": False,
                    "follower_id": state.drone_id,
                    "match_index": len(state.log),
                }
                messenger.send_to(leader_id, response)
                return
            existing = state.log[prev_log_index - 1]
            if existing.get("term") != prev_log_term:
                # Conflict — truncate from this point
                state.log = state.log[: prev_log_index - 1]

        # Append new entries
        for entry_dict in entries:
            idx = entry_dict["index"]
            if idx > len(state.log):
                state.log.append(entry_dict)
            else:
                # Overwrite conflicting entry
                state.log[idx - 1] = entry_dict

    # Update commit index
    if leader_commit > state.commit_index:
        state.commit_index = min(leader_commit, len(state.log))
        for entry in state.log[: state.commit_index]:
            entry["committed"] = True

    # Respond success
    response = {
        "type": "append_entries_response",
        "term": state.current_term,
        "success": True,
        "follower_id": state.drone_id,
        "match_index": len(state.log),
    }
    messenger.send_to(leader_id, response)

    if entries:
        logger.info(
            "[DRONE %d] Replicated %d entries from leader %d",
            state.drone_id,
            len(entries),
            leader_id,
        )
    else:
        logger.debug(
            "[DRONE %d] Heartbeat from leader %d (term=%d)",
            state.drone_id,
            leader_id,
            leader_term,
        )


def handle_append_entries_response(
    msg: dict,
    state: DroneState,
) -> None:
    """Leader processes an AppendEntries response from a follower.

    Updates ``next_index`` and ``match_index`` for the responding follower
    and advances ``commit_index`` when a majority have replicated.
    """
    if state.raft_state != "leader":
        return

    resp_term = msg["term"]
    follower_id = msg["follower_id"]
    success = msg["success"]
    match_index = msg.get("match_index", 0)

    if resp_term > state.current_term:
        state.become_follower(resp_term)
        return

    if success:
        state.match_index[follower_id] = match_index
        state.next_index[follower_id] = match_index + 1

        # Check if we can advance commit_index
        n_total = len(state.peers) + 1
        for idx in range(state.commit_index + 1, len(state.log) + 1):
            # Count how many nodes have this index replicated
            count = 1  # leader always has it
            for pid in state.peers:
                if state.match_index.get(pid, 0) >= idx:
                    count += 1
            if count >= (n_total // 2) + 1:
                # Only commit entries from the current term
                entry = state.log[idx - 1]
                if entry.get("term", 0) == state.current_term:
                    state.commit_index = idx
                    entry["committed"] = True
    else:
        # Decrement next_index and retry (log consistency backtracking)
        if follower_id in state.next_index:
            state.next_index[follower_id] = max(
                1, state.next_index.get(follower_id, 1) - 1
            )
