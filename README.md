# LangGraph Ops Supervisor

A stateful operations assistant built with LangGraph. A supervisor routes
requests to a log analyzer or GitHub issue creator. Configured HTTP health
checks run during investigations, and detected log errors or failed checks can
automatically create a deduplicated GitHub issue and notify Microsoft Teams.

## Requirements

- Python 3.9+
- Ollama with a locally pulled chat model (default), or an OpenAI API key
- Python 3.13 to run the LangGraph Studio development environment

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Ollama (default)

Install and start [Ollama](https://ollama.com/), then download the default model:

```bash
ollama pull llama3.2
ollama serve
```

The `.env.example` defaults to the local Ollama OpenAI-compatible endpoint at
`http://localhost:11434/v1`. Change `OLLAMA_MODEL` or `OLLAMA_BASE_URL` in
`.env` to use another model or endpoint.

### OpenAI (optional)

Set `LLM_PROVIDER=openai` in `.env`, then provide `OPENAI_API_KEY`. `OPENAI_MODEL`
is optional and defaults to `gpt-4o-mini`.

## Integrations and automatic actions

Configure these values in `.env`:

- `GITHUB_TOKEN`: a fine-grained token with Issues read/write access to the
  selected repository. `GITHUB_REPOSITORY` defaults to
  `nehadilkash/langgraph-ops-supervisor`.
- `HEALTHCHECK_URLS`: optional comma-separated HTTP(S) health endpoints.
- `TEAMS_WEBHOOK_URL`: optional Microsoft Teams Workflows webhook URL.

On an investigation, the app checks configured endpoints and scans the supplied
text for error/fatal/exception/critical log lines. If either errors or unhealthy
endpoints are found, it creates a GitHub issue automatically. Before creating,
it searches open issues for the same incident fingerprint; a duplicate is
reused instead. A Teams alert is sent only when a new issue is created. If the
Teams webhook is not configured, the result says so explicitly.

These checks run when the graph is invoked; this is not a continuous background
monitor. The database status tool and Jira tool remain mocks. Health checks
only access URLs explicitly configured by the operator.

## Run the CLI

```bash
python main.py
```

Enter an operations question, include relevant log lines in the request, or ask
to create a ticket. The supervisor decides whether to analyze logs, create a
ticket, do both, or answer directly. Type `exit` or `quit` to end the session.

To provide an existing conversation thread ID:

```bash
python main.py --thread-id incident-123
```

The CLI stores conversation state in memory until the process exits.

## View the graph in LangGraph Studio

The LangGraph CLI configuration currently supports server Python versions
through 3.13, so this project uses Python 3.13 for Studio. Install Python 3.13,
then create a separate environment and start the local server:

```bash
python3.13 -m venv .venv-studio
source .venv-studio/bin/activate
pip install -r requirements-studio.txt
cp .env.example .env
langgraph dev
```

Open the Studio URL printed by `langgraph dev`. The graph view shows the
supervisor, analyzer, ticket creator, and automatic issue/notification steps;
run traces show which steps executed and the resulting actions. The LangGraph
API server manages checkpointing for Studio sessions. If Studio requests
LangSmith authentication, set `LANGSMITH_API_KEY` in `.env`; the local graph
server can run without it. The standalone CLI remains compatible with Python
3.9+; this version constraint applies to the LangGraph Studio server.

## Project layout

```text
src/
  agents/       Supervisor, log analyzer, and ticket creator
  tools/        Log/health, GitHub Issues, Teams, and mock tools
  graph.py      StateGraph construction and routing
  llm.py        Ollama/OpenAI model configuration
  state.py      Typed graph state and conversation helpers
main.py         Interactive CLI
langgraph.json  LangGraph Studio configuration
```
