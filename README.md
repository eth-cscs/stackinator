# Stackinator

A tool for building a scientific software stack from a recipe for vClusters on CSCS' Alps infrastructure.

Read the [documentation](https://eth-cscs.github.io/stackinator/) to get started.

Create a ticket in our [GitHub issues](https://github.com/eth-cscs/stackinator/issues) if you find a bug, have a feature request or have a question.

## running tests:

Use uv to run the tests, which will in turn ensure that the correct dependencies from `pyproject.toml` are used:

```
uv run pytest
```

Before pushing, apply the linting rules (this calls uv under the hood):

```
./lint
```
## building the docs

The documentation for Stackinator is built from the markdown files in the `docs` path using MkDocs and MkDocs-material.
You can view the latest documentation online at [github.io](https://eth-cscs.github.io/stackinator/)

To view work in progress docs, run the serve script and follow the link it provides to view a local copy of the docs in your browser.
```bash
./serve
```
