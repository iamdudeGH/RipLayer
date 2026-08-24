"""Handle registration: proof tweet must be from the handle and contain the wallet."""

from tests.direct.conftest import CONTRACT_PATH, mock_tweet, register_handle, to_hex


def test_register_handle(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    alice = to_hex(direct_alice)

    register_handle(direct_vm, contract, "mrbeast", "111", alice)

    info = contract.get_handle("MrBeast")
    assert info["registered"] is True
    assert info["handle"] == "mrbeast"
    assert info["owner"] == alice
    assert info["tweet_id"] == "111"


def test_register_rejects_wrong_author(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    alice = to_hex(direct_alice)
    mock_tweet(direct_vm, "111", "notbeast", f"wallet {alice}")

    with direct_vm.expect_revert("[EXPECTED] Proof tweet is not from the claimed handle"):
        contract.register_handle("mrbeast", "https://x.com/mrbeast/status/111")


def test_register_requires_wallet_in_tweet(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    mock_tweet(direct_vm, "111", "mrbeast", "just a normal tweet")

    with direct_vm.expect_revert(
        "[EXPECTED] Proof tweet must contain your wallet address"
    ):
        contract.register_handle("mrbeast", "https://x.com/mrbeast/status/111")


def test_reregister_moves_payout_wallet(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT_PATH)
    alice = to_hex(direct_alice)
    bob = to_hex(direct_bob)

    direct_vm.sender = direct_alice
    register_handle(direct_vm, contract, "mrbeast", "111", alice)

    direct_vm.clear_mocks()
    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "222", bob)

    assert contract.get_handle("mrbeast")["owner"] == bob


def test_register_rejects_stale_proof_replay(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT_PATH)
    alice = to_hex(direct_alice)

    direct_vm.sender = direct_alice
    register_handle(direct_vm, contract, "mrbeast", "111", alice)

    # Attempting to reuse the exact same proof tweet ID again must be rejected as stale proof replay
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert(
        "[EXPECTED] Proof tweet has already been used"
    ):
        contract.register_handle("mrbeast", "https://x.com/mrbeast/status/111")
