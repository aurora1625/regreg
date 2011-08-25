"""
This module contains the implementation operator and nuclear norms, used in 
matrix completion problems and other low-rank factorization
problems.

"""
import numpy as np
from atoms import atom, conjugate_seminorm_pairs
import warnings
from affine import linear_transform, composition, affine_sum, power_L
from smooth import smooth_atom
from composite import composite
from algorithms import FISTA

try:
    from projl1_cython import projl1
except:
    warnings.warn('Cython version of projl1 not available. Using slower python version')
    from projl1_python import projl1


class factored_matrix(object):

    """
    A class for storing the SVD of a linear_tranform. Has affine_transform attributes like linear_map
    """

    def __init__(self,
                 linear_operator,
                 min_singular=0.,
                 tol=1e-5,
                 initial_rank=None,
                 initial = None,
                 affine_offset=None,
                 debug=False):

        self.affine_offset = affine_offset
        self.tol = tol
        self.initial_rank = initial_rank
        self.initial = initial
        self.debug = debug

        if min_singular >= 0:
            self.min_singular = min_singular
        else:
            raise ValueError("Minimum singular value must be non-negative")
        
        if type(linear_operator) == type([]) and len(linear_operator) == 3:
            self.SVD = linear_operator
        else:
            self.X = linear_operator


    def copy(self):
        return factored_matrix([self.SVD[0].copy(), self.SVD[1].copy(), self.SVD[2].copy()])

    def _setX(self,transform):
        if isinstance(transform, np.ndarray):
            transform = linear_transform(transform)
        self.primal_shape = transform.primal_shape
        self.dual_shape = transform.dual_shape
        U, D, VT = compute_svd(transform, min_singular=self.min_singular, tol=self.tol, initial_rank = self.initial_rank, initial=self.initial, debug=self.debug)
        self.SVD = [U,D,VT]

    def _getX(self):
        if not self.rankone:
            return np.dot(self.SVD[0], np.dot(np.diag(self.SVD[1]), self.SVD[2]))
        else:
            return self.SVD[1][0,0] * np.dot(self.SVD[0], self.SVD[2])
    X = property(_getX, _setX)

    def _getSVD(self):
        return self._SVD
    def _setSVD(self, SVD):
        self.rankone = False
        if len(SVD[1].flatten()) == 1:
            SVD[0] = SVD[0].reshape((SVD[0].flatten().shape[0],1))
            SVD[1] = SVD[1].reshape((1,1))
            SVD[2] = SVD[2].reshape((1,SVD[2].flatten().shape[0]))
            self.rankone = True
        self.primal_shape = (SVD[2].shape[1],)
        self.dual_shape = (SVD[0].shape[0],)
        self._SVD = SVD
    SVD = property(_getSVD, _setSVD)

    def linear_map(self, x):
        if self.rankone:
            return self.SVD[1][0,0] * np.dot(self.SVD[0], np.dot(self.SVD[2], x))
        else:
            return np.dot(self.SVD[0], np.dot(np.diag(self.SVD[1]), np.dot(self.SVD[2], x)))

    def adjoint_map(self, x):
        if self.rankone:
            return self.SVD[1][0,0] * np.dot(self.SVD[2].T, np.dot(self.SVD[0].T, x))
        else:
            return np.dot(self.SVD[2].T, np.dot(np.diag(self.SVD[1]), np.dot(self.SVD[0].T, x)))

    def affine_map(self,x):
        if self.affine_offset is None:
            return self.linear_map(x)
        else:
            return self.linear_map(x) + affine_offset

def compute_svd(transform,
                initial_rank = None,
                initial = None,
                min_singular = 0.,
                tol = 1e-5,
                debug=False):

    """
    Compute the SVD of a matrix
    """

    if isinstance(transform, np.ndarray):
        transform = linear_transform(transform)

    n = transform.dual_shape[0]
    p = transform.primal_shape[0]
    
    if initial_rank is None:
        r = np.round(np.min([n,p]) * 0.1) + 1
    else:
        r = np.max([initial_rank,1])

    min_so_far = 1.
    D = [np.inf]
    while D[-1] >= min_singular:
        if debug:
            print "Trying rank", r
        U, D, VT = partial_svd(transform, r=r, extra_rank=5, tol=tol, initial=initial, return_full=True, debug=debug)
        if D[0] < min_singular:
            return U[:,0], np.zeros((1,1)), VT[0,:]
        initial = 1. * U 
        r *= 2

    ind = np.where(D >= min_singular)[0]
    return U[:,ind], D[ind],  VT[ind,:]


def partial_svd(transform,
                r=1,
                extra_rank=2,
                max_its = 1000,
                tol = 1e-8,
                initial=None,
                return_full = False,
                debug=False):

    """
    Compute the partial SVD of the linear_transform X using the Mazumder/Hastie algorithm in (TODO: CITE)
    """

    if isinstance(transform, np.ndarray):
        transform = linear_transform(transform)

    n = transform.dual_shape[0]
    p = transform.primal_shape[0]


    r = np.int(np.min([r,p]))
    q = np.min([r + extra_rank, p])
    if initial is not None:
        if initial.shape == (n,q):
            U = initial
        elif len(initial.shape) == 1:
            U = np.hstack([initial.reshape((initial.shape[0],1)), np.random.standard_normal((n,q-1))])            
        else:
            U = np.hstack([initial, np.random.standard_normal((n,q-initial.shape[1]))])            
    else:
        U = np.random.standard_normal((n,q))

    if return_full:
        ind = np.arange(q)
    else:
        ind = np.arange(r)
    old_singular_values = np.zeros(r)
    change_ind = np.arange(r)

    itercount = 0
    singular_rel_change = 1.


    while itercount < max_its and singular_rel_change > tol:
        if debug and itercount > 0:
            print itercount, singular_rel_change, np.sum(np.fabs(singular_values)>1e-12), np.fabs(singular_values[range(np.min([5,len(singular_values)]))])
        V,_ = np.linalg.qr(transform.adjoint_map(U))
        X_V = transform.linear_map(V)
        U,R = np.linalg.qr(X_V)
        singular_values = np.diagonal(R)[change_ind]
        singular_rel_change = np.linalg.norm(singular_values - old_singular_values)/np.linalg.norm(singular_values)
        old_singular_values = singular_values * 1.
        itercount += 1
    singular_values = np.diagonal(R)[ind]

    nonzero = np.where(np.fabs(singular_values) > 1e-12)[0]
    if len(nonzero):
        return U[:,ind[nonzero]] * np.sign(singular_values[nonzero]), np.fabs(singular_values[nonzero]),  V[:,ind[nonzero]].T
    else:
        return U[:,ind[0]], np.zeros((1,1)),  V[:,ind[0]].T


def soft_threshold_SVD(X, c=0.):

    """
    Soft-treshold the singular values of a matrix X
    """
    if not isinstance(X, factored_matrix):
        X = factored_matrix(X)

    singular_values = X.SVD[1]
    ind = np.where(singular_values >= c)[0]
    if len(ind) == 0:
        X.SVD = [np.zeros(X.dual_shape[0]), np.zeros(1), np.zeros(X.primal_shape[0])]
    else:
        X.SVD = [X.SVD[0][:,ind], np.maximum(singular_values[ind] - c,0), X.SVD[2][ind,:]]

    return X



class interaction_loss(smooth_atom):

    """
    A class for the low-rank interaction problem.

    The gradient is a matrix. Instead of forming the matrix, a linear_transform is returned
    
    """


    def __init__(self, X, Y, coef=1.):

        self.X = X
        self.n = X.shape[0]
        self.Y = Y
        self.coef = coef

        self.multX = linear_transform(self.X)
        self.multXT = linear_transform(self.X.T)
        self.row_weights = linear_transform(np.ones(self.n), diag=True)

    def smooth_objective(self, A, mode='both', check_feasibility=False):
        """
        Evaluate a smooth function and/or its gradient

        if mode == 'both', return both function value and gradient
        if mode == 'grad', return only the gradient
        if mode == 'func', return only the function value
        """

        resid = self.Y - np.diag(np.dot(self.X, A.linear_map(self.X.T)))

        if mode == 'func':
            return self.scale( 0.5 * np.linalg.norm(resid)**2 )
        elif mode == 'grad':
            self.row_weights.linear_operator = -1. * resid
            return composition(self.multXT, self.row_weights, self.multX)
        elif mode == 'both':
            self.row_weights.linear_operator = -1. * resid
            return self.scale( 0.5 * np.linalg.norm(resid)**2 ), composition(self.multXT, self.row_weights, self.multX)
        else:
            raise ValueError("Mode not specified correctly")

def interactions_composite(X,Y, lambda1 = 0., initial=None, lipschitz=None, debug=False):

    n, p = X.shape
    loss = interaction_loss(X,Y)

    def nukenorm(Z, check_feasibility=False):
        if not hasattr(Z,'SVD'):
            raise ValueError("Argument is not a factored matrix")
        return lambda1 * np.fabs(Z.SVD[1]).sum()

    def prox(x,grad,prox_lipschitz):
        transform = affine_sum([x,grad],[1., -1./prox_lipschitz])
        L = factored_matrix(transform, initial=x.SVD[0], initial_rank = x.SVD[0].shape[1], debug=debug, tol=1e-10, min_singular=lambda1/prox_lipschitz)
        #print prox_lipschitz*L.SVD[1]
        return soft_threshold_SVD(L, c=lambda1/prox_lipschitz)

    if initial is None:
        u = np.random.standard_normal(p)
        v = np.random.standard_normal(p)
        u /= np.linalg.norm(u)
        v /= np.linalg.norm(v)
        initial = factored_matrix([u, (1e-4)*np.ones(1), v])
    if lipschitz is None:
        lipschitz = np.sum(X**2) * np.sqrt(np.min(X.shape))

    return composite(loss.smooth_objective, nukenorm, prox, initial=initial, lipschitz=lipschitz, compute_difference=False)
