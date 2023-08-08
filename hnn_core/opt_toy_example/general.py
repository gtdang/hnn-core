"""Parameter optimization."""

# Authors: Carolina Fernandez <cxf418@miami.edu>
#          Nick Tolley <nicholas_tolley@brown.edu>
#          Ryan Thorpe <ryan_thorpe@brown.edu>
#          Mainak Jas <mjas@mgh.harvard.edu>

import numpy as np

from metrics import _rmse_evoked  # change path***

from skopt import gp_minimize
from scipy.optimize import fmin_cobyla


class Optimizer:
    def __init__(self, net, constraints, set_params, solver, obj_fun,
                 tstop, scale_factor=1., smooth_window_len=None):
        if net.external_drives:
            raise ValueError("The current Network instance has external " +
                             "drives, provide a Network object with no " +
                             "drives.")
        self.net = net
        self.constraints = constraints
        self._set_params = set_params
        # Optimizer method
        if solver == 'bayesian':
            self._assemble_constraints = _assemble_constraints_bayesian
            self._run_opt = _run_opt_bayesian
        elif solver == 'cobyla':
            self._assemble_constraints = _assemble_constraints_cobyla
            self._run_opt = _run_opt_cobyla
        else:
            raise ValueError("solver must be 'bayesian' or 'cobyla'")
        # Response to be optimized
        if obj_fun == 'evoked':
            self.obj_fun = _rmse_evoked
        else:
            raise ValueError("obj_fun must be 'evoked'")
        self.scale_factor = scale_factor
        self.smooth_window_len = smooth_window_len
        self.tstop = tstop
        self.net_ = None
        self.obj = list()
        self.opt_params = None
        self.max_iter = 200

    def __repr__(self):
        class_name = self.__class__.__name__
        return class_name

    def fit(self, target):
        """
        Runs optimization routine.

        Parameters
        ----------
        target : ndarray
            The recorded dipole.

        Returns
        -------
        None.

        """

        constraints = self._assemble_constraints(self.constraints)
        initial_params = _get_initial_params(self.constraints)

        opt_params, obj, net_ = self._run_opt(self.net,
                                              constraints,
                                              initial_params,
                                              self._set_params,
                                              self.obj_fun,
                                              self.scale_factor,
                                              self.smooth_window_len,
                                              self.tstop,
                                              self.max_iter,
                                              target)

        self.opt_params = opt_params
        self.obj = obj
        self.net_ = net_
        return

    def plot_convergence(self, ax=None, show=True):
        """
        Convergence plot.

        Parameters
        ----------
        ax : instance of matplotlib figure, None
            The matplotlib axis. The default is None.
        show : bool
            If True, show the figure. The default is True.

        Returns
        -------
        fig : instance of plt.fig
            The matplotlib figure handle.
        """

        import matplotlib as mpl
        import matplotlib.pyplot as plt

        if ax is None:
            fig, ax = plt.subplots(constrained_layout=True)

        axis = ax if isinstance(ax, mpl.axes._axes.Axes) else ax

        x = list(range(1, self.max_iter + 1))
        y_min = min(self.obj) - 0.01
        y_max = max(self.obj) + 0.01

        axis.plot(x, self.obj, color='black')
        axis.set_ylim([y_min, y_max])
        axis.set_title('Convergence')
        axis.set_xlabel('Number of calls')
        axis.set_ylabel('Objective value')
        axis.grid(visible=True)

        fig.show(show)
        return axis.get_figure()


def _get_initial_params(constraints):
    """
    Gets initial parameters as midpoints of parameter ranges.

    Parameters
    ----------
    constraints : dict
        The user-defined constraints.

    Returns
    -------
    initial_params : dict
        Keys are parameter names, values are initial parameters.

    """

    initial_params = dict()
    for cons_key in constraints:
        initial_params.update({cons_key: ((constraints[cons_key][0] +
                                          constraints[cons_key][1]))/2})

    return initial_params


def _assemble_constraints_bayesian(constraints):
    """
    Assembles constraints in format required by gp_minimize.

    Parameters
    ----------
    constraints : dict
        The user-defined constraints.

    Returns
    -------
    cons_bayesian : list of tuples
        Lower and higher limit for each parameter.
    """

    # assemble constraints in solver-specific format
    cons_bayesian = list(constraints.values())
    return cons_bayesian


def _assemble_constraints_cobyla(constraints):
    """
    Assembles constraints in format required by fmin_cobyla.

    Parameters
    ----------
    constraints : dict
        The user-defined constraints.

    Returns
    -------
    cons_bayesian : dict
        Set of functions.
    """

    # assemble constraints in solver-specific format
    cons_cobyla = list()
    for idx, cons_key in enumerate(constraints):
        cons_cobyla.append(lambda x, idx=idx:
                           float(constraints[cons_key][1]) - x[idx])
        cons_cobyla.append(lambda x, idx=idx:
                           x[idx] - float(constraints[cons_key][0]))

    return cons_cobyla


def _update_params(initial_params, predicted_params):
    """
    Update param_dict with predicted parameters.

    Parameters
    ----------
    initial_params : dict
        Keys are parameter names, values are initial parameters.
    predicted_params : list
        Parameters selected by the optimizer.

    Returns
    -------
    params_dict : dict
        Keys are parameter names, values are parameters.
    """

    param_dict = dict()
    for param_key, param_name in enumerate(initial_params):
        param_dict.update({param_name: predicted_params[param_key]})

    return param_dict


def _run_opt_bayesian(net, constraints, initial_params, set_params, obj_fun,
                      scale_factor, smooth_window_len, tstop, max_iter,
                      target):
    """
    Runs optimization routine with gp_minimize optimizer.

    Parameters
    ----------
    net : Network
        The network object.
    constraints : list of tuples
        Parameter constraints in solver-specific format.
    initial_params : dict
        Keys are parameter names, values are initial parameters..
    set_params : func
        User-defined function that sets parameters in network drives.
    obj_fun : func
        The objective function.
    scale_factor : float
        The dipole scale factor.
    smooth_window_len : float
        The smooth window length.
    tstop : float
        The simulated dipole's duration.
    max_iter : int
        Number of calls the optimizer makes.
    target : ndarray
        The recorded dipole.

    Returns
    -------
    opt_params : list
        Optimized parameters.
    obj : list
        Objective values.
    net_ : Network
        Optimized network object.
    """

    obj_values = list()

    def _obj_func(predicted_params):
        return obj_fun(net,
                       initial_params,
                       set_params,
                       predicted_params,
                       _update_params,
                       obj_values,
                       scale_factor,
                       smooth_window_len,
                       tstop,
                       target)

    opt_results = gp_minimize(func=_obj_func,
                              dimensions=constraints,
                              acq_func='EI',
                              n_calls=max_iter,
                              x0=list(initial_params.values()))

    # get optimized params
    opt_params = opt_results.x

    # get objective values
    obj = [np.min(obj_values[:i]) for i in range(1, max_iter + 1)]

    # get optimized net
    param_dict = _update_params(initial_params, opt_params)
    net_ = net.copy()
    set_params(net_, param_dict)

    return opt_params, obj, net_


def _run_opt_cobyla(net, constraints, initial_params, set_params, obj_fun,
                    scale_factor, smooth_window_len, tstop, max_iter,
                    target):
    """
    Runs optimization routine with fmin_cobyla optimizer.

    Parameters
    ----------
    net : Network
        The network object.
    constraints : dict
        Parameter constraints in solver-specific format.
    initial_params : dict
        Keys are parameter names, values are initial parameters..
    set_params : func
        User-defined function that sets parameters in network drives.
    obj_fun : func
        The objective function.
    scale_factor : float
        The dipole scale factor.
    smooth_window_len : float
        The smooth window length.
    tstop : float
        The simulated dipole's duration.
    max_iter : int
        Number of calls the optimizer makes.
    target : ndarray, None
        The recorded dipole. The default is None.

    Returns
    -------
    opt_params : list
        Optimized parameters.
    obj : list
        Objective values.
    net_ : Network
        Optimized network object.
    """

    obj_values = list()

    def _obj_func(predicted_params):
        return obj_fun(net,
                       initial_params,
                       set_params,
                       predicted_params,
                       _update_params,
                       obj_values,
                       scale_factor,
                       smooth_window_len,
                       tstop,
                       target)

    opt_results = fmin_cobyla(_obj_func,
                              cons=constraints,
                              rhobeg=0.1,
                              rhoend=1e-4,
                              x0=list(initial_params.values()),
                              maxfun=max_iter,
                              catol=0.0)

    # get optimized params
    opt_params = opt_results

    # get objective values
    obj = [np.min(obj_values[:i]) for i in range(1, max_iter + 1)]

    # get optimized net
    param_dict = _update_params(initial_params, opt_params)
    net_ = net.copy()
    set_params(net_, param_dict)

    return opt_params, obj, net_
