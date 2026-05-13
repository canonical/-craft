# dashcraft

AI-powered Juju charm generator — charming, but fast.

Dashcraft takes an upstream Git repository, scaffolds a charm, and then hands off to [pi](https://www.npmjs.com/package/@earendil-works/pi-coding-agent) — an AI coding agent — to generate a production-ready charm with all the recommended integrations (observability, ingress, authentication, etc).

## Quickstart

```bash
# Create a project config
cat > dashcraft.yaml <<'EOF'
name: my-app
summary: My awesome application
description: A longer description of the app.
type: charm

parts:
  charm:
    plugin: -craft
    upstream: https://github.com/example/my-app.git
EOF

# Generate and pack the charm
dashcraft pack
```

## Installation

### 1. Install dashcraft

```bash
git clone https://github.com/juju/dashcraft.git
cd dashcraft
uv sync
```

### 2. Install quickpack (required)

Dashcraft uses `quickpack` — a fast local charm packer — to produce the final `.charm` file. It ships as part of the [`juju-cantrip`](https://pypi.org/project/juju-cantrip/) PyPI package:

```bash
uv tool install juju-cantrip
```

Verify the installation:

```bash
quickpack --help
```

### 3. Install pi (required)

Dashcraft uses `pi` — an AI coding agent — to generate charm code. Install it with npm:

```bash
sudo npm install -g @earendil-works/pi-coding-agent
```

Verify the installation:

```bash
pi --version
```

### 4. Set an API key

`pi` supports many model providers. Set at least one of the following environment variables:

```bash
# Google Gemini (default provider)
export GEMINI_API_KEY=<your-key>

# Or Anthropic Claude
export ANTHROPIC_API_KEY=<your-key>

# Or OpenAI
export OPENAI_API_KEY=<your-key>
```

Other supported providers include `AZURE_OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `OPENROUTER_API_KEY`, and `FIREWORKS_API_KEY`.

## Development

```bash
# Format code
make format

# Run lint checks
make lint

# Run unit tests
make unit

# All of the above
make all
```

## Configuration

Place a `dashcraft.yaml` in your project directory with the following fields:

```yaml
name: ...              # Charm name (kebab-case)
summary: ...           # One-line summary
description: ...       # Full description
type: charm            # Must be "charm"

parts:
  charm:
    plugin: -craft
    upstream: <git-url>   # Upstream source repository
    model: <optional>     # AI model to use (reserved for future use)
    language: <optional>  # Reserved for future use
```
