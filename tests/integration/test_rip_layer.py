"""Integration tests against a GenLayer environment.

Run with: gltest tests/integration/ -v -s

Opening a bounty is deterministic. Registration and submit_reply fetch a
live tweet JSON API, so those are marked slow.
"""

import pytest
from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def _transact(result, **kwargs):
    if hasattr(result, "transact"):
        receipt = result.transact(**kwargs)
        assert tx_execution_succeeded(receipt)
        return receipt
    assert tx_execution_succeeded(result)
    return result


def _call(result):
    if hasattr(result, "call"):
        return result.call()
    return result


@pytest.mark.integration
def test_open_bounty_and_read():
    factory = get_contract_factory("RipLayer")
    contract = factory.deploy(args=[])

    assert _call(contract.get_bounty_count(args=[])) == 0

    _transact(
        contract.open_bounty(
            args=["mrbeast", "https://x.com/fan/status/100", 2000000000, 1, ""],
            value=10**15,
        )
    )

    bounty = _call(contract.get_bounty(args=["1"]))
    assert bounty["exists"] is True
    assert bounty["status"] == "open"
    assert bounty["target_handle"] == "mrbeast"
    assert bounty["tweet_id"] == "100"
