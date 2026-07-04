import pytest
import aegis_dist


def test_sum_as_string():
    assert aegis_dist.sum_as_string(1, 1) == "2"
