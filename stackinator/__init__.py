import logging
import re

VERSION = "4.1.0-dev"
root_logger = logging.getLogger("stackinator")

stackinator_version_info = tuple(re.split(r"\.|-", VERSION))
