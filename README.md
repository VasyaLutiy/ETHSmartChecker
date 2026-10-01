# ETHSmartChecker

Bytecode forensics for Ethereum mainnet. ETHSmartChecker follows the chain, stores the
runtime bytecode of every contract that shows up in new blocks, clusters the codes by
identity and by shape, and alerts when a copy or a near-copy of a known scam or
vulnerable contract appears.

The question it answers: *given one contract that was exploited or used for a scam,
where are all the others built from the same code, and is a new one being deployed
right now?*

Standard library only, Python 3.9+, one SQLite file, no key required.

## How it works

```
 chain ──eth_getBlockReceipts──▶ candidates ──eth_getCode──▶ runtime bytecode
                                                                   │
                                                                   ▼
                                       fingerprint: sha256, selectors, skeleton, proxy
                                                                   │
                       ┌───────────────────────────────────────────┼─────────────────┐
                       ▼                                           ▼                 ▼
                  SQLite store                               clusters L0/L1      watchlist
            codes, addresses, seeds                        proxy, eip7702     seeds → ALERT
```

1. **Ingest.** For each block the receipts are fetched once. Every `contractAddress`,
   every `to` and every `logs[].address` is a candidate. Addresses already in the store
   are skipped; the rest cost one `eth_getCode` each. Accounts without code are stored
   as EOAs so they are never asked again.
2. **Fingerprint** (`ethsc/evm.py`, `ethsc/fingerprint.py`). Pure bytecode analysis, no
   I/O: the compiler metadata trailer is stripped, the body is disassembled, the
   4-byte function selectors are read from the dispatcher, EIP-1167 clones and EIP-7702
   delegation designators are recognised, and a *skeleton* is built by zeroing every
   PUSH20/PUSH32 immediate. Two contracts compiled from the same source with different
   addresses or constants baked in have the same skeleton.
3. **Clusters** (`ethsc/cluster.py`).
   - **L0** — identical runtime code (same sha256), two or more addresses.
   - **L1** — identical skeleton across different codes: the same template deployed
     with different parameters.
   - **proxy** — EIP-1167 minimal clones grouped by implementation target.
   - **eip7702** — delegating EOAs grouped by delegation target.
4. **Similarity.** The Jaccard index of two contracts' selector sets, with three rules:
   when either side is an EIP-1167 clone or an EIP-7702 designator the score is 1.0 if both
   are delegations with the same kind and target and 0.0 otherwise; a standard EIP-1967 /
   UUPS / beacon proxy scores 0.0 against everything (its selectors say nothing about the
   protocol behind it); otherwise the plain Jaccard of the two non-empty selector sets.
5. **Watchlist.** A *seed* is a stored contract with a label. Every new contract is
   scored against every seed as its block is ingested; a score at or above the
   threshold (default 0.8) is an `ALERT` line, printed before the next block is fetched.
   `recheck` runs the same comparison over the whole store, so copies that were stored
   before the seed was added become visible too.
6. **Risk flags.** Two flags read from the disassembly of the stripped body only, never
   from bytes inside a PUSH immediate or the metadata: `selfdestruct` (a SELFDESTRUCT
   opcode is present) and `mutable_delegatecall` (DELEGATECALL together with SLOAD in a
   code that is neither an EIP-1167 clone nor a standard proxy).
7. **Report.** One offline HTML + JSON report over the store: counts, cluster histogram,
   alerts per seed, risk flags, credit ledger. Byte-identical on a second run.

## Quick start

```bash
git clone https://github.com/VasyaLutiy/ETHSmartChecker.git
cd ETHSmartChecker
python3 -m venv venv && venv/bin/pip install matplotlib   # matplotlib only for `report`

# Follow the chain from the current head on the keyless public node
venv/bin/python -m ethsc --db ethsc.sqlite listen --source publicnode

# Add a seed from a known incident: the Balancer V2 ComposableStable pool of 3 Nov 2025
venv/bin/python -m ethsc --db ethsc.sqlite seed add --fetch \
    0xdacf5fa19b1f720111609043ac67a9818262850c --label "Balancer V2 ComposableStable, Nov 2025"

# Everything in the store that matches any seed
venv/bin/python -m ethsc --db ethsc.sqlite recheck

# Offline report
venv/bin/python -m ethsc --db ethsc.sqlite report --out ethsc-report
```

With an Infura key, put `INFURA_API_KEY=...` in `.env` (or the environment) and drop
`--source publicnode`; add `--daily-budget 3000000` to stop cleanly at the free tier.

## Commands

All commands work on one SQLite file given by `--db` (default `ethsc.sqlite`). Output is
plain text, one record per line, tab-separated, fully ordered; floats are printed with
four decimals.

| command | what it does |
|---|---|
| `listen [--source] [--workers K] [--interval S] [--daily-budget N] [--max-calls-per-block N] [--alert-on created\|seen\|all]` | follow the chain from the stored progress (or the head on a fresh store), forever, printing `ALERT` lines as blocks complete; `--alert-on` filters the printed lines only |
| `backfill --from B --to B [same options]` | the same over a fixed block range |
| `clusters top [--n N]` | the largest clusters: level, key, member count |
| `cluster <address>` | every cluster the address belongs to, with members and risk flags |
| `similar <address> [--min S]` | every stored address whose code scores at least S against this one |
| `seed add <address> --label L [--fetch]` | add a seed; `--fetch` pulls the code from the public node when the address is not in the store, then prints the alerts for that seed |
| `seed remove <address>` | drop a seed; its code and address stay |
| `seed list` | the seeds |
| `recheck [--min S] [--origin created\|seen\|fetched\|unknown]` | every stored address matching any seed |
| `risk [--flag selfdestruct\|mutable_delegatecall]` | stored addresses whose code carries at least one flag |
| `report [--out PATH]` | write `PATH.html` and `PATH.json`, print the two paths |

An `ALERT` record is `ALERT <address> <seed_address> <label> <score> <origin>`, where
`origin` says how the address entered the store: `created` (it was the `contractAddress`
of a receipt, a fresh deployment), `seen` (it was a transaction target or a log emitter:
an existing contract that was touched), `fetched` (`seed add --fetch`) or `unknown`
(stored before this field existed). A `seen` alert on an old contract is as real as a
`created` one: in the 1 Oct 2026 run a Balancer V1 pool from 2020 alerted when a router
swapped through it, with the same bytecode as the pool drained in Aug 2026. `cluster` and
`similar` records end with the risk flags of the address (`selfdestruct`,
`mutable_delegatecall`, or `-`).

**Exit codes:** 0 success, 1 a failed RPC call, 2 usage error, 3 a budget or cap stop
that left work undone (one `stopped: <budget|cap>, spent <N> credits, progress <P>`
line on stderr). Ctrl-C anywhere in `listen` or `backfill` is a clean stop: exit 0, no
traceback, progress kept, and the next run continues from the last completed block.

## Data sources

| source | key | cost model | notes |
|---|---|---|---|
| Infura | `INFURA_API_KEY` | credits: 1 000 per `eth_getBlockReceipts`, 80 per `eth_getCode`; a daily ledger is kept in the store and `--daily-budget` stops the run before a call would exceed it | `eth_getCode` at the block number of the receipt |
| `ethereum-rpc.publicnode.com` | none | free; no ledger | `eth_getCode` only at `latest` (archive queries need a token); `result: null` answers are retried five times and never advance progress; default 8 parallel `eth_getCode` workers |

The free Infura tier covers roughly 500 blocks a day. The public node followed the chain
at ~0.37 blocks/s on an 8-vCPU VPS during the 30 Sep 2026 live run, about 4.5× the
chain's own rate, with an empty stderr over 20 minutes.

## What it can and cannot see

- **Families, not vulnerabilities.** The watchlist finds copies of a *code*, not
  instances of a *bug class*. Good seeds are contracts that are deployed serially:
  factory pools, vault and strategy templates, token templates, clone families. A
  unique protocol contract as a seed will never alert.
- **Standard proxies are invisible on purpose.** Since a TransparentUpgradeableProxy
  seed produced 380 false alerts on the first live base, any code carrying the EIP-1967
  implementation or beacon slot scores 0.0. Families whose instances are such proxies
  (Ajna, Arrakis, Yearn V3 strategies, …) cannot be caught by selector similarity; that
  needs resolving the implementation slot, which is not implemented.
- **EIP-1167 clones are caught by target.** Two minimal proxies pointing at the same
  implementation score 1.0, so one Abracadabra cauldron or one Kashi pair as a seed
  covers the whole clone family.
- **Only what the chain shows.** A contract enters the store when it appears in a
  receipt: as the created address, the transaction target or a log emitter. A dormant
  contract is never fetched; `seed add --fetch` is the way in for a historical address.
- **Selectors, not semantics.** The score is a set overlap of 4-byte selectors. Two
  unrelated contracts with the same ABI (every ERC-20, for instance) score high; the
  default threshold of 0.8 and the L1 skeleton are what separate a template from an
  interface.

## Numbers from the live runs (30 Sep – 1 Oct 2026)

| | |
|---|---|
| store after one Infura day (500 blocks) + a 10.5 h public-node night | 18 594 codes, 197 257 addresses |
| `recheck` over 18 594 codes and 8 seeds | 0.54 s |
| `report` over 18 594 codes | 33 s, html and json byte-identical on rerun |
| a factory pool seed (`seed add --fetch`) | 0.35 s, alerts printed immediately |
| test suite | 357 tests, offline, real bytecode fixtures under `tests/fixtures/` |

## Project layout

```
ethsc/
  evm.py          disassembly, metadata stripping, selectors, proxy detection, skeleton, risk flags
  fingerprint.py  the Fingerprint record and the similarity score
  store.py        SQLite: codes by content hash, addresses, seeds, progress, credit ledger
  cluster.py      L0/L1/proxy/eip7702 clusters, similar, watchlist match and recheck
  rpc.py          the only module that touches the network: JSON-RPC, retries, credits
  ingest.py       one block: candidates → get_code → store → alerts; follow_chain
  cli.py          python -m ethsc
  report.py       the offline report; charts.py draws it (matplotlib, optional)
tests/            unittest, offline; helpers.py holds the fakes
docs/             one TASK_PHASE<n>.md per phase: why, contract, acceptance, results
contour.yaml      the behavioural contract every phase is cut from
```

## How it was built

The code was produced phase by phase (thirteen so far) by the
[Morph](https://github.com/VasyaLutiy/mrph) orchestration method: a human operator and
an orchestrating model write a contract (`contour.yaml`) with examples, cut it into
cards with file ownership and a shell acceptance, and executor models write the code
while a separate judge model writes the example tests. Every phase document in `docs/`
ends with the run in numbers: cards, attempts, wall time, cost, and the live check that
confirmed or refuted the phase's claim. Product code is never hand-edited by the
operator; the contract is.

## Requirements

- Python 3.9 or newer, standard library only for everything but `report`.
- `matplotlib` for `report` (without it the command exits 2 and names the package).
- Network only in `listen`, `backfill` and `seed add --fetch`; every other command,
  and the whole test suite, runs offline.
