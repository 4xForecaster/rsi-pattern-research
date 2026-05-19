# H23 — Major-Pair Expansion of the Daily Scheme D Regime Layer

**Date:** 2026-05-19
**Script:** [`scripts/h23_major_pair_expansion.py`](../scripts/h23_major_pair_expansion.py)
**Run dump:** [`results/_h23_run.json`](_h23_run.json)
**Figures:** [`figures/12_major_pair_equity_curves.png`](../figures/12_major_pair_equity_curves.png),
[`figures/13_major_pair_sortino_compare.png`](../figures/13_major_pair_sortino_compare.png)

## The only question

DXY daily Scheme D is **live** on Dr. A's machine via the hurst-agent cron.
Does that DXY-calibrated framework transfer, *unchanged*, to the remaining FX
majors? No per-symbol re-tuning was performed or attempted — that is out of
scope by design. Adding pairs that pass the go/no-go bar multiplies the edge
with zero new architecture.

## Foundation check (done first, before any new pair was trusted)

The H23 engine (`run_one`) is lifted **verbatim** from
[`scripts/h16_usdmxn_calibration.py`](../scripts/h16_usdmxn_calibration.py),
which in turn drives the same `rsi_pattern` v0.2.0 modules that
`hurst-agent` imports for the live DXY signal. Re-running the DXY reference
through it reproduces the recorded anchor **exactly**:

> DXY full-sample: **Sortino +5.75 / 56 trades** — recorded anchor +5.75 / 56. **Match.**

This is the stop-ship gate: if the harness had not reproduced the shipped
DXY number we would be testing a *different* strategy and any "transfer"
result would be spurious. It does reproduce it, so the transfer test is
valid.

## Methodology (inherited from H16 — the canonical protocol, not reinvented)

- Engine: `indicators.add_rsi(·,14)` → `position_sizing.fib_long_at_p1`
  (loose-M, `PatternConfig` default `m_inner_threshold=50`) →
  `fld.fld_bias(cycles=(10,20,40))` → Scheme D sizing
  **bullish 0× / neutral 1× / bearish 3×** at the entry bar →
  `rm.build_equity_curve` (1% risk/trade) → `rm.sortino`.
- **70/30 chronological split by bars.** IS = first 70%, OOS = last 30%.
- **OOS Sortino is the load-bearing metric.** Full sample is context only,
  *except* the trade-count floor, which is applied to the full sample — the
  "PRAGMATIC" reading H16 used and how USDMXN ("26 trades, below 30-floor")
  and DXY were recorded.
- Decision (task-locked thresholds on the OOS protocol):
  - **GO** = OOS Sortino ≥ +3.0 **and** full-sample trades ≥ 30
  - **NO-GO** = OOS Sortino < +1.0 **or** full-sample trades < 10
  - **SWEEP** = anything in between
- Deterministic pipeline; `SEED=4242` pinned for reproducibility.
- yfinance pulled once, cached under `data/yfinance_cache/` keyed by ticker
  (`YF_END=2026-05-19`). All 6 caches verified: 0 NaN, monotonic, 0 dup,
  0 inverted/zero bars.

## Phase 1 — Data inventory

| Symbol | Source | Bars | Start | End | IS→ | OOS→ |
|---|---|---:|---|---|---|---|
| DXY (ref) | BarChart CSV | 9,304 | 1990-01-02 | 2026-05-04 | …2015-07-22 | 2015-07-23…2026-05-04 |
| EURUSD | yfinance `EURUSD=X` | 5,827 | 2003-12-01 | 2026-05-18 | …2019-08-27 | 2019-08-28…2026-05-18 |
| GBPUSD | yfinance `GBPUSD=X` | 5,839 | 2003-12-01 | 2026-05-18 | …2019-08-22 | 2019-08-23…2026-05-18 |
| USDJPY | yfinance `USDJPY=X` | 7,661 | 1996-10-30 | 2026-05-18 | …2017-07-14 | 2017-07-17…2026-05-18 |
| USDCAD | yfinance `USDCAD=X` | 5,895 | 2003-09-17 | 2026-05-18 | …2019-07-30 | 2019-07-31…2026-05-18 |
| AUDUSD | yfinance `AUDUSD=X` | 5,203 | 2006-05-16 | 2026-05-18 | …2020-05-15 | 2020-05-18…2026-05-18 |
| NZDUSD | yfinance `NZDUSD=X` | 5,828 | 2003-12-01 | 2026-05-18 | …2019-08-27 | 2019-08-28…2026-05-18 |

USDSEK / USDZAR were **not** run. Per the brief, exotic-FX microstructure
needs separate calibration; and the two borderline majors here fail for
*structural* reasons (long-only bias, dislocation dependence), not
microstructure — so exotics would be worse, not better. Noted, not chased.

## Phase 2 — Comparison table (sorted by OOS Sortino, the load-bearing metric)

| Symbol | Decision | OOS Sortino | OOS Tr | Full Tr | OOS MaxDD | Full Sortino | Full Tr/univ |
|---|---|---:|---:|---:|---:|---:|---:|
| **GBPUSD** | **GO** ⚠ | **+5.57** | 9 | 34 | −1.0% | +4.91 | 34/60 |
| **NZDUSD** | **GO** ⚠⚠ | **+5.34** | 4 | 35 | −3.0% | +4.42 | 35/78 |
| **EURUSD** | **GO** | **+4.06** | 12 | 30 | −1.6% | +3.15 | 30/66 |
| **USDCAD** | **GO** | **+3.12** | 15 | 35 | −3.9% | +4.36 | 35/60 |
| AUDUSD | SWEEP | +1.85 | 9 | 33 | −4.6% | +2.21 | 33/69 |
| USDJPY | SWEEP | +1.64 | 16 | 47 | −3.0% | +1.34 | 47/115 |
| DXY (ref) | SWEEP† | +1.34 | 19 | 56 | −8.0% | **+5.75** | 56/124 |

† **Important honesty note.** DXY itself is SWEEP under this *strict* 70/30
OOS protocol — its OOS window (2015→2026) straddles the weak 2015–2018
dollar chop. DXY shipped on the **H15 full-sample** decision (+5.75 / 56)
and a *7-year* OOS window (+5.38), not on this stricter split. So the 70/30
bar is **harder than the bar DXY itself cleared**. EURUSD and USDCAD clear
this harder bar with healthy OOS trade counts — that is a *stronger* claim
than DXY's original ship, not a weaker one.

## Phase 3 — Decisions and the thin-OOS caveat (load-bearing)

Four pairs are mechanically **GO** by the locked rule. Two of them are
fragile and must not be flipped live without a follow-up:

- **EURUSD — GO (solid).** OOS +4.06 on 12 trades, full +3.15 / 30, OOS
  MaxDD −1.6%. IS +3.27 and OOS +4.06 are consistent → no IS/OOS
  degradation (the USDMXN failure mode). Clean transfer.
- **USDCAD — GO (solid).** OOS +3.12 on 15 trades, full +4.36 / 35, OOS
  MaxDD −3.9%. Most OOS trades of any GO pair → most trustworthy of the
  four. Clean transfer.
- **GBPUSD — GO ⚠ (thin OOS).** OOS Sortino +5.57 but on only **9 OOS
  trades** (one under the n<10 small-sample line the task uses for NO-GO on
  the full sample). Full sample is robust (+4.91 / 34) and IS (+5.51) ≈ OOS
  (+5.57) — no degradation — but the OOS Sortino itself is a 9-sample
  number and should be read as directional, not precise. **Do not flip
  live before an H24 OOS-robustness pass.**
- **NZDUSD — GO ⚠⚠ (statistically thin — treat as provisional).** OOS
  Sortino +5.34 rests on **4 OOS trades** with mean R +11.31 — i.e. one or
  two lucky trades dominate. This is exactly the spurious-signal shape the
  doctrine forbids shipping on. The *full* sample (+4.42 / 35) and IS
  (+4.70 / 31) are genuinely strong, so NZDUSD is not rejected — but the
  GO is carried on full-sample strength, **not** the 4-trade OOS slice.
  **Provisional GO. Must not be flipped live without H24.**

No symbol is NO-GO: USDJPY has 47 full trades and OOS +1.64 (SWEEP, not
NO-GO); AUDUSD OOS +1.85 (SWEEP).

## Phase 4 — SWEEP pairs: closest-to-shipping variants (documented, NOT run)

Scope discipline: these are written down for a future **H24**, not executed
here (the only H23 question is "does the DXY calibration transfer as-is").

### AUDUSD — SWEEP (OOS +1.85, full 33)

Dislocation robustness is *negative*: excluding 2008 the full-sample
Sortino **falls** +2.21 → +1.33. AUDUSD's edge partly *leans on* the 2008
GFC carry unwind rather than being hurt by it — a fragility, not a
robustness. Closest variants for H24, in priority order:
1. FLD cycles `(10,20,40)` → `(15,30,60)` — AUD is a risk/commodity
   currency with a longer dominant swing; the 20D trading cycle likely
   undershoots.
2. loose-M dip `50 → 45` (shallower retraces qualify; more trades, may
   stabilize the OOS slice which has only 9 trades).
3. Both combined.

### USDJPY — SWEEP (OOS +1.64, full 47)

Trade count is *not* the problem (47 full / 16 OOS — the richest universe
here). Excluding the BOJ/MoF intervention years {2003,2004,2011,2022,2024}
only nudges full Sortino +1.34 → +1.75 — so interventions are *not* the
core issue either. The structural reason (see Phase 5) is that the engine
is **long-only** and USDJPY's defining behaviour is multi-year USD-up
trends; long entries on RSI M-tops repeatedly fade into trend
continuation. A knob sweep will not fix a directional-bias mismatch — H24
should evaluate a **regime/trend overlay**, not parameter tweaks. (Pure
short-side mirrors were already nulled in H21/H22, so the answer is an
overlay, not a flip.)

## Phase 5 — Structural reasons (so a future agent does not re-litigate)

- **USDJPY (SWEEP, structural).** `fib_long_at_p1` is long-only. JPY's
  signature regime is durable USD strength + asymmetric BOJ defense of the
  weak yen. Long RSI-M-top entries enter *against* the dominant up-trend
  and get run over. Confirmed by the intervention-exclusion test barely
  moving the number. Needs a trend filter / regime gate, not calibration.
- **AUDUSD (SWEEP, structural).** Edge concentrates in crisis carry-unwind
  episodes (2008). Excluding 2008 degrades it, so the strategy is
  *episode-dependent*, not continuously edge-positive on AUD. Sizing/cycle
  changes might broaden it; that is an H24 question.
- **No NO-GO** among the six majors — the DXY framework is at minimum
  *non-destructive* on every major (worst full Sortino is USDJPY +1.34,
  still > 1.0).

## Net read

The DXY-calibrated daily Scheme D **transfers cleanly to EURUSD and
USDCAD** (solid GO, healthy OOS samples, clearing a bar stricter than the
one DXY itself shipped under). It transfers **GBPUSD and NZDUSD on
full-sample strength but with OOS samples too thin to flip live without
H24** (provisional GO). It does **not** transfer to USDJPY or AUDUSD, for
identified structural reasons (long-only bias; episode dependence) — both
SWEEP, neither NO-GO.

All four GO pairs are written to `hurst-agent/config/rsi_m_p1.yaml` with
**`enabled: false`** and `status: GO`. Nothing trades automatically. The
thin-OOS caveat for GBPUSD/NZDUSD is carried verbatim into the config
`notes:` and `docs/SYMBOLS_TESTED.md` so the manual flip is an informed
decision by Dr. A, not a silent one.

## Deliverable-numbering note (load-bearing)

The brief requested `results/H17_*` and `figures/11_*,12_*`. Those slots
are already occupied (H17 = walk-forward strict-M; figure 11 = H22 V-floor
short). Overwriting committed work is a no-history-rewrite violation and
destroys prior results, so this experiment ships as **H23** with figures
**12** and **13**. The science is unchanged; only the index moved to avoid
clobbering.
