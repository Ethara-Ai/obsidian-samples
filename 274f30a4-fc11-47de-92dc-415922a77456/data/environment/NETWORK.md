# Internet access in this task

This task ships a text browser (the `tools-gateway` service and the `skills/text-browser/` skill). It refuses the domains on the blocked-domain list. Whether the agent can also reach the internet without it depends on how the task is started.

## Normal start (the default)

    docker compose up

Every service, the agent's container (`main`) included, has normal internet access. The blocked-domain list applies only to pages read through the browser: the agent can reach any site directly.

## Locked start

    docker compose -f docker-compose.yaml -f docker-compose.locked.yaml up

The agent's container and the mock services lose internet access. They still reach each other and `tools-gateway` by name. Only `tools-gateway` keeps a route out, so the browser, and with it the blocked-domain list, is the agent's only way to the web. The image tool keeps working, because it also runs in `tools-gateway`.

Use it only if the agent needs nothing else from the internet:

- The agent reaches its model at `http://litellm-proxy:4000`, a service this task does not define. In a locked start that proxy must be attached to this task's network and have its own route out, or the agent cannot reach its model.
- Package installs (`pip`, `apt`) and direct downloads from the agent's container stop working.

## Notes

- The browser reads the live web on every request, so two runs of the task can see different page content.
- Every page the browser fetches is kept in the `tools-browser-pages` volume for review.
- The blocked-domain list is `tools-gateway/tools_gateway/data/blocked_domains.txt`, taken unchanged from the requirements it was given in; the provenance file beside it names that source and its checksum.
- `task.toml` says `allow_internet = true`. The locked start is a docker compose override; a runner that starts the task another way applies its own network settings.
