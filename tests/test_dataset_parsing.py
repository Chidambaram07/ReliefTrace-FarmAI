from datetime import date

from backend.dataset.parsing import (
    leading_int, parse_gt_date, parse_image_date, parse_image_filename, parse_image_id, split_raw,
    valid_coord,
)


def test_split_raw_preserves_order_and_duplicates():
    assert split_raw("a; b ;a") == ["a", "b", "a"]
    assert split_raw("") == [] and split_raw(None) == []


def test_id_formats():
    h = parse_image_id("fdbc9fbcc153608c-43509-10631721293620")
    assert h["id_format"] == "hex_triplet" and h["image_id"] == h["raw_id"]
    u = parse_image_id("97342de2-2ce5-4c4f-b02e-9c4ee08dd21c933538_399_169_.jpg")
    assert u["id_format"] == "uuid_file"
    assert u["image_id"].endswith("933538_399_169_") and not u["image_id"].endswith(".jpg")
    assert (u["filename_village_lgd"], u["filename_survey_no"]) == ("933538", "399")
    v = parse_image_id("88419c65-e3bd-4cb8-ba36-b16918fca060642625_680A_58_.jpg")
    assert v["id_format"] == "uuid_file" and v["filename_survey_no"] == "680A"
    e = parse_image_id("09cb6372-343d-4ee3-b68b-ed1c52b723a3642626_335__.jpg")
    assert e["id_format"] == "uuid_file"
    assert parse_image_id("garbage")["id_format"] == "unknown"


def test_dates_official_csv_formats():
    assert parse_gt_date("11-12-2024") == date(2024, 11, 12)          # official: MM-DD-YYYY
    assert parse_image_date("12-11-2024 00:00") == date(2024, 11, 12)  # official: DD-MM-YYYY HH:MM
    assert parse_gt_date("13-11-2024") == date(2024, 11, 13)          # month 13 impossible -> DD-MM-YYYY
    assert parse_gt_date("11/12/2024") == date(2024, 11, 12)          # Excel-resaved copy
    assert parse_image_date("12/11/2024 0:00") == date(2024, 11, 12)
    assert parse_gt_date("not a date") is None


def test_image_filename_mapping():
    a = parse_image_filename("642619_1365_58__07fc3bd6a27ce63c-43726-11447830423203-8893_590779_2024_11_09_15_03_11.jpg")
    assert a["image_id"] == "07fc3bd6a27ce63c-43726-11447830423203" and a["captured_at"] == "2024-11-09T15:03:11"
    assert (a["village_lgd"], a["survey_no"]) == ("642619", "1365")
    b = parse_image_filename("97342de2-2ce5-4c4f-b02e-9c4ee08dd21c933538_399_169_.jpg")
    assert b["image_id"].endswith("933538_399_169_") and b["captured_at"] is None and b["village_lgd"] == "933538"


def test_coord_validity():
    assert valid_coord(9.25, 77.4)
    assert not valid_coord(0.0, 0.0)
    assert not valid_coord(None, 77.4)
    assert not valid_coord(91.0, 77.4)


def test_leading_int():
    assert leading_int("399/1") == "399" and leading_int("680A") == "680" and leading_int(None) is None
