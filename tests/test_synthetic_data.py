import numpy as np

from data.synthetic_building import (COMFORT_BAND_C, SIMULATION_LABEL, STEPS_PER_DAY,
                                     generate_building_data)
from scenarios.college import COLLEGE, college_data


def test_shapes_label_and_ranges():
    d = college_data()
    z = COLLEGE.n_zones
    assert d.n_steps == STEPS_PER_DAY == 288
    assert d.occupancy.shape == (288, z) and d.q_internal_kw.shape == (288, z)
    assert d.label == SIMULATION_LABEL and "SIMULATION" in d.to_frame().attrs["label"]
    assert d.occupancy.min() >= 0 and d.occupancy.max() <= 1
    assert (d.q_solar_kw >= 0).all() and (d.base_load_kw > 0).all()


def test_deterministic():
    a, b = college_data(), college_data()
    assert np.array_equal(a.q_internal_kw, b.q_internal_kw)
    assert np.array_equal(a.t_out_c, b.t_out_c)


def test_demo_timeline_occupancy():
    d = college_data()
    occ = d.building_occupancy()
    assert abs(occ[d.index_at(13.5)] - 0.70) < 0.03
    assert occ[d.index_at(14 + 20 / 60)] > 0.85
    hall = d.occupancy[d.index_at(14.5), 0]
    assert hall >= 0.95 - 1e-9


def test_hot_is_hotter_than_mild():
    assert college_data("hot").t_out_c.max() > college_data("mild").t_out_c.max() + 4


def test_higher_occupancy_gives_higher_internal_gain():
    i = college_data().index_at(14.5)
    low = college_data(occupancy_level="low").q_internal_kw[i].sum()
    norm = college_data(occupancy_level="normal").q_internal_kw[i].sum()
    high = college_data(occupancy_level="high").q_internal_kw[i].sum()
    assert low < norm < high


def test_zero_occupancy_edge_case():
    import dataclasses
    zones = tuple(dataclasses.replace(z, occupancy_keypoints=((0, 0), (24, 0))) for z in COLLEGE.zones)
    spec = dataclasses.replace(COLLEGE, zones=zones)
    d = generate_building_data(spec)
    assert d.occupancy.max() == 0
    assert np.allclose(d.base_load_kw, spec.base_night_kw)
    assert (d.q_internal_kw > 0).all()  # standby equipment + security lighting remain


def test_invalid_selectors_rejected():
    import pytest
    with pytest.raises(ValueError):
        college_data(weather="stormy")
    with pytest.raises(ValueError):
        college_data(occupancy_level="packed")


def test_comfort_band_is_prototype_assumption():
    assert COMFORT_BAND_C == (23.0, 26.0)
