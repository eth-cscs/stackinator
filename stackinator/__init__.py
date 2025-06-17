import logging
import re

VERSION = "6.0.0-dev"
root_logger = logging.getLogger("stackinator")

stackinator_version_info = tuple(re.split(r"\.|-", VERSION))
