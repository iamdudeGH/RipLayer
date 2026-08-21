import { FormEvent, useEffect, useMemo, useState } from "react";
import { getContractAddress, getExplorerTxUrl, getNetworkName } from "./lib/config";
import {
  ConsensusPendingError,
  connectWallet,
  openBounty,
  parseGen,
  readBounties,
  readHandle,
  readNativeBalance,
  refundBounty,
  registerHandle,
  submitReply,
  type BountyView,
  type HandleView,
  type TxPhase,
} from "./lib/genlayer";
import { proofTweetText, requireTweetUrl, tweetIntentUrl } from "./lib/tweets";
import { subscribeWallet, walletErrorMessage } from "./lib/wallet";

type Tab = "bounty" | "register" | "lookup";
type Filter = "all" | "open" | "mine" | "settled";

function phaseLabel(phase: TxPhase): string {
  switch (phase) {
    case "submitted":
      return "Submitted to Bradbury";
    case "pending":
      return "Still in consensus — Bradbury can take a few minutes";
    case "accepted":
      return "Accepted. Board will show the new state.";
    case "finalized":
      return "Finalized on-chain";
    case "failed":
      return "Execution failed";
    default:
      return "";
  }
}

function formatGen(amount: number | string | undefined): string {
  const wei = BigInt(amount ?? 0);
  const whole = wei / BigInt(10 ** 18);
  const frac = wei % BigInt(10 ** 18);
  if (frac === BigInt(0)) {
    return `${whole}`;
  }
  const fracStr = frac.toString().padStart(18, "0").replace(/0+$/, "");
  return `${whole}.${fracStr.slice(0, 4)}`;
}

function shortAddr(value?: string): string {
  if (!value || value.length < 10) {
    return value ?? "";
  }
  return `${value.slice(0, 6)}…${value.slice(-4)}`;
}

function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function defaultDeadline(): string {
  return toLocalInput(new Date(Date.now() + 7 * 24 * 60 * 60 * 1000));
}

function isExpired(value?: number | string): boolean {
  const ts = Number(value ?? 0);
  return ts > 0 && ts * 1000 <= Date.now();
}

function formatDeadline(value?: number | string): string {
  const ts = Number(value ?? 0);
  if (!ts) {
    return "No deadline";
  }
  const delta = ts * 1000 - Date.now();
  if (delta <= 0) {
    return "expired";
  }
  const hours = Math.max(1, Math.round(delta / 3_600_000));
  if (hours < 48) {
    return `${hours}h left`;
  }
  return `${Math.round(hours / 24)}d left`;
}

function sameAddress(a?: string, b?: string): boolean {
  return Boolean(a && b && a.toLowerCase() === b.toLowerCase());
}

function Mark() {
  return (
    <img
      className="mark"
      src="/logo.png"
      width={42}
      height={42}
      alt="RipLayer"
    />
  );
}

export default function App() {
  const contractAddress = getContractAddress();
  const network = getNetworkName();
  const [account, setAccount] = useState<`0x${string}` | "">("");
  const [tab, setTab] = useState<Tab>("bounty");
  const [filter, setFilter] = useState<Filter>("all");
  const [handle, setHandle] = useState("");
  const [proofUrl, setProofUrl] = useState("");
  const [targetHandle, setTargetHandle] = useState("");
  const [tweetUrl, setTweetUrl] = useState("");
  const [amount, setAmount] = useState("1");
  const [deadlineLocal, setDeadlineLocal] = useState(defaultDeadline);
  const [minChars, setMinChars] = useState("8");
  const [lookupHandle, setLookupHandle] = useState("");
  const [binding, setBinding] = useState<HandleView | null>(null);
  const [bounties, setBounties] = useState<Record<string, BountyView>>({});
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
  const [phase, setPhase] = useState<TxPhase>("idle");
  const [txHash, setTxHash] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [balance, setBalance] = useState<bigint | null>(null);

  function onPhase(next: TxPhase, hash?: string) {
    setPhase(next);
    if (hash) {
      setTxHash(hash);
    }
  }

  const list = useMemo(
    () => Object.values(bounties).reverse(),
    [bounties],
  );
  const visible = list.filter((bounty) => {
    if (filter === "open") {
      return bounty.status === "open";
    }
    if (filter === "settled") {
      return bounty.status !== "open";
    }
    if (filter === "mine") {
      return sameAddress(bounty.requester, account);
    }
    return true;
  });
  const proofText = account ? proofTweetText(account) : "";
  const openCount = list.filter((bounty) => bounty.status === "open").length;
  const locked = list
    .filter((bounty) => bounty.status === "open")
    .reduce((sum, bounty) => sum + BigInt(bounty.amount ?? 0), BigInt(0));

  async function refresh() {
    if (!contractAddress) {
      return;
    }
    setBounties(await readBounties());
    if (lookupHandle.trim()) {
      setBinding(await readHandle(lookupHandle.trim()));
    }
  }

  useEffect(() => {
    refresh().catch((err: unknown) => {
      setError(walletErrorMessage(err));
    });
  }, [contractAddress]);

  useEffect(() => {
    return subscribeWallet((next) => setAccount(next));
  }, [account]);

  useEffect(() => {
    if (!account) {
      setBalance(null);
      return;
    }
    readNativeBalance(account)
      .then(setBalance)
      .catch(() => setBalance(null));
  }, [account, phase]);

  useEffect(() => {
    if (phase !== "pending" && phase !== "accepted") {
      return;
    }
    const timer = window.setInterval(() => {
      refresh().catch(() => undefined);
    }, 8000);
    return () => window.clearInterval(timer);
  }, [phase]);

  async function onConnect() {
    setError("");
    try {
      setAccount(await connectWallet());
    } catch (err) {
      setError(walletErrorMessage(err));
    }
  }

  async function runWrite(task: () => Promise<unknown>) {
    if (!account) {
      setError("Connect a wallet first");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await task();
      await refresh();
    } catch (err) {
      if (err instanceof ConsensusPendingError) {
        setPhase("pending");
        setTxHash(err.hash);
        setError(err.message);
        return;
      }
      setPhase("failed");
      setError(walletErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function onRegister(event: FormEvent) {
    event.preventDefault();
    try {
      const url = requireTweetUrl(proofUrl, "Proof tweet");
      return runWrite(async () => {
        await registerHandle(account as `0x${string}`, handle, url, onPhase);
        setLookupHandle(handle);
        setBinding(await readHandle(handle));
      });
    } catch (err) {
      setError(walletErrorMessage(err));
    }
  }

  function onOpen(event: FormEvent) {
    event.preventDefault();
    try {
      const url = requireTweetUrl(tweetUrl, "Tweet URL");
      const deadline = deadlineLocal
        ? Math.floor(new Date(deadlineLocal).getTime() / 1000)
        : 0;
      return runWrite(() =>
        openBounty(
          account as `0x${string}`,
          {
            targetHandle,
            tweetUrl: url,
            deadline,
            minChars: Number(minChars),
            valueWei: parseGen(amount),
          },
          onPhase,
        ),
      );
    } catch (err) {
      setError(walletErrorMessage(err));
    }
  }

  async function copyProof() {
    if (!proofText) {
      return;
    }
    await navigator.clipboard.writeText(proofText);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  function setDeadlineIn(ms: number) {
    setDeadlineLocal(toLocalInput(new Date(Date.now() + ms)));
  }

  function onLookup(event: FormEvent) {
    event.preventDefault();
    setError("");
    readHandle(lookupHandle.trim())
      .then(setBinding)
      .catch((err: unknown) => {
        setError(walletErrorMessage(err));
      });
  }

  return (
    <div className="shell">
      <nav className="nav">
        <div className="brand">
          <Mark />
          <div className="wordmark">
            <strong>RIPLAYER</strong>
            <span>Adjudicated replies</span>
          </div>
        </div>
        <div className="nav-right">
          <span className="pill">{network}</span>
          {balance !== null ? (
            <span className="pill">{formatGen(balance.toString())} GEN</span>
          ) : null}
          <button className="btn btn-primary" type="button" onClick={onConnect}>
            {account ? shortAddr(account) : "Connect wallet"}
          </button>
        </div>
      </nav>

      <section className="hero">
        <div>
          <p className="kicker">Escrow for attention</p>
          <h1>
            Pay for the <em>reply.</em>
            <br />
            Settle on proof.
          </h1>
          <p className="hero-copy">
            Lock GEN on a tweet. If that X account actually replies, GenLayer
            validators fetch the post and the registered wallet gets paid.
          </p>
        </div>
        <div className="steps">
          <div className="step">
            <b>01</b>
            <p>Influencer tweets their wallet and registers the handle.</p>
          </div>
          <div className="step">
            <b>02</b>
            <p>You lock a bounty on a specific tweet and deadline.</p>
          </div>
          <div className="step">
            <b>03</b>
            <p>Anyone submits the reply URL. Validators decide. GEN moves.</p>
          </div>
        </div>
      </section>

      <section className="stats">
        <div className="stat">
          <span>Open bounties</span>
          <strong>{openCount}</strong>
        </div>
        <div className="stat">
          <span>GEN locked</span>
          <strong>{formatGen(locked.toString())}</strong>
        </div>
        <div className="stat">
          <span>Tickets</span>
          <strong>{list.length}</strong>
        </div>
      </section>

      {error ? <p className="error">{error}</p> : null}

      <div className="layout">
        <section>
          <div className="board-head">
            <h2>Live board</h2>
            <div className="filters">
              {(["all", "open", "mine", "settled"] as Filter[]).map((item) => (
                <button
                  key={item}
                  className={filter === item ? "active" : ""}
                  type="button"
                  onClick={() => setFilter(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
          <div className="tickets">
            {visible.length === 0 ? (
              <div className="empty">No tickets in this tray yet. Fund a reply on the right.</div>
            ) : (
              visible.map((bounty) => (
                <article className="ticket" key={bounty.id}>
                  <div className="ticket-top">
                    <span
                      className={`stamp ${isExpired(bounty.deadline) && bounty.status === "open" ? "expired" : bounty.status}`}
                    >
                      {isExpired(bounty.deadline) && bounty.status === "open"
                        ? "expired"
                        : bounty.status}
                    </span>
                    <div className="amount">{formatGen(bounty.amount)} GEN</div>
                  </div>
                  <div className="handle">@{bounty.target_handle}</div>
                  <div className="mono">
                    #{bounty.id} · {formatDeadline(bounty.deadline)}
                    {sameAddress(bounty.requester, account) ? " · yours" : ""}
                  </div>
                  {bounty.tweet_url ? (
                    <a href={bounty.tweet_url} target="_blank" rel="noreferrer">
                      {bounty.tweet_url}
                    </a>
                  ) : null}
                  {bounty.status === "open" ? (
                    <div className="ticket-actions">
                      <input
                        value={replyDrafts[bounty.id] ?? ""}
                        onChange={(event) =>
                          setReplyDrafts((current) => ({
                            ...current,
                            [bounty.id]: event.target.value,
                          }))
                        }
                        placeholder="Paste the reply tweet URL"
                      />
                      <div className="row">
                        <button
                          className="btn btn-lime"
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            try {
                              const url = requireTweetUrl(
                                replyDrafts[bounty.id] ?? "",
                                "Reply URL",
                              );
                              return runWrite(() =>
                                submitReply(
                                  account as `0x${string}`,
                                  bounty.id,
                                  url,
                                  onPhase,
                                ),
                              );
                            } catch (err) {
                              setError(walletErrorMessage(err));
                            }
                          }}
                        >
                          Submit proof
                        </button>
                        {sameAddress(bounty.requester, account) &&
                        isExpired(bounty.deadline) ? (
                          <button
                            className="btn btn-ghost"
                            type="button"
                            disabled={busy}
                            onClick={() =>
                              runWrite(() =>
                                refundBounty(
                                  account as `0x${string}`,
                                  bounty.id,
                                  onPhase,
                                ),
                              )
                            }
                          >
                            Refund
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ) : bounty.reply_url ? (
                    <a href={bounty.reply_url} target="_blank" rel="noreferrer">
                      Paid proof {bounty.reply_url}
                    </a>
                  ) : (
                    <p className="mono">Returned to {shortAddr(bounty.requester)}</p>
                  )}
                </article>
              ))
            )}
          </div>
        </section>

        <aside className="composer">
          <div className="composer-head">
            <h2>Compose</h2>
          </div>
          <div className="tabs">
            <button
              className={tab === "bounty" ? "active" : ""}
              type="button"
              onClick={() => setTab("bounty")}
            >
              Fund
            </button>
            <button
              className={tab === "register" ? "active" : ""}
              type="button"
              onClick={() => setTab("register")}
            >
              Register
            </button>
            <button
              className={tab === "lookup" ? "active" : ""}
              type="button"
              onClick={() => setTab("lookup")}
            >
              Lookup
            </button>
          </div>

          {tab === "bounty" ? (
            <form onSubmit={onOpen}>
              <p className="hint">Name the handle, the tweet, and the GEN you are willing to lock.</p>
              <label htmlFor="target">Pay this handle</label>
              <input
                id="target"
                value={targetHandle}
                onChange={(event) => setTargetHandle(event.target.value)}
                placeholder="mrbeast"
                required
              />
              <label htmlFor="tweet">Tweet URL</label>
              <input
                id="tweet"
                value={tweetUrl}
                onChange={(event) => setTweetUrl(event.target.value)}
                placeholder="https://x.com/you/status/..."
                required
              />
              <label htmlFor="amount">Reward in GEN</label>
              <div className="chips">
                {["0.1", "1", "5"].map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    className={amount === preset ? "active" : ""}
                    onClick={() => setAmount(preset)}
                  >
                    {preset}
                  </button>
                ))}
              </div>
              <input
                id="amount"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                required
              />
              <label htmlFor="deadline">Deadline</label>
              <div className="chips">
                <button type="button" onClick={() => setDeadlineIn(60 * 60 * 1000)}>
                  1h
                </button>
                <button type="button" onClick={() => setDeadlineIn(24 * 60 * 60 * 1000)}>
                  24h
                </button>
                <button type="button" onClick={() => setDeadlineIn(7 * 24 * 60 * 60 * 1000)}>
                  7d
                </button>
              </div>
              <input
                id="deadline"
                type="datetime-local"
                value={deadlineLocal}
                onChange={(event) => setDeadlineLocal(event.target.value)}
                required
              />
              <label htmlFor="min">Minimum reply length</label>
              <input
                id="min"
                type="number"
                min={1}
                value={minChars}
                onChange={(event) => setMinChars(event.target.value)}
              />
              <div className="actions">
                <button className="btn btn-primary" type="submit" disabled={busy}>
                  Lock bounty
                </button>
              </div>
            </form>
          ) : null}

          {tab === "register" ? (
            <form onSubmit={onRegister}>
              <p className="hint">
                Tweet the line below from that X account, then paste the tweet URL.
                That wallet is the only one that can be paid.
              </p>
              {account ? (
                <div className="copy-box">
                  <code>{proofText}</code>
                  <button className="btn-tiny" type="button" onClick={copyProof}>
                    {copied ? "Copied" : "Copy text"}
                  </button>
                  <a
                    className="btn-tiny"
                    href={tweetIntentUrl(proofText)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Tweet it
                  </a>
                </div>
              ) : (
                <p className="hint">Connect a wallet to get the proof line.</p>
              )}
              <label htmlFor="handle">X handle</label>
              <input
                id="handle"
                value={handle}
                onChange={(event) => setHandle(event.target.value)}
                placeholder="mrbeast"
                required
              />
              <label htmlFor="proof">Proof tweet URL</label>
              <input
                id="proof"
                value={proofUrl}
                onChange={(event) => setProofUrl(event.target.value)}
                placeholder="https://x.com/handle/status/..."
                required
              />
              <div className="actions">
                <button className="btn btn-lime" type="submit" disabled={busy}>
                  Bind handle
                </button>
              </div>
            </form>
          ) : null}

          {tab === "lookup" ? (
            <form onSubmit={onLookup}>
              <p className="hint">See which wallet a handle pays out to.</p>
              <label htmlFor="lookup">Handle</label>
              <input
                id="lookup"
                value={lookupHandle}
                onChange={(event) => setLookupHandle(event.target.value)}
                placeholder="mrbeast"
              />
              <div className="actions">
                <button className="btn btn-ghost" type="submit">
                  Read registration
                </button>
              </div>
              {binding ? (
                <div className="binding">
                  {binding.registered ? (
                    <>
                      <div className="handle">@{binding.handle}</div>
                      <p className="owner">{binding.owner}</p>
                    </>
                  ) : (
                    <p className="hint">@{lookupHandle} is not registered yet.</p>
                  )}
                </div>
              ) : null}
            </form>
          ) : null}
        </aside>
      </div>

      {phase !== "idle" ? (
        <div className="tx-dock">
          <span className={`status ${phase}`}>{phaseLabel(phase)}</span>
          {txHash ? (
            <a href={getExplorerTxUrl(txHash)} target="_blank" rel="noreferrer">
              {shortAddr(txHash)}
            </a>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
