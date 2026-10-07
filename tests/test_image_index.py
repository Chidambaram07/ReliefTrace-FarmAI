import base64
import io
import json

import numpy as np
import pytest
from PIL import Image

from backend.agentic import image_index
from backend.agentic.state import SharedState
from backend.agentic.tools import image_retrieval_tool
from backend.dataset import db
from backend.dataset.builder import build_dataset
from backend.services.model_client import ClientSettings, ModelClient
from backend.services.model_registry import build_registry
from backend.storage.schema import init_image_index_schema
from tests.conftest import row
from tests.test_model_client import FakeBody, client_error

MODEL_ID = "amazon.titan-embed-image-v1"
HEXES = [f"{c*16}-1-{i}" for i, c in enumerate("abcd")]
COLORS = {HEXES[0]: (250, 10, 10), HEXES[1]: (240, 30, 20), HEXES[2]: (10, 10, 250), HEXES[3]: (10, 240, 10)}
CROPS = {HEXES[0]: "Rice (Paddy)", HEXES[1]: "Rice (Paddy)", HEXES[2]: "Coconut", HEXES[3]: "Maize"}


def jpg(color):
    b = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(b, "JPEG", quality=95)
    return b.getvalue()


class EmbedRuntime:
    """Deterministic fake Titan: embedding = mean RGB of the image, so similar colours are similar."""
    def __init__(self, fail_for_colors=(), error=None):
        self.calls, self.bodies = 0, []
        self.fail_for_colors, self.error = fail_for_colors, error

    def invoke_model(self, **kw):
        self.calls += 1
        body = json.loads(kw["body"])
        self.bodies.append(body)
        img = Image.open(io.BytesIO(base64.b64decode(body["inputImage"]))).convert("RGB")
        mean = tuple(int(x) for x in np.asarray(img).reshape(-1, 3).mean(axis=0))
        if any(all(abs(a - b) < 30 for a, b in zip(mean, c)) for c in self.fail_for_colors):
            raise self.error
        return {"body": FakeBody({"embedding": [float(x) + 1.0 for x in mean]})}


def mc(rt):
    return ModelClient(ClientSettings(region="ap-south-1"), runtime_client=rt)


@pytest.fixture
def world(tmp_path, make_csv):
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    rows = []
    for i, h in enumerate(HEXES):
        (imgs / f"642626_29{i}_58__{h}-1_2_2024_11_06_10_00_00.jpg").write_bytes(jpg(COLORS[h]))
        rows.append(row(survey_n_1=str(290 + i), image_path=h, final_crop_name=CROPS[h],
                        image_latitude="9.25", image_longitude="77.42"))
    csv_p = make_csv(rows)
    conn = db.connect(":memory:")
    db.load_bundle(conn, build_dataset(csv_p, imgs), str(csv_p))
    init_image_index_schema(conn)
    images = [{"image_id": r[0], "file_path": r[1]} for r in conn.execute("SELECT image_id, file_path FROM images")]
    return conn, images


def test_build_index_embeds_all_and_is_resumable(world):
    conn, images = world
    rt = EmbedRuntime()
    stats = image_index.build_index(conn, mc(rt), MODEL_ID, 256, images, workers=2)
    assert stats["embedded"] == 4 and stats["failed"] == 0 and rt.calls == 4
    assert image_index.index_size(conn, MODEL_ID, 256) == 4
    assert rt.bodies[0]["embeddingConfig"] == {"outputEmbeddingLength": 256}
    stats2 = image_index.build_index(conn, mc(rt), MODEL_ID, 256, images)
    assert stats2["attempted"] == 0 and stats2["already_indexed"] == 4 and rt.calls == 4  # no new AWS calls


def test_build_index_limit_and_partial_progress_is_kept(world):
    conn, images = world
    rt = EmbedRuntime()
    image_index.build_index(conn, mc(rt), MODEL_ID, 256, images, limit=2, workers=1)
    assert image_index.index_size(conn, MODEL_ID, 256) == 2
    image_index.build_index(conn, mc(rt), MODEL_ID, 256, images, workers=1)
    assert image_index.index_size(conn, MODEL_ID, 256) == 4 and rt.calls == 4


def test_one_failing_image_does_not_abort_the_build(world):
    conn, images = world
    rt = EmbedRuntime(fail_for_colors=[COLORS[HEXES[3]]], error=client_error("AccessDeniedException", "denied"))
    stats = image_index.build_index(conn, mc(rt), MODEL_ID, 256, images, workers=1)
    assert stats["embedded"] == 3 and stats["failed"] == 1
    assert HEXES[3] in stats["failures"][0]["image_id"] and "BEDROCK_ACCESS_DENIED" in stats["failures"][0]["error"]


def test_top_k_orders_by_cosine_and_excludes():
    ids = ["a", "b", "c"]
    m = np.array([[1, 0], [0.9, 0.1], [0, 1]], dtype=np.float32)
    m = m / np.linalg.norm(m, axis=1, keepdims=True)
    hits = image_index.top_k(ids, m, [1, 0], 2)
    assert [h[0] for h in hits] == ["a", "b"] and hits[0][1] == pytest.approx(1.0)
    assert [h[0] for h in image_index.top_k(ids, m, [1, 0], 2, exclude={"a"})] == ["b", "c"]
    assert image_index.top_k(ids, m, [0, 0], 2) == [] and image_index.top_k(ids, m, [1, 0, 0], 2) == []


def test_retrieval_tool_returns_similar_images_with_reference_labels_and_traces(world):
    conn, images = world
    rt = EmbedRuntime()
    image_index.build_index(conn, mc(rt), MODEL_ID, 256, images, workers=1)
    s = SharedState(claim_id="CLM-1", claim={})
    tr = image_retrieval_tool(s, client=mc(rt), registry=build_registry(), conn=conn, image_bytes=jpg((245, 20, 15)),
                              query_label="claim photo", top_k=3, claimed_crop="Rice (Paddy)")
    assert tr.status == "success"
    sim = tr.output["similar_images"]
    assert [x["image_id"] for x in sim[:2]] == [HEXES[1], HEXES[0]] or {x["image_id"] for x in sim[:2]} == {HEXES[0], HEXES[1]}
    assert sim[0]["crop"] == "Rice (Paddy)" and sim[0]["timestamp"] == "2024-11-06" and sim[0]["location"]["lat"] == 9.25
    assert sim[0]["similarity"] > sim[-1]["similarity"]
    assert tr.output["claimed_crop_agreement_fraction"] == pytest.approx(0.67, abs=0.01)
    assert tr.output["limitations"] and tr.output["index_size"] == 4
    assert [m.model_key for m in s.selected_models] == ["titan_embed_image_v1"]
    assert s.model_outputs[-1].ok and s.audit_trace[-1].tool == "image_retrieval"


def test_query_photo_that_is_already_in_the_index_is_excluded_from_its_own_results(world):
    conn, images = world
    rt = EmbedRuntime()
    image_index.build_index(conn, mc(rt), MODEL_ID, 256, images, workers=1)
    own_bytes = open(images[0]["file_path"], "rb").read()
    tr = image_retrieval_tool(SharedState("C", {}), client=mc(rt), registry=build_registry(), conn=conn,
                              image_bytes=own_bytes, query_label="dataset photo", top_k=4)
    assert images[0]["image_id"] not in [x["image_id"] for x in tr.output["similar_images"]]
    assert len(tr.output["similar_images"]) == 3


def test_retrieval_fails_cleanly_when_index_is_empty(world):
    conn, _ = world
    tr = image_retrieval_tool(SharedState("C", {}), client=mc(EmbedRuntime()), registry=build_registry(), conn=conn,
                              image_bytes=jpg((1, 2, 3)), query_label="x")
    assert tr.status == "failed" and "build it first" in tr.error


def test_retrieval_reports_embedding_failure_and_traces_the_failed_model_call(world):
    conn, images = world
    image_index.build_index(conn, mc(EmbedRuntime()), MODEL_ID, 256, images, workers=1)
    bad = EmbedRuntime(fail_for_colors=[(5, 5, 5)], error=client_error("ThrottlingException", "slow"))
    s = SharedState("C", {})
    tr = image_retrieval_tool(s, client=mc(bad), registry=build_registry(), conn=conn, image_bytes=jpg((5, 5, 5)),
                              query_label="dark")
    assert tr.status == "failed" and "BEDROCK_THROTTLED" in tr.error
    assert s.model_outputs[-1].ok is False


def test_retrieval_respects_disabled_model(world, monkeypatch):
    conn, images = world
    monkeypatch.setenv("MODEL_TITAN_MULTIMODAL_EMBED_ENABLED", "false")
    tr = image_retrieval_tool(SharedState("C", {}), client=mc(EmbedRuntime()), registry=build_registry(), conn=conn,
                              image_bytes=jpg((1, 2, 3)), query_label="x")
    assert tr.status == "failed" and "not enabled" in tr.error
