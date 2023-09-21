import jax
import jax.experimental
import jax.numpy as jnp
import jpu.numpy as jnpu
import numpy as np
import pytest

from jaxoplanet import orbits
from jaxoplanet.test_utils import assert_allclose, assert_quantity_allclose
from jaxoplanet.units import unit_registry as ureg


@pytest.fixture(
    params=[
        {
            "central": orbits.KeplerianCentral(mass=1.3, radius=1.1),
            "mass": 0.1,
            "time_transit": 0.1,
            "period": 12.5,
            "inclination": 0.3,
        },
        {
            "central": orbits.KeplerianCentral(mass=1.3, radius=1.1),
            "mass": 0.1,
            "time_transit": 0.1,
            "period": 12.5,
            "inclination": 0.3,
            "eccentricity": 0.3,
            "omega_peri": -1.5,
            "asc_node": 0.3,
        },
    ]
)
def keplerian_body(request):
    return orbits.KeplerianBody(**request.param)


@pytest.fixture
def time():
    return jnp.linspace(-50.0, 50.0, 500) * ureg.day


def test_keplerian_central_shape():
    assert orbits.KeplerianCentral(mass=0.98, radius=0.93).shape == ()


def test_keplerian_central_density():
    star = orbits.KeplerianCentral()
    assert_quantity_allclose(
        star.density, 1.4 * ureg.g / ureg.cm**3, atol=0.01, convert=True
    )


def test_keplerian_body_keplers_law():
    orbit = orbits.KeplerianBody(semimajor=1.0 * ureg.au)
    assert_quantity_allclose(orbit.period, 1.0 * ureg.year, atol=0.01, convert=True)

    orbit = orbits.KeplerianBody(period=1.0 * ureg.year)
    assert_quantity_allclose(orbit.semimajor, 1.0 * ureg.au, atol=0.01, convert=True)


@pytest.mark.parametrize("prefix", ["", "central_", "relative_"])
def test_keplerian_body_velocity(time, keplerian_body, prefix):
    v = getattr(keplerian_body, f"{prefix}velocity")(time)
    for i, v_ in enumerate(v):
        pos_func = getattr(keplerian_body, f"{prefix}position")
        assert_allclose(
            v_.magnitude,
            jax.vmap(jax.grad(lambda t: pos_func(t)[i].magnitude))(time).magnitude,
        )


def test_keplerian_body_radial_velocity(time, keplerian_body):
    computed = keplerian_body.radial_velocity(time)
    expected = keplerian_body.radial_velocity(
        time,
        semiamplitude=keplerian_body._baseline_rv_semiamplitude
        * keplerian_body.mass
        * keplerian_body.sin_inclination,
    )
    assert_quantity_allclose(expected, computed)


def test_keplerian_body_impact_parameter(keplerian_body):
    x, y, z = keplerian_body.relative_position(keplerian_body.time_transit)
    assert_quantity_allclose(
        (jnpu.sqrt(x**2 + y**2) / keplerian_body.central.radius),
        keplerian_body.impact_param,
    )
    assert jnpu.all(z > 0)


def test_keplerian_body_coordinates_match_batman(time, keplerian_body):
    _rsky = pytest.importorskip("batman._rsky")
    with jax.experimental.enable_x64(True):
        r_batman = _rsky._rsky(
            np.array(time.magnitude, dtype=np.float64),
            float(keplerian_body.time_transit.magnitude),
            float(keplerian_body.period.magnitude),
            float(keplerian_body.semimajor.magnitude),
            float(keplerian_body.inclination.magnitude),
            float(keplerian_body.eccentricity.magnitude)
            if keplerian_body.eccentricity
            else 0.0,
            float(keplerian_body.omega_peri.magnitude)
            if keplerian_body.omega_peri
            else 0.0,
            1,
            1,
        )
        m = r_batman < 100.0
        assert m.sum() > 0

        x, y, z = keplerian_body.relative_position(time)
        r = jnpu.sqrt(x**2 + y**2)

        # Make sure that the in-transit impact parameter matches batman
        assert_allclose(r_batman[m], r.magnitude[m])

        # In-transit should correspond to positive z in our parameterization
        assert np.all(z.magnitude[m] > 0)

        # Therefore, when batman doesn't see a transit we shouldn't be transiting
        no_transit = z.magnitude[~m] < 0
        no_transit |= r.magnitude[~m] > 2
        assert np.all(no_transit)


def test_keplerian_body_positions_small_star(time):
    _rsky = pytest.importorskip("batman._rsky")
    with jax.experimental.enable_x64(True):
        keplerian_body = orbits.KeplerianBody(
            central=orbits.KeplerianCentral(radius=0.189, mass=0.151),
            period=0.4626413,
            time_transit=0.2,
            impact_param=0.5,
            eccentricity=0.1,
            omega_peri=0.1,
        )

        r_batman = _rsky._rsky(
            np.array(time.magnitude, dtype=np.float64),
            float(keplerian_body.time_transit.magnitude),
            float(keplerian_body.period.magnitude),
            float(keplerian_body.semimajor.magnitude),
            float(keplerian_body.inclination.magnitude),
            float(keplerian_body.eccentricity.magnitude)
            if keplerian_body.eccentricity
            else 0.0,
            float(keplerian_body.omega_peri.magnitude)
            if keplerian_body.omega_peri
            else 0.0,
            1,
            1,
        )
        m = r_batman < 100.0
        assert m.sum() > 0

        x, y, _ = keplerian_body.relative_position(time)
        r = jnpu.sqrt(x**2 + y**2)
        assert_allclose(r_batman[m], r[m].magnitude)