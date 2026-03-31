from app.services.external_transfer_rules import map_external_transfer_to_transaction_status


def test_pending_external_transfer_maps_to_pending_transaction():
    assert map_external_transfer_to_transaction_status("pending") == "pending"


def test_approved_external_transfer_does_not_map_to_pending_transaction():
    assert map_external_transfer_to_transaction_status("approved") == "initiated"


def test_succeeded_external_transfer_maps_to_succeeded_transaction():
    assert map_external_transfer_to_transaction_status("succeeded") == "succeeded"
