"""Open, submit, pay, and refund bounties."""

from tests.direct.conftest import (
    CONTRACT_PATH,
    FAR_DEADLINE,
    ONE_GEN,
    mock_criteria_llm,
    mock_tweet,
    register_handle,
    to_hex,
)


def _open(
    vm,
    contract,
    sender,
    amount=ONE_GEN,
    deadline=FAR_DEADLINE,
    min_chars=1,
    criteria="",
):
    vm.sender = sender
    vm.deal(sender, amount * 2)
    vm.value = amount
    contract.open_bounty(
        "mrbeast",
        "https://x.com/fan/status/100",
        deadline,
        min_chars,
        criteria,
    )
    vm.value = 0


def test_open_bounty(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "11", to_hex(direct_bob))

    _open(direct_vm, contract, direct_alice)

    bounty = contract.get_bounty("1")
    assert bounty["exists"] is True
    assert bounty["status"] == "open"
    assert bounty["target_handle"] == "mrbeast"
    assert bounty["beneficiary"] == to_hex(direct_bob)
    assert bounty["tweet_id"] == "100"
    assert bounty["criteria"] == ""
    assert bounty["amount"] == ONE_GEN
    assert bounty["requester"] == to_hex(direct_alice)
    assert contract.get_bounty_ids() == ["1"]
    assert contract.get_handle_bounties("mrbeast") == ["1"]


def test_open_bounty_rejects_unregistered_handle(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    direct_vm.deal(direct_alice, ONE_GEN * 2)
    direct_vm.value = ONE_GEN
    with direct_vm.expect_revert("[EXPECTED] Target handle is not registered"):
        contract.open_bounty(
            "unregistered_user",
            "https://x.com/fan/status/100",
            FAR_DEADLINE,
            1,
            "",
        )


def test_open_bounty_rejects_zero(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "11", to_hex(direct_bob))

    direct_vm.sender = direct_alice
    direct_vm.value = 0
    with direct_vm.expect_revert("[EXPECTED] Bounty amount must be greater than 0"):
        contract.open_bounty(
            "mrbeast",
            "https://x.com/fan/status/100",
            FAR_DEADLINE,
            1,
            "",
        )


def test_submit_reply_pays_registered_owner(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT_PATH)
    bob = to_hex(direct_bob)

    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "11", bob)

    _open(direct_vm, contract, direct_alice)
    mock_tweet(
        direct_vm,
        "200",
        "mrbeast",
        "Nice build",
        reply_to="100",
    )

    # Anyone can submit the public proof.
    direct_vm.sender = direct_alice
    contract.submit_reply("1", "https://x.com/mrbeast/status/200")

    bounty = contract.get_bounty("1")
    assert bounty["status"] == "paid"
    assert bounty["reply_id"] == "200"
    assert bounty["paid_to"] == bob


def test_submit_rejects_wrong_author(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "11", to_hex(direct_bob))
    _open(direct_vm, contract, direct_alice)
    mock_tweet(direct_vm, "200", "elonmusk", "hi", reply_to="100")

    with direct_vm.expect_revert("[EXPECTED] Reply is not from the target handle"):
        contract.submit_reply("1", "https://x.com/elonmusk/status/200")


def test_submit_rejects_non_reply(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "11", to_hex(direct_bob))
    _open(direct_vm, contract, direct_alice)
    mock_tweet(direct_vm, "200", "mrbeast", "unrelated post", reply_to="")

    with direct_vm.expect_revert(
        "[EXPECTED] Tweet is not a reply to the bounty tweet"
    ):
        contract.submit_reply("1", "https://x.com/mrbeast/status/200")


def test_submit_requires_registration(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    direct_vm.deal(direct_alice, ONE_GEN * 2)
    direct_vm.value = ONE_GEN
    with direct_vm.expect_revert("[EXPECTED] Target handle is not registered"):
        contract.open_bounty(
            "unregistered_user",
            "https://x.com/fan/status/100",
            FAR_DEADLINE,
            1,
            "",
        )


def test_submit_already_paid_fails(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "11", to_hex(direct_bob))
    _open(direct_vm, contract, direct_alice)
    mock_tweet(direct_vm, "200", "mrbeast", "Nice", reply_to="100")
    contract.submit_reply("1", "https://x.com/mrbeast/status/200")

    with direct_vm.expect_revert("[EXPECTED] Bounty is not open"):
        contract.submit_reply("1", "https://x.com/mrbeast/status/200")


def test_refund_after_deadline(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "11", to_hex(direct_bob))

    direct_vm.warp("2024-01-01T00:00:00Z")
    _open(direct_vm, contract, direct_alice, deadline=1706745600)  # 2024-02-01
    direct_vm.warp("2024-03-01T00:00:00Z")

    contract.refund("1")
    assert contract.get_bounty("1")["status"] == "refunded"


def test_refund_before_deadline_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "11", to_hex(direct_bob))

    _open(direct_vm, contract, direct_alice)
    with direct_vm.expect_revert("[EXPECTED] Bounty has not expired"):
        contract.refund("1")


def test_criteria_reply_pays(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "11", to_hex(direct_bob))
    _open(
        direct_vm,
        contract,
        direct_alice,
        criteria="Answer the technical question with a real explanation.",
    )
    mock_tweet(direct_vm, "100", "fan", "How does optimistic consensus work?")
    mock_tweet(
        direct_vm,
        "200",
        "mrbeast",
        "Optimistic consensus lets a leader propose, then validators independently re-run the task and vote.",
        reply_to="100",
    )
    mock_criteria_llm(direct_vm, meets=True, reasoning="Explains the mechanism.")

    contract.submit_reply("1", "https://x.com/mrbeast/status/200")
    bounty = contract.get_bounty("1")
    assert bounty["status"] == "paid"
    assert bounty["verdict_note"] == "Explains the mechanism."


def test_criteria_rejects_spam_reply(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "11", to_hex(direct_bob))
    _open(
        direct_vm,
        contract,
        direct_alice,
        criteria="Provide genuine product feedback.",
    )
    mock_tweet(direct_vm, "100", "fan", "What did you think of the launch?")
    mock_tweet(direct_vm, "200", "mrbeast", "asdfghjkl123", reply_to="100")
    mock_criteria_llm(direct_vm, meets=False, reasoning="Spam, not feedback.")

    with direct_vm.expect_revert("[EXPECTED] Reply does not meet bounty criteria"):
        contract.submit_reply("1", "https://x.com/mrbeast/status/200")
    assert contract.get_bounty("1")["status"] == "open"


def test_only_requester_can_refund(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "11", to_hex(direct_bob))

    direct_vm.warp("2024-01-01T00:00:00Z")
    _open(direct_vm, contract, direct_alice, deadline=1706745600)
    direct_vm.warp("2024-03-01T00:00:00Z")
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("[EXPECTED] Only the requester can refund"):
        contract.refund("1")


def test_rebind_does_not_redirect_existing_bounty(
    direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie
):
    """If handle is rebound after a bounty is opened, the bounty still pays the original beneficiary."""
    contract = direct_deploy(CONTRACT_PATH)
    bob = to_hex(direct_bob)
    charlie = to_hex(direct_charlie)

    # 1. Bob registers mrbeast with proof 11
    direct_vm.sender = direct_bob
    register_handle(direct_vm, contract, "mrbeast", "11", bob)

    # 2. Alice opens bounty #1 targeting mrbeast (beneficiary is locked as Bob)
    _open(direct_vm, contract, direct_alice)

    # 3. Later, Charlie legitimately re-binds mrbeast with fresh proof 22
    direct_vm.clear_mocks()
    direct_vm.sender = direct_charlie
    register_handle(direct_vm, contract, "mrbeast", "22", charlie)
    assert contract.get_handle("mrbeast")["owner"] == charlie

    # 4. Valid reply is submitted for bounty #1
    mock_tweet(
        direct_vm,
        "200",
        "mrbeast",
        "Replying to the original bounty",
        reply_to="100",
    )
    direct_vm.sender = direct_alice
    contract.submit_reply("1", "https://x.com/mrbeast/status/200")

    # Bounty must pay the original beneficiary (Bob), NOT the new owner (Charlie)
    bounty = contract.get_bounty("1")
    assert bounty["status"] == "paid"
    assert bounty["paid_to"] == bob
    assert bounty["beneficiary"] == bob
