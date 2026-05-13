# Contributing

We welcome contributions! This document explains how to get involved.

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR-USERNAME/dashcraft
   cd dashcraft
   ```
3. Create a branch for your changes:
   ```bash
   git checkout -b feature/my-feature
   ```

## Development Workflow

### Running Tests

```bash
# Run all tests
make test

# Run a single test
pytest tests/path/to/test_file.py -v
```

### Linting and Formatting

```bash
# Format and check everything
make lint
```

### Installing Pre-commit Hooks

```bash
pre-commit install
```

## Code Style

- **Formatting**: Handled by ruff (line length 99)
- **Docstrings**: Google style
- **Error handling**: Never catch bare `Exception` — always be specific
- **Type hints**: Required where applicable

## Pull Request Process

1. Make your changes and commit with clear messages
2. Ensure all checks pass (lint, tests, type-check if applicable)
3. Fill in the PR template with:
   - Description of changes
   - Related issues
   - Testing performed

## Reporting Issues

- Use GitHub Issues for bug reports and feature requests
- Include reproduction steps for bugs
- Check existing issues before creating new ones

## Questions?

Feel free to open a discussion on GitHub or reach out to the maintainers.
