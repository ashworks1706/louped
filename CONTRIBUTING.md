# Contributing

1. `just bootstrap`, then work on a branch.
2. `just check` must pass; the pre-push hook runs it.
3. Open a pull request with a conventional-commit title. `CI` is the one required check.
4. UI changes: review the `screenshots` artifact CI uploads.

## Releases

release-please keeps a release pull request open on `main`. Merging it tags `vX.Y.Z`, and
`release.yml` publishes the wheel to PyPI (trusted publishing) and the image to
`ghcr.io/ashworks1706/louped`.

## Repository settings

The branch ruleset is in `.github/rulesets/main.json`. Import it once under Settings → Rules →
Rulesets → Import. PyPI publishing needs a trusted publisher configured on PyPI for this repository,
workflow `release.yml`, environment `pypi`.
