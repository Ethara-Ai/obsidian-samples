"""Run the agent tools gateway: ``python -m tools_gateway`` inside its sidecar image."""

import os

import uvicorn

from .server import DEFAULT_PORT, Settings, create_app


def main() -> None:
    port = int(os.environ.get("WCB_TOOLS_PORT") or DEFAULT_PORT)
    uvicorn.run(create_app(Settings.from_env()), host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
