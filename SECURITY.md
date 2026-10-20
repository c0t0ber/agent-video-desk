# Security

## What runs where

- **Script Desk and Footage Desk** are Python standard-library HTTP servers bound to `127.0.0.1`. They make no outbound network requests. `/media/` serves only files inside the project folder passed with `--project`; paths that resolve outside it return 404.
- **The browser page** talks only to that local server. It loads no third-party scripts, fonts or analytics.
- **ru-transcribe** is the only part that goes online. On first run, `uv` installs its dependencies from PyPI, plus GigaAM from its GitHub repository, and the models download weights from Hugging Face (about 2.5 GB). After that it runs offline.
- **Data** stays in the project folder: `_work/script/` and `_work/review/`. Nothing is uploaded anywhere.

The servers have no authentication: anything that can reach `127.0.0.1` on your machine can read and write the desk. Do not expose the port to a network (for example with port forwarding or a tunnel).

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting: **Security → Report a vulnerability** on https://github.com/c0t0ber/agent-video-desk. Do not open a public issue for security problems. You will get a reply within a week.

## Supported versions

Only the latest release gets fixes.
