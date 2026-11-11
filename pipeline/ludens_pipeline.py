from __future__ import annotations

import os

import uvicorn

from pipeline.tavern.api import TavernService
from pipeline.tavern.router import TavernApp


def main() -> None:
    application = TavernApp(TavernService())
    uvicorn.run(application.app, host="0.0.0.0", port=int(os.environ.get("LUDENS_PORT", "8792")))


if __name__ == "__main__":
    main()
