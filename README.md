# Rational conformance

This harness connects the **independent** SQLite and browser projects to PostgreSQL
pgmp. Neither library depends on this directory or on the other library to build,
test, or distribute.

Publish this directory's contents, including `.github`, as a standalone GitHub
repository. [The CI workflow](.github/workflows/ci.yml) fetches
[sqlite-rational](https://github.com/athanclark/sqlite-rational) and
[rational-map](https://github.com/athanclark/rational-map) from their upstream
repositories; the conformance repository does not vendor either library.
See [CI.md](CI.md) for triggers, reproducible upstream refs, and runner setup.

Fixture version 1 is generated deterministically by fixture.py. Its independent
oracle uses Python's exact Fraction type. Each backend checks 160 range/overview
cases and 42 arithmetic cases: inclusive/exclusive/unbounded/reversed/singleton
bounds, equivalent coordinates, weighted buckets, strict threshold boundaries,
both grouping modes, zero threshold, and tiny gaps at 1,200-digit offsets.

From the parent directory, after building both projects:

~~~sh
python3 rational-conformance/run.py
python3 rational-conformance/run.py --require-pgmp \
  --pg-dsn 'postgresql://localhost/rational_test'
~~~

Install pgmp in a **dedicated test database** before the PostgreSQL command:

~~~sql
CREATE EXTENSION pgmp;
~~~

Supply --sqlite-extension for a custom module path. For an isolated locally loaded
pgmp schema, use --pg-schema. In environments without socket access, --pg-data can
use PostgreSQL's single-user backend on an initialized, **stopped disposable**
cluster owned by the invoking user. It must already contain pgmp.

With independent checkouts, all paths are explicit and relative to your current
working directory:

~~~sh
python3 run.py --require-pgmp --pg-dsn 'dbname=rational_conformance' \
  --sqlite-extension /path/to/sqlite-rational/build/sqlite_rational.so \
  --rational-map /path/to/rational-map/dist/index.js \
  --rational-map /path/to/rational-map/dist/browser.js \
  --report artifacts/conformance.json
~~~

Repeat `--rational-map` to check multiple public JS exports. Both are exercised
under Node; actual Chromium, Firefox, and WebKit tests run in rational-map's own
CI. Without explicit paths, the original sibling-directory layout remains the
local default. Python 3.10+ and Node 20+ are supported; the harness itself has no
third-party Python or npm dependencies. The JS ESM entry needs the built
library's dependencies installed; its browser bundle is self-contained.

Any mismatch, failed process, missing module, or timeout returns a nonzero status.
With `--report`, backend failures are recorded and remaining backends are still
checked. `--require-pgmp` rejects an invocation that would skip PostgreSQL.
Run the harness's own regression tests with:

~~~sh
python3 -m unittest discover -s test -v
~~~

All test tables/functions are temporary and the transaction is rolled back.
The PostgreSQL adapter uses pgmp's native comparisons, arithmetic, and B-tree
equality. It normalizes mpq_cmp's signed magnitude to -1/0/1 and reconstructs
canonical n/d strings from num/den (pgmp omits /1 in its usual display).
Its overview implementation is a scanning reference for semantic compatibility,
not an optimized PostgreSQL summary index.

PostgreSQL's built-in B-tree imposes an index-tuple size limit even though mpq can
store larger values. The fixture's large values compress sufficiently for its
test B-tree; that is not a guarantee for arbitrary huge keys. Correct unrestricted
range scans remain possible, or an ID-based augmented index is needed for such keys.
