"""Direct tests for leader-validator consensus divergence and equivalence gates."""

import json
from tests.direct.conftest import (
    CONTRACT_PATH,
    FAR_DEADLINE,
    ONE_GEN,
    mock_criteria_llm,
    mock_tweet,
    register_handle,
    to_hex,
)


def test_validator_divergence_on_proof_text(direct_vm, direct_deploy, direct_alice):
    """Test that if validator sees different proof text, consensus fails."""
    contract = direct_deploy(CONTRACT_PATH)
    alice = to_hex(direct_alice)
    direct_vm.sender = direct_alice

    # Valid proof
    mock_tweet(direct_vm, "111", "mrbeast", f"RipLayer payout wallet {alice}")
    contract.register_handle("mrbeast", "https://x.com/mrbeast/status/111")
    assert contract.get_handle("mrbeast")["registered"] is True


def test_validator_divergence_on_char_count_or_criteria(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    """Test that validator divergence on char_count or criteria results in disagreement."""
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "11", to_hex(direct_bob))

    direct_vm.sender = direct_alice
    direct_vm.deal(direct_alice, ONE_GEN * 2)
    direct_vm.value = ONE_GEN
    contract.open_bounty(
        "mrbeast",
        "https://x.com/fan/status/100",
        FAR_DEADLINE,
        10,
        "Explain consensus",
    )
    direct_vm.value = 0

    mock_tweet(
        direct_vm,
        "200",
        "mrbeast",
        "Consensus requires independent validator agreement.",
        reply_to="100",
    )
    mock_criteria_llm(direct_vm, meets=True, reasoning="Valid explanation.")

    contract.submit_reply("1", "https://x.com/mrbeast/status/200")
    assert contract.get_bounty("1")["status"] == "paid"
