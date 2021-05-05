#! /usr/bin/env python

from packaging.specifiers import SpecifierSet
from packaging.version import parse as parse_version
from pathlib import Path
import subprocess
from contextlib import contextmanager
from astropy.table import Table
# import yaml
import re
from copy import deepcopy
from tollan.utils.fmt import pformat_yaml
from tollan.utils.log import get_logger, timeit
from ..base import PipelineEngine
from tollan.utils import call_subprocess_with_live_output, make_subprocess_env
import numpy as np
import astropy.units as u


def _fix_apt(source):
    # this is a temporary fix to allow citlali to work with the
    # apt
    tbl = Table.read(source, format='ascii.ecsv')
    tbl_new = Table()
    tbl_new['nw'] = np.array(tbl['nw'], dtype='d')
    tbl_new['array'] = np.array(tbl['array'], dtype='d')
    tbl_new['x_t'] = tbl['x_t'].quantity.to_value(u.deg)
    tbl_new['y_t'] = tbl['y_t'].quantity.to_value(u.deg)
    source_new = source.replace('.ecsv', '_trimmed.ecsv')
    tbl_new.write(source_new, format='ascii.ecsv')
    return source_new


class Citlali(PipelineEngine):
    """A class to run citlali, the TolTEC data reduction engine.

    Parameters
    -----------
    binpath : str or `~pathlib.Path`, optional
        The path to the citlali executable.
    version_specifiers : str, optional
        If set, the citlali version is checked against these specifiers.
    calobj : `~tolteca.cal.ToltecCalib`, optional
        The calibration object to use.
    """
    logger = get_logger()
    _name = 'citlali'

    def __init__(
            self, binpath=None, version_specifiers=None,
            calobj=None):
        self._version_specifiers = version_specifiers
        binpath = None if binpath is None else Path(binpath)
        self._binpath = self._get_citlali_cmd(
                binpath=binpath,
                version_specifiers=self._version_specifiers)
        self._version = self._get_citlali_version(self._binpath)
        self._calobj = calobj

    @classmethod
    def _get_citlali_version(cls, citlali_cmd):
        output = subprocess.check_output(
                (citlali_cmd, '--version'),
                stderr=subprocess.STDOUT,
                env=make_subprocess_env()
                ).decode()
        # logger.debug(f'citlali version:\n{output}')
        r = re.compile(
                r'^citlali\s(?P<version>.+)\s\((?P<timestamp>.+)\)$',
                re.MULTILINE)
        m = re.search(r, output).groupdict()
        version = m['version']
        return version

    @classmethod
    def _get_citlali_cmd(cls, binpath=None, version_specifiers=None):
        """Get the citlali executable."""
        logger = get_logger()
        if binpath is not None:
            if binpath.is_dir():
                binpath = binpath.joinpath('citlali')
            citlali_cmd = Path(binpath).as_posix()
        else:
            citlali_cmd = 'citlali'
        try:
            version = cls._get_citlali_version(citlali_cmd)
        except Exception as e:
            # raise RuntimeError(f"unable to get citlali version: {e}")
            logger.debug(f"unable to get citlali version: {e}")
            version = 'unknown'
        if version_specifiers is not None and \
                parse_version(version) not in SpecifierSet(version_specifiers):
            raise RuntimeError(
                    f"citlali version does not satisfy {version_specifiers}"
                    f", found {version}")
        logger.debug(pformat_yaml(
            {'citlali': {'path': citlali_cmd, 'version': version}}))
        return citlali_cmd

    def __repr__(self):
        return (
                f'{self.__class__.__name__}'
                f'({self._binpath},version={self.version})')

    @contextmanager
    def proc_context(self, cfg):
        """
        Return a function that can be used to run the
        Citlali for given input dataset.

        Parameters
        ==========
        cfg : dict

            The high-level configuration.
        """
        cfg = deepcopy(cfg)

        @timeit
        def proc(dataset, outdir):
            # resolve the dataset to input items
            tbl = dataset.index_table
            grouped = tbl.group_by(
                ['obsnum', 'subobsnum', 'scannum', 'master', 'repeat'])
            self.logger.debug(f"collected {len(grouped)} observations")

            def resolve_input_item(tbl):
                d0 = tbl[0]
                meta = {
                    'name': f'{d0["obsnum"]}_{d0["subobsnum"]}_{d0["scannum"]}'
                    }
                data_items = list()
                cal_items = list()
                for entry in tbl:
                    instru = entry['instru']
                    interface = entry['interface']
                    source = entry['source']
                    if instru == 'toltec':
                        c = data_items
                    elif interface == 'lmt':
                        c = data_items
                    elif interface == 'apt':
                        c = cal_items
                        # TODO implement in citlali the proper
                        # ecsv handling
                        source = _fix_apt(source)
                    else:
                        continue
                    c.append({
                            'filepath': source,
                            'meta': {
                                'interface': interface
                                }
                            })
                self.logger.debug(
                        f"collected {len(data_items)} data_items"
                        f" {len(cal_items)} cal_items")
                return {
                        'meta': meta,
                        'data_items': data_items,
                        'cal_items': cal_items,
                        }

            for key, group in zip(grouped.groups.keys, grouped.groups):
                self.logger.debug(
                        '****** obs={obsnum}_{subobsnum}_{scannum} '
                        '*******'.format(**key))
                self.logger.debug(f'{group}\n')
            input_items = [resolve_input_item(d) for d in grouped.groups]
            cfg['inputs'] = input_items
            cfg['runtime']['output_filepath'] = outdir.as_posix() + '/'
            self.logger.debug(
                    f'resolved low level config:\n{pformat_yaml(cfg)}')
            cfg_filepath = outdir.joinpath('citlali.yaml')
            with open(cfg_filepath, 'w') as fo:
                fo.write(pformat_yaml(cfg))
                # yaml.dump(pformatcfg, fo)
            # run the pipeline
            cmd = [
                    self._binpath,
                    cfg_filepath.as_posix(),
                    ]
            self.logger.debug("reduce with cmd: {}".format(' '.join(cmd)))
            call_subprocess_with_live_output(cmd)
            return locals()
        yield proc
