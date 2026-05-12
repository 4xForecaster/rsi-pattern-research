# Pattern Definitions

All thresholds are configurable via `PatternConfig` in `src/rsi_pattern/patterns.py`. Defaults below are starting values, to be tuned after first detection pass.

## M (top pattern)

A double-peak structure in RSI near the upper extreme.

**Formal definition:**

A window of RSI bars contains an **M** if:

1. Two RSI local maxima `P1`, `P2` exist within ≤ `max_span_bars` bars of each other.
2. Both `P1` and `P2` are ≥ `peak_threshold` (default 65).
3. The RSI minimum between `P1` and `P2` (call it `dip`) satisfies `dip ≥ inner_threshold` (default 50).
4. The pattern is **completed** when RSI subsequently breaks below `completion_threshold` (default 50) within `max_completion_bars` of `P2`.

**Notation:** `M(P1_idx, P2_idx, completion_idx)` — three bar indices defining the shape's anchors.

**Default parameters:**

| Parameter | Default | Rationale |
|---|---|---|
| `peak_threshold` | 65 | Captures "near 70-line" without requiring strict 70. |
| `inner_threshold` | 50 | Dip must stay in upper half for M to remain a "top" structure. |
| `max_span_bars` | 30 | Peak-to-peak distance; tune per timeframe. |
| `max_completion_bars` | 30 | Time from P2 to break-below-50. |

## V (bottom pattern)

Mirror of M. Double-trough structure near the lower extreme.

**Formal definition:**

A window of RSI bars contains a **V** if:

1. Two RSI local minima `T1`, `T2` exist within ≤ `max_span_bars` bars of each other.
2. Both `T1` and `T2` are ≤ `trough_threshold` (default 35).
3. The RSI maximum between `T1` and `T2` (call it `peak`) satisfies `peak ≤ inner_threshold` (default 50).
4. The pattern is **completed** when RSI subsequently breaks above `completion_threshold` (default 50) within `max_completion_bars` of `T2`.

**Notation:** `V(T1_idx, T2_idx, completion_idx)`.

## C (consolidation / traversal)

[NEEDS USER CONFIRMATION — two candidate definitions below]

### Candidate (a): Traversal phase

C is the bars between the completion of an M (or V) and the formation of the next V (or M). RSI traverses the 30-70 zone without forming a new extreme shape. By construction, C bars are exactly the bars not labeled M or V.

**Pros:** Simple, deterministic, complete state-space partitioning.
**Cons:** C has no intrinsic shape — it's defined by absence.

### Candidate (b): Specific topology

C is its own pattern with rules — e.g., a single peak or trough that does NOT meet M or V criteria (insufficient amplitude, insufficient peak count), often appearing as a "failed" extreme attempt before the real M or V forms.

**Formal candidate:**

A window contains a **C** if:

1. RSI has a single local maximum `P` in the upper half (45-65) OR a single local minimum `T` in the lower half (35-55).
2. The extreme does NOT meet M or V thresholds (so it's a "weaker" structure).
3. RSI returns to the 50-line within `max_completion_bars`.

**Pros:** Topologically distinct, useful as a "weak signal" state.
**Cons:** Detection rules need careful calibration to avoid overlap with M/V.

**Decision pending.** Defaulting to candidate (a) in v0 detector — easy to swap later by changing `PatternConfig.c_definition`.

## State machine

Sequence flow (under candidate (a)):

```
              ┌──────┐
        ┌────►│  M   │────┐
        │     └──────┘    │
        │                 ▼
   ┌────┴───┐         ┌──────┐
   │   V    │◄────────│  C   │
   └────────┘         └──────┘
        ▲                 │
        │                 │
        └─────────────────┘
```

Under candidate (b) the same diagram applies but C is its own labeled segment, not "everything else."

## Fractal expectation

If H2 holds, the average duration of each state (measured in bars) should scale roughly proportionally with timeframe:

| Timeframe | Expected M duration (bars) | Expected M duration (calendar) |
|---|---|---|
| Daily | ~10 | ~10 days |
| 4h | ~60 | ~10 days |
| 1h | ~240 | ~10 days |
| 5m | ~2880 | ~10 days |

**Test:** Normalize by trading-hours-per-day; the calendar duration should be invariant if the pattern is fractal. Deviations expose timeframe-specific dynamics.
