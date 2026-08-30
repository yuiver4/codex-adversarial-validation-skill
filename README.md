# Adversarial Validation + TRACE for Codex

This repository contains two complementary Codex Skills:

- **`adversarial-validation`** — challenges a consequential technical plan once
  before implementation and challenges the final candidate once after the work
  is complete.
- **`trace-adversarial-validation`** — an explicit-only extension that audits
  the observable reasoning and action process behind one of those gates.

The Skills are designed to catch ordinary technical failures, scope
substitution, evaluator capture, and cases where a persuasive explanation is
not supported by the actual actions or evidence.

## Workflow

```text
concrete plan
    -> Plan Gate: one adversarial review
    -> implementation without repeated reviewer calls
    -> final candidate + tests/evidence
    -> Result Gate: one adversarial review
    -> one targeted recheck only after REVISE
```

TRACE does not add a permanent Analyst/Adversary/Judge tree. When explicitly
enabled, it uses the single reviewer allocated to that gate and adds process
analysis, Step Kill, and separate P-out/P-proc verdicts.

## Why two Skills?

`adversarial-validation` answers whether the plan or result survives the
strongest realistic countercase.

`trace-adversarial-validation` additionally asks whether the available process
record supports the claimed route to that result. It can work from observable
plans, tool calls, diffs, tests, logs, and decision records. Raw
chain-of-thought is neither required nor reconstructed.

Keeping TRACE independent makes its additional cost and evidence boundary
explicit. It is not activated merely because a task is difficult.

## Install

Ask Codex to use `$skill-installer` for the paths in this repository.

Install the baseline Skill from the repository root:

```text
Use $skill-installer to install adversarial-validation from
yuiver4/codex-adversarial-validation-skill, path ., with the name
adversarial-validation.
```

Install TRACE separately:

```text
Use $skill-installer to install trace-adversarial-validation from
https://github.com/yuiver4/codex-adversarial-validation-skill/tree/main/trace-adversarial-validation
```

A freshly installed Skill is available on the next Codex turn. The installer
does not overwrite an existing destination; updating an existing installation
requires a separately chosen replacement or Git-managed workflow. TRACE is
configured with `allow_implicit_invocation: false`.

## Use

Baseline plan review:

```text
Use $adversarial-validation on this implementation plan. Review it once before
implementation and reserve the final review for the completed result.
```

Final review with TRACE:

```text
Use $adversarial-validation and explicitly enable
$trace-adversarial-validation for the Result Gate. Compare the observable
process with the final artifact and tests, then try to kill the load-bearing
steps.
```

TRACE may also be invoked directly for a bounded Plan Gate or Result Gate.

## Verdicts

Adversarial Validation uses:

- `PASS`
- `PASS WITH CONDITIONS`
- `UNVERIFIED`
- `REVISE`
- `REJECT`

For completion claims, the baseline Skill separates **P-task** (the requested
task was fulfilled) from **P-tech** (the produced artifact is technically sound
within its actual scope).

TRACE separates **P-out** (the external conclusion or artifact survives) from
**P-proc** (the available process evidence supports the claimed reasoning
path). A P-proc failure does not automatically reject a result that has
independent evidence.

## Evidence boundary

- A useful prototype is not proof that a broader requested product was
  completed.
- A correct final answer is not proof that its explanation was faithful.
- Observable actions and authored summaries are not raw chain-of-thought.
- Reviewer separation is only as strong as the host isolation actually used.
- A passing finite regression set is not proof that either Skill improves
  difficult-task accuracy in general.
- Keep credentials, personal data, private requests, and unpublished artifacts
  out of public review material.

## Repository layout

```text
SKILL.md                              # adversarial-validation
trace-adversarial-validation/
  SKILL.md                            # TRACE
  agents/openai.yaml                  # explicit-only activation
```

The full protocols are in [SKILL.md](SKILL.md) and
[trace-adversarial-validation/SKILL.md](trace-adversarial-validation/SKILL.md).

## Validation

Before accepting a revision:

1. Run the Skill structural validator on both Skill directories.
2. Forward-test plan-only, implementation-window, final-result, and targeted
   recheck timing.
3. Test a scope-substituted artifact that passes its local tests.
4. Test an observable process whose summary conflicts with its tool output.
5. Confirm that TRACE remains usable without raw chain-of-thought and does not
   claim internal faithfulness.

These checks validate the documented behavior boundaries. Comparative accuracy,
false-accept rate, latency, and token cost still require a separate controlled
evaluation rather than a single anecdotal success.
