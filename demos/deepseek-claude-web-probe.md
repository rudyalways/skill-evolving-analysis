# DeepSeek + Claude Agent SDK web-tool probe

This probe answers three separate questions with captured evidence:

1. Does Claude Agent SDK expose and call `WebSearch`/`WebFetch` when its model backend is DeepSeek?
2. What JSONL events and persisted Claude session history are available?
3. Do search/fetch results or citations contain inspectable source URLs?

## Run

The repository already pins `claude-agent-sdk` in `pyproject.toml`. Use the existing virtual environment:

```bash
export DEEPSEEK_API_KEY='...'
export DEEPSEEK_BASE_URL='https://api.deepseek.com/anthropic' # optional; this is the default
export DEEPSEEK_MODEL='deepseek-flash'                       # optional; this is the default

.venv/bin/python demos/deepseek-claude-web-probe.py
```

Use a custom question if desired:

```bash
.venv/bin/python demos/deepseek-claude-web-probe.py \
  --prompt 'Use WebSearch to find today’s DeepSeek API documentation and cite exact URLs.'
```

Each run creates a timestamped directory below `artifacts/deepseek-claude-web-probe/`:

- `sdk-events.jsonl`: every object yielded by the Python SDK, including partial stream events.
- `session-history.jsonl`: a copy of Claude Code's persisted transcript, when one was created.
- `summary.json`: detected web-tool names, source URLs, session ID, and compatibility error.
- `claude-stderr.log`: Claude Code diagnostics. It never intentionally records the API key.

The original persisted transcript is normally at
`~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`.

## Interpret the result

- `web_tool_call_observed: true` means the model attempted `WebSearch` or `WebFetch`.
- Non-empty `reference_urls` means URLs were visible in the SDK stream, transcript, citations, or tool results.
- A provider error after a web-tool request means the SDK offered the tool but the DeepSeek Anthropic-compatible endpoint did not implement the required behavior.
- A normal answer with no tool call is not proof of web search. The default prompt explicitly requires the tools to make this easier to detect.

DeepSeek API compatibility and Anthropic-hosted server tools are different layers. The compatible endpoint can accept Anthropic-shaped message requests without necessarily providing Anthropic's hosted web-search service.
