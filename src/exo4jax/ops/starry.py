from functools import partial

import numpy as np
import jax
import jax.numpy as jnp
from scipy.special import roots_legendre


@partial(jax.jit, static_argnums=0, static_argnames=["order"])
def solution_vector(l_max, b, r, *, order=20):
    b = jnp.abs(b)
    r = jnp.abs(r)
    kappa0, kappa1 = kappas(b, r)

    P = p(order, l_max, b, r, kappa0)
    Q = q(l_max, kappa1 + 0.5 * jnp.pi)

    return P - Q


def kappas(b, r):
    b2 = jnp.square(b)
    factor = (r - 1) * (r + 1)
    b_cond = jnp.logical_and(
        jnp.greater(b, jnp.abs(1 - r)), jnp.less(b, 1 + r)
    )
    b_ = jnp.where(b_cond, b, 1)
    area = jnp.where(b_cond, kite_area(r, b_, 1), 0)
    return jnp.arctan2(area, b2 + factor), jnp.arctan2(area, b2 - factor)


def kite_area(a, b, c):
    def sort2(a, b):
        return jnp.minimum(a, b), jnp.maximum(a, b)

    a, b = sort2(a, b)
    b, c = sort2(b, c)
    a, b = sort2(a, b)

    square_area = (a + (b + c)) * (c - (a - b)) * (c + (a - b)) * (a + (b - c))
    return jnp.sqrt(jnp.maximum(square_area, 0.0))


@partial(jax.jit, static_argnums=0)
def q(l_max, lam):
    zero = jnp.zeros_like(lam)
    c = jnp.cos(lam)
    s = jnp.sin(lam)
    h = {
        (0, 0): 2 * lam + jnp.pi,
        (0, 1): -2 * c,
    }

    def get(u, v):
        if (u, v) in h:
            return h[(u, v)]
        if u >= 2:
            comp = 2 * c ** (u - 1) * s ** (v + 1) + (u - 1) * get(u - 2, v)
        else:
            assert v >= 2
            comp = -2 * c ** (u + 1) * s ** (v - 1) + (v - 1) * get(u, v - 2)
        comp /= u + v
        h[(u, v)] = comp
        return comp

    U = []
    for l in range(l_max + 1):
        for m in range(-l, l + 1):
            mu = l - m
            nu = l + m
            if (mu // 2) % 2 == 0:
                u = mu // 2 + 2
                v = nu // 2
                assert u % 2 == 0
                U.append(get(u, v))
            else:
                U.append(zero)

    return jnp.stack(U)


@partial(jax.jit, static_argnums=(0, 1))
def p(order, l_max, b, r, kappa0):
    b2 = jnp.square(b)
    r2 = jnp.square(r)

    # This is a hack for when r -> 0 or b -> 0, so k2 -> inf
    k2_factor = 4 * b * r
    k2_cond = jnp.less(k2_factor, 10 * jnp.finfo(k2_factor.dtype).eps)
    k2_factor = jnp.where(k2_cond, 1, k2_factor)
    k2 = jnp.maximum(0, (1 - r2 - b2 + 2 * b * r) / k2_factor)
    f0 = k2_factor**1.5

    # And for when r -> 0
    r_cond = jnp.less(r, 10 * jnp.finfo(r.dtype).eps)
    delta = (b - r) / (2 * jnp.where(r_cond, 1, r))
    rng = 0.5 * kappa0

    roots, weights = roots_legendre(order)
    phi = rng * roots
    c = jnp.cos(phi)
    s = jnp.sin(phi)
    s2 = jnp.square(s)

    a1 = s2 - jnp.square(s2)
    a2 = delta + s2
    a3 = jnp.maximum(0, k2 - s2) ** 1.5
    a4 = a3 * (1 - 2 * s2)

    ind = []
    arg = []
    conds = []
    n = 0
    for l in range(l_max + 1):
        f = (2 * r) ** (l - 1) * f0
        for m in range(-l, l + 1):
            mu = l - m
            nu = l + m

            if mu == 1 and l == 1:
                # FIXME - probably wrong
                omz2 = r2 + b2 - 2 * b * r * c
                z2 = jnp.maximum(0, 1 - omz2)
                arg.append(r * (r - b * c) * (1 - z2 * jnp.sqrt(z2)) / omz2)
                conds.append(k2_cond)

            elif mu % 2 == 0 and (mu // 2) % 2 == 0:
                arg.append(
                    2
                    * (2 * r) ** (l + 2)
                    * a1 ** (0.25 * (mu + 4))
                    * a2 ** (0.5 * nu)
                )
                conds.append(r_cond)

            elif mu == 1 and l % 2 == 0:
                arg.append(f * a1 ** (l // 2 - 1) * a4)
                conds.append(k2_cond)

            elif mu == 1:
                arg.append(f * a1 ** ((l - 3) // 2) * a2 * a4)
                conds.append(k2_cond)

            elif (mu - 1) % 2 == 0 and ((mu - 1) // 2) % 2 == 0:
                arg.append(
                    2 * f * a1 ** ((mu - 1) // 4) * a2 ** (0.5 * (nu - 1)) * a3
                )
                conds.append(k2_cond)

            else:
                n += 1
                continue

            ind.append(n)
            n += 1

    P0 = rng * jnp.sum(jnp.stack(arg, axis=0) * weights[None, :], axis=1)
    P0 = jnp.where(jnp.stack(conds), 0, P0)
    P = jnp.zeros(l_max**2 + 2 * l_max + 1)

    # Yes, using np not jnp here: 'ind' is always static.
    ind = np.stack(ind)

    return P.at[ind].set(P0)