# Releasing

`pyproject.toml` holds the only version number anyone edits. `scripts/sync_version.py` copies it
into `server.json` (the top-level `version` and every `packages[]` entry with `registryType: pypi`),
`gemini-extension.json`, and `diffbot_mcp/__init__.py`. CI fails a pull request whose copies drift.

Pushing a `vX.Y.Z` tag runs [`.github/workflows/release.yml`](.github/workflows/release.yml), which
publishes to PyPI, then to the MCP Registry, then cuts a GitHub release. Nothing publishes without a
tag.

## Cutting a release

```bash
uv version --bump patch --frozen  # or: uv version 0.3.0 --frozen
python3 scripts/sync_version.py   # stamp the new version into the other files
git switch -c release/0.2.3 && git commit -am "Release 0.2.3" && git push -u origin HEAD
```

`--frozen` keeps `uv version` from locking and syncing on the side; without it, uv writes a `uv.lock`
and a `.venv` into the checkout, and this project deliberately ships neither.

Open the pull request, let **Version check** and the other checks pass, and merge. Merging also runs
**Deploy to Production**, which redeploys the hosted `https://mcp.diffbot.com/mcp` remote; that is
unrelated to the tag below, which is what publishes the package. Tag the merge commit on `main`:

```bash
git switch main && git pull
git tag v0.2.3
git push origin v0.2.3
```

Watch the **Release** run. In order it:

1. **verify** — the tag equals `v` + the `pyproject.toml` version, and the version copies are in sync.
2. **build** — `uv build` produces the sdist and wheel, `twine check --strict` passes, and the package
   description still carries the `<!-- mcp-name: io.github.diffbot/diffbot-mcp -->` comment.
3. **publish-pypi** — uploads to PyPI through Trusted Publishing, in the `pypi` environment.
4. **publish-mcp-registry** — waits for the new version to appear on PyPI, then publishes `server.json`.
5. **github-release** — creates the release with generated notes and the built files attached.

The tag is what makes the version public, so a mistake is cheap to avoid and expensive to undo: PyPI
will not accept the same version twice, and neither will the registry. If a tag was wrong, bump to the
next patch version and tag again.

## Dry run

Run **Release** by hand (Actions → Release → Run workflow) on any branch. `workflow_dispatch` runs
only `verify` and `build`; the three publishing jobs are gated on a tag push and will not run.

## If the registry step fails

PyPI has the version at that point, so only the registry needs retrying. Run **Publish to MCP
Registry** by hand (Actions → Publish to MCP Registry → Run workflow) and pick the `vX.Y.Z` tag as the
ref. It runs the same steps as the release path — it is the same workflow, called directly rather than
from `release.yml`. Common causes:

- PyPI had not yet served the new version. The workflow waits up to 10 minutes; a rerun usually passes.
- The registry rejects a version it already has, which means the publish actually succeeded.

## One-time setup

**PyPI trusted publisher.** On [pypi.org](https://pypi.org/project/diffbot-mcp/) → project
`diffbot-mcp` → Manage → Publishing, add a GitHub publisher:

| field | value |
| --- | --- |
| Owner | `diffbot` |
| Repository | `diffbot-mcp` |
| Workflow | `release.yml` |
| Environment | `pypi` |

No API token goes anywhere; the upload authenticates with the workflow's OIDC identity.

**The `pypi` GitHub environment.** It does not exist yet. GitHub creates it automatically the first
time the job references it, but a repo admin should create it first under Settings → Environments
(this needs admin, not maintain) and restrict its deployment branches and tags to `v*` so no other ref
can reach the trusted publisher. Required reviewers there also give a human gate before each upload.

The MCP Registry needs no setup: `mcp-publisher login github-oidc` exchanges the workflow's OIDC token
for publish rights to `io.github.diffbot/*`, based on the repository owner in the token.
