# Adversarial Validation Skill for Codex

A Codex Skill for challenging high-impact technical conclusions before they are accepted.

It is designed to catch both ordinary technical failures and **scope laundering**: completing an easier substitute, validating that substitute, and then reporting the original task as complete.

## What it changes

- Grounds completion reviews in the original request, authoritative specifications, and explicit user amendments.
- Separates **P-task** (was the requested task fulfilled?) from **P-tech** (is the implemented, possibly narrower artifact technically sound?).
- Treats Author-written summaries, success labels, and post-hoc rationales as claims rather than task-authority evidence.
- Requires a fresh no-history reviewer when independent review is triggered.
- Searches for the strongest realistic countercase and decision-reversing test.
- Prefers measurements, runtime evidence, logs, tests, and primary documentation over verbal defense.
- Returns `INVALID REVIEW INPUT` instead of PASS when the authoritative task source or material scope is unavailable.

The overall completion verdict cannot be more favorable than P-task. A useful or correct prototype is not proof that the original task was completed.

## Install

Ask Codex to install the Skill from this repository:

```text
Use $skill-installer to install the adversarial-validation skill from this repository.
```

For a manual Git-managed installation, clone the repository into the global Skill directory used by your agent host. For example:

```bash
git clone <repository-url> "$HOME/.agents/skills/adversarial-validation"
```

Codex detects installed or changed Skills automatically. If the Skill does not
appear, restart Codex.

## Use

Invoke the Skill after a non-trivial proposal or conclusion exists:

```text
Use $adversarial-validation to review this implementation.
Bind the review to the original request and approved scope changes, then try to falsify it.
```

Typical uses include architecture, code review, performance, concurrency, caching, persistence, security, SDK selection, deployment, and other costly-to-reverse decisions.

## Verdicts

- `PASS`
- `PASS WITH CONDITIONS`
- `UNVERIFIED`
- `REVISE`
- `REJECT`

For completion claims, report P-task and P-tech separately. `UNVERIFIED` is not PASS.

## Required regression coverage

Before accepting a revision to this Skill, test it against:

- favorable, neutral, and unfavorable Author framing with identical underlying evidence;
- an approved intermediate milestone that does not replace the full task;
- an explicit user-approved scope replacement; and
- missing authoritative task sources.

These are finite regression requirements, not proof that every framing or
reviewer-isolation attack is impossible. This repository does not currently
provide comparative evidence that the Skill improves difficult-task accuracy,
false-accept rate, latency, or cost.

## Limitations

- This Skill is an adversarial review protocol, not a correctness oracle.
- Prompt-level no-history separation does not cryptographically prove reviewer independence or speaker identity.
- Technical evidence for a narrower artifact cannot prove that the user authorized the narrower scope.
- Keep private requests, credentials, internal specifications, and unpublished evidence out of public review artifacts.

The complete protocol is in [SKILL.md](SKILL.md).

## 한국어 요약

이 Skill은 기술적으로 맞는 축소 구현을 원래 과업의 성공으로 잘못 승인하는 문제를 막기 위해, 원 요청 이행 여부인 **P-task**와 좁은 구현의 기술적 타당성인 **P-tech**를 분리합니다. 원 요청이나 승인된 범위 변경을 확인할 수 없으면 PASS 대신 `INVALID REVIEW INPUT`으로 종료합니다.
