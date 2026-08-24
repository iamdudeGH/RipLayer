import { createClient } from "genlayer-js";
import { ExecutionResult, TransactionHash, TransactionStatus } from "genlayer-js/types";
import { getChain, getContractAddress, getNetworkName } from "./config";
import {
  connectInjectedWallet,
  getActiveProvider,
  isRpcCapacityError,
  retryAfterMs,
  walletErrorMessage,
} from "./wallet";

export type TxPhase = "idle" | "submitted" | "pending" | "accepted" | "finalized" | "failed";
export type PhaseHandler = (phase: TxPhase, hash?: string) => void;

export class ConsensusPendingError extends Error {
  hash: string;

  constructor(hash: string, message: string) {
    super(message);
    this.name = "ConsensusPendingError";
    this.hash = hash;
  }
}

export type HandleView = {
  handle: string;
  registered: boolean;
  owner: string;
  proof_url: string;
  tweet_id: string;
};

export type BountyView = {
  id: string;
  exists?: boolean;
  requester?: string;
  target_handle?: string;
  beneficiary?: string;
  tweet_url?: string;
  tweet_id?: string;
  amount?: number | string;
  deadline?: number | string;
  min_chars?: number | string;
  status?: string;
  reply_url?: string;
  reply_id?: string;
  paid_to?: string;
  criteria?: string;
  verdict_note?: string;
};

function requireAddress(): `0x${string}` {
  const address = getContractAddress();
  if (!address) {
    throw new Error("Set VITE_CONTRACT_ADDRESS in frontend/.env");
  }
  return address;
}

export function createReadClient() {
  return createClient({
    chain: getChain(),
  });
}

export function createWriteClient(account: `0x${string}`) {
  return createClient({
    chain: getChain(),
    account,
    provider: getActiveProvider() ?? window.ethereum,
  });
}

export async function connectWallet(): Promise<`0x${string}`> {
  try {
    return await connectInjectedWallet();
  } catch (err) {
    throw new Error(walletErrorMessage(err));
  }
}

export async function readNativeBalance(address: `0x${string}`): Promise<bigint> {
  const client = createReadClient() as {
    request: (args: { method: string; params?: unknown[] }) => Promise<string>;
  };
  const hex = await client.request({
    method: "eth_getBalance",
    params: [address, "latest"],
  });
  return BigInt(hex);
}

export async function readHandle(handle: string): Promise<HandleView> {
  const client = createReadClient();
  return (await client.readContract({
    address: requireAddress(),
    functionName: "get_handle",
    args: [handle],
  })) as HandleView;
}

export async function readBounty(bountyId: string): Promise<BountyView> {
  const client = createReadClient();
  return (await client.readContract({
    address: requireAddress(),
    functionName: "get_bounty",
    args: [bountyId],
  })) as BountyView;
}

export async function readBounties(): Promise<Record<string, BountyView>> {
  const client = createReadClient();
  return (await client.readContract({
    address: requireAddress(),
    functionName: "list_bounties",
    args: [],
  })) as Record<string, BountyView>;
}

function waitBudget() {
  if (getNetworkName() === "testnetBradbury") {
    return { interval: 5000, retries: 84 };
  }
  return { interval: 3000, retries: 20 };
}

function statusCode(tx: { status?: unknown; statusName?: unknown }): string {
  if (tx.statusName) {
    return String(tx.statusName);
  }
  return String(tx.status ?? "");
}

function isAcceptedOrLater(tx: { status?: unknown; statusName?: unknown }): boolean {
  const value = statusCode(tx);
  return (
    value === "5" ||
    value === "7" ||
    value === "11" ||
    value === "ACCEPTED" ||
    value === "FINALIZED" ||
    value === "READY_TO_FINALIZE"
  );
}

function isTimeoutError(err: unknown): boolean {
  const message = err instanceof Error ? err.message : String(err);
  return message.includes("Timed out waiting for transaction");
}

function assertExecutionOk(
  tx: { txExecutionResultName?: ExecutionResult },
  hash: string,
  onPhase: PhaseHandler,
) {
  if (tx.txExecutionResultName === ExecutionResult.FINISHED_WITH_ERROR) {
    onPhase("failed", hash);
    throw new Error("Contract execution failed. State was not changed.");
  }
}

async function waitAndCheck(hash: TransactionHash, onPhase: PhaseHandler) {
  const client = createReadClient();
  onPhase("pending", hash);
  const { interval, retries } = waitBudget();
  let accepted;

  try {
    accepted = await client.waitForTransactionReceipt({
      hash,
      status: TransactionStatus.ACCEPTED,
      interval,
      retries,
    });
  } catch (err) {
    if (!isTimeoutError(err)) {
      throw err;
    }
    const latest = await client.getTransaction({ hash });
    if (latest && isAcceptedOrLater(latest)) {
      accepted = latest;
    } else {
      throw new ConsensusPendingError(
        hash,
        "Bradbury is still in consensus. This can take several minutes. The explorer may show success before this page does — we will keep refreshing.",
      );
    }
  }

  assertExecutionOk(accepted, hash, onPhase);
  onPhase("accepted", hash);

  void client
    .waitForTransactionReceipt({
      hash,
      status: TransactionStatus.FINALIZED,
      interval: 8000,
      retries: 90,
    })
    .then((finalized) => {
      if (finalized.txExecutionResultName === ExecutionResult.FINISHED_WITH_ERROR) {
        onPhase("failed", hash);
        return;
      }
      onPhase("finalized", hash);
    })
    .catch(() => undefined);

  return accepted;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function write(
  account: `0x${string}`,
  functionName: string,
  args: Array<string | number>,
  value: bigint,
  onPhase: PhaseHandler,
) {
  const client = createWriteClient(account);
  onPhase("submitted");
  const payload = {
    address: requireAddress(),
    functionName,
    args,
    value,
  };
  const attempts = 6;
  let lastError: unknown;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const hash = (await client.writeContract(payload)) as TransactionHash;
      onPhase("submitted", hash);
      return waitAndCheck(hash, onPhase);
    } catch (err) {
      lastError = err;
      if (!isRpcCapacityError(err) || attempt === attempts) {
        throw err;
      }
      onPhase("pending");
      await sleep(retryAfterMs(err) * attempt);
    }
  }
  throw lastError;
}

export function registerHandle(
  account: `0x${string}`,
  handle: string,
  proofUrl: string,
  onPhase: PhaseHandler,
) {
  return write(account, "register_handle", [handle, proofUrl], BigInt(0), onPhase);
}

export function openBounty(
  account: `0x${string}`,
  args: {
    targetHandle: string;
    tweetUrl: string;
    deadline: number;
    minChars: number;
    valueWei: bigint;
    criteria: string;
  },
  onPhase: PhaseHandler,
) {
  return write(
    account,
    "open_bounty",
    [args.targetHandle, args.tweetUrl, args.deadline, args.minChars, args.criteria],
    args.valueWei,
    onPhase,
  );
}

export function submitReply(
  account: `0x${string}`,
  bountyId: string,
  replyUrl: string,
  onPhase: PhaseHandler,
) {
  return write(account, "submit_reply", [bountyId, replyUrl], BigInt(0), onPhase);
}

export function refundBounty(
  account: `0x${string}`,
  bountyId: string,
  onPhase: PhaseHandler,
) {
  return write(account, "refund", [bountyId], BigInt(0), onPhase);
}

export function parseGen(amount: string): bigint {
  const trimmed = amount.trim();
  if (!trimmed) {
    throw new Error("Enter an amount in GEN");
  }
  const [whole, frac = ""] = trimmed.split(".");
  const fracPadded = (frac + "000000000000000000").slice(0, 18);
  return BigInt(whole || "0") * BigInt(10 ** 18) + BigInt(fracPadded || "0");
}
