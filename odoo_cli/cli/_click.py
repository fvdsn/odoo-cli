"""Single import point for click.

All CLI-layer modules import click from here, never directly. Packages that
unvendor click (e.g. Debian, depending on python3-click) only need the
vendored copy removed; the fallback import below picks up the system click.

Core modules must not import this module (or click at all); see
specs/architecture.md.
"""

try:
    from odoo_cli._vendor import click
    from odoo_cli._vendor.click import testing  # noqa: F401  (click.testing)
except ImportError:  # unvendored distribution package
    import click
    import click.testing as testing  # noqa: F401

__all__ = ["click", "testing"]
