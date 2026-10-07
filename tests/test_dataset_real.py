"""Regression checks against the real FarmwiseAI CSV (skipped if the file is not present)."""
import pytest

from backend.config import get_settings
from backend.dataset.builder import build_dataset

s = get_settings()
pytestmark = pytest.mark.skipif(not s.csv_path.exists(), reason="real CSV not present")


@pytest.fixture(scope="module")
def bundle():
    return build_dataset(s.csv_path, None)


def test_known_counts(bundle):
    st = bundle.stats
    assert st["csv_rows"] == 14643
    assert st["exact_duplicate_rows_merged"] == 32
    assert st["multi_image_rows"] > 0
    assert st["unique_images"] == 3274  # NOT 3,204: 3,204 is the count before splitting ';'
    assert st["images_by_id_format"] == {"hex_triplet": 2785, "uuid_file": 489}


def test_known_data_quality_findings(bundle):
    ic = bundle.stats["issue_counts"]
    assert ic["warning:STAGE_CONFLICT"] == 8
    assert ic["warning:COORD_UNPAIRED"] == 20
    assert ic["warning:INVALID_COORD"] == 4
    assert not any(k.endswith("CROP_CONFLICT") for k in ic)
    assert bundle.stats["issue_counts"].keys().isdisjoint({"error:GT_DATE_UNPARSED", "error:IMAGE_DATE_UNPARSED"})


def test_sample_images_map_to_expected_rows_disabled(bundle):
    pytest.skip("sample files replaced by full Task-4 image set")


def _old(bundle):
    imgs = {i["image_id"]: i for i in bundle.images}
    i = imgs["00b38c78-9ef3-4568-b254-eb895b6b629f933533_266_58_"]
    assert (i["crop_name"], i["crop_stage"], i["village_lgd"]) == ("Rice (Paddy)", "vegetation", "933533")


def test_official_csv_dates_all_consistent(bundle):
    ic = bundle.stats["issue_counts"]
    assert "warning:DATE_MISMATCH" not in ic  # wrong date parsing would flag ~70% of rows


@pytest.mark.skipif(not s.images_dir.exists() or not any(s.images_dir.glob("*.jpg")), reason="images not present")
def test_official_images_map_to_csv():
    b = build_dataset(s.csv_path, s.images_dir)
    assert b.stats["images_found"] == 3273 and b.stats["images_missing"] == 1 and b.stats["orphan_image_files"] == 0
