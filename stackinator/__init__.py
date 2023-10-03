import logging
import re

VERSION = "2.0"
root_logger = logging.getLogger("stackinator")

stackinator_version_info = tuple(re.split(r"\.|-", VERSION))
