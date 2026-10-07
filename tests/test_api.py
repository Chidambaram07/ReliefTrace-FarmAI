import io
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.config import Settings
from backend.dataset import db
from backend.dataset.builder import build_dataset
from backend.main import create_app
from backend.services.image_service import dms_to_deg
from tests.conftest import HEX_A, HEX_B, UUID_D, row


def jpeg_bytes(color=(10, 120, 20), size=(40, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


def make_settings(tmp_path, **kw) -> Settings:
    return Settings(csv_path=tmp_path / "x.csv", images_dir=tmp_path / "imgs", db_path=tmp_path / "t.db",
                    upload_dir=tmp_path / "uploads", **kw)


@pytest.fixture
def client(tmp_path, make_csv):
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    (imgs / UUID_D).write_bytes(jpeg_bytes())
    csv_p = make_csv([
        row(image_path=f"{HEX_A};{UUID_D}", image_latitude="9.1;9.2", image_longitude="77.1;77.2"),
        row(survey_n_1="9", image_path=HEX_B, final_crop_name="Coconut", final_crop_stage="full_growth"),
    ])
    s = make_settings(tmp_path)
    conn = db.connect(s.db_path)
    db.load_bundle(conn, build_dataset(csv_p, imgs), str(csv_p))
    conn.close()
    with TestClient(create_app(s)) as c:
        yield c


CLAIM = {"survey_no": "293", "village_lgd": "642626", "claimed_cause": "drought",
         "incident_date": "2024-11-06", "claimed_crop": "Rice (Paddy)"}


def test_health_reports_dataset(client):
    j = client.get("/api/health").json()
    assert j["status"] == "ok" and j["dataset_loaded"] and j["dataset"]["images"] == 3
    assert j["dataset"]["images_with_file"] == 1


def test_health_without_dataset_does_not_crash(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        assert c.get("/api/health").json()["dataset_loaded"] is False
        r = c.get("/api/dataset/summary")
        assert r.status_code == 503 and r.json()["error"]["code"] == "DATASET_NOT_LOADED"


def test_create_and_get_claim(client):
    r = client.post("/api/claims", json=CLAIM)
    assert r.status_code == 201
    j = r.json()
    assert j["claim_id"].startswith("CLM-") and j["status"] == "submitted"
    assert "unverified" in j["provenance"] and j["claim"]["claimed_cause"] == "drought"
    assert client.get(f"/api/claims/{j['claim_id']}").json()["claim"]["survey_no"] == "293"
    assert client.get("/api/claims").json()["total"] == 1


@pytest.mark.parametrize("patch,field", [
    ({"incident_date": (date.today() + timedelta(days=2)).isoformat()}, "incident_date"),
    ({"claimed_cause": "alien_attack"}, "claimed_cause"),
    ({"survey_no": "   "}, "survey_no"),
    ({"village_lgd": "12"}, "village_lgd"),
    ({"claimed_lat": 9.2}, "__root__"),
])
def test_claim_validation_errors(client, patch, field):
    r = client.post("/api/claims", json={**CLAIM, **patch})
    j = r.json()
    assert r.status_code == 422 and j["error"]["code"] == "VALIDATION_ERROR" and j["error"]["request_id"]


def test_not_found_uses_error_envelope(client):
    r = client.get("/api/claims/CLM-NOPE")
    assert r.status_code == 404 and r.json()["error"]["code"] == "CLAIM_NOT_FOUND"


def test_upload_image_and_duplicate(client):
    cid = client.post("/api/claims", json=CLAIM).json()["claim_id"]
    data = jpeg_bytes()
    r = client.post(f"/api/claims/{cid}/images", files={"file": ("leaf.jpg", data, "image/jpeg")})
    assert r.status_code == 201
    j = r.json()
    assert (j["width"], j["height"], j["mime"], j["source"]) == (40, 60, "image/jpeg", "upload")
    assert j["file_available"] and j["exif"] == {"gps_lat": None, "gps_lon": None, "captured_at": None}
    dup = client.post(f"/api/claims/{cid}/images", files={"file": ("leaf2.jpg", data, "image/jpeg")})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "DUPLICATE_IMAGE"
    f = client.get(f"/api/claims/{cid}/images/{j['image_key']}/file")
    assert f.status_code == 200 and f.content == data
    assert len(client.get(f"/api/claims/{cid}").json()["images"]) == 1


def test_upload_rejects_non_image_empty_and_oversize(tmp_path, make_csv):
    s = make_settings(tmp_path, max_upload_bytes=500)
    with TestClient(create_app(s)) as c:
        cid = c.post("/api/claims", json=CLAIM).json()["claim_id"]
        url = f"/api/claims/{cid}/images"
        assert c.post(url, files={"file": ("a.txt", b"hello", "text/plain")}).json()["error"]["code"] == "UNSUPPORTED_IMAGE"
        assert c.post(url, files={"file": ("a.jpg", b"", "image/jpeg")}).json()["error"]["code"] == "EMPTY_FILE"
        big = jpeg_bytes(size=(400, 400))
        r = c.post(url, files={"file": ("big.jpg", big, "image/jpeg")})
        assert r.status_code == 413 and r.json()["error"]["code"] == "FILE_TOO_LARGE"
        assert c.post("/api/claims/CLM-NOPE/images", files={"file": ("a.jpg", b"x", "image/jpeg")}).status_code == 404


def test_attach_dataset_image(client):
    cid = client.post("/api/claims", json=CLAIM).json()["claim_id"]
    iid = UUID_D[:-4]
    r = client.post(f"/api/claims/{cid}/images/from-dataset", json={"image_id": iid})
    assert r.status_code == 201 and r.json()["dataset_image_id"] == iid and r.json()["file_available"]
    assert r.json()["sha256"] and (r.json()["width"], r.json()["height"]) == (40, 60)
    assert client.post(f"/api/claims/{cid}/images/from-dataset", json={"image_id": iid}).status_code == 409
    assert client.post(f"/api/claims/{cid}/images/from-dataset", json={"image_id": "nope"}).status_code == 404
    # image in dataset but file absent is attachable, flagged unavailable
    r2 = client.post(f"/api/claims/{cid}/images/from-dataset", json={"image_id": HEX_B})
    assert r2.status_code == 201 and r2.json()["file_available"] is False


def test_dataset_lookup_endpoints(client):
    j = client.get(f"/api/dataset/images/{HEX_A}").json()
    assert "NO disease/damage" in j["provenance"]
    assert j["image"]["crop_name"] == "Rice (Paddy)" and j["records"][0]["survey_no"] == "293"
    assert j["records"][0]["gt_to_image_m"] is not None
    assert client.get("/api/dataset/images/unknown").status_code == 404
    lst = client.get("/api/dataset/images", params={"crop_name": "Coconut"}).json()
    assert lst["total"] == 1 and lst["items"][0]["image_id"] == HEX_B
    assert client.get("/api/dataset/images", params={"file_status": "found"}).json()["total"] == 1
    p = client.get("/api/dataset/parcels", params={"village_lgd": "642626", "survey_no": "9"}).json()
    assert p["total"] == 1
    assert client.get("/api/dataset/parcels").status_code == 422
    assert client.get(f"/api/dataset/images/{UUID_D[:-4]}/file").status_code == 200
    assert client.get(f"/api/dataset/images/{HEX_A}/file").json()["error"]["code"] == "IMAGE_FILE_MISSING"
    assert client.get("/api/dataset/summary").json()["images"] == 3


def test_dms_to_deg():
    assert dms_to_deg((9, 15, 0), "N") == pytest.approx(9.25)
    assert dms_to_deg((77, 25, 12), "E") == pytest.approx(77.42)
    assert dms_to_deg((9, 15, 0), b"S") == pytest.approx(-9.25)
    assert dms_to_deg(None, "N") is None


def test_exif_gps_roundtrip(client):
    from PIL import Image as PI
    exif = PI.Exif()
    exif[0x8825] = {1: "N", 2: (9.0, 15.0, 0.0), 3: "E", 4: (77.0, 25.0, 12.0)}
    exif[0x8769] = {36867: "2024:11:06 10:30:00"}
    buf = io.BytesIO()
    PI.new("RGB", (30, 30), (1, 2, 3)).save(buf, "JPEG", exif=exif)
    cid = client.post("/api/claims", json=CLAIM).json()["claim_id"]
    j = client.post(f"/api/claims/{cid}/images", files={"file": ("g.jpg", buf.getvalue(), "image/jpeg")}).json()
    assert j["exif"]["gps_lat"] == pytest.approx(9.25) and j["exif"]["gps_lon"] == pytest.approx(77.42)
    assert j["exif"]["captured_at"] == "2024-11-06T10:30:00"


def test_lambda_handler_export_and_event():
    from backend.main import handler
    event = {
        "version": "2.0",
        "routeKey": "GET /api/health",
        "rawPath": "/api/health",
        "rawQueryString": "",
        "headers": {"host": "localhost"},
        "requestContext": {
            "http": {
                "method": "GET",
                "path": "/api/health",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "pytest",
            }
        },
        "isBase64Encoded": False,
    }
    res = handler(event, {})
    assert res["statusCode"] == 200
    assert "status" in res["body"]
