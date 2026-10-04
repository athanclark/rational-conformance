# GitHub Actions

Use this directory as a separate repository root, including the hidden `.github`
directory. The workflow at `.github/workflows/ci.yml` runs on pushes and pull
requests to the conformance repository, daily at 07:23 UTC, and manual dispatch.
Scheduled workflows run from the default branch, following
[GitHub's scheduling rules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Each run checks out the current default branches of
`athanclark/sqlite-rational` and `athanclark/rational-map`. Thus daily runs catch
upstream changes even when the harness has not changed. Pushes in those upstream
repositories do not directly trigger this repository's workflow. To check a
particular combination immediately, choose **Actions → Rational conformance →
Run workflow** and supply `sqlite_ref` and/or `map_ref` as branches, tags, or commit
SHAs. Blank values use the respective repository's default branch.

The pgmp default is its public stable
[1.0.6 release commit](https://github.com/dvarrazzo/pgmp/tree/1849585416f2bc3d070bf8cef6a659907687ec7f).
Its `pgmp_ref` manual input can select another upstream ref. The pinned default
avoids treating unreleased pgmp changes as the compatibility baseline.

The Ubuntu 24.04 job uses Node 24 and PostgreSQL 16. It:

- Builds SQLite with required native/Python tests and runs them.
- Installs rational-map's locked dependencies and runs its build/unit tests.
- Compiles upstream pgmp against the installed PostgreSQL headers and installs
  the extension. Its SQL scripts are generated explicitly with Python 3.
- Initializes a disposable PostgreSQL cluster with its own Unix socket directory,
  disables TCP listening, and creates a test database with `CREATE EXTENSION pgmp`.
- Runs all 160 bounded range/overview and 42 arithmetic cases against SQLite,
  RationalMap's ESM export, its standalone browser bundle, and actual pgmp.
  Each result must match the independent Python `Fraction` oracle; PostgreSQL
  cannot be skipped in CI.
- Writes a run summary and uploads JSON results, exact upstream/suite commits,
  runtime versions, and the PostgreSQL log, including on failed runs. The
  disposable server is stopped during cleanup.

The harness also tests its own failure behavior, and a separate workflow syntax
job uses checksum-verified actionlint. Actions are pinned to release commit hashes.
The public upstream checkouts require only `contents: read`; no secrets or
cross-repository write token are needed. Nothing is published by this workflow.

To reproduce a failure, check out the three SHAs in the run's `versions.json`,
build each library, install pgmp in a dedicated PostgreSQL database, and use the
explicit-path command in [README.md](README.md). The JSON report identifies the
failed backend and preserves its error. PostgreSQL's grouping adapter is an exact
scanning reference; this suite checks behavior rather than query performance.

The independent library workflows remain in their own repositories:
[sqlite-rational CI](https://github.com/athanclark/sqlite-rational/actions/workflows/ci.yml)
and [rational-map CI](https://github.com/athanclark/rational-map/actions/workflows/ci.yml).
RationalMap's workflow also runs actual Chromium, Firefox, and WebKit jobs; this
suite runs both JS exports under Node.

Validation on 2026-10-04: actionlint and ShellCheck passed for all three workflows.
The conformance suite passed from an isolated directory using the libraries'
published commits (`7239057` for SQLite and `16b87f0` for RationalMap), Node 24,
and actual pgmp 1.0.6 installed through `CREATE EXTENSION` on PostgreSQL 18.6.
Local socket restrictions required PostgreSQL's single-user backend and local
extension load paths. The new hosted PostgreSQL 16 job still needs its first
conformance-repository push; the two libraries' hosted workflows already passed.
