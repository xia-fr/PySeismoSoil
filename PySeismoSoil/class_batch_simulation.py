from __future__ import annotations

import itertools
import multiprocessing as mp
import os
from typing import Any

from PySeismoSoil import helper_generic as hlp
from PySeismoSoil.class_simulation import (
    Equiv_Linear_Simulation,
    Linear_Simulation,
    Nonlinear_Simulation,
)
from PySeismoSoil.class_simulation_results import Simulation_Results


class Batch_Simulation:
    """
    Run site response simulations in batch.

    Parameters
    ----------
    list_of_simulations : list[Simulation_Results]
        A list of simulation objects. Valid simulation objects include objects
        from these classes: ``Linear_Simulation``, ``Equiv_Linear_Simulation``,
        and ``Nonlinear_Simulation``.
    use_ctx : bool
        For unix systems, provides the option to use the forkserver context for spawning
        subprocesses when running simulations in batch. The forkserver context is recommended
        to avoid slowdowns when PySeismoSoil is being run in batch as part of a code that
        contains additional non-PySeismoSoil variables and module imports. If use_ctx is
        set to True, the top-level code must be guarded under `if __name__ == "__main__":`.

    Attributes
    ----------
    list_of_simulations : list[Simulation_Results]
        Same as the input parameter `list_of_simulations`.
    n_simulations : int
        Number of simulations in the list.
    sim_type : {``Linear_Simulation``, ``Equiv_Linear_Simulation``, ``Nonlinear_Simulation``}
        The object type of the site response simulations.

    Raises
    ------
    TypeError
        When ``list_of_simulations`` is not a list
    ValueError
        When ``list_of_simulations`` has length 0
    """

    def __init__(
            self,
            list_of_simulations: list[Simulation_Results],
            use_ctx: bool = False,
    ) -> None:
        if not isinstance(list_of_simulations, list):
            raise TypeError('`list_of_simulations` should be a list.')

        if len(list_of_simulations) == 0:
            raise ValueError(
                '`list_of_simulations` should have at least one element.'
            )

        sim_0 = list_of_simulations[0]
        if not isinstance(
            sim_0,
            (Linear_Simulation, Equiv_Linear_Simulation, Nonlinear_Simulation),
        ):
            raise TypeError(
                'Elements of `list_of_simulations` should be of '
                'type `Linear_Simulation`, `Equiv_Linear_Simulation`, '
                'or `Nonlinear_Simulation`.',
            )

        if not all(isinstance(i, type(sim_0)) for i in list_of_simulations):
            raise TypeError(
                'All the elements of `list_of_simulations` should be of the same type.',
            )

        n_simulations = len(list_of_simulations)

        self.list_of_simulations = list_of_simulations
        self.n_simulations = n_simulations
        self.sim_type = type(sim_0)

        self.use_ctx = use_ctx
        if use_ctx:
            self.ctx = mp.get_context('forkserver')
            self.ctx.set_forkserver_preload([
                'PySeismoSoil.class_Vs_profile',
                'PySeismoSoil.class_ground_motion',
                'PySeismoSoil.class_simulation',
                'PySeismoSoil.class_batch_simulation',
            ])

    def run(
            self,
            parallel: bool = False,
            n_cores: int | None = 1,
            base_output_dir: str | None = None,
            catch_errors: bool = False,
            verbose: bool = True,
            options: dict[str, Any] | None = None,
    ) -> list[Simulation_Results]:
        """
        Run simulations in batch.

        Parameters
        ----------
        parallel : bool
            Whether to use multiple CPU cores to run simulations.
        n_cores : int | None
            Number of CPU cores to be used. If ``None``, all CPU cores will be
            used.
        base_output_dir : str | None
            The parent directory for saving the output files/figures of the
            current batch.
        catch_errors : bool
            Optionally allows for ValueErrors to be caught during batch simulation,
            so a single error simulation doesn't interrupt the running of others in the
            batch. Simulations that have caught errors will be replaced by `None` in the
            results list.
        verbose : bool
            Whether to print the parallel computing progress info.
        options : dict[str, Any] | None
            Options to be passed to the ``run()`` methods of the relevant
            simulation classes (linear, equivalent linear, or nonlinear). Check
            out the API documentation of the ``run()`` methods here:
            https://pyseismosoil.readthedocs.io/en/stable/api_docs/class_simulation.html
            If None, it is equivalent to an empty dict.

        Returns
        -------
        sim_results : list[Simulation_Results]
            Simulation results corresponding to each simulation object.
        """
        options = {} if options is None else options

        N = self.n_simulations
        n_digits = len(str(N))

        if base_output_dir is None:
            current_time = hlp.get_current_time(for_filename=True)
            base_output_dir = os.path.join('./', 'batch_sim_%s' % current_time)

        other_params = [n_digits, base_output_dir, catch_errors, options]

        if not parallel:
            sim_results = []
            for i in range(self.n_simulations):
                sim_results.append(self._run_single_sim([i, other_params]))
            # END FOR
        else:
            sim_results = []

            if self.use_ctx:
                if verbose:
                    print(
                        'Parallel computing in progress using forkserver...',
                        end=' ',
                    )

                with self.ctx.Pool(processes=n_cores) as p:
                    sim_results = p.map(
                        self._run_single_sim,
                        itertools.product(range(N), [other_params]),
                    )

            else:
                if verbose:
                    print('Parallel computing in progress...', end=' ')

                with mp.Pool(n_cores) as p:
                    sim_results = p.map(
                        self._run_single_sim,
                        itertools.product(range(N), [other_params]),
                    )

            if verbose:
                print('done.')

            # Because no figures can be plotted in the parallel pool:
            if options.get('show_fig', False):
                for sim_result in sim_results:
                    sim_result.plot(save_fig=options.get('save_fig', False))
                # END FOR
            # END IF
        # END IF

        return sim_results

    def _run_single_sim(self, all_params: list[Any]) -> Simulation_Results:
        """
        Run a single simulation.

        Parameters
        ----------
        all_params : list[Any]
            All the parameters needed for running the simulation. It should
            have the following structure:
                [i, [n_digits, base_output_dir, catch_errors, options]]
            where:
                - ``i`` is the index of the current simulation in the batch.
                - ``n_digits`` is the number of digits of the length of the
                  batch. (For example, if there are 125 simulations, then
                  ``n_digits`` should be 3.)
                - ``base_output_dir``: same as in the ``run()`` method
                - ``catch_errors``: same as in the ``run()`` method
                - ``options``: same as in the ``run()`` method

        Returns
        -------
        sim_result : Simulation_Results
            Simulation results of a single simulation object.
        """
        i, other_params = all_params  # unpack
        n_digits, base_output_dir, catch_errors, options = other_params  # unpack
        output_dir = os.path.join(base_output_dir, str(i).rjust(n_digits, '0'))
        if self.sim_type == Nonlinear_Simulation:
            options.update({'sim_dir': output_dir})
        else:  # linear or equivalent linear
            options.update({'output_dir': output_dir})

        sim_obj = self.list_of_simulations[i]
        if catch_errors:
            try:
                sim_result = sim_obj.run(**options)
            except ValueError:
                sim_result = None
                print('Warning: ValueError encountered.')
        else:
            sim_result = sim_obj.run(**options)

        return sim_result
