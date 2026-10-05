# Contributing

1. Run `just bootstrap`. Work on a branch.
2. Make sure `just check` passes. The pre-push hook runs it.
3. Open a pull request with a conventional-commit title. `CI` is the one required check.
4. For UI changes, review the `screenshots` artifact that CI uploads.

## Releases

release-please keeps a release pull request open on `main`. Merging it tags `vX.Y.Z`. Then
`release.yml` publishes the wheel to PyPI (trusted publishing) and the image to
`ghcr.io/ashworks1706/louped`.

## Repository settings

The branch ruleset is in `.github/rulesets/main.json`. Import it once under Settings → Rules →
Rulesets → Import. PyPI publishing needs a trusted publisher configured on PyPI with these values:

- repository: this repository
- workflow: `release.yml`
- environment: `pypi`
