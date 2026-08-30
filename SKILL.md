---
name: adversarial-validation
description: "Adversarially validate non-trivial technical work at two bounded task-level gates: once before committing to a consequential plan and once after a final candidate exists. Ground completion claims in the original request and approved scope changes, then try to break the plan or result with the strongest plausible alternative, counterexample, hidden assumption, failure mode, or falsifiable test. Use for architecture, code review, performance, concurrency, caching, persistence, security, infrastructure, deployment, and other costly-to-reverse decisions. Do not continuously re-review routine implementation steps or use for trivial getters, DTOs, formatting, or mechanical edits."
---

# Adversarial Validation

## Purpose

Prevent confirmation cascades in technical work.

A coherent explanation, a passing happy-path test, or a list of advantages is not validation.

At an enabled plan or result gate, stop accumulating reasons that support the
current proposal. Change roles from author to hostile reviewer and attempt to
falsify it.

The goal is **not** to reject the proposal.

The goal is:

> Make rejection maximally plausible using the strongest realistic evidence and see whether the proposal survives.

Do not oppose for the sake of opposition. Do not invent absurd edge cases merely to create objections.

## Core Rule

At each enabled task-level gate:

> Do not continue supporting the current conclusion. Find the strongest plausible argument, competing design, counterexample, benchmark, or failure mode that could break it.

If a challenge is measurable, do not resolve it by argument when it can reasonably be resolved by measurement.

Do not open a new adversarial review for every intermediate decision. Review
the plan, let the Author implement it, then review the completed candidate.

## Review Timing and Budget

This timing rule replaces continuous or per-conclusion review.

1. **Plan Gate** — after a concrete approach and acceptance evidence are
   proposed, but before substantial implementation. Run one bounded review of
   the plan, its strongest realistic alternative, and its decision-reversing
   test.
2. **Implementation Window** — execute the accepted plan without new
   adversarial reviewers. Routine design choices, tool calls, test failures,
   and fixes stay inside the Author loop. Re-open the Plan Gate only when the
   user changes the task, the planned artifact type changes, or new evidence
   invalidates a load-bearing plan assumption.
3. **Result Gate** — after one final candidate, diff, or decision package
   exists. Run one bounded review against the original task and the evidence
   produced by the implementation.
4. **Targeted Recheck** — after `REVISE`, review only the changed finding and
   its affected claims. Do not restart the entire attack. Allow one targeted
   recheck by default; further rounds require an explicit user request.

Reserve the Result Gate. Never consume its review by spawning reviewers for
intermediate conclusions. A user-requested mid-work review is allowed, but it
does not silently replace the final review.

## Task Grounding Invariant

Adversarial review is independent only when both the reviewer and the proposition
are grounded independently of the Author's success narrative. A fresh reviewer
given an altered task contract can independently validate the wrong task.

Before reviewing a task-completion claim, bind the review to a **source-grounded
task contract** created from authoritative inputs that existed before the
Author's defense:

- the relevant original user request or authoritative specification, preserved
  verbatim or by lossless source reference;
- explicit constraints and acceptance criteria, each traceable to its source;
- chronological user-authored scope amendments;
- whether each amendment approves an intermediate milestone, defers work, or
  replaces the effective task scope; and
- the artifact or answer whose completion claim is being reviewed.

An Author-written proposition, requirement summary, completion report, memory,
roadmap, or rationale is a claim under review. It is not evidence that the user
requested, approved, changed, or received that scope. Technical evidence can
establish that a narrower artifact works; it cannot establish that the user
authorized narrowing the task.

If the relevant source request is unavailable, provenance is missing, or a
material scope ambiguity cannot be resolved from authoritative inputs, return
`INVALID REVIEW INPUT` and do not issue PASS. Ask the user when their choice is
needed. Keep private request text private; pass only the minimum necessary
content to the reviewer and do not publish it in review artifacts.

## Independent Review Escalation

Inline falsification is the default at each enabled gate.

At the Plan Gate or Result Gate:

- if the user explicitly requests independent or adversarial review, spawn
  exactly one independent reviewer for that gate regardless of the Author's
  risk classification
- otherwise, for a non-trivial plan or result, spawn exactly one independent
  reviewer for that gate when the host explicitly indicates Max or Ultra, or
  when applicable project, agent, or task instructions require independent
  validation

An explicit request is always a sufficient escalation condition. For
non-trivial gate artifacts, Max/Ultra is also sufficient; do not require the
Author to classify the decision as high risk first. If the current reasoning
tier is not exposed, do not infer it from task complexity; a host or profile
that wants Max/Ultra escalation must provide an explicit model-visible
instruction.

Do not spawn independent reviewers during the Implementation Window merely
because a consequential subdecision appeared. Do not create reviewer trees or
let a reviewer spawn another reviewer.

When escalation is triggered by Max/Ultra, use a reviewer at Max/Ultra if supported. Otherwise use the strongest available reviewer and disclose the downgrade.

The reviewer must:

- be freshly created for each proposition in a no-history context (`fork_turns="none"` or the host equivalent), not reused from any prior review or created from a default or full-history fork, and remain read-only
- receive the source-grounded task contract, the separately labeled Author proposition, raw evidence or artifact references, and decision criteria; do not replace authoritative source material with an Author summary
- first compare the Author proposition and artifact scope with the effective task contract; when the proposition is biased, ambiguous, or artificially narrow, state both `P-task` for original-task fulfillment and a neutral `P-tech` for technical correctness within the claimed scope
- treat a milestone as full scope only when an authoritative user amendment explicitly replaces the task; "do this first" or approval of an intermediate prototype does not silently cancel the remaining task
- not receive the author's reasoning, defense, desired verdict, confidence, or prior failed rebuttals
- construct the strongest realistic countercase and decision-reversing test
- not edit files, implement fixes, or spawn further agents

The same raw evidence may be shared. Independence comes from withholding the author's reasoning and desired conclusion, not from withholding relevant facts.

The main agent owns the final verdict, but must not make the final decision more favorable than the reviewer's result unless it cites new decision-relevant evidence the reviewer did not consider and explains which exact countercase or failed assumption that evidence resolves. A more favorable decision includes raising the verdict, dropping or weakening conditions, reducing stated risk, expanding approved scope or rollout, or strengthening an implementation or deployment recommendation. Author summaries, restated requirements, post-hoc success narratives, and technical evidence about a narrower artifact cannot override a task-scope failure. If new evidence changes the task contract, approved scope, or artifact identity, run a fresh no-history delta review bound to the new authoritative source and artifact before raising the verdict. Record the reviewer's original verdict, the source-bound evidence, the delta-review result, and any unresolved disagreement in Residual Risk.

If the host cannot create a fresh no-history reviewer, do not simulate or claim independent review. Perform inline falsification when possible and leave required independent validation UNVERIFIED. Reviewer failure or timeout is never evidence of PASS.

### Optional TRACE Expansion

`trace-adversarial-validation` is a separate, explicit-only Skill for auditing
the observable reasoning and action process behind a plan or result. Activate
it only when the user explicitly requests TRACE or explicitly includes process
validation in the current gate.

TRACE replaces the one independent reviewer allocated to that gate; it does
not add an Analyst, Adversary, and Judge tree on top of the baseline reviewer.
The main agent still owns the final Adversarial Validation verdict. Do not
activate TRACE implicitly from task difficulty alone.

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

## 0. Ground the Task Contract

Before reading or validating the Author's completion narrative:

1. Identify the authoritative source request and every relevant user-authored
   amendment in chronological order.
2. Derive the effective requirements with source references. Mark material
   ambiguity instead of silently selecting the easier interpretation.
3. Distinguish an approved intermediate milestone from an explicit replacement
   of the full task.
4. Bind the effective contract, candidate artifact, and completion claim to the
   same review.
5. Compare the artifact's declared and implemented scope with that contract.

For completion reviews, state two propositions when they differ:

- **P-task** — the artifact fulfills the effective user task.
- **P-tech** — the artifact or conclusion is technically correct within its
  actual, possibly narrower, scope.

An unauthorized scope substitution rejects P-task even when P-tech survives.
Do not let a local test, useful prototype, or internally coherent subsystem
raise the task-fulfillment verdict. Continue technical review only to report
the narrower artifact's actual value and defects.

## 1. State the Proposition

Write the exact conclusion being evaluated in one falsifiable sentence.

Bad:

> This looks good.

Good:

> Using a persistent dictionary cache here reduces frame-time cost without introducing meaningful memory, invalidation, or lifecycle risk.

Do not validate a vague conclusion. Do not let an Author-supplied P-tech replace
P-task. When no task-completion claim is involved, state only the relevant
technical proposition.

## 2. Separate Facts From Assumptions

Before attacking the conclusion, classify its foundations.

Use:

- **Confirmed** — directly supported by code, tests, measurements, logs, primary documentation, or observed behavior.
- **Inference** — strongly suggested but not directly demonstrated.
- **Unverified** — required for the conclusion but not yet demonstrated.
- **Rejected** — contradicted by evidence.

Classify Author-produced summaries, status labels, requirement restatements,
and rationales as claims, not evidence of the task contract or artifact truth.

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

## 9. Challenge the Requirement Without Rewriting It

Sometimes both the proposal and its competitor are solving the wrong problem.

This step may recommend a simpler requirement or deletion to the user. It does
not change the effective task contract, excuse non-fulfillment, or authorize the
reviewer to grade a different task. Until the user explicitly approves a scope
replacement, evaluate P-task against the existing contract and record the
simpler alternative separately.

Ask:

- Is this actually a bottleneck?
- Is this requirement still necessary?
- Can the problem be deleted rather than optimized?
- Can a simpler workflow avoid the entire class of complexity?
- Is the requested abstraction caused by an upstream design flaw?
- Are we paying complexity to support a hypothetical future that has no evidence?

## 10. Re-evaluate After the Attack

For task-completion reviews, report P-task independently of P-tech. The overall
completion result cannot be more favorable than P-task. A PASS for P-tech means
only that the narrower technical proposition survived; it is not task success.

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
State task-contract validity and scope provenance. For completion claims, state
P-task and P-tech separately. If the source-grounded contract is unavailable,
return `INVALID REVIEW INPUT` and stop before a technical verdict can be
presented as task success.

## Strongest Countercase
The best realistic argument against it.

## Evidence
What is confirmed, inferred, unverified, or contradicted.

## Decision-Reversing Test
The test or observation most likely to change the verdict.

## Verdict
PASS / PASS WITH CONDITIONS / UNVERIFIED / REVISE / REJECT. For completion
reviews, give separate P-task and P-tech verdicts and state that the overall
completion result is bounded by P-task.

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

Instead, switch to falsification at the enabled Plan Gate or Result Gate.

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
- an Author-written requirement summary into the user's actual request
- approval of an intermediate milestone into replacement of the full task
- a passing subsystem or narrow prototype into fulfillment of the original task
- technical correctness within reduced scope into authorization to reduce scope
- a post-hoc completion narrative into new decision-relevant evidence

Keep evidence categories separate.

## Scope Laundering

Do not make a hard request easier and then validate only the substituted task.
This remains a failure when the substituted artifact is useful, well tested, or
accurately documented as limited.

Bad:

1. User requests a production system or a stated fidelity target.
2. Author silently chooses a prototype or easier proxy.
3. Prototype-local checks pass.
4. Review reports the original task as successful.

Correct handling:

- reject or revise P-task for unauthorized narrowing;
- evaluate the prototype under P-tech only;
- ask whether the user wants to approve the narrower milestone or restore the
  original scope.

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

Never treat the Author's reframing as user approval. Never call a task complete
because a different, easier task was completed correctly.

If adversarial validation overturns the original conclusion, say so directly and update the recommendation.

## Behavioral Regression for This Skill

When validating changes to this Skill, include both timing and
framing-invariance tests.

Timing regression:

- use a task with several consequential intermediate decisions;
- require one Plan Gate review and one Result Gate review;
- require zero independent reviewer calls during the Implementation Window;
- after `REVISE`, allow only one targeted recheck of the affected finding; and
- when TRACE is explicitly enabled, require it to replace rather than add to
  the independent reviewer allocated to that gate.

Any routine intermediate reviewer call, recursive reviewer, missing reserved
Result Gate, or implicit TRACE activation requires `REVISE`.

Framing-invariance regression:

- keep the authoritative request, amendments, artifact, and measurements fixed;
- vary only the Author narrative between favorable, neutral, and unfavorable;
- require the same P-task verdict in every variant; and
- include controls for a user-approved intermediate milestone and an explicit
  user-approved scope replacement.

Any critical false accept, any success path without authoritative task-source
provenance, or any narrative-dependent P-task verdict requires REVISE. Passing
this finite suite is scoped regression evidence, not proof against all framing
attacks.
