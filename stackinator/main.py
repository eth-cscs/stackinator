import argparse
import hashlib
import logging
import os
import platform
import sys
import time
import traceback

from . import VERSION, root_logger
from .builder import Builder
from .recipe import Recipe


def generate_logfile_name(name=""):
    #idstr = f"{time.localtime()}{os.getpid}{platform.uname()}"
    #return f"log{name}_{hashlib.md5(idstr.encode('utf-8')).hexdigest()}"
    return f"stackinator_log"


def configure_logging(logfile):
    root_logger.setLevel(logging.DEBUG)

    # create stdout handler and set level to info
    ch = logging.StreamHandler(stream=sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(ch)

    # create log file handler and set level to debug
    fh = logging.FileHandler(logfile)  # , mode='w')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s : %(levelname)-7s : %(message)s"))
    root_logger.addHandler(fh)


def log_header(args):
    root_logger.info("Stackinator")
    root_logger.info(f"  recipe path: {args.recipe}")
    root_logger.info(f"  build path : {args.build}")
    root_logger.info(f"  system     : {args.system}")
    mount = args.mount or "default"
    root_logger.info(f"  mount      : {mount}")
    root_logger.info(f"  build cache: {args.cache}")
    root_logger.info(f"  develop    : {args.develop}")


def make_argparser():
    parser = argparse.ArgumentParser(description=("Generate a build configuration for a spack stack from a recipe."))
    parser.add_argument("--version", action="version", version=f"stackinator version {VERSION}")
    parser.add_argument("-b", "--build", required=True, type=str)
    parser.add_argument("--no-bwrap", action="store_true", required=False)
    parser.add_argument("-r", "--recipe", required=True, type=str)
    parser.add_argument("-s", "--system", required=True, type=str)
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("-m", "--mount", required=False, type=str)
    parser.add_argument("-c", "--cache", required=False, type=str)
    parser.add_argument("--develop", action="store_true", required=False)

    return parser


def main():
    logfile = generate_logfile_name("_config")
    configure_logging(logfile)

    try:
        parser = make_argparser()
        args = parser.parse_args()
        root_logger.debug(f"Command line arguments: {args}")
        log_header(args)

        recipe = Recipe(args)
        builder = Builder(args)

        builder.generate(recipe)

        root_logger.info("\nConfiguration finished, run the following to build the environment:\n")
        root_logger.info(f"cd {builder.path}")
        root_logger.info(
            "env --ignore-environment PATH=/usr/bin:/bin:`pwd`/spack/bin HOME=$HOME make store.squashfs -j32"
        )
        return 0
    except Exception as e:
        root_logger.debug(traceback.format_exc())
        root_logger.error(str(e))
        root_logger.info(f"see {logfile} for more information")
        return 1
