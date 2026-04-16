from types import SimpleNamespace

import pytest

from app.services.external_transfer_rules import (
    map_external_transfer_to_transaction_status,
    transition_external_transfer_status,
)


def test_pending_external_transfer_maps_to_pending_transaction():
    assert map_external_transfer_to_transaction_status("pending") == "pending"


def test_approved_external_transfer_does_not_map_to_pending_transaction():
    assert map_external_transfer_to_transaction_status("approved") == "initiated"


def test_succeeded_external_transfer_maps_to_succeeded_transaction():
    assert map_external_transfer_to_transaction_status("succeeded") == "succeeded"


def test_partially_repaid_external_transfer_maps_to_succeeded_transaction():
    assert map_external_transfer_to_transaction_status("partially_repaid") == "succeeded"


def test_repaid_external_transfer_maps_to_succeeded_transaction():
    assert map_external_transfer_to_transaction_status("repaid") == "succeeded"


def test_succeeded_transfer_can_transition_to_partially_repaid_then_repaid():
    transfer = SimpleNamespace(status="succeeded")
    transition_external_transfer_status(transfer, "partially_repaid")
    assert transfer.status == "partially_repaid"
    transition_external_transfer_status(transfer, "repaid")
    assert transfer.status == "repaid"


def test_repaid_transfer_cannot_transition_back():
    transfer = SimpleNamespace(status="repaid")
    with pytest.raises(ValueError):
        transition_external_transfer_status(transfer, "succeeded")
