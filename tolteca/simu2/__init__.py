#!/usr/bin/env python

import numpy as np
import astropy.units as u
from typing import Union
from dataclasses import dataclass, field, is_dataclass
from cached_property import cached_property
import copy

from tollan.utils.dataclass_schema import add_schema
from tollan.utils.log import get_logger, logit, log_to_file
from tollan.utils.fmt import pformat_yaml
from tollan.utils import rupdate

from ..utils.common_schema import PhysicalTypeSchema
from ..utils.config_registry import ConfigRegistry
from ..utils.config_schema import add_config_schema
from ..utils.runtime_context import RuntimeContext, RuntimeContextError
from ..utils import config_from_cli_args


__all__ = ['SimulatorRuntime', 'SimulatorRuntimeError']


@add_schema
@dataclass
class ObsParamsConfig(object):
    """The config class for ``simu.obs_params``."""

    t_exp: Union[u.Quantity, None] = field(
        default=None,
        metadata={
            'description': 'The duration of the observation to simulate.',
            'schema': PhysicalTypeSchema('time'),
            }
        )

    f_smp_mapping: u.Quantity = field(
        default=12. << u.Hz,
        metadata={
            'description': 'The sampling frequency to '
                           'evaluate mapping models.',
            'schema': PhysicalTypeSchema("frequency"),
            }
        )
    f_smp_probing: u.Quantity = field(
        default=120. << u.Hz,
        metadata={
            'description': 'The sampling frequency '
                           'to evaluate detector signals.',
            'schema': PhysicalTypeSchema("frequency"),
            }
        )

    class Meta:
        schema = {
            'ignore_extra_keys': False,
            'description': 'The parameters related to observation.'
            }


@add_schema
@dataclass
class PerfParamsConfig(object):
    """The config class for ``simu.pef_params``."""

    chunk_len: u.Quantity = field(
        default=10 << u.s,
        metadata={
            'description': 'Chunk length to split the simulation to '
                           'reduce memory footprint.',
            'schema': PhysicalTypeSchema("time"),
            }
        )
    catalog_model_render_pixel_size: u.Quantity = field(
        default=0.5 << u.arcsec,
        metadata={
            'description': 'Pixel size to render catalog source model.',
            'schema': PhysicalTypeSchema("angle"),
            }
        )
    mapping_eval_interp_len: Union[u.Quantity, None] = field(
        default=None,
        metadata={
            'description': 'Interp length to speed-up mapping evaluation.',
            'schema': PhysicalTypeSchema("time"),
            }
        )
    mapping_erfa_interp_len: u.Quantity = field(
        default=300 << u.s,
        metadata={
            'description': 'Interp length to speed-up AltAZ to '
                           'ICRS coordinate transformation.',
            'schema': PhysicalTypeSchema("time"),
            }
        )
    atm_eval_interp_alt_step: u.Quantity = field(
        default=4 << u.arcmin,
        metadata={
            'description': 'Interp altitude step to speed-up atm eval.',
            'schema': PhysicalTypeSchema("angle"),
            }
        )
    pre_run_setup_time_grid_size: int = field(
        default=100,
        metadata={
            'description': 'Size of time grid used for pre-run setup.',
            'schema': PhysicalTypeSchema("angle"),
            }
        )

    anim_frame_rate: u.Quantity = field(
        default=300 << u.s,
        metadata={
            'description': 'Frame rate for plotting animation.',
            'schema': PhysicalTypeSchema("frequency"),
            }
        )

    class Meta:
        schema = {
            'ignore_extra_keys': False,
            'description': 'The parameters related to performance tuning.'
            }


mapping_registry = ConfigRegistry.create(
    name='MappingConfig',
    dispatcher_key='type',
    dispatcher_description='The mapping type.'
    )
"""The registry for ``simu.mapping``."""


instrument_registry = ConfigRegistry.create(
    name='InstrumentConfig',
    dispatcher_key='name',
    dispatcher_description='The instrument name.'
    )
"""The registry for ``simu.instrument``."""


sources_registry = ConfigRegistry.create(
    name='SourcesConfig',
    dispatcher_key='type',
    dispatcher_description='The simulator source type.'
    )
"""The registry for ``simu.sources``."""


plots_registry = ConfigRegistry.create(
    name='PlotsConfig',
    dispatcher_key='type',
    dispatcher_description='The plot type.'
    )
"""The registry for ``simu.plots``."""


exports_registry = ConfigRegistry.create(
    name='ExportsConfig',
    dispatcher_key='type',
    dispatcher_description='The export type.'
    )
"""The registry for ``simu.exports``."""

# Load submodules here to populate the registries
from . import mapping as _  # noqa: F401, E402, F811
from . import sources as _  # noqa: F401, E402, F811
from . import plots as _  # noqa: F401, E402, F811
from . import exports as _  # noqa: F401, E402, F811
from . import toltec as _  # noqa: F401, E402, F811
# from . import lmt as _  # noqa: F401, E402, F811


@add_config_schema
@add_schema
@dataclass
class SimuConfig(object):
    """The config for `tolteca.simu`."""

    jobkey: str = field(
        metadata={
            'description': 'The unique identifier the job.'
            }
        )
    instrument: dict = field(
        metadata={
            'description': 'The dict contains the instrument setting.',
            'schema': instrument_registry.schema,
            'pformat_schema_type': f'<{instrument_registry.name}>',
            })
    mapping: dict = field(
        metadata={
            'description': "The simulator mapping trajectory config.",
            'schema': mapping_registry.schema,
            'pformat_schema_type': f'<{mapping_registry.name}>'
            }
        )
    obs_params: ObsParamsConfig = field(
        metadata={
            'description': 'The dict contains the observation parameters.',
            })
    sources: list = field(
        default_factory=list,
        metadata={
            'description': 'The list contains input sources for simulation.',
            'schema': list(sources_registry.item_schemas),
            'pformat_schema_type': f"[<{sources_registry.name}>, ...]"
            })
    perf_params: PerfParamsConfig = field(
        default_factory=PerfParamsConfig,
        metadata={
            'description': 'The dict contains the performance related'
                           ' parameters.',
            })
    plots: list = field(
        default_factory=list,
        metadata={
            'description': 'The list contains config for plotting.',
            'schema': list(plots_registry.item_schemas),
            'pformat_schema_type': f"[<{plots_registry.name}>, ...]"
            })
    exports: list = field(
        default_factory=list,
        metadata={
            'description': 'The list contains config for exporting.',
            'schema': list(exports_registry.item_schemas),
            'pformat_schema_type': f"[<{exports_registry.name}>, ...]"
            })
    plot_only: bool = field(
        default=False,
        metadata={
            'description': 'Make plots of those defined in `plots`.'
            })

    class Meta:
        schema = {
            'ignore_extra_keys': True,
            'description': 'The config dict for the simulator.'
            }
        config_key = 'simu'

    def get_or_create_output_dir(self):
        logger = get_logger()
        rootpath = self.runtime_info.config_info.runtime_context_dir
        output_dir = rootpath.joinpath(self.jobkey)
        if not output_dir.exists():
            with logit(logger.debug, 'create output dir'):
                output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def get_log_file(self):
        return self.runtime_info.logdir.joinpath('simu.log')


class SimulatorRuntimeError(RuntimeContextError):
    """Raise when errors occur in `SimulatorRuntime`."""
    pass


class SimulatorRuntime(RuntimeContext):
    """A class that manages the runtime context of the simulator.

    This class drives the execution of the simulator.
    """

    config_cls = SimuConfig

    logger = get_logger()

    @cached_property
    def simu_config(self):
        """Validate and return the simulator config object..

        The validated config is cached. :meth:`SimulatorRuntime.update`
        should be used to update the underlying config and re-validate.
        """
        return self.config_cls.from_config(
            self.config, rootpath=self.rootpath,
            runtime_info=self.runtime_info)

    def update(self, config):
        self.config_backend.update_override_config(config)
        if 'simu_config' in self.__dict__:
            del self.__dict__['simu_config']

    def cli_run(self, args=None):
        """Run the simulator with CLI as save the result.
        """
        if args is not None:
            _cli_cfg = config_from_cli_args(args)
            # note the cli_cfg is under the namespace simu
            cli_cfg = {self.config_cls.config_key: _cli_cfg}
            if _cli_cfg:
                self.logger.info(
                    f"config specified with commandline arguments:\n"
                    f"{pformat_yaml(cli_cfg)}")
            self.update(cli_cfg)
            cfg = self.simu_config.to_config()
            # here we recursively check the cli_cfg and report
            # if any of the key is ignored by the schema and
            # throw an error

            def _check_ignored(key_prefix, d, c):
                if isinstance(d, dict) and isinstance(c, dict):
                    ignored = set(d.keys()) - set(c.keys())
                    ignored = [f'{key_prefix}.{k}' for k in ignored]
                    if len(ignored) > 0:
                        raise SimulatorRuntimeError(
                            f"Invalid config items specified in "
                            f"the commandline: {ignored}")
                    for k in set(d.keys()).intersection(c.keys()):
                        _check_ignored(f'{key_prefix}{k}', d[k], c[k])
            _check_ignored('', cli_cfg, cfg)
        return self.run()

    def run(self):
        """Run the simulator."""

        cfg = self.simu_config

        self.logger.debug(
            f"run simu with config dict: "
            f"{pformat_yaml(cfg.to_config())}")

        if cfg.plot_only:
            results = []
            for plotter in cfg.plots:
                result = plotter(cfg)
                results.append(result)
                if plotter.save:
                    # TODO handle save here
                    pass
            return results
        # run simulator
        sim = cfg.instrument(cfg)
        obs_params = cfg.obs_params
        perf_params = cfg.perf_params
        m_mapping = cfg.mapping(cfg)
        m_sources = [s(cfg) for s in cfg.sources]

        self.logger.debug(
            f'run {sim} with:{{}}\n'.format(
                pformat_yaml({
                    'obs_params': obs_params.to_dict(),
                    'perf_params': perf_params.to_dict(),
                    })))
        self.logger.debug(
            'mapping:\n{}\n\nsources:\n{}\n'.format(
                m_mapping,
                '\n'.join(str(s) for s in m_sources)
                )
            )

        # create the time grid and run the simulation
        # here we use t_pattern when t_exp is not set
        t_exp = obs_params.t_exp
        if t_exp is None:
            t_pattern = m_mapping.t_pattern
            self.logger.debug(f"mapping pattern time: {t_pattern}")
            t_exp = t_pattern
            self.logger.info(f"use t_exp={t_exp} from mapping pattern")
        else:
            self.logger.info(f"use t_exp={t_exp} from obs_params")

        t_chunks = self._make_time_chunks(
            t_exp=t_exp,
            f_smp=obs_params.f_smp_probing,
            chunk_len=perf_params.chunk_len)

        output_dir = cfg.get_or_create_output_dir()
        log_file = cfg.get_log_file()
        self.logger.info(f'setup logging to file {log_file}')
        with log_to_file(
                filepath=log_file,
                level='DEBUG',
                disable_other_handlers=False
                ):
            output_ctx = sim.output_context(dirpath=output_dir)
            with output_ctx.open():
                self.logger.info(
                    f"write output to {output_ctx.rootpath}")
                # save the config file as YAML
                config_filepath = output_ctx.make_output_filename(
                    'tolteca', '.yaml')
                with open(config_filepath, 'w') as fo:
                    config = copy.deepcopy(self.config)
                    rupdate(config, self.simu_config.to_config())
                    self.yaml_dump(config, fo)
                # save mapping model meta
                output_ctx.write_mapping_meta(
                    mapping=m_mapping, simu_config=cfg)
                # save simulator meta
                output_ctx.write_sim_meta(simu_config=cfg)

                # run simulator for each chunk and save the data
                tod_eval = sim.tod_evaluator(
                    mapping=m_mapping, sources=m_sources,
                    simu_config=cfg,
                    pre_run_setup_time_grid=np.linspace(
                        0, t_exp.to_value(u.s),
                        cfg.perf_params.pre_run_setup_time_grid_size
                        ) << u.s
                    )
                n_chunks = len(t_chunks)
                for ci, t in enumerate(t_chunks):
                    self.logger.info(f"working on chunk {ci} of {n_chunks}")
                    output_ctx.write_sim_data(tod_eval(t))
        return output_dir

    def plot(self, type, **kwargs):
        """Make plot of type `type`."""
        if type not in plots_registry:
            raise ValueError(
                f"Invalid plot type {type}. "
                f"Available types: {plots_registry.keys()}")
        plotter = plots_registry[type].from_dict(kwargs)
        return plotter(self.simu_config)

    @classmethod
    def _make_time_chunks(cls, t_exp, f_smp, chunk_len):
        t = np.arange(
                0, t_exp.to_value(u.s),
                (1 / f_smp).to_value(u.s)) * u.s
        chunk_len = chunk_len
        n_times_per_chunk = int((
                chunk_len * f_smp).to_value(
                        u.dimensionless_unscaled))
        n_times = len(t)
        n_chunks = n_times // n_times_per_chunk + bool(
                n_times % n_times_per_chunk)
        t_chunks = []
        for i in range(n_chunks):
            t_chunks.append(
                    t[i * n_times_per_chunk:(i + 1) * n_times_per_chunk])
        # merge the last chunk if it is too small
        if n_chunks >= 2:
            if len(t_chunks[-1]) * 10 < len(t_chunks[-2]):
                last_chunk = t_chunks.pop()
                t_chunks[-1] = np.hstack([t_chunks[-1], last_chunk])
        n_chunks = len(t_chunks)
        cls.logger.info(
                f"simulate with n_times_per_chunk={n_times_per_chunk}"
                f" n_times={len(t)} n_chunks={n_chunks}")
        return t_chunks


# make a list of all simu config item types
_locals = list(locals().values())
simu_config_item_types = list()
for v in _locals:
    if is_dataclass(v) and hasattr(v, 'schema'):
        simu_config_item_types.append(v)
    elif isinstance(v, ConfigRegistry):
        simu_config_item_types.append(v)
