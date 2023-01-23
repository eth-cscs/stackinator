#: (major, minor, micro, dev release) tuple
sstool_version_info = (0, 0, 1, "dev0")

#: PEP440 canonical <major>.<minor>.<micro>.<devN> string
sstool_version = ".".join(str(s) for s in sstool_version_info)

__all__ = ["sstool_version_info", "sstool_version"]
__version__ = sstool_version
