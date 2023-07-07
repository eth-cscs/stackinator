The documentation for Stackinator is built from the markdown files in this path using MkDocs and MkDocs-material.
You can view the latest documentation online at [github.io](https://eth-cscs.github.io/stackinator/)

To build a copy locally, first install `mkdocs-material`, e.g.:
```bash
python3 -m venv docs-env
source docs-env/bin/activate
pip install mkdocs-material
```

Then in the root of this project, build the docs and view them with your favourite browser:
```bash
mkdocs build
firefox site/index.html
```
