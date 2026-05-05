# Contributing to NeoVax-Agent

Thank you for your interest in contributing. Please read this document carefully
before submitting any code, documentation, or skill packs.

## Safety Review Requirement

**All contributions must pass safety review before merge.**

Because this project deals with cancer research coordination, we have strict
safety boundaries. Contributions that violate the [SAFETY_POLICY.md](SAFETY_POLICY.md)
or [ETHICS.md](ETHICS.md) will be rejected.

### Prohibited Contributions

- DIY vaccine manufacturing instructions
- Injection or dosing instructions
- LNP formulation instructions
- "Ready to administer" sequence packages
- Claims of clinical validity without professional review
- Any feature that bypasses the safety preflight system

### Required in All Contributions

- If your code generates any output visible to users, it must include
  appropriate safety labels and uncertainty warnings
- If your code touches exports, it must go through the safety preflight system
- If your code adds a new agent skill, it must include safety boundaries in
  its SKILL.md

## Development Setup

```bash
# Install dependencies
make install

# Run tests
make test

# Run linters
make lint

# Run in demo mode
make dev
```

## Code Style

- Python: ruff + mypy + black
- All type annotations required
- All functions require docstrings
- Structured logging via structlog

## Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Add tests for your changes
4. Verify all tests pass: `make test`
5. Verify linters pass: `make lint`
6. Ensure no prohibited outputs in your changes
7. Submit PR with a clear description

## Reporting Issues

Please report bugs, safety concerns, or policy violations via GitHub Issues.

For security vulnerabilities, please report privately via GitHub Security
Advisories rather than public issues.

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions will be licensed under the
same license as the project (Apache-2.0 or AGPL-3.0, TBD).