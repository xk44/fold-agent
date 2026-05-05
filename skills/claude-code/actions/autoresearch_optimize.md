---
name: autoresearch_optimize
description: Run autoresearch software pipeline optimization experiments via the FoldAgent autoresearch module.
action_type: write
primary_endpoint: POST /autoresearch/experiment/propose
framework: Claude Code
safety_gate: check_safety
---

# Action: Autoresearch Optimize

> **RESEARCH ONLY — NOT FOR CLINICAL USE**
>
> This action targets software pipeline performance metrics only. It must
> never be used to optimize clinical thresholds, safety gate pass rates,
> treatment parameters, or any metric with patient/animal implications.
> All experiments are sandboxed and automatically reverted on test failure.

## Purpose

Run an automated pipeline optimization experiment using the autoresearch
adapter. Proposes a small, verifiable change targeting a pre-approved
software metric, sandboxes the change in a git branch, runs the test suite,
and accepts the change only if all tests pass.

## Safety Disclaimers

- Only metrics from `GET /autoresearch/metrics` with `category: "allowed"` may
  be targeted. Verify with `GET /autoresearch/metrics/{metric_name}/allowed`
  before proposing.
- The autoresearch adapter's safety gate will block prohibited metrics. Do not
  attempt to circumvent this gate.
- If a proposal is blocked, surface the `block_reason` to the user and stop.
- No changes from autoresearch experiments may be applied to production
  pipelines handling real patient or animal data.

## API Endpoints

- `GET /autoresearch/metrics` — list all allowed and prohibited metrics
- `GET /autoresearch/metrics/{metric_name}/allowed` — check a specific metric
- `POST /autoresearch/experiment/propose` — propose an optimization experiment
- `POST /autoresearch/experiment/evaluate` — evaluate experiment results
- `GET /autoresearch/experiments` — view experiment history

## Steps

1. **Check metric is allowed**: Call
   `GET /autoresearch/metrics/{metric_name}/allowed`.
   - `allowed: true` → proceed
   - `allowed: false` → stop, inform user this metric is prohibited

2. **Propose experiment**: Call `POST /autoresearch/experiment/propose` with:

   ```json
   {"metric": "<metric_name>", "current_value": <baseline>}
   ```

   Check the response for `blocked: true`. If blocked, surface `block_reason`
   and stop.

3. **User confirmation**: Surface the `hypothesis` and `proposed_change` to
   the user and require explicit confirmation before any file modifications.

4. **Apply in sandbox**: Implement the proposed change in a sandboxed git
   branch. Run the full test suite. If any test fails, revert all changes.

5. **Evaluate**: Call `POST /autoresearch/experiment/evaluate` with the
   experiment ID and before/after measurements.
   - `recommendation: "accept"` → merge and record
   - `recommendation: "reject"` → revert and record failure
   - `recommendation: "inconclusive"` → surface to user for decision

6. **Check history**: Call `GET /autoresearch/experiments` to confirm the
   record was appended.

## Expected Output

- Proposal details: metric, hypothesis, proposed change
- Sandbox run result: test pass/fail, revert status
- Evaluation: improvement percentage, recommendation
- Experiment ID for audit reference

## Failure Handling

- Blocked proposal: surface `block_reason`, do not modify any files.
- Test failure: confirm all changes were reverted; report which tests failed.
- API unavailable: do not apply any changes; report the connectivity issue.

## Audit

All experiment proposals and evaluations are recorded in the experiment log.
Review via `GET /autoresearch/experiments`.
