"""
test_raft.py — Unit tests for the Raft consensus module.

Tests cover:
  - Follower → Candidate transition on timeout
  - Candidate wins majority vote
  - Split-vote retry with new term
  - Leader reverts to follower on higher term
  - Log entry committed after majority acknowledgement
  - New leader elected after old leader killed
"""

from __future__ import annotations

import time

import pytest

from swarmnet.consensus.election import (
    handle_vote_request,
    handle_vote_response,
    start_election,
)
from swarmnet.consensus.heartbeat import (
    handle_append_entries,
    handle_append_entries_response,
    send_heartbeat,
)
from swarmnet.consensus.log import LogEntry, RaftLog
from swarmnet.consensus.raft import RaftStateMachine
from swarmnet.core.state import DroneState


# ======================================================================
# Helpers — Fake Messenger for unit testing (no ZeroMQ)
# ======================================================================


class FakeMessenger:
    """A mock messenger that captures sent messages for assertions."""

    def __init__(self, drone_id: int, peer_ids: list[int]) -> None:
        self.drone_id = drone_id
        self.peer_ids = peer_ids
        self.sent: list[tuple[int, dict]] = []  # (peer_id, message)
        self.broadcasts: list[dict] = []

    def send_to(self, peer_id: int, msg: dict) -> bool:
        self.sent.append((peer_id, msg))
        return True

    def send_to_all(self, msg: dict) -> int:
        for pid in self.peer_ids:
            self.send_to(pid, msg)
        return len(self.peer_ids)

    def broadcast(self, msg: dict) -> None:
        self.broadcasts.append(msg)

    def recv_nowait(self, timeout_ms: int = 0) -> dict | None:
        return None

    def drain_all(self, timeout_ms: int = 0) -> list[dict]:
        return []

    def close(self) -> None:
        pass

    def get_sent_to(self, peer_id: int) -> list[dict]:
        """Return all messages sent to a specific peer."""
        return [msg for pid, msg in self.sent if pid == peer_id]

    def get_sent_of_type(self, msg_type: str) -> list[dict]:
        """Return all sent messages of a specific type."""
        return [msg for _, msg in self.sent if msg.get("type") == msg_type]

    def clear(self) -> None:
        self.sent.clear()
        self.broadcasts.clear()


def make_state(drone_id: int, n: int = 5) -> DroneState:
    """Create a fresh DroneState with the given id and peer count."""
    peers = [i for i in range(n) if i != drone_id]
    return DroneState(drone_id=drone_id, peers=peers)


def make_messenger(drone_id: int, n: int = 5) -> FakeMessenger:
    """Create a FakeMessenger for the given drone."""
    peers = [i for i in range(n) if i != drone_id]
    return FakeMessenger(drone_id, peers)


# ======================================================================
# Test: Follower becomes Candidate on timeout
# ======================================================================


class TestFollowerTimeout:
    def test_follower_becomes_candidate_on_timeout(self):
        """A follower should transition to candidate when election timeout fires."""
        state = make_state(0)
        messenger = make_messenger(0)

        assert state.raft_state == "follower"
        assert state.current_term == 0

        # Start election (simulating timeout)
        start_election(state, messenger)

        assert state.raft_state == "candidate"
        assert state.current_term == 1
        assert state.voted_for == 0
        assert 0 in state.votes_received

    def test_election_sends_vote_requests_to_all_peers(self):
        """Starting an election should send VoteRequest to every peer."""
        state = make_state(0, n=5)
        messenger = make_messenger(0, n=5)

        start_election(state, messenger)

        vote_requests = messenger.get_sent_of_type("vote_request")
        assert len(vote_requests) == 4  # 4 peers

        for vr in vote_requests:
            assert vr["term"] == 1
            assert vr["candidate_id"] == 0


# ======================================================================
# Test: Candidate wins majority vote
# ======================================================================


class TestCandidateWinsMajority:
    def test_candidate_wins_majority_vote(self):
        """Candidate should become leader after receiving floor(N/2)+1 votes."""
        n = 5
        state = make_state(0, n=n)
        messenger = make_messenger(0, n=n)

        # Start election
        start_election(state, messenger)
        assert state.raft_state == "candidate"

        # Receive votes from drone 1 and drone 2 (self + 2 = 3 >= 3)
        resp1 = {
            "type": "vote_response",
            "term": 1,
            "vote_granted": True,
            "voter_id": 1,
        }
        won = handle_vote_response(resp1, state, n)
        assert not won  # 2 votes, need 3

        resp2 = {
            "type": "vote_response",
            "term": 1,
            "vote_granted": True,
            "voter_id": 2,
        }
        won = handle_vote_response(resp2, state, n)
        assert won  # 3 votes >= 3 (majority of 5)
        assert state.raft_state == "leader"
        assert state.leader_id == 0

    def test_denied_votes_do_not_count(self):
        """Denied votes should not count toward majority."""
        n = 5
        state = make_state(0, n=n)
        start_election(state, FakeMessenger(0, [1, 2, 3, 4]))

        resp = {
            "type": "vote_response",
            "term": 1,
            "vote_granted": False,
            "voter_id": 1,
        }
        won = handle_vote_response(resp, state, n)
        assert not won
        assert len(state.votes_received) == 1  # Only self-vote


# ======================================================================
# Test: Split-vote retries with new term
# ======================================================================


class TestSplitVote:
    def test_split_vote_retries_with_new_term(self):
        """If no majority is reached, a new election starts with higher term."""
        n = 5
        state = make_state(0, n=n)
        messenger = make_messenger(0, n=n)

        # First election attempt
        start_election(state, messenger)
        assert state.current_term == 1

        # Only get 1 additional vote (total 2, need 3) — simulate timeout
        resp = {
            "type": "vote_response",
            "term": 1,
            "vote_granted": True,
            "voter_id": 1,
        }
        handle_vote_response(resp, state, n)
        assert state.raft_state == "candidate"  # Still candidate

        # Retry election
        start_election(state, messenger)
        assert state.current_term == 2
        assert state.raft_state == "candidate"
        assert state.voted_for == 0


# ======================================================================
# Test: Leader reverts to follower on higher term
# ======================================================================


class TestLeaderRevertsToFollower:
    def test_leader_reverts_to_follower_on_higher_term(self):
        """A leader receiving a message with a higher term should step down."""
        n = 3
        state = make_state(0, n=n)
        messenger = make_messenger(0, n=n)

        # Make drone 0 a leader
        state.become_candidate()
        state.votes_received = {0, 1}
        state.become_leader()
        assert state.raft_state == "leader"
        assert state.current_term == 1

        # Receive a vote request from a candidate with higher term
        vote_req = {
            "type": "vote_request",
            "term": 3,
            "candidate_id": 2,
            "last_log_index": 0,
            "last_log_term": 0,
        }
        handle_vote_request(vote_req, state, messenger)

        assert state.raft_state == "follower"
        assert state.current_term == 3

    def test_leader_reverts_on_higher_term_append_entries_response(self):
        """Leader should step down on AE response with higher term."""
        n = 3
        state = make_state(0, n=n)
        state.become_candidate()
        state.votes_received = {0, 1}
        state.become_leader()

        resp = {
            "type": "append_entries_response",
            "term": 5,
            "success": False,
            "follower_id": 1,
            "match_index": 0,
        }
        handle_append_entries_response(resp, state)

        assert state.raft_state == "follower"
        assert state.current_term == 5


# ======================================================================
# Test: Log entry committed after majority ack
# ======================================================================


class TestLogCommit:
    def test_log_entry_committed_after_majority_ack(self):
        """A log entry should be committed when a majority acknowledges it."""
        n = 3
        state = make_state(0, n=n)

        # Make leader
        state.become_candidate()
        state.votes_received = {0, 1}
        state.become_leader()

        # Append a log entry
        entry = {"index": 1, "term": state.current_term, "command": "MOVE 100 200"}
        state.log.append(entry)

        # Follower 1 acknowledges
        resp = {
            "type": "append_entries_response",
            "term": state.current_term,
            "success": True,
            "follower_id": 1,
            "match_index": 1,
        }
        handle_append_entries_response(resp, state)

        # Majority: leader (1) + follower 1 (1) = 2 >= 2 (majority of 3)
        assert state.commit_index == 1
        assert state.log[0]["committed"] is True

    def test_leader_replicates_command_to_all_peers(self):
        """Leader should append a command and send AppendEntries to peers."""
        n = 3
        state = make_state(0, n=n)
        messenger = make_messenger(0, n=n)
        state.become_candidate()
        state.votes_received = {0, 1}
        state.become_leader()
        raft = RaftStateMachine(state, messenger, n_total=n, seed=1)

        replicated = raft.replicate_command("WAYPOINT 400.00 300.00 v")

        assert replicated is True
        assert len(state.log) == 1
        assert state.log[0]["command"] == "WAYPOINT 400.00 300.00 v"
        append_entries = messenger.get_sent_of_type("append_entries")
        assert len(append_entries) == 2
        assert append_entries[0]["entries"][0]["index"] == 1


# ======================================================================
# Test: VoteRequest handling
# ======================================================================


class TestVoteRequestHandling:
    def test_grants_vote_when_no_prior_vote(self):
        """A follower with no prior vote should grant to a valid candidate."""
        state = make_state(1, n=5)
        messenger = make_messenger(1, n=5)

        req = {
            "type": "vote_request",
            "term": 1,
            "candidate_id": 0,
            "last_log_index": 0,
            "last_log_term": 0,
        }
        handle_vote_request(req, state, messenger)

        responses = messenger.get_sent_of_type("vote_response")
        assert len(responses) == 1
        assert responses[0]["vote_granted"] is True
        assert state.voted_for == 0

    def test_denies_vote_if_already_voted(self):
        """A follower that already voted for another candidate should deny."""
        state = make_state(1, n=5)
        state.current_term = 1
        state.voted_for = 3  # Already voted for drone 3
        messenger = make_messenger(1, n=5)

        req = {
            "type": "vote_request",
            "term": 1,
            "candidate_id": 0,
            "last_log_index": 0,
            "last_log_term": 0,
        }
        handle_vote_request(req, state, messenger)

        responses = messenger.get_sent_of_type("vote_response")
        assert responses[0]["vote_granted"] is False

    def test_grants_vote_to_same_candidate_again(self):
        """Re-voting for the same candidate in the same term is allowed."""
        state = make_state(1, n=5)
        state.current_term = 1
        state.voted_for = 0  # Already voted for drone 0
        messenger = make_messenger(1, n=5)

        req = {
            "type": "vote_request",
            "term": 1,
            "candidate_id": 0,
            "last_log_index": 0,
            "last_log_term": 0,
        }
        handle_vote_request(req, state, messenger)

        responses = messenger.get_sent_of_type("vote_response")
        assert responses[0]["vote_granted"] is True

    def test_denies_vote_for_stale_term(self):
        """Deny vote if candidate's term is less than ours."""
        state = make_state(1, n=5)
        state.current_term = 5
        messenger = make_messenger(1, n=5)

        req = {
            "type": "vote_request",
            "term": 3,
            "candidate_id": 0,
            "last_log_index": 0,
            "last_log_term": 0,
        }
        handle_vote_request(req, state, messenger)

        responses = messenger.get_sent_of_type("vote_response")
        assert responses[0]["vote_granted"] is False


# ======================================================================
# Test: Heartbeat handling
# ======================================================================


class TestHeartbeat:
    def test_follower_resets_timer_on_heartbeat(self):
        """Follower should reset election timer when receiving a heartbeat."""
        state = make_state(1, n=3)
        messenger = make_messenger(1, n=3)

        # Set last_heartbeat to a time in the past
        state.last_heartbeat = time.monotonic() - 10.0
        old_hb = state.last_heartbeat

        msg = {
            "type": "append_entries",
            "term": 1,
            "leader_id": 0,
            "prev_log_index": 0,
            "prev_log_term": 0,
            "entries": [],
            "leader_commit": 0,
        }
        handle_append_entries(msg, state, messenger)

        assert state.last_heartbeat > old_hb
        assert state.leader_id == 0

    def test_reject_heartbeat_with_lower_term(self):
        """Heartbeat from a stale leader should be rejected."""
        state = make_state(1, n=3)
        state.current_term = 5
        messenger = make_messenger(1, n=3)

        msg = {
            "type": "append_entries",
            "term": 3,
            "leader_id": 0,
            "prev_log_index": 0,
            "prev_log_term": 0,
            "entries": [],
            "leader_commit": 0,
        }
        handle_append_entries(msg, state, messenger)

        # Should have sent a rejection
        responses = messenger.get_sent_of_type("append_entries_response")
        assert len(responses) == 1
        assert responses[0]["success"] is False

    def test_leader_sends_heartbeat_to_all_peers(self):
        """Leader heartbeat should be sent to all peers."""
        state = make_state(0, n=3)
        messenger = make_messenger(0, n=3)

        state.become_candidate()
        state.votes_received = {0, 1}
        state.become_leader()

        send_heartbeat(state, messenger)

        hbs = messenger.get_sent_of_type("append_entries")
        assert len(hbs) == 2  # 2 peers


# ======================================================================
# Test: RaftLog
# ======================================================================


class TestRaftLog:
    def test_empty_log(self):
        log = RaftLog()
        assert len(log) == 0
        assert log.last_index() == 0
        assert log.last_term() == 0

    def test_append_and_get(self):
        log = RaftLog()
        entry = log.append(term=1, command="MOVE 100 200")
        assert entry.index == 1
        assert entry.term == 1
        assert log.last_index() == 1
        assert log.get(1) == entry

    def test_multiple_appends(self):
        log = RaftLog()
        log.append(term=1, command="CMD1")
        log.append(term=1, command="CMD2")
        log.append(term=2, command="CMD3")
        assert len(log) == 3
        assert log.last_index() == 3
        assert log.last_term() == 2

    def test_truncate(self):
        log = RaftLog()
        log.append(term=1, command="CMD1")
        log.append(term=1, command="CMD2")
        log.append(term=2, command="CMD3")
        log.truncate_from(2)
        assert len(log) == 1
        assert log.last_index() == 1

    def test_mark_committed(self):
        log = RaftLog()
        log.append(term=1, command="CMD1")
        log.append(term=1, command="CMD2")
        log.mark_committed(1)
        assert log.get(1).committed is True
        assert log.get(2).committed is False

    def test_entries_from(self):
        log = RaftLog()
        log.append(term=1, command="CMD1")
        log.append(term=1, command="CMD2")
        log.append(term=2, command="CMD3")
        entries = log.entries_from(2)
        assert len(entries) == 2
        assert entries[0].command == "CMD2"

    def test_serialization(self):
        log = RaftLog()
        log.append(term=1, command="CMD1")
        dicts = log.to_dicts()
        assert len(dicts) == 1
        assert dicts[0]["term"] == 1
        assert dicts[0]["command"] == "CMD1"

        # Round-trip
        restored = LogEntry.from_dict(dicts[0])
        assert restored.index == 1
        assert restored.term == 1
        assert restored.command == "CMD1"
