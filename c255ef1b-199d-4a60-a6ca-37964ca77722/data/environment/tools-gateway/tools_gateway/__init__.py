"""Agent tools gateway: the text browser and the image-generation proxy.

The agent container sits on an ``--internal`` task network with no egress, so
every browser fetch and every image request goes through this gateway. It runs
as a sidecar (``sidecar.py``) attached to the task network for the agent and to
the default bridge for egress, which puts the client's blocked-domain list, the
browser's write-only page records, the image API credentials, and per-run usage
metering in one place the agent cannot route around.
"""
