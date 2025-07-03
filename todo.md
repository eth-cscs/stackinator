Create some example recipes that exercise all workflows.

For each example recipe
- `compilers/*/packges.yaml` and `environments/*/packges.yaml` are generated correctly
- `config/*.yaml` are generated correctly
- `modules` are generated correctly
- compilers are correctly linked into the views
- the correct default compiler is set
- iterative builds don't break unreasonable

To consider:
- test on systems where gcc 7.5.0 is the only available option
- user overriding gcc in `recipe/packages.yaml`
- 

## Examples

prgenv-gnu:
- only use gcc

prgenv-nvhpc
- use gcc and nvhpc

prgenv-llvm
- a stretch goal
