from __future__ import annotations

import sys

from .cli import main as depot_main
from .i18n import translate


def main() -> int:
    print(f"warning: {translate('deprecated')}", file=sys.stderr)
    return depot_main()
