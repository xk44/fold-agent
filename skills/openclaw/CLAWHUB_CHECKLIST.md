---
title: ClawHub Publication Checklist — neovax-openclaw
framework: OpenClaw
skill: neovax-openclaw
version: 1.0.0
---

# ClawHub Publication Checklist: neovax-openclaw

Complete every item before publishing this skill pack to ClawHub or any other
public skill registry.

## 1. Content Review

- [ ] `SKILL.md` has accurate `name`, `description`, `version`, `license`,
      and `tags` frontmatter
- [ ] All task YAML files (`pipeline_run.yaml`, `candidate_review.yaml`,
      `safety_check.yaml`) parse without errors (`python -c "import yaml; yaml.safe_load(open('…'))"`)
- [ ] All `safety_disclaimer` fields in task files are present and accurate
- [ ] `examples/websocket_usage.md` is accurate and tested against the
      current API version
- [ ] No internal hostnames, IP addresses, or internal URLs appear in any file
- [ ] No personal names, emails, or institutional identifiers appear in any file
      unless they are fictional/demo placeholders

## 2. Security Gate (MANDATORY)

- [ ] OPSEC checklist (`OPSEC_CHECKLIST.md`) is fully completed and signed off
- [ ] No secrets, API keys, passwords, or tokens are present in any file
      (run `git grep -i "token\|secret\|password\|apikey"` to verify)
- [ ] No `.env` files are included in the published package
- [ ] `skills/shared/` helper files contain no hardcoded credentials

## 3. Safety and Ethics

- [ ] Safety disclaimer is present in `SKILL.md` and all three task YAML files
- [ ] All task files enforce `POST /safety/preflight` before write operations
- [ ] No task file can be configured to bypass the safety gate
- [ ] The `no_medical_advice` statement is present and unambiguous
- [ ] The skill does not expose endpoints that could generate dosing,
      formulation, or manufacturing instructions

## 4. API Compatibility

- [ ] All endpoint paths in task YAML files match the current NeoVax API
      (verify against `skills/shared/openapi.json` or live `/openapi.json`)
- [ ] `version` field in each task YAML is updated to match the current release
- [ ] The skill is tested against the NeoVax API version it targets
      (document the target version in `SKILL.md` or a `CHANGELOG`)

## 5. Tests

- [ ] `skills/openclaw/tests/test_openclaw_skills.py` passes with no failures
      (`pytest skills/openclaw/tests/`)
- [ ] No test fixtures contain real patient data or PII

## 6. Documentation

- [ ] `examples/websocket_usage.md` includes at least one working code example
- [ ] All YAML `description` fields are human-readable and accurate
- [ ] `SKILL.md` `install_path` is correct for the target OpenClaw version

## 7. Licensing

- [ ] `license: Apache-2.0` is set in `SKILL.md` and all task YAML files
- [ ] No task file incorporates code or content from a more restrictive license
- [ ] Contribution from third parties (if any) is attributed per the
      `CONTRIBUTING.md` policy in the NeoVax project root

## 8. Final Checks

- [ ] Skill pack version is bumped appropriately (semver)
- [ ] A brief changelog entry is added if this is an update to an existing
      published version
- [ ] At least one team member other than the author has reviewed the full
      skill pack before publication

---

Reviewer: ********\_\_\_******** Date: ****\_\_\_**** Target registry: ClawHub
