#! /usr/bin/env python

import re
from pathlib import Path
from datetime import datetime
import os

from astropy import log


class ToltecDataFileSpec(object):

    name = "toltec.1"

    @classmethod
    def _info_from_filename(cls, filename):
        re_toltec_file = (
            r'^(?P<interface>(?P<instru>toltec)(?P<nwid>\d+))_(?P<obsid>\d+)_'
            r'(?P<subobsid>\d+)_(?P<scanid>\d+)_(?P<ut>\d{4}_'
            r'\d{2}_\d{2}(?:_\d{2}_\d{2}_\d{2}))(?:_(?P<kindstr>[^\/.]+))?'
            r'\.(?P<fileext>.+)$')
        dispatch_toltec = {
            'nwid': int,
            'obsid': int,
            'subobsid': int,
            'scanid': int,
            'ut': lambda v: datetime.strptime(v, '%Y_%m_%d_%H_%M_%S'),
                }

        def post_toltec(info):
            if 'kindstr' not in info:
                info['kindstr'] = 'timestream'
            if info is not None and info['fileext'].lower() != "nc":
                info['kindstr'] = 'ancillary'

        re_wyatt_file = (
            r'^(?P<interface>(?P<instru>wyatt))'
            r'_(?P<ut>\d{4}-\d{2}-\d{2})'
            r'_(?P<obsid>\d+)_(?P<subobsid>\d+)_(?P<scanid>\d+)'
            r'(?:_(?P<kindstr>[^\/.]+))?'
            r'\.(?P<fileext>.+)$')
        dispatch_wyatt = {
            'obsid': int,
            'subobsid': int,
            'scanid': int,
            'ut': lambda v: datetime.strptime(v, '%Y-%m-%d'),
                }

        def post_wyatt(info):
            pass

        info = None
        for re_, dispatch, post in [
                (re_toltec_file, dispatch_toltec, post_toltec),
                (re_wyatt_file, dispatch_wyatt, post_wyatt)
                ]:
            m = re.match(re_, filename)
            if m is not None:
                info = {k: dispatch.get(k, lambda v: v)(v) for k, v
                        in m.groupdict().items()}
                post(info)
                break
        return info

    @classmethod
    def info_from_filename(cls, path, resolve=True):
        if resolve and path.is_symlink():
            path = path.resolve()
        info = cls._info_from_filename(path.name)
        if info is not None:
            info['source'] = path
            master = path.parent.name
            if master == f'{info["interface"]}':
                master = path.parent.parent.name
            info['master'] = master
        return info

    @staticmethod
    def runtime_datafile_links(path, master=None):
        runtime_link_patterns = ['toltec[0-9].nc', 'toltec[0-9][0-9].nc']
        files = []
        for pattern in runtime_link_patterns:
            if master is not None:
                pattern = os.path.join(
                        master, pattern.split('.')[0], pattern)
            files.extend(path.glob(pattern))
        return files


class DataFileStore(object):

    spec = ToltecDataFileSpec

    def __init__(self, rootpath=None):
        self.rootpath = rootpath

    @property
    def rootpath(self):
        return self._rootpath

    @rootpath.setter
    def rootpath(self, path):
        self._rootpath = self._normalize_path(path)

    @staticmethod
    def _normalize_path(p):
        try:
            return Path(p).expanduser().absolute()
        except Exception:
            log.error(f"unable to resolve path {p}")
            return Path(p).absolute()

    def runtime_datafile_links(self, master=None):
        path = self.rootpath
        result = self.spec.runtime_datafile_links(path, master=None)
        for p, m in ((path, ''), (path.parent, path.name)):
            result = self.spec.runtime_datafile_links(p, master=m)
            if result:
                return result
        else:
            return list()