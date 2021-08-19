"""
Settings files - read settings from env

Process:

 * Loads dotenv to read environment from .env files
 * Setup logging - root logger, read logging config, etc.
 * Settings init - read all env and init settings module

Will load environment in order:

 * `.env`
 * `.env.{environment}`
 * system env
 * pydantic settings

"""
import logging
import logging.config
import os
import sys
from pathlib import Path

# @NOTE load first external deps in an exception block so that we can catch if the ENV is
# loaded and be friendly
try:
    from dotenv import load_dotenv
    from pydantic import ValidationError
except ImportError:
    logging.error("Could not load required modules. Likely virtualenv not active or installed.")
    sys.exit(-1)

from pydantic.error_wrappers import _display_error_loc, _display_error_type_and_ctx

from opennem.settings.log import LOGGING_CONFIG
from opennem.settings.utils import load_env_file
from opennem.utils.proc import running_as_scrapy

from .schema import OpennemSettings  # noqa: E402

# Setup logging - root logger and handlers
__root_logger = logging.getLogger()
__root_logger.setLevel(logging.INFO)
__root_logger_formatter = logging.Formatter(fmt=" * %(levelname)s %(message)s")
num_handlers = len(__root_logger.handlers)

if num_handlers == 0:
    __root_logger.addHandler(logging.StreamHandler())

__root_logger.handlers[0].setFormatter(__root_logger_formatter)

MODULE_DIR = os.path.dirname(__file__)

ENV = os.getenv("ENV", default="development")

logging.info(f"Loading OpenNEM ENV {ENV}")

env_files = load_env_file(ENV)


# Load the env files
# @TODO add logging
for _env_file in env_files:
    _env_full_path = Path(_env_file).resolve()
    logging.info("Loading env file: {}".format(_env_full_path))
    load_dotenv(dotenv_path=_env_file, override=True)

# @NOTE don't use pydantics env file support since it doesn't support multiple
try:
    settings: OpennemSettings = OpennemSettings()
except ValidationError as e:
    logging.error("{} validation errors in settings schema".format(len(e.errors())))

    for err_no, _validation_error in enumerate(e.errors()):
        logging.error(
            f'{_display_error_loc(_validation_error)}: {_validation_error["msg"]} \
                ({_display_error_type_and_ctx(_validation_error)})'
        )

    try:
        logging.info("Exiting")
        sys.exit(-1)
    except Exception:
        pass

    do_exit = True


# skip if the current cli is scrapy
if LOGGING_CONFIG and not running_as_scrapy():
    # don't mess with scrapy logging

    logging.config.dictConfig(LOGGING_CONFIG)

    log_level = logging.getLevelName(settings.log_level)

    # set root log level
    logging.root.setLevel(log_level)

    opennem_logger = logging.getLogger("opennem")
    opennem_logger.setLevel(log_level)

    # other misc loggers
    logging.getLogger("PIL").setLevel(logging.ERROR)
