"""Vendored third-party dependencies.

Upstream source distributions ship `click` here so the bash installer only
needs a Python interpreter. Distribution packages (Debian/Ubuntu) may delete
this copy and depend on the system `python3-click` instead; the import switch
happens in `odoo_cli.cli._click`, the only module that imports from here.
"""
