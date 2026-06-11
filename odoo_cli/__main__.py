"""`python -m odoo_cli`: same entry as the installed `odoo` executable."""

import sys

from odoo_cli.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
