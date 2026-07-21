"""
election.py — Raft vote request / vote response handlers.

Implements the election protocol:
  1. Candidate increments term, votes for self, sends VoteRequest to all.
  2. Peers respond with VoteResponse (grant / deny).
  3. Candidate becomes leader on receiving a majority.
"""

from __future__ import annotations

import logging

from swarmnet.comms.messenger import Messenger
from swarmnet.core.state import DroneState

logger = logging.getLogger(__name__)


# ======================================================================
# Starting an election
# ======================================================================

def start_election(state: DroneState, messenger: Messenger) -> None:
    """Transition to candidate and broadcast VoteRequest to all peers.

    This is called when the election timeout fires on a follower or
    when a candidate's election timeout fires again (split-vote retry).
    """
    state.become_candidate()
    logger.info(
        "[DRONE %d] Election started, term=%d",
        state.drone_id,
        state.current_term,
    )

    vote_request = {
        "type": "vote_request",
        "term": state.current_term,
        "candidate_id": state.drone_id,
        "last_log_index": len(state.log),
        "last_log_term": state.log[-1]["term"] if state.log else 0,
    }
    messenger.send_to_all(vote_request)


# ======================================================================
# Handling an incoming VoteRequest
# ======================================================================

def handle_vote_request(
    request: dict,
    state: DroneState,
    messenger: Messenger,
) -> None:
    """Process a VoteRequest from a candidate.

    A vote is granted if:
      1. The candidate's term is >= our current term.
      2. We have not yet voted in this term (or already voted for this
         candidate).
      3. The candidate's log is at least as up-to-date as ours.

    If the candidate's term is higher than ours, we step down to follower
    for that term before evaluating the vote.
    """
    candidate_term = request["term"]
    candidate_id = request["candidate_id"]
    candidate_last_log_index = request.get("last_log_index", 0)
    candidate_last_log_term = request.get("last_log_term", 0)

    # Step down if we see a higher term
    if candidate_term > state.current_term:
        state.become_follower(candidate_term)

    grant = False
    if candidate_term >= state.current_term:
        # Check if we can vote for this candidate
        if state.voted_for is None or state.voted_for == candidate_id:
            # Log up-to-date check (§5.4.1 of Raft paper)
            our_last_log_index = len(state.log)
            our_last_log_term = state.log[-1]["term"] if state.log else 0

            if (candidate_last_log_term > our_last_log_term) or (
                candidate_last_log_term == our_last_log_term
                and candidate_last_log_index >= our_last_log_index
            ):
                grant = True
                state.voted_for = candidate_id
                state.current_term = candidate_term
                # Reset election timer when granting a vote
                import time
                state.last_heartbeat = time.monotonic()
                logger.info(
                    "[DRONE %d] Voted for drone %d in term %d",
                    state.drone_id,
                    candidate_id,
                    candidate_term,
                )

    response = {
        "type": "vote_response",
        "term": state.current_term,
        "vote_granted": grant,
        "voter_id": state.drone_id,
    }
    messenger.send_to(candidate_id, response)


# ======================================================================
# Handling an incoming VoteResponse
# ======================================================================

def handle_vote_response(
    response: dict,
    state: DroneState,
    n_total: int,
) -> bool:
    """Process a VoteResponse.  Returns ``True`` if we just won the election.

    If the response carries a higher term, we revert to follower immediately.
    Otherwise, if the vote is granted, we add it to our tally and check for
    a majority.
    """
    resp_term = response["term"]
    voter_id = response["voter_id"]
    granted = response["vote_granted"]

    # Higher term → step down
    if resp_term > state.current_term:
        state.become_follower(resp_term)
        return False

    # Only count votes if we are still a candidate for this term
    if state.raft_state != "candidate" or resp_term != state.current_term:
        return False

    if granted:
        state.votes_received.add(voter_id)
        logger.info(
            "[DRONE %d] Received vote from drone %d (%d/%d)",
            state.drone_id,
            voter_id,
            len(state.votes_received),
            (n_total // 2) + 1,
        )

        if state.has_majority(n_total):
            state.become_leader()
            logger.info(
                "[DRONE %d] *** Elected as LEADER for term=%d ***",
                state.drone_id,
                state.current_term,
            )
            return True

    return False
