# RipLayer

Pay an X account to reply — money moves only if GenLayer validators agree the reply is real.

A fan locks GEN on a specific tweet and a specific handle. The influencer (or anyone) pastes the reply URL. Validators fetch the tweet, check the author and that it replies to the named tweet, then the **registered wallet for that handle** gets paid. If the deadline passes with no valid reply, the fan refunds.

GenLayer is the adjudication protocol. The Intelligent Contract is the escrow.

## How it works

1. **Register a handle.** Tweet your GenLayer/EVM address from that X account and submit the tweet URL. Whoever currently controls the handle can re-bind the payout wallet.
2. **Open a bounty.** Name the handle, the tweet you want a reply on, a deadline, and lock GEN.
3. **Submit proof.** Anyone can submit a public reply URL. If the bounty has criteria, GenLayer validators judge whether the reply actually answers it — not just whether a reply exists. Payment always goes to the registered wallet.
4. **Refund.** After expiry, only the requester can pull unspent GEN back.

Validators agree on stable tweet fields from `api.fxtwitter.com` (author, tweet id, reply-to id). They do not rubber-stamp the UI.

## Architecture boundary

| Layer | Owns |
|---|---|
| Frontend | Wallet, forms, bounty list, submitted/pending/finalized/failed UX |
| RipLayer contract | Handle binding, escrow, tweet-id parsing, fetch + equivalence, payout/refund |
| External sources | Public tweet JSON. Re-fetched independently. Not a trusted oracle |

## Setup

Python 3.12+ and Node.js 18+.

```shell
py -3 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
npm install
```

```shell
genvm-lint check contracts/rip_layer.py --json
pytest tests/direct/ -v
```

Direct tests include a Windows workaround in `tests/direct/conftest.py` for a genlayer-test tempfile unlink bug.

Integration tests on Bradbury:

```shell
gltest tests/integration/ -v -s --network testnet_bradbury
```

## Deploy (Testnet Bradbury)

The CLI is set to `testnet-bradbury`. StudioNet is gasless; **Bradbury is not**.

1. Fund the deployer. Faucet: https://testnet-faucet.genlayer.foundation/  
   100 GEN per week. The claiming address must hold **0.01 ETH on Ethereum mainnet**.
2. Deployer account `riplayer`: `0x3c888269ca4ffcb41bbd76707c8f576c925dd41e`
3. Then:

```shell
npx genlayer network set testnet-bradbury
npx genlayer deploy --contract contracts/rip_layer.py
```

Live on Bradbury:

```
VITE_CONTRACT_ADDRESS=0x5f1c824Cd62cACDc83C8926cEcbeeC9CF93A2249
VITE_NETWORK=testnetBradbury
```

Explorer: https://explorer-bradbury.genlayer.com/

## Frontend on Vercel

Import https://github.com/iamdudeGH/RipLayer and set:

- **Root Directory:** `frontend`
- **Build Command:** `npm run build`
- **Output Directory:** `dist`

Environment variables (must be set before the first build — Vite inlines them):

```
VITE_CONTRACT_ADDRESS=0x27Ec9DdA20bBE01a0e4BC0a3FbcA71f6aBEd61DE
VITE_NETWORK=testnetBradbury
```

Framework preset can be Vite. After deploy, connect MetaMask to Bradbury (chain id `4221`).
