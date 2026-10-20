# Privacy

Agent Video Desk collects no data.

- Everything runs on your machine. The desks are local servers bound to `127.0.0.1`, and the pages talk only to them.
- Your scripts, footage, transcripts and marks stay in your project folder (`_work/script/`, `_work/review/`). Nothing is uploaded, and there is no telemetry, analytics or account.
- The only network access is `ru-transcribe` downloading its dependencies and model weights on first run (PyPI, GitHub, Hugging Face). It sends none of your recordings or text anywhere.
- Your AI agent (Claude Code, Codex or another) reads the files it works with under that agent's own terms.

Questions: open an issue at https://github.com/c0t0ber/agent-video-desk/issues.
