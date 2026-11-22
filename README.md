# Max Planck Project: Human-AI Experiment Platform

Rebuilding from scratch. See [SPEC.md](SPEC.md) and the spec issue #9 with its tickets #10-#17.

The first attempt (written with qwen3.5 9B) is kept on the `qwen-attempt` branch for reference.

## Run

```sh
docker compose up --build
```

Then open <http://localhost:8000/waiting>. Set `APP_PORT` to publish on another host port
(e.g. `APP_PORT=8080 docker compose up`).

The active Condition and timings live in [`config.yml`](config.yml); edit it and run
`docker compose restart app`. An invalid `condition:` stops the app with a message listing the
valid values. LLM settings come only from the env vars in [`.env.example`](.env.example); none are
needed in mock mode.
