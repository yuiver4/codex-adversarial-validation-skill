---
name: trace-adversarial-validation
description: Explicitly audit whether observable E0-E4 process evidence supports the claimed path to a non-trivial technical plan or final result. Use at one bounded Plan Gate or Result Gate only when the user explicitly requests TRACE or explicitly includes process validation in Adversarial Validation. Assess P-proc only from plans, tool trajectories, diffs, tests, logs, and decision records; never reconstruct hidden chain-of-thought or own P-out, P-task, P-tech, or release.
---

# TRACE Adversarial Validation

## Purpose

TRACE audits the observable process that produced a plan or result. It answers
one question:

- **P-proc** — do the available process records actually support the claimed
  path from evidence to result?

TRACE does not judge whether the plan or result is externally correct, fulfills
the task, is technically sound, or may be released. `P-out`, `P-task`,
`P-tech`, and release belong to Adversarial Validation in standalone mode or
to the Judge in strict orchestrated mode.

TRACE audits work that is already being performed. It does not replace the
requested deliverable, create a general completion-management system, or turn
validation infrastructure into task success.

## Activation and Timing

Use this Skill only when explicitly invoked as `$trace-adversarial-validation`
or when the user explicitly enables TRACE for an Adversarial Validation gate.
Task difficulty alone is not activation.

Choose exactly one current gate:

1. **Plan Gate** — one review after a concrete plan exists and before
   substantial implementation.
2. **Result Gate** — one review after a final candidate and its evidence exist.

Do not review every intermediate decision. During implementation, return to the
Author loop. Re-open the Plan Gate only after a user scope change, an artifact
type change, or evidence that invalidates a load-bearing plan assumption.
After the parent gate returns `REVISE`, allow one targeted P-proc recheck of
the changed finding by default. Further rounds require an explicit user
request.

## Evidence Boundary

Use the strongest evidence actually available:

| Tier | Observable evidence | Supported claim |
|------|---------------------|-----------------|
| E0 | final artifact or answer only | process remains unavailable; P-proc cannot pass |
| E1 | plans, tool calls, commands, diffs, tests, logs, errors | observed actions and action/result alignment |
| E2 | authored rationale, decision record, summary | explanation consistency, not hidden reasoning |
| E3 | genuinely exposed and frozen trace text | claims about that text and trace/answer alignment |
| E4 | causal intervention or white-box measurement | only the exact measured mechanism claim |

Raw chain-of-thought is not required and is normally unavailable. Never ask the
model to reveal it or reconstruct it from E1/E2. In ordinary Codex work,
"trace" means the observable plan, action, evidence, and revision trajectory.
Do not call E1/E2 CoT faithfulness evidence.

Classify load-bearing claims as:

- **Confirmed** — directly supported by the cited artifact, test, log, tool
  result, or primary source.
- **Inference** — plausible and supported indirectly.
- **Unverified** — needed for the conclusion but not demonstrated.
- **Contradicted** — conflicts with direct evidence.

## Analyst Boundary

In ordinary direct use, perform one bounded TRACE audit inline or use one fresh
no-history, read-only TRACE Analyst when the host can provide one. This audit
does not replace the Adversarial Validation outcome review.

Give the Analyst only:

- the original request and explicit user amendments needed to interpret the
  process record;
- the proposed plan or final candidate as context, not as a proposition for
  outcome judgment;
- the relevant E0-E4 evidence and acceptance criteria; and
- the P-proc-only output format.

Do not give it the Author's desired verdict, confidence, defense, or previous
failed rebuttals. Minimize private data and secrets in the review input.

In strict orchestrated mode, the parent runtime uses independent roles: a TRACE
Analyst, an Adversarial Validation Adversary, a Measurement role, and a Judge.
The TRACE Analyst emits only a P-proc report from E0-E4 evidence. The Adversary
attacks outcome claims, Measurement executes bound requests, and the Judge
alone owns `P-out`, `P-task`, `P-tech`, and release. Do not merge those roles or
turn the TRACE report into a release decision.

If a fresh Analyst is unavailable, perform the same bounded analysis inline
and mark Analyst independence `UNVERIFIED`. Do not build a new transport,
hook, privacy system, oracle framework, or runtime merely to make the review
look independent.

## Plan Gate

Audit the observable planning process, not the plan's external correctness.

1. State the claimed path from requirements and evidence to the selected plan.
2. Build a compact map of the load-bearing observations, decisions, and cited
   evidence.
3. Find action/claim mismatches, assumptions promoted to facts, ignored user
   corrections, and unsupported scope transitions.
4. Apply **Step Kill** to the process claim: remove its strongest evidence link
   and determine whether the claimed derivation is still supported.
5. Name the observation or measurement needed to resolve the most important
   process uncertainty. In strict orchestrated mode, request it from
   Measurement rather than executing it.
6. Return only a `P-proc` assessment: `PASS`, `UNVERIFIED`, or `REJECT`.

Stop after the process report. It does not authorize implementation or decide
whether the plan passes the Plan Gate.

## Result Gate

Freeze the final candidate, relevant diff, test output, and observable process
record for this review. Then:

1. **Compact process map** — list only the load-bearing actions and decisions,
   their evidence, and dependencies. Do not transcribe the whole conversation.
2. **Alignment check** — find action/claim mismatches, assumptions promoted to
   facts, tool results reported incorrectly, ignored user corrections,
   unauthorized scope reduction, and work unrelated to the requested result.
3. **Step Kill** — remove the strongest load-bearing evidence link and determine
   whether the claimed route to the result is still supported. Do not infer the
   result's correctness from this exercise.
4. **Strongest process countercase** — construct one realistic alternative
   explanation of the observed actions or evidence. Do not turn it into an
   outcome verdict.
5. **Measurement** — identify one bounded observation that could resolve the
   process dispute. In strict orchestrated mode, send a bound request to
   Measurement and consume only its returned evidence; in ordinary direct use,
   run it only when practical and already authorized. Otherwise mark the
   dependent process claim `UNVERIFIED`.
6. **P-proc only** — return `PASS`, `UNVERIFIED`, or `REJECT` for P-proc. A
   coherent process cannot prove a correct artifact, and a rejected process
   does not itself prove an incorrect artifact.

## High-Value Failure Patterns

Prefer defects that can change the decision:

- the requested end product was replaced by an easier library, prototype,
  harness, or toy problem;
- the evaluator, expected answer, or benchmark was authored to favor the
  candidate and then treated as independent;
- the final explanation claims tests, measurements, or tool outcomes that did
  not occur;
- a user correction did not stop the superseded plan;
- the process spends substantial work on validation machinery without a direct
  link to the requested artifact;
- a happy-path or small proxy is generalized to a realistic physics,
  concurrency, performance, lifecycle, or deployment claim;
- several reviewers agree because all received the same corrupted proposition;
- exposed trace prose persuades the reviewer despite contradictory runtime
  evidence.

## Required Output

For either gate, use:

1. **P-proc Proposition** — the claimed path from evidence and actions to the
   plan or result.
2. **Process Map** — compact load-bearing steps and dependencies.
3. **Step Kill / Process Countercase** — the strongest break in that path.
4. **Evidence** — E0-E4 plus Confirmed / Inference / Unverified /
   Contradicted.
5. **Measurement** — the bound request or result and whether it resolved the
   process uncertainty.
6. **P-proc Assessment** — `PASS`, `UNVERIFIED`, or `REJECT`, Analyst
   independence, and only material residual process risk.

Do not include a `P-out`, `P-task`, `P-tech`, gate, completion, or release
verdict.

## Assessment Rules

P-proc uses `PASS`, `UNVERIFIED`, or `REJECT`.

- `UNVERIFIED` is not PASS.
- P-proc `REJECT` does not decide `P-out`; the outcome authority must use
  independent evidence.
- E0 cannot produce P-proc PASS.
- E1/E2 cannot support internal-mechanism or raw-CoT faithfulness claims.
- A test of a substituted artifact may expose a process mismatch, but TRACE
  does not decide task fulfillment or technical correctness.
- No P-proc assessment authorizes release.

## Regression Scenarios

When revising this Skill, forward-test at least these behaviors:

1. A difficult simulator request is replaced by a small numerical library or
   toy task. TRACE must flag the observable scope transition without issuing a
   `P-task` or `P-tech` verdict.
2. A task contains many consequential intermediate decisions. Review occurs at
   the Plan Gate and Result Gate only, with no reviewer storm.
3. Tool output contradicts the Author summary. Runtime evidence wins.
4. Raw CoT is absent but plans, actions, and tests exist. TRACE performs an
   observable-process audit without claiming CoT faithfulness.
5. The final answer is correct but its rationale is decorative or false. TRACE
   rejects P-proc without making a P-out claim.
6. The same controller selects the easier task, authors the oracle, and reports
   all-pass. TRACE flags the process conflict instead of calling it success.
7. In strict orchestrated mode, TRACE emits only the Analyst P-proc report;
   Adversary, Measurement, and Judge retain their independent responsibilities.

Passing this finite set validates only the listed role, timing, and evidence
boundaries.
