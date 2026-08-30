---
name: trace-adversarial-validation
description: Explicitly audit a non-trivial technical plan or final result by comparing its observable reasoning and action process with the artifact and evidence, then trying to break the load-bearing steps. Use at one bounded Plan Gate or Result Gate when the user explicitly requests TRACE or explicitly includes process validation in Adversarial Validation. Work from plans, tool trajectories, diffs, tests, and decision records when raw chain-of-thought is unavailable. Do not run continuously, reconstruct hidden reasoning, create reviewer trees, or replace the requested deliverable with validation infrastructure.
---

# TRACE Adversarial Validation

## Purpose

TRACE extends Adversarial Validation from the external conclusion to the
observable process that produced it.

It answers two separate questions:

- **P-out** — does the plan or result survive the strongest realistic attack?
- **P-proc** — do the available process records actually support the claimed
  path from evidence to result?

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
After `REVISE`, allow one targeted recheck of the changed finding by default.
Further rounds require an explicit user request.

## Evidence Boundary

Use the strongest evidence actually available:

| Tier | Observable evidence | Supported claim |
|------|---------------------|-----------------|
| E0 | final artifact or answer only | P-out only; process remains unavailable |
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

## Reviewer Boundary

Use one fresh no-history, read-only TRACE reviewer when the host can provide
one. It replaces the independent reviewer allocated to the current
Adversarial Validation gate; it is not an additional reviewer tree.

Give the reviewer only:

- the original request and explicit user amendments needed for this gate;
- the proposed plan or final candidate;
- the relevant E0-E4 evidence and acceptance criteria; and
- the allowed output format.

Do not give it the Author's desired verdict, confidence, defense, or previous
failed rebuttals. Minimize private data and secrets in the review input. A
separate Analyst, Adversary, and Judge are research mode and require an explicit
user request; they are not the production default.

If a fresh reviewer is unavailable, perform the same bounded analysis inline
and mark reviewer independence `UNVERIFIED`. Do not build a new transport,
hook, privacy system, oracle framework, or runtime merely to make the review
look independent.

## Plan Gate

Audit the proposed approach, not a completed artifact.

1. Restate the requested outcome and the proposed artifact in one sentence
   each. If their artifact types or scopes differ without user approval, return
   `REVISE` before technical optimization.
2. Identify the strongest realistic competing approach.
3. Identify the one or two assumptions that carry most of the plan.
4. Apply **Step Kill**: if a load-bearing assumption is false or removed, does
   the plan still reach the requested outcome?
5. Name the decision-reversing observation or test that should be produced
   during implementation.
6. Return `PASS`, `PASS WITH CONDITIONS`, `UNVERIFIED`, `REVISE`, or `REJECT`
   for the plan only. A Plan Gate PASS is permission to execute the plan, not
   evidence that the final task is complete.

Stop after the gate result. Do not design or implement the artifact during the
review.

## Result Gate

Freeze the final candidate, relevant diff, test output, and observable process
record for this review. Then:

1. **Compact process map** — list only the load-bearing actions and decisions,
   their evidence, and dependencies. Do not transcribe the whole conversation.
2. **Alignment check** — find action/claim mismatches, assumptions promoted to
   facts, tool results reported incorrectly, ignored user corrections,
   unauthorized scope reduction, and work unrelated to the requested result.
3. **Step Kill** — choose the strongest load-bearing step. Invert or remove it
   conceptually. If P-out survives, P-proc for that claimed path fails and
   P-out needs independent evidence.
4. **Strongest countercase** — construct one realistic failure case or stronger
   competing design. Do not list many weak objections.
5. **Decision-reversing test** — run one bounded test when practical. Prefer
   the real workload, failure path, profiler, logs, primary source, or minimal
   reproduction. Otherwise mark the dependent claim `UNVERIFIED`.
6. **Separate verdicts** — judge P-out and P-proc independently. A coherent
   process cannot prove a wrong artifact, and a correct artifact can survive a
   rejected rationale only through independent evidence.

When paired with `adversarial-validation`, that Skill still owns P-task and the
overall completion verdict. TRACE evidence may lower or condition that verdict;
it cannot raise completion above an unmet P-task.

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

For a Plan Gate, use the lightweight form:

1. **Proposition** — requested outcome and proposed approach.
2. **Challenge** — strongest competitor, Step Kill, evidence status, and
   decision-reversing test.
3. **Gate Verdict** — plan verdict and the one important residual risk.

For a Result Gate, use:

1. **Proposition** — P-out and P-proc.
2. **Process Map** — compact load-bearing steps and evidence status.
3. **Strongest Countercase** — including Step Kill.
4. **Evidence** — Confirmed / Inference / Unverified / Contradicted.
5. **Decision-Reversing Test** — whether it ran and what happened.
6. **Verdict** — P-out and P-proc separately, plus only material residual risk.

## Verdict Rules

P-out uses:

- `PASS`
- `PASS WITH CONDITIONS`
- `UNVERIFIED`
- `REVISE`
- `REJECT`

P-proc uses `PASS`, `UNVERIFIED`, or `REJECT`.

- `UNVERIFIED` is not PASS.
- P-proc `REJECT` does not automatically reject P-out; independent evidence may
  still support the result.
- E0 cannot produce P-proc PASS.
- E1/E2 cannot support internal-mechanism or raw-CoT faithfulness claims.
- A test of a substituted artifact cannot establish completion of the requested
  artifact.
- A single successful case cannot establish that TRACE improves difficult-task
  accuracy in general.

## Regression Scenarios

When revising this Skill, forward-test at least these behaviors:

1. A difficult simulator request is replaced by a small numerical library or
   toy task. TRACE must flag the artifact mismatch even if local tests pass.
2. A task contains many consequential intermediate decisions. Review occurs at
   the Plan Gate and Result Gate only, with no reviewer storm.
3. Tool output contradicts the Author summary. Runtime evidence wins.
4. Raw CoT is absent but plans, actions, and tests exist. TRACE performs an
   observable-process audit without claiming CoT faithfulness.
5. The final answer is correct but its rationale is decorative or false. P-out
   may survive while P-proc is rejected.
6. The same controller selects the easier task, authors the oracle, and reports
   all-pass. TRACE flags evaluator capture instead of calling it success.

Passing this finite set is regression evidence only, not proof that TRACE
improves reasoning accuracy or catches every future failure.
