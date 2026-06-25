"""Frontend-independent domain logic.

Rules (specs/architecture.md): no click, no printing, no stdin, no sys.exit.
Services raise typed errors from `core.errors` and return structured results.
"""
