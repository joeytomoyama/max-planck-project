"""Entry point: `python -m app`.

Loads `config.yml` before anything else so an invalid Condition stops the
process with a clear message instead of a traceback.
"""

import logging
import os
import sys

import uvicorn

from .config import ConfigError, load_config
from .main import create_app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"\nCONFIG ERROR: {exc}\nFix config.yml and start again.\n", file=sys.stderr, flush=True)
        sys.exit(1)

    uvicorn.run(create_app(config), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
