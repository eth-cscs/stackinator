import logging
import re


VERSION = '0.1-dev'
root_logger = logging.getLogger('stackinator')

stackinator_version_info = tuple(re.split(r'\.|-', VERSION))
