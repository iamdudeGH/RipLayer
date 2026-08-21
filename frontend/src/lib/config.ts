import { localnet, studionet, testnetBradbury } from "genlayer-js/chains";
import type { GenLayerChain } from "genlayer-js/types";

export const NETWORKS = {
  localnet,
  studionet,
  testnetBradbury,
} as const;

export type NetworkName = keyof typeof NETWORKS;

export function getNetworkName(): NetworkName {
  const value = (import.meta.env.VITE_NETWORK ?? "testnetBradbury") as NetworkName;
  if (value in NETWORKS) {
    return value;
  }
  return "testnetBradbury";
}

export function getChain(): GenLayerChain {
  return NETWORKS[getNetworkName()];
}

export function getContractAddress(): `0x${string}` | "" {
  const address = import.meta.env.VITE_CONTRACT_ADDRESS ?? "";
  return address as `0x${string}` | "";
}

export function getExplorerTxUrl(hash: string): string {
  const base = (getChain().blockExplorers?.default.url ?? "").replace(/\/$/, "");
  return `${base}/tx/${hash}`;
}

export const CONNECT_NETWORK: Record<
  NetworkName,
  "localnet" | "studionet" | "testnetBradbury"
> = {
  localnet: "localnet",
  studionet: "studionet",
  testnetBradbury: "testnetBradbury",
};
