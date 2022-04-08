#!/usr/bin/env python

from dash_component_template import ComponentTemplate
from dash import html, dcc, Input, Output, State
import dash_bootstrap_components as dbc

from dasha.web.templates.common import (
        LabeledChecklist,
        DownloadButton
        )
import dash_js9 as djs9

import astropy.units as u
from astropy.table import QTable
from astropy.modeling.functional_models import GAUSSIAN_SIGMA_TO_FWHM
from astropy.coordinates import SkyCoord
from astropy.convolution import convolve_fft
from astropy.convolution import Gaussian2DKernel
from astropy.io import fits
from astropy.wcs import WCS
import numpy as np
import pandas as pd
import cv2
from io import BytesIO
from base64 import b64encode

from tollan.utils.log import get_logger, timeit

from ....utils import yaml_dump
from ....simu.toltec.toltec_info import toltec_info
from ....simu import instrument_registry
from ....simu.utils import SkyBoundingBox, make_wcs
from ....simu.exports import LmtOTExporterConfig
from .base import ObsInstru, ObsSite


class Toltec(ObsInstru, name='toltec'):
    """An `ObsInstru` for TolTEC."""

    info = toltec_info
    display_name = info['name_long']

    class ResultPanel(ComponentTemplate):
        class Meta:
            component_cls = dbc.Container

        def __init__(self, instru, **kwargs):
            kwargs.setdefault("fluid", True)
            super().__init__(**kwargs)
            self._instru = instru
            container = self
            fitsview_container, info_container = container.colgrid(1, 2)
            self._fitsview_loading = fitsview_container.child(
                dbc.Spinner,
                show_initially=False, color='primary',
                spinner_style={"width": "5rem", "height": "5rem"}
                )
            self._fitsview = self._fitsview_loading.child(
                djs9.DashJS9,
                style={
                    'width': '100%',
                    'min-height': '500px',
                    'height': '40vh'
                    },
                )
            self._info_loading = info_container.child(
                dbc.Spinner,
                show_initially=False, color='primary',
                spinner_style={"width": "5rem", "height": "5rem"}
                )

        def make_callbacks(self, app, exec_info_store_id):
            fitsview = self._fitsview
            info = self._info_loading.child(
                html.Div, style={'min-height': '500px'})

            app.clientside_callback(
                '''
                function(exec_info) {
                    // console.log(exec_info);
                    if (!exec_info) {
                        return Array(1).fill(window.dash_clientside.no_update);
                    }
                    return [exec_info.instru.fits_images];
                }
                ''',
                [
                    Output(fitsview.id, 'data'),
                    ],
                [
                    Input(exec_info_store_id, 'data'),
                    ]
                )

            app.clientside_callback(
                '''
                function(exec_info) {
                    // console.log(exec_info);
                    if (!exec_info) {
                        return Array(1).fill(window.dash_clientside.no_update);
                    }
                    return [exec_info.instru.info];
                }
                ''',
                [
                    Output(info.id, 'children'),
                    ],
                [
                    Input(exec_info_store_id, 'data'),
                    ]
                )

        @property
        def loading_indicators(self):
            return {
                'outputs': [
                    Output(self._fitsview_loading.id, 'color'),
                    Output(self._info_loading.id, 'color')
                    ],
                'states': [
                    State(self._fitsview_loading.id, 'color'),
                    State(self._info_loading.id, 'color'),
                    ]
                }

    class ResultControlPanel(ComponentTemplate):
        class Meta:
            component_cls = dbc.Container

        def __init__(self, instru, **kwargs):
            kwargs.setdefault("fluid", True)
            super().__init__(**kwargs)
            container = self
            dlbtn_props = {'disabled': True}

            self._lmtot_download = container.child(
                DownloadButton(
                    button_text='LMT OT Script',
                    className='me-2',
                    button_props=dlbtn_props,
                    tooltip=(
                        'Download LMT Observation Tool script to '
                        'execute the observation at LMT.')
                    )
                )
            self._simuconfig_download = container.child(
                DownloadButton(
                    button_text='Simu. Config',
                    className='me-2',
                    button_props=dlbtn_props,
                    tooltip=(
                        'Download tolteca.simu 60_simu.yaml config file to '
                        'run the observation simulator.')
                    )
                )
            self._fits_download = container.child(
                DownloadButton(
                    button_text='Coverage Map',
                    className='me-2',
                    button_props=dlbtn_props,
                    tooltip=(
                        'Download the generated FITS (approximate) coverage '
                        'image for the observation.'
                        )
                    )
                )

        def make_callbacks(self, app, exec_info_store_id):

            for dl in [
                    self._lmtot_download,
                    self._simuconfig_download,
                    self._fits_download]:
                app.clientside_callback(
                    '''
                    function(exec_info) {
                        if (!exec_info) {
                            return true;
                        }
                        return false;
                    }
                    ''',
                    Output(dl.button.id, 'disabled'),
                    [
                        Input(exec_info_store_id, 'data'),
                        ]
                    )

            app.clientside_callback(
                r'''
                function(n_clicks, exec_info) {
                    // console.log(exec_info);
                    if (!exec_info) {
                        return window.dash_clientside.no_update;
                    }
                    target = exec_info.exec_config.mapping.target

                    filename = (
                        'target_' + target + '.lmtot').replace(/\s+/g, '-');
                    return {
                        content: exec_info.instru.lmtot,
                        base64: false,
                        filename: filename,
                        type: 'text/plain;charset=UTF-8'
                        };
                }
                ''',
                Output(self._lmtot_download.download.id, 'data'),
                [
                    Input(self._lmtot_download.button.id, 'n_clicks'),
                    State(exec_info_store_id, 'data'),
                    ]
                )

            app.clientside_callback(
                '''
                function(n_clicks, exec_info) {
                    // console.log(exec_info);
                    if (!exec_info) {
                        return window.dash_clientside.no_update;
                    }
                    filename = '60_simu.yaml'
                    return {
                        content: exec_info.instru.simu_config,
                        base64: false,
                        filename: filename,
                        type: 'text/plain;charset=UTF-8'
                        };
                }
                ''',
                Output(self._simuconfig_download.download.id, 'data'),
                [
                    Input(self._simuconfig_download.button.id, 'n_clicks'),
                    State(exec_info_store_id, 'data'),
                    ]
                )

            app.clientside_callback(
                '''
                function(n_clicks, exec_info) {
                    // console.log(exec_info);
                    if (!exec_info) {
                        return window.dash_clientside.no_update;
                    }
                    im = exec_info.instru.fits_images[0]
                    return {
                        content: im.blob,
                        base64: true,
                        filename: im.options.file,
                        type: 'application/fits'
                        };
                }
                ''',
                Output(self._fits_download.download.id, 'data'),
                [
                    Input(self._fits_download.button.id, 'n_clicks'),
                    State(exec_info_store_id, 'data'),
                    ]
                )

    class ControlPanel(ComponentTemplate):
        class Meta:
            component_cls = dbc.Form

        def __init__(self, instru, **kwargs):
            super().__init__(**kwargs)
            self._instru = instru
            container = self
            self._info_store = container.child(dcc.Store, data={
                'name': instru.name
                })

        @property
        def info_store(self):
            return self._info_store

        def setup_layout(self, app):
            toltec_info = self._instru.info
            container = self.child(dbc.Row, className='gy-2')
            band_select = container.child(
                    LabeledChecklist(
                        label_text='TolTEC band',
                        className='w-auto',
                        size='sm',
                        # set to true to allow multiple check
                        multi=False,
                        input_props={
                            'style': {
                                'text-transform': 'none'
                                }
                            }
                        )).checklist
            band_select.options = [
                    {
                        'label': str(toltec_info[a]['wl_center']),
                        'value': a,
                        }
                    for a in toltec_info['array_names']
                    ]
            band_select.value = toltec_info['array_names'][0]

            covtype_select = container.child(
                    LabeledChecklist(
                        label_text='Coverage Unit',
                        className='w-auto',
                        size='sm',
                        # set to true to allow multiple check
                        multi=False
                        )).checklist
            covtype_select.options = [
                    {
                        'label': 'mJy/beam',
                        'value': 'depth',
                        },
                    {
                        'label': 's/pixel',
                        'value': 'time',
                        },
                    ]
            covtype_select.value = 'depth'
            super().setup_layout(app)

            # collect inputs to store
            app.clientside_callback(
                """
                function(band_select_value, covtype_select_value, data_init) {
                    data = {...data_init}
                    data['array_name'] = band_select_value
                    data['coverage_map_type'] = covtype_select_value
                    return data
                }
                """,
                Output(self.info_store.id, 'data'),
                [
                    Input(band_select.id, 'value'),
                    Input(covtype_select.id, 'value'),
                    State(self.info_store.id, 'data')
                    ]
                )

    @staticmethod
    def _hdulist_to_base64(hdulist):
        fo = BytesIO()
        hdulist.writeto(fo, overwrite=True)
        return b64encode(fo.getvalue()).decode("utf-8")

    @classmethod
    def make_traj_data(cls, exec_config, bs_traj_data):
        logger = get_logger()
        logger.debug("make traj data for instru toltec")
        # get observer from site name
        observer = ObsSite.get_observer(exec_config.site_data['name'])
        mapping_model = exec_config.mapping.get_model(observer=observer)
        instru = instrument_registry.schema.validate({
            'name': 'toltec',
            'polarized': False
            }, create_instance=True)
        simulator = instru.simulator
        array_name = exec_config.instru_data['array_name']
        apt = simulator.array_prop_table
        # apt_0 is the apt for the current selected array
        apt_0 = apt[apt['array_name'] == array_name]
        # this is the apt including only detectors on the edge
        # useful for making the footprint outline
        ei = apt.meta[array_name]["edge_indices"]

        det_dlon = apt_0['x_t']
        det_dlat = apt_0['y_t']

        # apply the footprint on target
        # to do so we find the closest poinit in the trajectory to
        # the target and do the transformation
        bs_coords_icrs = SkyCoord(
                bs_traj_data['ra'], bs_traj_data['dec'], frame='icrs')
        target_icrs = mapping_model.target.transform_to('icrs')
        i_closest = np.argmin(
                target_icrs.separation(bs_coords_icrs))
        # the center of the array overlay in altaz
        az1 = bs_traj_data['az'][i_closest]
        alt1 = bs_traj_data['alt'][i_closest]
        t1 = bs_traj_data['time_obs'][i_closest]
        c1 = SkyCoord(
                az=az1, alt=alt1, frame=observer.altaz(time=t1)
                )
        det_altaz = SkyCoord(
                det_dlon, det_dlat,
                frame=c1.skyoffset_frame()).transform_to(c1.frame)
        det_icrs = det_altaz.transform_to("icrs")

        det_sky_bbox_icrs = SkyBoundingBox.from_lonlat(
            det_icrs.ra,
            det_icrs.dec
            )
        # make coverage fits image in s_per_pix
        # we'll init the power loading model to estimate the conversion factor
        # of this to mJy/beam
        cov_hdulist_s_per_pix = cls._make_cov_hdulist(ctx=locals())
        # overlay traces
        # each trace is for one polarimetry group
        offset_traces = list()
        for i, (pg, marker) in enumerate([(0, 'cross'), (1, 'x')]):
            mask = apt_0['pg'] == pg
            offset_traces.append({
                'x': det_dlon[mask].to_value(u.arcmin),
                'y': det_dlat[mask].to_value(u.arcmin),
                'mode': 'markers',
                'marker': {
                    'symbol': marker,
                    'color': 'gray',
                    'size': 6,
                    },
                'legendgroup': 'toltec_array_fov',
                'showlegend': i == 0,
                'name': f"Toggle FOV: {cls.info[array_name]['name_long']}"
                })

        # skyview layers
        skyview_layers = list()
        n_dets = len(det_icrs)
        det_tbl = pd.DataFrame.from_dict({
            "ra": det_icrs.ra.degree,
            "dec": det_icrs.dec.degree,
            "color": ["blue"] * n_dets,
            "type": ["circle"] * n_dets,
            "radius": [
                cls.info[array_name]["a_fwhm"].to_value(u.deg) * 0.5
                ] * n_dets,
            })
        skyview_layers.extend([
            {
                "type": "overlay",
                "data": det_tbl.to_dict(orient="records"),
                "options": {
                    'name': f"Detectors: {cls.info[array_name]['name_long']}",
                    "show": False,
                }
            },
            {
                'type': "overlay",
                "data": [{
                    "type": "polygon",
                    "data": list(zip(
                        det_icrs.ra.degree[ei],
                        det_icrs.dec.degree[ei]
                        )),
                    }],
                "options": {
                    'name': f"FOV: {cls.info[array_name]['name_long']}",
                    "color": "#cc66cc",
                    "show": True,
                    "lineWidth": 8,
                    }
                },
            ])

        # tolteca.simu
        simrt = exec_config.get_simulator_runtime()
        simu_config = simrt.config
        simu_config_yaml = yaml_dump(simrt.config.to_config_dict())

        # use power loading model to infer the sensitivity
        # this is rough esitmate based on the mean altitude of the observation.
        tplm = simu_config.sources[0].get_power_loading_model()
        target_alt = bs_traj_data['target_alt']
        alt_mean = target_alt.mean()
        t_exp = bs_traj_data['t_exp']
        # for this purpose we generate the info for all the three arrays
        sens_coeff = np.sqrt(2.)
        sens_tbl = list()
        array_names = cls.info['array_names']

        for an in array_names:
            # TODO fix the api
            aplm = tplm._array_power_loading_models[an]
            result = {
                'array_name': an,
                'alt_mean': alt_mean,
                'P': aplm._get_P(alt_mean)
                }
            result.update(aplm._get_noise(alt_mean, return_avg=True))
            result['dsens'] = sens_coeff * result['nefd'].to(
                u.mJy * u.s ** 0.5)
            sens_tbl.append(result)
        sens_tbl = QTable(rows=sens_tbl)
        logger.debug(f"summary table for all arrays:\n{sens_tbl}")

        # for the current array we get the mapping area from the cov map
        # and convert to mJy/beam if requested
        def _get_entry(an):
            return sens_tbl[sens_tbl['array_name'] == an][0]

        sens_entry = _get_entry(array_name)
        cov_data = cov_hdulist_s_per_pix[1].data
        cov_wcs = WCS(cov_hdulist_s_per_pix[1].header)
        cov_pixarea = cov_wcs.proj_plane_pixel_area()
        cov_max = cov_data.max()
        m_cov = (cov_data > 0.02 * cov_max)
        m_cov_01 = (cov_data > 0.1 * cov_max)
        map_area = (m_cov_01.sum() * cov_pixarea).to(u.deg ** 2)
        a_stddev = cls.info[array_name]['a_fwhm'] / GAUSSIAN_SIGMA_TO_FWHM
        b_stddev = cls.info[array_name]['b_fwhm'] / GAUSSIAN_SIGMA_TO_FWHM
        beam_area = 2 * np.pi * a_stddev * b_stddev
        beam_area_pix2 = (beam_area / cov_pixarea).to_value(
            u.dimensionless_unscaled)

        cov_data_mJy_per_beam = np.zeros(cov_data.shape, dtype='d')
        cov_data_mJy_per_beam[m_cov] = (
            sens_coeff * sens_entry['nefd']
            / np.sqrt(cov_data[m_cov] * beam_area_pix2))
        # calculate rms depth from the depth map
        depth_rms = np.median(cov_data_mJy_per_beam[m_cov_01]) << u.mJy
        # scale the depth rms to all arrays and update the sens tbl
        sens_tbl['depth_rms'] = (
            depth_rms / sens_entry['nefd'] * sens_tbl['nefd'])
        sens_tbl['t_exp'] = t_exp
        sens_tbl['map_area'] = map_area

        # make cov hdulist depending on the instru_data cov unit settings
        if exec_config.instru_data['coverage_map_type'] == 'depth':
            cov_hdulist = cov_hdulist_s_per_pix.copy()
            cov_hdulist[1].header['BUNIT'] = 'mJy / beam'
            cov_hdulist[1].data = cov_data_mJy_per_beam
        else:
            cov_hdulist = cov_hdulist_s_per_pix

        # from the cov image we can create a countour showing the outline of
        # the observation on the skyview
        cov_ctr = cov_hdulist[1].data.copy()
        cov_ctr[~m_cov] = 0
        im = cv2.normalize(
            src=cov_ctr,
            dst=None,
            alpha=0,
            beta=255,
            norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8UC1)
        cxy = cv2.findContours(
            im,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE)[0]
        # the cxy is a tuple of multiple contours
        # we select the first significant one to use
        # hopefully this is the outline...
        for c in cxy:
            if c.shape[0] > 2:
                cxy = c
                break
        else:
            # no coutrous found, just set to the last one
            # current one
            logger.debug("unabled to generate outline contour")
            cxy = c
        cxy_s = cv2.approxPolyDP(
            cxy,
            0.002 * cv2.arcLength(cxy, True), True
            )[:, 0, :]
        cra, cdec = cov_wcs.pixel_to_world_values(
            cxy_s[:, 0], cxy_s[:, 1]
            )
        skyview_layers.extend([
            {
                'type': "overlay",
                "data": [{
                    "type": "polygon",
                    "data": list(zip(cra, cdec)),
                    }],
                "options": {
                    'name': "Coverage Outline",
                    "color": "#66cccc",
                    "show": True,
                    "lineWidth": 4,
                    }
                },
            ])

        # create the layout to display the sensitivity info table
        def _make_sens_tab_content(an):
            entry = _get_entry(an)

            def _fmt(v):
                if isinstance(v, str):
                    return v
                return f'{v.value:.3g} {v.unit:unicode}'
            key_labels = {
                'array_name': 'Array Name',
                'alt_mean': 'Mean Alt.',
                't_exp': 'Total Exp. Time',
                'dsens': 'Detector Sens.',
                'map_area': 'Map Area',
                'depth_rms': 'Median RMS sens.'
            }
            data = {v: _fmt(entry[k]) for k, v in key_labels.items()}
            data['Coverage Map Unit'] = cov_hdulist[1].header['BUNIT']
            df = pd.DataFrame(data.items(), columns=['', ''])
            t = dbc.Table.from_dataframe(
                    df, striped=True, bordered=True, hover=True,
                    className='mx-0 my-0')
            # get rid of the first child which is the header
            t.children = t.children[1:]
            return dbc.Card(
                [
                    dbc.CardBody(
                        t,
                        className='py-0 px-0',
                        style={'border-width': '0px'}
                    ),
                ],
            )
        sens_tbl_layout = dbc.Tabs(
            [
                dbc.Tab(
                    _make_sens_tab_content(an),
                    label=str(cls.info[an]['wl_center']),
                    tab_id=an,
                    activeTabClassName="fw-bold",
                    )
                for an in array_names
                ],
            active_tab=array_name
            )

        # lmtot script export
        lmtot_exporter = LmtOTExporterConfig(save=False)
        lmtot_content = lmtot_exporter(simu_config)
        return {
            "dlon": det_dlon,
            "dlat": det_dlat,
            "az": det_altaz.az,
            "alt": det_altaz.alt,
            "ra": det_icrs.ra,
            "dec": det_icrs.dec,
            "sky_bbox_icrs": det_sky_bbox_icrs,
            'overlay_traces': {
                'offset': offset_traces
                },
            'skyview_layers': skyview_layers,
            'results': {
                'fits_images': [
                    {
                        'options': {
                            'file': f"obsplanner_toltec_{array_name}_cov.fits",
                            },
                        'blob': cls._hdulist_to_base64(cov_hdulist),
                        }
                    ],
                'lmtot': lmtot_content,
                'simu_config': simu_config_yaml,
                'info': sens_tbl_layout,
                }
            }

    @classmethod
    def _make_cov_hdu_approx(cls, ctx):
        logger = get_logger()
        # unpack the cxt
        bs_traj_data = ctx['bs_traj_data']
        det_icrs = ctx['det_icrs']
        det_sky_bbox_icrs = ctx['det_sky_bbox_icrs']
        dt_smp = bs_traj_data['time_obs'][1] - bs_traj_data['time_obs'][0]
        array_name = ctx['array_name']

        # create the wcs
        pixscale = u.pixel_scale(4. << u.arcsec / u.pix)
        # the pixsize will be int factor of 2 arcsec.
        adaptive_pixscale_factor = 0.5
        n_pix_max = 1e6  # 8 MB of data
        bs_sky_bbox_icrs = bs_traj_data['sky_bbox_icrs']
        sky_bbox_wcs = bs_sky_bbox_icrs.pad_with(
            det_sky_bbox_icrs.width + (2 << u.arcmin),
            det_sky_bbox_icrs.height + (2 << u.arcmin),
            )
        wcsobj = make_wcs(
            sky_bbox=sky_bbox_wcs, pixscale=pixscale, n_pix_max=n_pix_max,
            adaptive_pixscale_factor=adaptive_pixscale_factor)

        bs_xy = wcsobj.world_to_pixel_values(
            bs_traj_data['ra'].degree,
            bs_traj_data['dec'].degree,
            )
        det_xy = wcsobj.world_to_pixel_values(
            det_icrs.ra.degree,
            det_icrs.dec.degree,
            )
        # because these are bin edges, we add 1 at end to
        # makesure the nx and ny are included in the range.
        xbins = np.arange(wcsobj.pixel_shape[0] + 1)
        ybins = np.arange(wcsobj.pixel_shape[1] + 1)
        det_xbins = np.arange(
                np.floor(det_xy[0].min()),
                np.ceil(det_xy[0].max()) + 1 + 1
                )
        det_ybins = np.arange(
                np.floor(det_xy[1].min()),
                np.ceil(det_xy[1].max()) + 1 + 1
                )
        # note the axis order ij -> yx
        bs_im, _, _ = np.histogram2d(
                bs_xy[1],
                bs_xy[0],
                bins=[ybins, xbins])
        # scale to coverage image of unit s / pix
        bs_im *= dt_smp.to_value(u.s)

        det_im, _, _ = np.histogram2d(
                det_xy[1],
                det_xy[0],
                bins=[det_ybins, det_xbins]
                )
        # convolve boresignt image with the detector image
        with timeit("convolve with array layout"):
            cov_im = convolve_fft(
                bs_im, det_im,
                normalize_kernel=False, allow_huge=True)
        with timeit("convolve with beam"):
            a_stddev = cls.info[array_name]['a_fwhm'] / GAUSSIAN_SIGMA_TO_FWHM
            b_stddev = cls.info[array_name]['b_fwhm'] / GAUSSIAN_SIGMA_TO_FWHM
            g = Gaussian2DKernel(
                    a_stddev.to_value(
                        u.pix, equivalencies=pixscale),
                    b_stddev.to_value(
                        u.pix, equivalencies=pixscale),
                   )
            cov_im = convolve_fft(cov_im, g, normalize_kernel=False)
        logger.debug(
                f'total exp time on coverage map: '
                f'{(cov_im.sum() / det_im.sum() << u.s).to(u.min)}')
        logger.debug(
                f'total time of observation: '
                f'{bs_traj_data["t_exp"].to(u.min)}')
        cov_hdr = wcsobj.to_header()
        cov_hdr['BUNIT'] = 's / pix'
        cov_hdr.append((
            "ARRAYNAM", array_name,
            "The name of the TolTEC array"))
        cov_hdr.append((
            "BAND", array_name,
            "The name of the TolTEC array"))
        return fits.ImageHDU(data=cov_im, header=cov_hdr)

    @classmethod
    def _make_cov_hdulist(cls, ctx):
        bs_traj_data = ctx['bs_traj_data']
        t_exp = bs_traj_data['t_exp']
        target_alt = bs_traj_data['target_alt']
        site_info = cls.info['site']
        phdr = fits.Header()
        phdr.append((
            'ORIGIN', 'The TolTEC Project',
            'Organization generating this FITS file'
            ))
        phdr.append((
            'CREATOR', cls.__qualname__,
            'The software used to create this FITS file'
            ))
        phdr.append((
            'TELESCOP', site_info['name'],
            site_info['name_long']
            ))
        phdr.append((
            'INSTRUME', cls.info['name'],
            cls.info['name_long']
            ))
        phdr.append((
            'EXPTIME', f'{t_exp.to_value(u.s):.3g}',
            'Exposure time (s)'
            ))
        phdr.append((
            'OBSDUR', f'{t_exp.to_value(u.s):g}',
            'Observation duration (s)'
            ))
        phdr.append((
            'MEANALT', '{0:f}'.format(
                  target_alt.mean().to_value(u.deg)),
            'Mean altitude of the target during observation (deg)'))
        hdulist = [
            fits.PrimaryHDU(header=phdr),
            cls._make_cov_hdu_approx(ctx)
            ]
        hdulist = fits.HDUList(hdulist)
        return hdulist