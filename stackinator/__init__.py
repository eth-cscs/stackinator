import logging
import re

VERSION = "1.1-dev0"
root_logger = logging.getLogger("stackinator")

stackinator_version_info = tuple(re.split(r"\.|-", VERSION))
