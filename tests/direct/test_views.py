from tests.direct.conftest import (
    CONTRACT_PATH,
    FAR_DEADLINE,
    ONE_GEN,
    register_handle,
    to_hex,
)


def test_empty_registry(direct_deploy):
    contract = direct_deploy(CONTRACT_PATH)
    assert contract.list_bounties() == {}
    assert contract.get_bounty_ids() == []
    assert contract.get_bounty_count() == 0
    assert contract.get_handle("mrbeast")["registered"] is False
    assert contract.get_bounty("1")["exists"] is False


def test_list_bounties(direct_vm, direct_deploy, direct_alice, direct_bob):
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
        1,
        "",
    )
    listed = contract.list_bounties()
    assert "1" in listed
    assert listed["1"]["status"] == "open"
