# Autoresearch Module

> **RESEARCH ONLY — NOT FOR CLINICAL USE**
>
> This module is strictly experimental. No output from autoresearch may be used
> to guide clinical decisions, treatment planning, dosage selection, or patient/
> animal management of any kind.

## What Is Autoresearch?

Autoresearch is an automated pipeline optimization system inspired by Karpathy's
autoresearch concept: an agent-driven loop that proposes small, measurable
changes to software parameters, runs experiments in a sandboxed environment,
measures outcomes against pre-approved metrics, and retains changes only when
tests pass.

In FoldAgent, autoresearch targets **software pipeline performance** — things
like execution speed, memory efficiency, cache hit rates, and test coverage. It
does not touch scientific thresholds, clinical parameters, or safety gates.

## Safety Boundaries

### What Autoresearch CAN Do

- Optimize pipeline execution time and memory usage
- Improve cache hit rates and prediction throughput
- Increase test pass rate and code coverage
- Tune step success rates for mock/synthetic workloads
- Improve annotation completeness on synthetic data

### What Autoresearch MUST NEVER Do

- Modify binding affinity thresholds (what counts as a "good" neoantigen)
- Adjust clinical outcome targets or treatment efficacy metrics
- Change survival rate baselines or endpoints
- Alter patient or animal selection criteria
- Modify dosage, treatment, or formulation parameters
- Game or lower safety gate pass rates
- Optimize against any metric with clinical significance

These prohibitions are enforced programmatically in `config.py` and checked by
`AutoresearchAdapter.is_safe()` before any experiment is proposed or executed.

## Sandbox Model

All experiments run inside a `GitSandbox`:

1. A temporary git branch is created before any file changes.
2. All modifications are tracked.
3. If tests fail, the sandbox automatically reverts all changes and returns
   to the base branch.
4. No changes persist unless the full test suite passes.

## Karpathy Reference

The design follows Andrej Karpathy's autoresearch framing: automated agents
should propose small, verifiable hypotheses; run them against objective
benchmarks; and integrate only what strictly improves measurable outcomes.
The key guard rails are: (1) only optimize what you can measure safely, and
(2) never let the optimizer redefine the measurement criteria.

## Experiment Log

Every experiment is recorded in `experiment_log.json` with before/after values,
test results, and revert status. This log is append-only and must never be
deleted, as it forms an audit trail.

## Usage

```python
from research_modes.autoresearch.adapter import AutoresearchAdapter
from research_modes.autoresearch.benchmark import run_benchmark

# Run baseline benchmark
result = run_benchmark(api_base="http://localhost:8000")

# Propose an experiment (safety-gated)
adapter = AutoresearchAdapter()
proposal = adapter.propose_experiment("pipeline_execution_time_s", current_value=12.4)

if adapter.is_safe(proposal):
    # ... apply and test in sandbox
    pass
```

## Disclaimer

This module is for research infrastructure optimization only. It has no
awareness of, and must not be connected to, live patient data, clinical
workflows, or treatment decision systems.
