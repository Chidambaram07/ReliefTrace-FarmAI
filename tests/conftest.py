import csv
from pathlib import Path

import pytest

HEADER = ["Village LG", "district_1", "taluk_co_1", "village__1", "survey_n_1", "sub_divi_1",
          "final_lat", "final_long", "timestamp", "rabi_crop_classification", "final_crop_name",
          "final_crop_stage", "image_path", "image_timestamp", "image_latitude", "image_longitude"]

HEX_A = "aaaaaaaaaaaaaaaa-11111-22222222222222"
HEX_B = "bbbbbbbbbbbbbbbb-11111-33333333333333"
HEX_C = "cccccccccccccccc-11111-44444444444444"
UUID_D = "01234567-89ab-cdef-0123-456789abcdef642626_293A_58_.jpg"


def row(**kw):
    base = dict(zip(HEADER, ["642626", "34", "5", "101", "293", "", "9.2500", "77.4200", "11/6/2024",
                             "Cereals", "Rice (Paddy)", "vegetation", HEX_A, "6/11/2024 0:00",
                             "9.2510", "77.4210"]))
    base.update(kw)
    return [base[h] for h in HEADER]


@pytest.fixture
def make_csv(tmp_path):
    def _make(rows, name="gt.csv"):
        p = tmp_path / name
        with open(p, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            w.writerows(rows)
        return p
    return _make
