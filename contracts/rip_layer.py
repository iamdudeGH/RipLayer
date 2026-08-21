# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from genlayer import *


ERROR_EXPECTED = "[EXPECTED]"
ERROR_EXTERNAL = "[EXTERNAL]"
ERROR_TRANSIENT = "[TRANSIENT]"
ERROR_LLM = "[LLM_ERROR]"

MAX_HANDLE_LEN = 40
MAX_URL_LEN = 500
MAX_TEXT_LEN = 4000
MIN_BOUNTY_WEI = 1


@gl.evm.contract_interface
class _Recipient:
    class View:
        pass

    class Write:
        pass


@allow_storage
@dataclass
class HandleBinding:
    handle: str
    owner: Address
    proof_url: str
    tweet_id: str


@allow_storage
@dataclass
class Bounty:
    id: str
    requester: Address
    target_handle: str
    tweet_url: str
    tweet_id: str
    amount: u256
    deadline: u256
    min_chars: u256
    status: str
    reply_url: str
    reply_id: str
    paid_to: Address


def _user_error(prefix: str, message: str):
    raise gl.vm.UserError(f"{prefix} {message}")


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _error_message(err) -> str:
    if hasattr(err, "message") and err.message:
        return str(err.message)
    if hasattr(err, "data") and err.data is not None:
        return str(err.data)
    return str(err)


def _handle_leader_error(leaders_res, leader_fn) -> bool:
    leader_msg = _error_message(leaders_res)
    try:
        leader_fn()
        return False
    except gl.vm.UserError as exc:
        validator_msg = _error_message(exc)
        if validator_msg.startswith(ERROR_EXPECTED) or validator_msg.startswith(
            ERROR_EXTERNAL
        ):
            return validator_msg == leader_msg
        if validator_msg.startswith(ERROR_TRANSIENT) and leader_msg.startswith(
            ERROR_TRANSIENT
        ):
            return True
        return False
    except Exception:
        return False


def _norm_handle(handle: str) -> str:
    value = handle.strip()
    if value.startswith("@"):
        value = value[1:]
    return value.lower()


def _tweet_id_from_url(url: str) -> str:
    path = url.strip().split("?")[0].split("#")[0].rstrip("/")
    parts = path.split("/")
    for index, part in enumerate(parts):
        if part == "status" and index + 1 < len(parts):
            tweet_id = parts[index + 1]
            if tweet_id.isdigit():
                return tweet_id
    last = parts[-1] if parts else ""
    if last.isdigit():
        return last
    _user_error(ERROR_EXPECTED, "Could not parse tweet id from url")
    return ""


def _response_status(res) -> int:
    if hasattr(res, "status"):
        return int(res.status)
    if hasattr(res, "status_code"):
        return int(res.status_code)
    return 200


def _response_body(res) -> str:
    body = getattr(res, "body", res)
    if isinstance(body, bytes):
        return body.decode("utf-8")
    return str(body)


def _fetch_tweet(tweet_id: str) -> dict:
    url = "https://api.fxtwitter.com/status/" + tweet_id
    try:
        res = gl.nondet.web.get(url)
    except Exception as exc:
        _user_error(ERROR_TRANSIENT, f"Tweet lookup failed: {exc}")

    status = _response_status(res)
    if status >= 500:
        _user_error(ERROR_TRANSIENT, f"Tweet API unavailable: {status}")
    if status == 404:
        _user_error(ERROR_EXTERNAL, "Tweet not found")
    if status >= 400:
        _user_error(ERROR_EXTERNAL, f"Tweet API returned {status}")

    try:
        data = json.loads(_response_body(res))
    except Exception as exc:
        _user_error(ERROR_EXTERNAL, f"Tweet API returned invalid JSON: {exc}")

    if not isinstance(data, dict):
        _user_error(ERROR_EXTERNAL, "Tweet API returned a non-object")

    code = data.get("code", status)
    try:
        code_n = int(code)
    except (TypeError, ValueError):
        code_n = status
    if code_n == 404:
        _user_error(ERROR_EXTERNAL, "Tweet not found")
    if code_n >= 500:
        _user_error(ERROR_TRANSIENT, f"Tweet API unavailable: {code_n}")
    if code_n >= 400:
        _user_error(ERROR_EXTERNAL, f"Tweet API returned {code_n}")

    tweet = data.get("tweet") or data.get("status") or data
    if not isinstance(tweet, dict):
        _user_error(ERROR_EXTERNAL, "Tweet payload missing")

    author = tweet.get("author") or tweet.get("user") or {}
    if not isinstance(author, dict):
        author = {}
    handle = (
        author.get("screen_name")
        or author.get("username")
        or author.get("handle")
        or tweet.get("screen_name")
        or ""
    )
    fetched_id = str(tweet.get("id") or tweet.get("id_str") or tweet_id)
    reply_to = (
        tweet.get("replying_to_status")
        or tweet.get("in_reply_to_status_id")
        or tweet.get("in_reply_to_status_id_str")
        or ""
    )
    if isinstance(reply_to, dict):
        reply_to = reply_to.get("id") or reply_to.get("status") or ""
    text = tweet.get("text") or tweet.get("full_text") or ""

    author_norm = _norm_handle(str(handle))
    if author_norm == "":
        _user_error(ERROR_EXTERNAL, "Tweet has no author handle")
    if fetched_id == "":
        _user_error(ERROR_EXTERNAL, "Tweet has no id")

    return {
        "author": author_norm,
        "tweet_id": str(fetched_id),
        "reply_to_id": str(reply_to) if reply_to else "",
        "text": str(text)[:MAX_TEXT_LEN],
        "char_count": len(str(text).strip()),
    }


class RipLayer(gl.Contract):
    handles: TreeMap[str, HandleBinding]
    bounties: TreeMap[str, Bounty]
    bounty_ids: DynArray[str]
    handle_bounty_ids: TreeMap[str, str]
    bounty_count: u256

    def __init__(self):
        self.bounty_count = u256(0)

    def _require(self, value: str, field: str) -> str:
        trimmed = value.strip()
        if trimmed == "":
            _user_error(ERROR_EXPECTED, f"{field} is required")
        return trimmed

    def _require_handle(self, handle: str) -> str:
        norm = _norm_handle(self._require(handle, "handle"))
        if norm == "":
            _user_error(ERROR_EXPECTED, "handle is required")
        if len(norm) > MAX_HANDLE_LEN:
            _user_error(ERROR_EXPECTED, "handle is too long")
        return norm

    def _require_url(self, url: str, field: str) -> str:
        value = self._require(url, field)
        if len(value) > MAX_URL_LEN:
            _user_error(ERROR_EXPECTED, f"{field} is too long")
        if not (
            value.startswith("https://") or value.startswith("http://")
        ):
            _user_error(ERROR_EXPECTED, f"{field} must be an http(s) url")
        return value

    def _pay(self, to: Address, amount: u256) -> None:
        _Recipient(to).emit_transfer(value=amount)

    def _append_handle_bounty(self, handle: str, bounty_id: str) -> None:
        raw = self.handle_bounty_ids.get(handle, "[]")
        try:
            ids = json.loads(raw)
        except Exception:
            ids = []
        if not isinstance(ids, list):
            ids = []
        ids.append(bounty_id)
        self.handle_bounty_ids[handle] = json.dumps(ids)

    def _handle_bounty_list(self, handle: str) -> list:
        raw = self.handle_bounty_ids.get(handle, "[]")
        try:
            ids = json.loads(raw)
        except Exception:
            return []
        if not isinstance(ids, list):
            return []
        return [str(item) for item in ids]

    def _binding_view(self, binding: HandleBinding) -> dict:
        return {
            "handle": binding.handle,
            "owner": binding.owner.as_hex,
            "proof_url": binding.proof_url,
            "tweet_id": binding.tweet_id,
            "registered": True,
        }

    def _bounty_view(self, bounty: Bounty) -> dict:
        return {
            "id": bounty.id,
            "requester": bounty.requester.as_hex,
            "target_handle": bounty.target_handle,
            "tweet_url": bounty.tweet_url,
            "tweet_id": bounty.tweet_id,
            "amount": int(bounty.amount),
            "deadline": int(bounty.deadline),
            "min_chars": int(bounty.min_chars),
            "status": bounty.status,
            "reply_url": bounty.reply_url,
            "reply_id": bounty.reply_id,
            "paid_to": bounty.paid_to.as_hex,
            "exists": True,
        }

    def _run_tweet_fetch(self, tweet_id: str) -> dict:
        def leader_fn():
            return _fetch_tweet(tweet_id)

        def validator_fn(leaders_res: gl.vm.Result) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                return _handle_leader_error(leaders_res, leader_fn)
            leader = leaders_res.calldata
            if not isinstance(leader, dict):
                return False
            mine = leader_fn()
            return (
                mine.get("author") == leader.get("author")
                and mine.get("tweet_id") == leader.get("tweet_id")
                and mine.get("reply_to_id") == leader.get("reply_to_id")
            )

        return gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

    @gl.public.write
    def register_handle(self, handle: str, proof_url: str) -> None:
        handle = self._require_handle(handle)
        proof_url = self._require_url(proof_url, "proof_url")
        tweet_id = _tweet_id_from_url(proof_url)
        sender = gl.message.sender_address
        marker = sender.as_hex.lower()

        tweet = self._run_tweet_fetch(tweet_id)
        author = str(tweet.get("author", ""))
        text = str(tweet.get("text", "")).lower()
        if author != handle:
            _user_error(
                ERROR_EXPECTED,
                "Proof tweet is not from the claimed handle",
            )
        if marker not in text and marker[2:] not in text:
            _user_error(
                ERROR_EXPECTED,
                "Proof tweet must contain your wallet address",
            )

        self.handles[handle] = HandleBinding(
            handle=handle,
            owner=sender,
            proof_url=proof_url,
            tweet_id=str(tweet.get("tweet_id", tweet_id)),
        )

    @gl.public.write.payable
    def open_bounty(
        self,
        target_handle: str,
        tweet_url: str,
        deadline: int,
        min_chars: int,
    ) -> None:
        handle = self._require_handle(target_handle)
        tweet_url = self._require_url(tweet_url, "tweet_url")
        tweet_id = _tweet_id_from_url(tweet_url)
        amount = gl.message.value
        if int(amount) < MIN_BOUNTY_WEI:
            _user_error(ERROR_EXPECTED, "Bounty amount must be greater than 0")
        if int(deadline) <= _now():
            _user_error(ERROR_EXPECTED, "Deadline must be in the future")
        if int(min_chars) < 1:
            _user_error(ERROR_EXPECTED, "min_chars must be at least 1")
        if int(min_chars) > MAX_TEXT_LEN:
            _user_error(ERROR_EXPECTED, "min_chars is too large")

        next_id = int(self.bounty_count) + 1
        bounty_id = str(next_id)
        self.bounty_count = u256(next_id)
        self.bounties[bounty_id] = Bounty(
            id=bounty_id,
            requester=gl.message.sender_address,
            target_handle=handle,
            tweet_url=tweet_url,
            tweet_id=tweet_id,
            amount=amount,
            deadline=u256(int(deadline)),
            min_chars=u256(int(min_chars)),
            status="open",
            reply_url="",
            reply_id="",
            paid_to=Address("0x0000000000000000000000000000000000000000"),
        )
        self.bounty_ids.append(bounty_id)
        self._append_handle_bounty(handle, bounty_id)

    @gl.public.write
    def submit_reply(self, bounty_id: str, reply_url: str) -> None:
        bounty_id = self._require(bounty_id, "bounty_id")
        if bounty_id not in self.bounties:
            _user_error(ERROR_EXPECTED, "Bounty not found")
        bounty = self.bounties[bounty_id]
        if bounty.status != "open":
            _user_error(ERROR_EXPECTED, "Bounty is not open")
        if _now() >= int(bounty.deadline):
            _user_error(ERROR_EXPECTED, "Bounty has expired")
        if bounty.target_handle not in self.handles:
            _user_error(ERROR_EXPECTED, "Target handle is not registered")

        reply_url = self._require_url(reply_url, "reply_url")
        reply_id = _tweet_id_from_url(reply_url)
        tweet = self._run_tweet_fetch(reply_id)

        author = str(tweet.get("author", ""))
        fetched_id = str(tweet.get("tweet_id", reply_id))
        reply_to = str(tweet.get("reply_to_id", ""))
        char_count = int(tweet.get("char_count", 0))

        if author != bounty.target_handle:
            _user_error(ERROR_EXPECTED, "Reply is not from the target handle")
        if reply_to != bounty.tweet_id:
            _user_error(ERROR_EXPECTED, "Tweet is not a reply to the bounty tweet")
        if char_count < int(bounty.min_chars):
            _user_error(ERROR_EXPECTED, "Reply is shorter than min_chars")

        payee = self.handles[bounty.target_handle].owner
        amount = bounty.amount
        bounty.status = "paid"
        bounty.reply_url = reply_url
        bounty.reply_id = fetched_id
        bounty.paid_to = payee
        self._pay(payee, amount)

    @gl.public.write
    def refund(self, bounty_id: str) -> None:
        bounty_id = self._require(bounty_id, "bounty_id")
        if bounty_id not in self.bounties:
            _user_error(ERROR_EXPECTED, "Bounty not found")
        bounty = self.bounties[bounty_id]
        if gl.message.sender_address != bounty.requester:
            _user_error(ERROR_EXPECTED, "Only the requester can refund")
        if bounty.status != "open":
            _user_error(ERROR_EXPECTED, "Bounty is not open")
        if _now() < int(bounty.deadline):
            _user_error(ERROR_EXPECTED, "Bounty has not expired")
        amount = bounty.amount
        requester = bounty.requester
        bounty.status = "refunded"
        self._pay(requester, amount)

    @gl.public.view
    def get_handle(self, handle: str) -> dict:
        key = _norm_handle(handle)
        if key not in self.handles:
            return {
                "handle": key,
                "registered": False,
                "owner": "",
                "proof_url": "",
                "tweet_id": "",
            }
        return self._binding_view(self.handles[key])

    @gl.public.view
    def get_bounty(self, bounty_id: str) -> dict:
        if bounty_id not in self.bounties:
            return {"id": bounty_id, "exists": False}
        return self._bounty_view(self.bounties[bounty_id])

    @gl.public.view
    def get_bounty_ids(self) -> list:
        return [str(bounty_id) for bounty_id in self.bounty_ids]

    @gl.public.view
    def list_bounties(self) -> dict:
        result = {}
        for bounty_id in self.bounty_ids:
            result[str(bounty_id)] = self._bounty_view(self.bounties[bounty_id])
        return result

    @gl.public.view
    def get_handle_bounties(self, handle: str) -> list:
        return self._handle_bounty_list(_norm_handle(handle))

    @gl.public.view
    def get_bounty_count(self) -> int:
        return int(self.bounty_count)
