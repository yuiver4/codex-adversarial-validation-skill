---
name: adversarial-validation
description: Adversarially validate high-impact technical conclusions, and any non-trivial technical conclusion when the host explicitly signals Max or Ultra, before accepting them. Use for architecture and design decisions, code reviews, refactors, optimization/performance claims, concurrency, caching, state/lifecycle management, networking or file I/O, persistence, security, platform abstractions, SDK/API/framework/library choices, benchmarks, infrastructure, build/deployment decisions, and expensive or hard-to-reverse technical choices. After an initial proposal or conclusion exists, stop trying to support it and actively try to break it with the strongest plausible competing design, counterexample, hidden assumption, failure mode, scale limit, or falsifiable test. Prefer measurement, profiler data, tests, logs, primary documentation, and reproducible benchmarks over verbal defense. Do not use for trivial getters/DTOs/formatting or when no meaningful technical decision is being made.
---

# Adversarial Validation

## Purpose

Prevent confirmation cascades in technical work.

A coherent explanation, a passing happy-path test, or a list of advantages is not validation.

Once a provisional conclusion exists, stop accumulating reasons that support it. Change roles from author to hostile reviewer and attempt to falsify the conclusion.

The goal is **not** to reject the proposal.

The goal is:

> Make rejection maximally plausible using the strongest realistic evidence and see whether the proposal survives.

Do not oppose for the sake of opposition. Do not invent absurd edge cases merely to create objections.

## Core Rule

For every consequential conclusion:

> Do not continue supporting the current conclusion. Find the strongest plausible argument, competing design, counterexample, benchmark, or failure mode that could break it.

If a challenge is measurable, do not resolve it by argument when it can reasonably be resolved by measurement.

## Independent Review Escalation

Inline falsification is the default.

After a provisional conclusion exists:

- if the user explicitly requests independent or adversarial review, spawn exactly one independent reviewer regardless of the author's risk or triviality classification
- otherwise, for a non-trivial conclusion, spawn exactly one independent reviewer when the host explicitly indicates Max or Ultra, or when applicable project, agent, or task instructions require independent validation

An explicit request is always a sufficient escalation condition. For non-trivial conclusions, Max/Ultra is also sufficient; do not require the authoring agent to first classify the decision as high risk. If the current reasoning tier is not exposed, do not infer it from task complexity; a host or profile that wants Max/Ultra escalation must provide an explicit model-visible instruction.

When escalation is triggered by Max/Ultra, use a reviewer at Max/Ultra if supported. Otherwise use the strongest available reviewer and disclose the downgrade.

The reviewer must:

- be freshly created for each proposition in a no-history context (`fork_turns="none"` or the host equivalent), not reused from any prior review or created from a default or full-history fork, and remain read-only
- receive only the falsifiable proposition, raw evidence or artifact references, actual requirements and constraints, and decision criteria
- when the received proposition is biased, ambiguous, or artificially narrow, state both the original proposition and a neutral reformulation, preserve the actual requirements and decision criteria, and attack the reformulated proposition
- not receive the author's reasoning, defense, desired verdict, confidence, or prior failed rebuttals
- construct the strongest realistic countercase and decision-reversing test
- not edit files, implement fixes, or spawn further agents

The same raw evidence may be shared. Independence comes from withholding the author's reasoning and desired conclusion, not from withholding relevant facts.

The main agent owns the final verdict, but must not make the final decision more favorable than the reviewer's result unless it cites new decision-relevant evidence the reviewer did not consider and explains which exact countercase or failed assumption that evidence resolves. A more favorable decision includes raising the verdict, dropping or weakening conditions, reducing stated risk, expanding approved scope or rollout, or strengthening an implementation or deployment recommendation. When making such a change, record the reviewer's original verdict, the evidence-based override rationale, and any unresolved disagreement in Residual Risk.

If the host cannot create a fresh no-history reviewer, do not simulate or claim independent review. Perform inline falsification when possible and leave required independent validation UNVERIFIED. Reviewer failure or timeout is never evidence of PASS.

### Optional Measurement Executor

When the challenge is measurable and a validated bounded compute executor is available, the reviewer may specify a decision-reversing experiment and the main agent may delegate only its execution. Bind inputs, environment, commands or configuration, outputs, and artifacts reproducibly. The executor produces evidence, not the verdict.

Do not automatically use an unvalidated or unavailable worker. If no suitable executor exists, measure locally when permitted or report the claim as UNVERIFIED.

## When to Apply

Apply this skill when a mistake would be costly, persistent, difficult to detect, or difficult to reverse.

Typical triggers include:

- architecture or system design
- API or abstraction boundaries
- code review involving non-trivial behavior
- refactors with behavioral or structural risk
- performance or optimization claims
- allocation, memory, latency, throughput, or bandwidth claims
- caching
- concurrency, async work, threading, locks, queues
- state machines and lifecycle management
- persistence and data migration
- networking and file I/O
- external SDK/API/framework/library selection
- platform-specific code
- build, CI, deployment, packaging, or infrastructure decisions
- security-sensitive behavior
- recovery, retry, cancellation, timeout, and failure handling
- expensive hardware or cloud decisions
- technical choices that create lock-in or long-lived technical debt

Usually skip full adversarial validation for:

- trivial DTOs
- obvious property accessors
- formatting-only edits
- mechanical renames
- isolated boilerplate with no meaningful behavioral choice

Use proportional depth. A small decision may need one strong challenge. A foundational architecture decision may need a full adversarial pass.

---

# Protocol

## 1. State the Proposition

Write the exact conclusion being evaluated in one falsifiable sentence.

Bad:

> This looks good.

Good:

> Using a persistent dictionary cache here reduces frame-time cost without introducing meaningful memory, invalidation, or lifecycle risk.

Do not validate a vague conclusion.

## 2. Separate Facts From Assumptions

Before attacking the conclusion, classify its foundations.

Use:

- **Confirmed** — directly supported by code, tests, measurements, logs, primary documentation, or observed behavior.
- **Inference** — strongly suggested but not directly demonstrated.
- **Unverified** — required for the conclusion but not yet demonstrated.
- **Rejected** — contradicted by evidence.

Pay special attention to assumptions that were silently converted into facts.

Examples:

- "This runs only on the main thread."
- "The collection stays small."
- "This API is stable."
- "Users will never call this twice."
- "This allocation is negligible."
- "This model will fit in memory."
- "This optimization improves the actual bottleneck."

### Version-Sensitive External Claims

When a conclusion depends on an externally maintained claim about an API, SDK, framework, library, version, feature flag, configuration default, availability, or supported behavior, distinguish:

- **Supported contract** — confirm it with current primary documentation or an explicit support or compatibility declaration in authoritative vendor source for the claimed version.
- **Observed behavior** — confirm it with a reproducible test against the actual pinned runtime/version in the claimed environment. Source code may explain the result but does not substitute for runtime reproduction.

Secondary sources, memory, plausibility, and unpinned tests are insufficient. If the evidence category required by a claim is unavailable, mark that claim and any dependent conclusion UNVERIFIED. Observed behavior does not prove vendor support or behavior outside the pinned version.

## 3. Find the Strongest Failure Case

Do not list ten weak objections.

Find the strongest realistic reason the conclusion could be wrong.

Attack, as relevant:

### Correctness
- incorrect state transitions
- invalid assumptions
- stale data
- partial failure
- order dependence
- null/missing/malformed input
- exception paths
- reentrancy

### Lifecycle
- initialization order
- enable/disable cycles
- destruction/disposal
- reload/reconnect
- scene/app/domain changes
- repeated invocation
- cleanup after partial initialization

### Concurrency
- races
- duplicate work
- deadlocks
- lock contention
- callbacks on unexpected threads
- cancellation races
- out-of-order completion

### Performance
- optimizing a non-bottleneck
- hidden copies/conversions
- cache misses
- synchronization cost
- allocation/GC pressure
- bandwidth limits
- CPU/GPU transfer cost
- warm-up cost
- pathological tail latency

### Scale
- 10x/100x input size
- long-running accumulation
- many users/connections/entities
- high event rate
- queue/backpressure growth
- resource exhaustion

### Platform/Environment
- mobile/VR/console differences
- OS/API version differences
- device limits
- driver/runtime differences
- sandbox/permission constraints

### Dependency Risk
- unsupported usage
- version-sensitive behavior
- undocumented assumptions
- vendor lock-in
- maintenance abandonment
- new-model/new-format incompatibility

### Operations
- observability
- rollback
- recovery
- migration
- deployment failure
- configuration drift

### Security
- trust boundaries
- input validation
- privilege assumptions
- secret exposure
- unsafe deserialization
- dependency attack surface

## 4. Construct the Strongest Competing Design

For a meaningful design decision, compare against the best realistic alternative, not a strawman.

Examples:

- no cache vs cache
- raw ComputeShader vs Sentis
- polling vs event-driven
- local state vs centralized state
- custom implementation vs mature library
- synchronous vs asynchronous
- GPU vs CPU
- existing architecture vs proposed abstraction

Steelman the competitor.

Ask:

> If a highly competent engineer rejected our proposal, what would they choose instead and why?

If no serious competing design exists, state why.

## 5. Identify the Decision-Reversing Evidence

Ask:

> What evidence would make us abandon the current conclusion?

This is mandatory.

If the answer is "nothing", the conclusion is not being validated; it is being defended.

Examples:

- profiler shows the target code is <1% of frame time
- cache hit rate is below 20%
- memory grows continuously across scene reloads
- competing implementation is 2x faster under the real workload
- SDK documentation explicitly marks the API unsupported
- stress test produces stale state after reconnection
- p99 latency violates the service requirement

## 6. Prefer Reality Over Argument

If a claim is measurable and the tools/environment allow measurement, measure it.

Preferred evidence order:

1. reproducible test or benchmark under the real workload
2. profiler / tracing / telemetry / logs
3. primary source documentation or source code
4. minimal reproduction
5. controlled experiment
6. strong inference
7. intuition

Do not replace an available benchmark with prose.

Do not use theoretical peak values when real workload measurements are available.

Do not compare mismatched conditions without clearly marking the comparison invalid or limited.

## 7. Test the Failure Path, Not Only the Happy Path

A passing normal-path test does not validate a design.

Where relevant, test:

- repeated execution
- partial initialization
- cancellation
- timeout
- disconnect/reconnect
- process interruption
- corrupted or missing data
- low memory/resource pressure
- invalid order of operations
- lifecycle teardown
- concurrent calls
- large inputs
- slow dependencies

## 8. Attack the Benchmark

Whenever a benchmark supports the conclusion, ask:

- Was the benchmark chosen because it favors this design?
- Are the workloads representative?
- Is the baseline the strongest realistic competitor?
- Are versions/configuration/precision/batch/context/input sizes equal?
- Are warm-up and caching controlled?
- Are averages hiding tail latency?
- Is peak/TDP/theoretical throughput being substituted for actual usage?
- Does the benchmark measure what users actually care about?
- Does the optimization survive when total-system cost is included?

Never generalize beyond the benchmark's actual scope.

## 9. Attack the Requirement Itself

Sometimes both the proposal and its competitor are solving the wrong problem.

Ask:

- Is this actually a bottleneck?
- Is this requirement still necessary?
- Can the problem be deleted rather than optimized?
- Can a simpler workflow avoid the entire class of complexity?
- Is the requested abstraction caused by an upstream design flaw?
- Are we paying complexity to support a hypothetical future that has no evidence?

## 10. Re-evaluate After the Attack

Use one of these verdicts:

### PASS
The strongest plausible objections were tested or convincingly resolved. Remaining risk is understood and acceptable.

### PASS WITH CONDITIONS
The design is acceptable only under explicit constraints. State them.

### UNVERIFIED
The conclusion may be correct, but an important assumption or claim could not be tested or confirmed.

**UNVERIFIED is not PASS.**

### REVISE
The proposal has value, but the adversarial pass found material weaknesses requiring changes.

### REJECT
A stronger alternative or a decisive failure invalidates the proposal.

---

# Required Output

For non-trivial validation, present the result compactly in this order:

## Proposition
The exact conclusion being tested.

## Strongest Countercase
The best realistic argument against it.

## Evidence
What is confirmed, inferred, unverified, or contradicted.

## Decision-Reversing Test
The test or observation most likely to change the verdict.

## Verdict
PASS / PASS WITH CONDITIONS / UNVERIFIED / REVISE / REJECT.

## Residual Risk
Only the important remaining risks.

Do not bury a failed assumption inside a generally positive review.

For a proportionate lightweight validation, preserve all six required elements but combine them into three sections:

## Proposition
State the original proposition and any required neutral reformulation.

## Challenge
Combine Strongest Countercase, Evidence, and Decision-Reversing Test.

## Verdict
State the verdict and Residual Risk.

Use the full six-section form for foundational, high-risk, or disputed decisions.

---

# Anti-Patterns

## Confirmation Cascade

Bad:

1. Proposal has advantage A.
2. Advantage A implies B.
3. B would be useful.
4. Therefore proposal is good.
5. Search for more reasons it is good.

Instead, after a provisional conclusion exists, switch immediately to falsification.

## IR-Pitch Review

Do not list only favorable metrics.

A technically true list of advantages can still imply a false overall conclusion when:

- the denominator is missing
- the competitor is weak
- the benchmark is cherry-picked
- the user/customer does not value the metric
- switching cost dominates the gain
- the claimed advantage disappears at system level

## Strawman Opposition

Do not manufacture weak objections merely to say adversarial validation was performed.

The challenge must be strong enough that a competent skeptic could reasonably hold it.

## Infinite Skepticism

Do not demand impossible certainty.

Once the strongest realistic objections are resolved and residual risks are proportionate, accept the conclusion.

## Verbal Benchmarking

Bad:

> This should be faster because it avoids allocations.

Good:

> Allocation should decrease. Verify with profiler and compare frame-time/p99 before accepting the optimization.

## Evidence Laundering

Do not transform:

- roadmap into shipment
- planned deployment into purchase order
- purchase order into recognized revenue
- theoretical peak into workload performance
- vendor benchmark into independent validation
- successful PoC into scalable production proof
- test coverage into correctness proof

Keep evidence categories separate.

---

# Coding-Specific Review Checklist

When validating generated or modified code, challenge at least the applicable items:

- Does it preserve existing behavior?
- What implicit preconditions were introduced?
- What happens on the second call?
- What happens after partial failure?
- What owns each resource?
- Who disposes/unsubscribes/cancels it?
- Can callbacks arrive after teardown?
- Are thread assumptions explicit?
- Can state become stale?
- Can work be duplicated?
- Is error handling observable?
- Does recovery return to a valid state?
- Is the code optimizing a measured bottleneck?
- Did complexity increase more than the measured benefit?
- Is there a simpler implementation?
- Is the new abstraction justified by current use cases?
- Does the implementation survive realistic platform constraints?
- What test would most likely break this code?

---

# Performance-Specific Rules

Never accept a performance conclusion from:

- asymptotic complexity alone
- peak FLOPS/TOPS
- TDP alone
- bandwidth specification alone
- allocation count alone
- a microbenchmark unrelated to the real workload

Require the metric relevant to the actual objective, such as:

- frame time
- p95/p99 latency
- throughput at an explicit SLO
- memory high-water mark
- GC pause time
- J/op or J/token
- total CPU/GPU time
- wall-clock completion time
- cost per completed task

Compare under equivalent conditions.

---

# Architecture-Specific Rules

For architecture decisions, always ask:

1. What failure mode does this architecture create that the simpler design does not?
2. What does the abstraction cost today?
3. Which current requirement pays for that cost?
4. What happens if the expected future requirement never arrives?
5. What is the migration/rollback path?
6. What vendor or framework assumption becomes hard to reverse?
7. What is the strongest simpler competing architecture?
8. What evidence shows the added complexity is necessary now?

Prefer reversible decisions when evidence is weak.

---

# Final Discipline

Never conclude that a design is good merely because no objection was immediately found.

Never treat plausibility as proof.

Never treat a current implementation as correct merely because it compiles or passes happy-path tests.

Never preserve the original conclusion out of politeness, sunk cost, or consistency with earlier advice.

If adversarial validation overturns the original conclusion, say so directly and update the recommendation.
