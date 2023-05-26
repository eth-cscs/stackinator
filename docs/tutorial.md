# Tutorial

!!! warning "TODO"
    write a tutorial that explains building an image step by step.

A spack stack with everything needed to develop Arbor on for the A100 nodes on Hohgant.

This guide walks us through the process of configuring a spack stack, building and using it.

Arbor is a C++ library, with optional support for CUDA, MPI and Python. An Arbor developer would ideally have an environment that provides everything needed to build Arbor with these options enabled.

The full list of all of the Spack packages needed to build a full-featured CUDA version is:

- MPI: `cray-mpich-binary`
- compiler: `gcc@11`
- Python: `python@3.10`
- CUDA: `cuda@11.8`
- `cmake`
- `fmt`
- `pugixml`
- `nlohmann-json`
- `random123`
- `py-mpi4py`
- `py-numpy`
- `py-pybind11`
- `py-sphinx`
- `py-svgwrite`

For the compiler, we choose `gcc@11`, which is compatible with cuda@11.8.
