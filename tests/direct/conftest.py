"""Shared helpers for RipLayer direct mode tests."""

import json
import os

from gltest.direct import loader


CONTRACT_PATH = "contracts/rip_layer.py"
FAR_DEADLINE = 2000000000
ONE_GEN = 10**18

_orig_inject = loader._inject_message_to_fd0


def _inject_message_to_fd0_windows(vm):
    """Windows cannot unlink a temp file still mapped to stdin."""
    orig_unlink = os.unlink

    def _unlink_win(path):
        try:
            orig_unlink(path)
        except PermissionError:
            pass

    os.unlink = _unlink_win
    try:
        return _orig_inject(vm)
    finally:
        os.unlink = orig_unlink


loader._inject_message_to_fd0 = _inject_message_to_fd0_windows


def to_hex(addr_bytes):
    if hasattr(addr_bytes, "as_hex"):
        return addr_bytes.as_hex
    from genlayer.py.types import Address

    return Address(addr_bytes).as_hex


def mock_tweet(vm, tweet_id, author, text, reply_to=""):
    payload = {
        "code": 200,
        "tweet": {
            "id": str(tweet_id),
            "text": text,
            "author": {"screen_name": author},
            "replying_to_status": reply_to,
        },
    }
    vm.mock_web(
        rf".*api\.fxtwitter\.com/status/{tweet_id}.*",
        {"status": 200, "body": json.dumps(payload)},
    )


def mock_criteria_llm(vm, meets=True, reasoning="Reply addresses the prompt."):
    vm.mock_llm(
        r".*Judge whether this X reply satisfies the bounty criteria.*",
        json.dumps({"meets": meets, "reasoning": reasoning}),
    )


def register_handle(vm, contract, handle, tweet_id, owner_hex):
    mock_tweet(
        vm,
        tweet_id,
        handle,
        f"RipLayer payout wallet {owner_hex}",
    )
    contract.register_handle(
        handle,
        f"https://x.com/{handle}/status/{tweet_id}",
    )
