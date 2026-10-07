import pytest

from backend.dataset import db
from backend.dataset.builder import DatasetError, build_dataset
from backend.dataset.validation import build_report
from tests.conftest import HEX_A, HEX_B, HEX_C, UUID_D, row


def test_missing_columns_raises(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("a,b\n1,2\n")
    with pytest.raises(DatasetError):
        build_dataset(p)


def test_exact_duplicates_merged_and_sources_kept(make_csv):
    p = make_csv([row(), row(), row(survey_n_1="294")])
    b = build_dataset(p)
    assert b.stats["csv_rows"] == 3 and len(b.records) == 2
    assert b.records[0]["source_rows"] == [2, 3]


def test_multi_image_rows_split_and_paired_by_position(make_csv):
    p = make_csv([row(image_path=f"{HEX_A};{HEX_B}", image_latitude="9.30;9.31",
                      image_longitude="77.40;77.41")])
    b = build_dataset(p)
    imgs = {i["image_id"]: i for i in b.images}
    assert set(imgs) == {HEX_A, HEX_B}
    assert (imgs[HEX_A]["image_lat"], imgs[HEX_A]["image_lon"]) == (9.30, 77.40)
    assert (imgs[HEX_B]["image_lat"], imgs[HEX_B]["image_lon"]) == (9.31, 77.41)
    assert len(b.links) == 2 and all(l["gt_to_image_m"] is not None for l in b.links)


def test_reordered_rows_pair_consistently(make_csv):
    p = make_csv([
        row(image_path=f"{HEX_A};{HEX_B}", image_latitude="9.30;9.31", image_longitude="77.40;77.41"),
        row(survey_n_1="9", image_path=f"{HEX_B};{HEX_A}", image_latitude="9.31;9.30", image_longitude="77.41;77.40"),
    ])
    b = build_dataset(p)
    imgs = {i["image_id"]: i for i in b.images}
    assert imgs[HEX_A]["coord_status"] == "ok" and imgs[HEX_A]["n_records"] == 2


def test_unpaired_coords_are_not_guessed(make_csv):
    p = make_csv([row(image_path=f"{HEX_A};{HEX_B};{HEX_C}", image_latitude="9.1;9.2;9.3",
                      image_longitude="77.1;77.2")])
    b = build_dataset(p)
    assert all(i["image_lat"] is None and i["coord_status"] == "unpaired" for i in b.images)
    assert any(i.code == "COORD_UNPAIRED" for i in b.issues)


def test_zero_coordinates_invalid(make_csv):
    p = make_csv([row(image_latitude="0.0", image_longitude="0.0")])
    img = build_dataset(p).images[0]
    assert img["coord_status"] == "invalid" and img["image_lat"] is None


def test_stage_conflict_flagged_not_resolved(make_csv):
    p = make_csv([row(), row(survey_n_1="9", final_crop_stage="harvesting")])
    img = build_dataset(p).images[0]
    assert img["crop_stage"] is None and img["crop_stage_values"] == ["harvesting", "vegetation"]
    assert "STAGE_CONFLICT" in img["flags"] and img["crop_name"] == "Rice (Paddy)"


def test_date_formats_and_mismatch(make_csv):
    p = make_csv([row(timestamp="13-11-2024", image_timestamp="13-11-2024 00:00"),
                  row(survey_n_1="9", timestamp="11-06-2024", image_timestamp="07-11-2024 00:00")])
    b = build_dataset(p)
    assert b.records[0]["gt_date"] == "2024-11-13" == b.records[0]["image_date"]
    assert [i.code for i in b.issues if i.code == "DATE_MISMATCH"] == ["DATE_MISMATCH"]


def test_file_matching_missing_orphan_and_unchecked(make_csv, tmp_path):
    p = make_csv([row(image_path=f"{HEX_A};{UUID_D}", image_latitude="9.1;9.2", image_longitude="77.1;77.2")])
    assert build_dataset(p).stats["images_found"] == 0
    assert all(i["file_status"] == "unchecked" for i in build_dataset(p).images)  # no dir: unknown
    d = tmp_path / "imgs"
    d.mkdir()
    (d / UUID_D).write_bytes(b"x")
    (d / "orphan.jpg").write_bytes(b"x")
    b = build_dataset(p, d)
    st = {i["image_id"]: i["file_status"] for i in b.images}
    assert st[UUID_D[:-4]] == "found" and st[HEX_A] == "missing"
    assert b.stats["orphan_image_files"] == 1


def test_filename_village_mismatch_flag(make_csv):
    p = make_csv([row(**{"Village LG": "999999"}, image_path=UUID_D)])
    assert "FILENAME_VILLAGE_MISMATCH" in build_dataset(p).images[0]["flags"]


def test_no_label_columns_in_schema_and_db_roundtrip(make_csv):
    b = build_dataset(make_csv([row()]))
    conn = db.connect(":memory:")
    db.load_bundle(conn, b, "x.csv")
    db.load_bundle(conn, b, "x.csv")  # idempotent
    assert conn.execute("select count(*) from images").fetchone()[0] == 1
    for t in ("survey_records", "images"):
        cols = [r[1].lower() for r in conn.execute(f"pragma table_info({t})")]
        assert not any(k in c for c in cols for k in ("disease", "damage", "label"))
    assert build_report(b)["issue_severity_totals"]["error"] == 0


def test_hex_id_files_map_and_multiple_files_flagged(make_csv, tmp_path):
    d = tmp_path / "imgs"
    d.mkdir()
    for q in ("1960_878232", "2955_658490"):
        (d / f"642626_293_58__{HEX_A}-{q}_2024_11_06_11_57_27.jpg").write_bytes(b"x")
    b = build_dataset(make_csv([row()]), d)
    i = b.images[0]
    assert i["file_status"] == "found" and i["n_files"] == 2 and i["file_captured_at"] == "2024-11-06T11:57:27"
    assert "MULTIPLE_FILES" in i["flags"] and b.stats["orphan_image_files"] == 0
