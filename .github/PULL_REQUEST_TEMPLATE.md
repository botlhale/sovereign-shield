## Intent

<!-- Every change has an intent folder (see intent/README.md). Link it here. -->

- Intent folder:
- Status after this change (implemented or verified):
- Requirements not met, or work beyond the spec:

## Summary

<!-- What problem does this change solve? -->

## Why This Is Correct

<!-- Cite tests, standards, provider behavior, or runtime evidence. -->

## Security and Data Impact

- Personas or authorization boundaries affected:
- Data lifecycle or quarantine behavior affected:
- SDMX structures or formats affected:
- Infrastructure or deployment ownership affected:
- Observation-existence or public-value reconstruction risk affected:

## Validation

<!-- List exact commands run and results. -->

```text

```

## Checklist

- [ ] The change is focused and contains no unrelated formatting or generated files.
- [ ] `intent.md`, `spec.md` and `plan.md` match the change, and `plan.md` records the evidence.
- [ ] Commits end with an `Intent:` trailer, plus `Assisted-by:` when an agent contributed.
- [ ] Tests cover the behavior or the pull request explains why no test applies.
- [ ] Offline tests pass.
- [ ] Terraform changes pass `terraform fmt -recursive -check` and `terraform validate`.
- [ ] Documentation reflects changed behavior or operational steps.
- [ ] No credentials, state, private keys, personal data, client data, or real institutional records are included.
- [ ] New fixtures and screenshots use synthetic data only.
- [ ] Security controls remain fail-closed.
- [ ] Substantial AI assistance is disclosed above, every line was reviewed, and no secret or non-public material was placed in a prompt ([AI-assisted SDLC](../CONTRIBUTING.md#ai-assisted-software-development-life-cycle)).
- [ ] The Code of Conduct has been reviewed and accepted.
- [ ] The contribution is intentionally submitted under Apache License 2.0.
