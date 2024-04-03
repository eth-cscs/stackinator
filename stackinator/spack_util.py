def is_repo(path):
    """
    Returns True if path contains a spack package repo, where the definition of
    a spack package repo is a directory with a sub-directory named packages

    Otherwise returns False.
    """
    pkg_path = path / "packages"
    if pkg_path.exists() and pkg_path.is_dir():
        return True
    return False
