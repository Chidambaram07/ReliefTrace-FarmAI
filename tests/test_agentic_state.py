from backend.agentic.state import ModelOutput, SharedState, ToolResult


def test_route_records_selection_and_trace_step():
    s = SharedState(claim_id="CLM-1", claim={"claimed_cause": "drought"})
    s.route("visual_crop_verification", "nova_lite", "multimodal visual reasoning required")
    assert s.selected_models[0].model_key == "nova_lite"
    step = s.audit_trace[-1]
    assert step.agent == "router" and step.model == "nova_lite" and step.status == "success"


def test_route_with_fallback_is_traced_as_fallback_not_failure():
    s = SharedState(claim_id="CLM-1", claim={})
    s.route("independent_verification", "ministral_8b", "nova lite call failed", fallback_of="nova_lite")
    step = s.audit_trace[-1]
    assert step.status == "fallback" and step.fallback_of == "nova_lite"


def test_record_model_output_traces_failure_with_error():
    s = SharedState(claim_id="CLM-1", claim={})
    s.record_model_output(ModelOutput(task="classify", model_key="nova_micro", model_id="apac.amazon.nova-micro-v1:0",
                                      ok=False, output_summary="", error="BEDROCK_THROTTLED", latency_ms=50))
    assert s.model_outputs[0].ok is False
    step = s.audit_trace[-1]
    assert step.status == "failed" and step.error == "BEDROCK_THROTTLED" and step.model.startswith("apac.")


def test_record_tool_result_traces_source_and_status():
    s = SharedState(claim_id="CLM-1", claim={})
    s.record_tool_result(ToolResult(tool="weather", input_summary={"lat": 9.2, "lon": 77.4}, output={"rainfall_mm": 5},
                                    status="success", latency_ms=200, source_type="public_dataset",
                                    source_name="Open-Meteo"))
    step = s.audit_trace[-1]
    assert step.tool == "weather" and step.evidence_source == "Open-Meteo" and step.status == "success"


def test_contradictions_and_missing_evidence_deduplicate():
    s = SharedState(claim_id="CLM-1", claim={})
    s.add_contradiction("weather is wetter than usual")
    s.add_contradiction("weather is wetter than usual")
    s.add_missing("no photo attached")
    assert s.contradictions == ["weather is wetter than usual"] and s.missing_evidence == ["no photo attached"]


def test_plan_verification_and_review_are_traced_in_order():
    s = SharedState(claim_id="CLM-1", claim={})
    s.set_plan({"checks": ["weather", "location"]})
    s.set_verification_result({"status": "Contradictory evidence found"})
    s.set_review_status("open", decision=None)
    steps = [t.step for t in s.audit_trace]
    assert steps == ["plan", "verification", "human_review"]
    assert s.audit_trace[-1].human_review_decision == "open"


def test_to_dict_is_fully_serializable_and_inspectable():
    s = SharedState(claim_id="CLM-1", claim={"survey_no": "293"})
    s.route("task", "nova_lite", "reason")
    s.add_evidence({"evidence_id": "EV-1"})
    d = s.to_dict()
    assert d["claim_id"] == "CLM-1" and d["evidence"] == [{"evidence_id": "EV-1"}]
    assert d["selected_models"][0]["model_key"] == "nova_lite"
    import json
    json.dumps(d)  # must round-trip through JSON with no custom-object leftovers
