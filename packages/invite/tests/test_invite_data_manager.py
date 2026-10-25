from __future__ import annotations

from xducraft_invite.data_manager import (
    ACQUIRED,
    ALREADY_CLAIMED,
    IN_PROGRESS,
    LEASE_TTL_SECONDS,
    InviteStore,
)


def test_initialization_is_one_shot_and_persists_legacy_members(tmp_path):
    store = InviteStore(str(tmp_path / "invite.db"))

    assert store.initialize([10001, 10002], initialized_at=100, initialized_by=90001) is True
    assert store.initialize([10003], initialized_at=200, initialized_by=90001) is False

    state = store.get_state()
    assert state.initialized is True
    assert state.initialized_at == 100
    assert state.self_service_enabled is True
    assert store.is_legacy(10001) is True
    assert store.is_legacy(10003) is False


def test_claim_blocks_normal_issuance_but_force_is_audited(tmp_path):
    store = InviteStore(str(tmp_path / "invite.db"))
    store.initialize([], initialized_at=100, initialized_by=90001)

    assert store.acquire_lease(233333, source="self", operator_id=233333, now=200) == ACQUIRED
    assert store.acquire_lease(233333, source="admin", operator_id=90001, now=201) == IN_PROGRESS

    store.record_success(
        233333,
        source="self",
        group_id=123456,
        operator_id=233333,
        forced=False,
        api_generated_at="2026-08-24 12:00:00",
        issued_at=202,
    )

    assert store.has_claim(233333) is True
    assert store.acquire_lease(233333, source="admin", operator_id=90001, now=203) == ALREADY_CLAIMED
    assert store.acquire_lease(
        233333,
        source="admin",
        operator_id=90001,
        allow_claimed=True,
        now=203,
    ) == ACQUIRED

    store.record_success(
        233333,
        source="admin",
        group_id=123456,
        operator_id=90001,
        forced=True,
        api_generated_at="2026-08-24 12:01:00",
        issued_at=204,
    )

    stats = store.stats()
    assert stats.claimed_count == 1
    assert stats.issuance_count == 2


def test_stale_lease_can_be_recovered_after_process_failure(tmp_path):
    store = InviteStore(str(tmp_path / "invite.db"))

    assert store.acquire_lease(233333, source="self", operator_id=233333, now=100) == ACQUIRED
    assert store.acquire_lease(233333, source="self", operator_id=233333, now=101) == IN_PROGRESS
    assert store.acquire_lease(
        233333,
        source="self",
        operator_id=233333,
        now=100 + LEASE_TTL_SECONDS,
    ) == ACQUIRED
