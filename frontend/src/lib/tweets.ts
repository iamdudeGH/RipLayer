const HOSTS = new Set([
  "x.com",
  "www.x.com",
  "twitter.com",
  "www.twitter.com",
  "mobile.twitter.com",
  "fxtwitter.com",
  "fixupx.com",
]);

export function tweetIdFromUrl(url: string): string | null {
  try {
    const parsed = new URL(url.trim());
    if (!HOSTS.has(parsed.hostname)) {
      return null;
    }
    const parts = parsed.pathname.split("/").filter(Boolean);
    const statusAt = parts.indexOf("status");
    const id = statusAt >= 0 ? parts[statusAt + 1] : "";
    return /^\d+$/.test(id) ? id : null;
  } catch {
    return null;
  }
}

export function requireTweetUrl(url: string, label: string): string {
  const trimmed = url.trim();
  if (!tweetIdFromUrl(trimmed)) {
    throw new Error(`${label} must be an x.com/status/… URL`);
  }
  return trimmed;
}

export function proofTweetText(address: string): string {
  return `RipLayer payout wallet ${address}`;
}

export function tweetIntentUrl(text: string): string {
  return `https://x.com/intent/tweet?text=${encodeURIComponent(text)}`;
}
