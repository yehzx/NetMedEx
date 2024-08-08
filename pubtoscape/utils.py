import logging
import sys


def config_logger(is_debug):
    if is_debug:
        logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S",
                            level=logging.DEBUG,
                            stream=sys.stdout)
    else:
        logging.basicConfig(format="%(message)s",
                            level=logging.INFO,
                            stream=sys.stdout)
