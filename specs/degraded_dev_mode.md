# Degraded dev mode — capability tiers instead of full parity

Status: design intent (August 2026), distilled from a full-suite validation
run on a fresh macOS workspace (all 648 community 19.0 modules installed and
tested). Not committed scope; supersedes nothing.

## The problem

Odoo's dependency truth is split across three artifacts: `requirements.txt`
(the pip layer, python-only by nature), `debian/control` (the supported
platform: python deps as distro packages, native libs resolved transitively
by apt), and the runbot Docker image (control + an undeclared test tier:
pylint/astroid, aiosmtpd, websocket-client, Chrome, rtlcss, eslint, GeoIP
test data, faketime, PYTHONHASHSEED). A pip-based install on any platform —
including Debian itself — is therefore incomplete by construction, and the
incompleteness is *silent*: some tests crash (unguarded imports), some fail
(rtlcss error-path assertions), and some skip without a trace at normal log
levels (1233 browser tests skipped for a missing websocket-client, invisible
across four full runs).

Two rejected answers frame the design space:

- Full parity chase (install everything everywhere): a treadmill; native
  tools (Chrome, rtlcss, wkhtmltopdf, distro-built debs) can be unavailable
  or unbuildable on a given host (amd64-only debs on ARM macs).
- Docker-only dev (run the runbot image): proven env by construction, but
  amd64-bound (QEMU pain on Apple Silicon), bind-mount I/O and debugger
  ergonomics tax daily development.

## The contract

Dev mode is **degraded by default, honestly**:

1. **Minimal install runs core.** The venv (requirements.txt + the small
   essentials list) plus postgres is enough to develop, start, and run the
   at_install/post_install suites of ordinary modules.
2. **Every missing optional capability deactivates its tests — visibly.**
   A test that needs an absent optional dependency must *skip with a
   reason*, never crash and never fail. Where Odoo upstream violates this
   (unguarded `import astroid` in test_lint, rtlcss error-path assertion in
   test_assetsbundle), the fix is an upstream skip-guard PR — two such
   patches already exist on the fix-test-portability branch and define the
   pattern. Odoo's own code mostly complies already (websocket-client,
   aiosmtpd, pdfminer probes).
3. **The degradation is measured, not implied.** `odoo test` reports, per
   run, which capabilities were absent and how many tests they cost
   ("tours: skipped (websocket-client missing) — `odoo deps install
   browser`"). Silence is the only failure mode this spec forbids. This is
   runbot's `ODOO_RUNBOT=1` idea (absence of an optional dep is *loud* in
   CI) inverted for dev: absence is fine, invisible absence is not.
4. **More is one command away.** Named capability tiers group the extras;
   installing a tier upgrades the venv/host and un-skips the tests.

## Capability tiers (initial cut)

| Tier      | Contents                                            | Kind |
|-----------|-----------------------------------------------------|------|
| core      | requirements.txt, websocket-client, watchdog        | py (always installed) |
| pdf       | cairo + rlPyCairo, wkhtmltopdf                      | native + py |
| browser   | Chrome/Chromium presence check                      | native (check-only) |
| lint      | pylint, astroid; es-check/eslint (check-only)       | py + native |
| mail      | aiosmtpd                                            | py |
| documents | pdfminer.six, python-magic (+ libmagic), ocrmypdf   | py + native |
| geo       | GeoIP test databases (mmdb files)                   | data |
| db        | template_odoo extensions: pg_trgm, unaccent,        | pg (converged |
|           | fuzzystrmatch, vector                               | best-effort) |
| rtl       | rtlcss via npm                                      | native |

Notes:
- websocket-client is core, not a tier: without it the entire post_install
  browser suite vanishes, which is too much silent loss for a default.
- Tier membership is odoo-cli-maintained but small and stable; the native
  entries reuse the report_deps plan machinery (detect → offer → best-effort
  → warn). Python entries install into the shared venv.
- Per-branch drift is handled by the sources of truth already in the
  worktree: debian/control (native residue), manifests
  (external_dependencies), and — if upstream ever adopts dependency groups
  in pyproject.toml — those, in preference to this table.

## Mechanics

- `odoo deps` (name tbd): list tiers with installed/missing status per
  entry; `odoo deps install <tier>` runs the plans. Also runnable as part
  of `odoo init` (core + offered tiers).
- `odoo test`: pre-flight probes the tiers (cheap: importlib.find_spec,
  shutil.which, template status) and prints one line per absent capability
  that the selected modules could exercise; post-run, the skip counts from
  the result stream make the cost concrete.
- Venv recipe changes reach existing venvs via a versioned ready-marker
  (recipe version in the marker file; mismatch → top-up/rebuild). Two
  incidents this week (rlPyCairo, websocket-client both absent from a venv
  predating their addition to the recipe) motivate this.
- The reference environment for "is this failure my env or real?" stays the
  runbot image (or a future `odoo test --reference` docker mode). Degraded
  mode makes the delta *known*; it does not try to make it zero.

## Evidence base (validation run, 2026-08-13/14)

- 14,630 tests; every failure classified. Environment-caused failures all
  mapped to undeclared dependencies or db semantics now covered above.
- Silent skips measured: 1233 (websocket-client), unknown counts for
  aiosmtpd/pdfminer/eslint (no reporting — hence contract point 3).
- Upstream patches proving the skip-guard pattern: test_assetsbundle rtlcss
  guard, test_configmanager portability, base_setup StopIteration guard,
  fleet backport completion (branch fix-test-portability).
