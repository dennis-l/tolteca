#! /usr/bin/env python

from tollan.utils.log import get_logger
from tollan.utils import rupdate
from tollan.utils.cli.path_type import PathType

from . import main_parser
from ..utils import RuntimeContext
from ..version import version

from astropy.time import Time
import sys
import yaml


@main_parser.register_action_parser(
        'setup',
        help="Setup a pipeline/simu workdir."
        )
def cmd_setup(parser):

    parser.add_argument(
            'workdir',
            type=PathType(exists=None, type_="dir"),
            metavar="DIR",
            help="The workdir to setup.",
            )
    parser.add_argument(
            "-f", "--force", action="store_true",
            help="Force the setup even if DIR is not empty",
            )
    parser.add_argument(
            "-o", "--overwrite", action="store_true",
            help="Overwrite any existing file without backup in case "
                 "a forced setup is requested"
            )
    parser.add_argument(
            "-n", "--dry_run", action="store_true",
            help="Run without actually create files."
            )

    @parser.parser_action
    def action(option, unknown_args=None):
        logger = get_logger()

        logger.debug(f"option: {option}")
        logger.debug(f"unknown_args: {unknown_args}")

        ctx = RuntimeContext.from_dir(
                option.workdir,
                create=True,
                force=option.force,
                overwrite=option.overwrite,
                dry_run=option.dry_run,
                )
        logger.debug(f"runtime context: {ctx}")

        config = option.config or dict()
        rupdate(
            config,
            {
                'setup': {
                    'jobkey': option.workdir.resolve().name,
                    'prog': sys.argv[0],
                    'version': version,
                    'created_at': Time.now().isot,
                    }
            })
        # write the setup context to the config_file
        with open(ctx.setup_file, 'w') as fo:
            yaml.dump(config, fo)