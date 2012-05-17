"""
This module has a class for specifying a problem from just
a smooth function and a single penalty.

"""
import numpy as np

from .composite import composite
from .affine import identity
from .atoms import atom
from .cones import zero as zero_cone
from .smooth import zero as zero_smooth
from .identity_quadratic import identity_quadratic

class simple_problem(composite):
    
    def __init__(self, smooth_atom, nonsmooth_atom):
        self.smooth_atom = smooth_atom
        self.nonsmooth_atom = nonsmooth_atom
        self.coefs = self.smooth_atom.coefs = self.nonsmooth_atom.coefs

    def smooth_objective(self, x, mode='both', check_feasibility=False):
        return self.smooth_atom.smooth_objective(x, mode, check_feasibility)

    def nonsmooth_objective(self, x, check_feasibility=False):
        vn = self.nonsmooth_atom.nonsmooth_objective(x, check_feasibility=check_feasibility)
        if self.smooth_atom.quadratic is not None:
            vs = self.smooth_atom.nonsmooth_objective(x, check_feasibility=check_feasibility)
            return vn + vs
        return vn

    def proximal(self, lipschitz, x, grad):
        if self.smooth_atom.quadratic is not None:
            proxq = identity_quadratic(lipschitz, x, grad)
            proxq = proxq + self.smooth_atom.quadratic
            lipschitz, x, grad = proxq.coef, proxq.offset, proxq.linear_term
        return self.nonsmooth_atom.proximal(lipschitz, x, grad)

    @staticmethod
    def smooth(smooth_atom):
        """
        A problem with no nonsmooth part except possibly
        the quadratic of smooth_atom.

        The proximal function is (almost) a nullop.
        """
        nonsmooth_atom = zero_cone(smooth_atom.primal_shape)
        return simple_problem(smooth_atom, nonsmooth_atom)

    @staticmethod
    def nonsmooth(nonsmooth_atom):
        """
        A problem with no nonsmooth part except possibly
        the quadratic of smooth_atom.

        The proximal function is (almost) a nullop.
        """
        smooth_atom = zero_smooth(nonsmooth_atom.primal_shape)
        return simple_problem(smooth_atom, nonsmooth_atom)

def gengrad(simple_problem, L, tol=1.0e-8, max_its=1000, debug=False):
    """
    A simple generalized gradient solver
    """
    itercount = 0
    coef = simple_problem.coefs
    print 'coef', coef
    v = np.inf
    while True:
        vnew, g = simple_problem.smooth_objective(coef, 'both')
        vnew += simple_problem.nonsmooth_objective(coef)
        newcoef = simple_problem.proximal(L, coef, g)
        if np.linalg.norm(coef-newcoef) <= tol * np.max([np.linalg.norm(coef),
                                                         np.linalg.norm(newcoef)]):
            break
        if itercount == max_its:
            break
        if debug:
            print itercount, vnew, v, (vnew - v) / vnew
        v = vnew
        itercount += 1
        coef = newcoef
    return coef
