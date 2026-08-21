import { getChain } from "./config";

export type InjectedProvider = {
  request: (args: { method: string; params?: unknown }) => Promise<unknown>;
  on?: (event: string, handler: (...args: unknown[]) => void) => void;
  removeListener?: (event: string, handler: (...args: unknown[]) => void) => void;
  isMetaMask?: boolean;
};

let activeProvider: InjectedProvider | null = null;

export function getActiveProvider(): InjectedProvider | null {
  return activeProvider ?? getFallbackProvider();
}

export function walletErrorMessage(err: unknown): string {
  if (!err) {
    return "Wallet request failed";
  }
  if (typeof err === "string") {
    if (isRpcCapacityError(err)) {
      return "Bradbury RPC is at capacity. Wait a second and try again — this is the network, not your wallet.";
    }
    return err;
  }
  if (err instanceof Error) {
    if (isRpcCapacityError(err)) {
      return "Bradbury RPC is at capacity. Wait a second and try again — this is the network, not your wallet.";
    }
    return err.message;
  }
  if (typeof err === "object") {
    const value = err as {
      code?: number | string;
      message?: string;
      shortMessage?: string;
      data?: { message?: string };
    };
    if (value.code === 4001 || value.code === "ACTION_REJECTED") {
      return "Wallet request was rejected";
    }
    if (isRpcCapacityError(err)) {
      return "Bradbury RPC is at capacity. Wait a second and try again — this is the network, not your wallet.";
    }
    if (typeof value.shortMessage === "string" && value.shortMessage) {
      return value.shortMessage;
    }
    if (typeof value.message === "string" && value.message) {
      return value.message;
    }
    if (typeof value.data?.message === "string") {
      return value.data.message;
    }
    try {
      return JSON.stringify(err);
    } catch {
      return "Wallet request failed";
    }
  }
  return "Wallet request failed";
}

export function isRpcCapacityError(err: unknown): boolean {
  const text = stringifyErr(err);
  return (
    text.includes("-32005") ||
    /rate limit|node is at capacity|gas rate limit/i.test(text)
  );
}

export function retryAfterMs(err: unknown): number {
  const text = stringifyErr(err);
  const match = text.match(/retryAfterMs["\s:]*(\d+)/i) || text.match(/retry in ~(\d+)ms/i);
  if (match) {
    const ms = Number(match[1]);
    if (Number.isFinite(ms) && ms > 0) {
      return Math.min(Math.max(ms, 400), 8000);
    }
  }
  return 1200;
}

function stringifyErr(err: unknown): string {
  if (!err) {
    return "";
  }
  if (typeof err === "string") {
    return err;
  }
  if (err instanceof Error) {
    return `${err.message} ${err.stack ?? ""}`;
  }
  try {
    return JSON.stringify(err);
  } catch {
    return String(err);
  }
}

function getFallbackProvider(): InjectedProvider | null {
  if (typeof window === "undefined") {
    return null;
  }
  const ethereum = window.ethereum as
    | (InjectedProvider & { providers?: InjectedProvider[] })
    | undefined;
  if (!ethereum) {
    return null;
  }
  if (Array.isArray(ethereum.providers) && ethereum.providers.length > 0) {
    return (
      ethereum.providers.find((provider) => provider.isMetaMask) ??
      ethereum.providers[0]
    );
  }
  return ethereum;
}

function announceProviders(): Promise<InjectedProvider[]> {
  if (typeof window === "undefined") {
    return Promise.resolve([]);
  }
  return new Promise((resolve) => {
    const found: InjectedProvider[] = [];
    const onAnnounce = (event: Event) => {
      const provider = (event as CustomEvent).detail?.provider as
        | InjectedProvider
        | undefined;
      if (provider) {
        found.push(provider);
      }
    };
    window.addEventListener("eip6963:announceProvider", onAnnounce);
    window.dispatchEvent(new Event("eip6963:requestProvider"));
    window.setTimeout(() => {
      window.removeEventListener("eip6963:announceProvider", onAnnounce);
      resolve(found);
    }, 150);
  });
}

async function pickProvider(): Promise<InjectedProvider> {
  const announced = await announceProviders();
  const metamask = announced.find((provider) => provider.isMetaMask);
  const provider = metamask ?? announced[0] ?? getFallbackProvider();
  if (!provider) {
    throw new Error(
      "No browser wallet found. Install MetaMask and refresh this page.",
    );
  }
  return provider;
}

async function switchToGenLayer(provider: InjectedProvider): Promise<void> {
  const chain = getChain();
  const chainIdHex = `0x${chain.id.toString(16)}`;
  const explorer = chain.blockExplorers?.default.url;
  try {
    await provider.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: chainIdHex }],
    });
    return;
  } catch (err) {
    const code = (err as { code?: number })?.code;
    if (code !== 4902 && code !== -32603) {
      throw err;
    }
  }
  try {
    await provider.request({
      method: "wallet_addEthereumChain",
      params: [
        {
          chainId: chainIdHex,
          chainName: chain.name,
          nativeCurrency: chain.nativeCurrency,
          rpcUrls: [...chain.rpcUrls.default.http],
          ...(explorer ? { blockExplorerUrls: [explorer] } : {}),
        },
      ],
    });
  } catch (err) {
    if (chain.isStudio) {
      return;
    }
    throw err;
  }
}

export async function connectInjectedWallet(): Promise<`0x${string}`> {
  const provider = await pickProvider();
  const accounts = (await provider.request({
    method: "eth_requestAccounts",
    params: [],
  })) as string[];
  if (!accounts?.[0]) {
    throw new Error("Wallet returned no account");
  }
  await switchToGenLayer(provider);
  activeProvider = provider;
  return accounts[0] as `0x${string}`;
}

export function subscribeWallet(
  onAccounts: (address: `0x${string}` | "") => void,
): () => void {
  const provider = getActiveProvider();
  if (!provider?.on) {
    return () => undefined;
  }
  const handler = (accounts: unknown) => {
    const list = Array.isArray(accounts) ? accounts : [];
    onAccounts((list[0] as `0x${string}`) ?? "");
  };
  provider.on("accountsChanged", handler);
  return () => {
    provider.removeListener?.("accountsChanged", handler);
  };
}
