#: (major, minor, micro, dev release) tuple
stackinator_version_info = (0, 0, 1, "dev0")

#: PEP440 canonical <major>.<minor>.<micro>.<devN> string
stackinator_version = ".".join(str(s) for s in stackinator_version_info)

__all__ = ["stackinator_version_info", "stackinator_version"]
__version__ = stackinator_version
