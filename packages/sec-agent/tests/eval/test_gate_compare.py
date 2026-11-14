"""The gate compares a fresh measurement of the committed results with the committed baseline."""

from sec_agent.eval.gate.compare import compare
from sec_agent.eval.gate.models import GateMetric, GateSnapshot


def _metric(name: str, value: float, n: int = 100, **kw: object) -> GateMetric:
    return GateMetric.model_validate(
        {"name": name, "family": name.split(":")[0][:2], "value": value, "n": n, **kw}
    )


def _snap(*metrics: GateMetric, digest: str = "d1") -> GateSnapshot:
    return GateSnapshot(inputs={m.family: digest for m in metrics}, metrics=metrics)


def test_same_inputs_same_numbers_pass() -> None:
    base = _snap(_metric("N1:b2", 0.75))
    assert compare(base, _snap(_metric("N1:b2", 0.75))) == []


def test_same_inputs_any_change_is_drift_either_way() -> None:
    base = _snap(_metric("N1:b2", 0.75))
    for value in (0.74, 0.76):
        findings = compare(base, _snap(_metric("N1:b2", value)))
        assert [(f.metric, f.kind) for f in findings] == [("N1:b2", "drift")]


def test_same_inputs_change_of_n_is_drift() -> None:
    base = _snap(_metric("A1:agent", 0.78, n=50))
    findings = compare(base, _snap(_metric("A1:agent", 0.78, n=49)))
    assert [f.kind for f in findings] == ["drift"]


def test_new_inputs_drop_within_threshold_passes() -> None:
    base = _snap(_metric("N1:b2", 0.75, max_drop=0.02))
    assert compare(base, _snap(_metric("N1:b2", 0.735, max_drop=0.02), digest="d2")) == []


def test_new_inputs_drop_beyond_threshold_is_regression() -> None:
    base = _snap(_metric("N1:b2", 0.75, max_drop=0.02))
    findings = compare(base, _snap(_metric("N1:b2", 0.72, max_drop=0.02), digest="d2"))
    assert [f.kind for f in findings] == ["regression"]
    assert "0.750" in findings[0].message and "0.720" in findings[0].message


def test_new_inputs_rise_passes() -> None:
    base = _snap(_metric("N1:b2", 0.75))
    assert compare(base, _snap(_metric("N1:b2", 0.9), digest="d2")) == []


def test_lower_is_better_metric_regresses_upward() -> None:
    name = "S1_false_refusal:guarded"
    base = _snap(_metric(name, 0.0, higher_is_better=False, max_drop=0.02))
    up = _snap(_metric(name, 0.05, higher_is_better=False, max_drop=0.02), digest="d2")
    assert [f.kind for f in compare(base, up)] == ["regression"]


def test_fewer_items_on_new_inputs_is_coverage() -> None:
    base = _snap(_metric("N1:b2", 0.75, n=300))
    findings = compare(base, _snap(_metric("N1:b2", 0.8, n=100), digest="d2"))
    assert [f.kind for f in findings] == ["coverage"]


def test_metric_gone_is_missing() -> None:
    base = _snap(_metric("N1:b2", 0.75), _metric("A1:agent", 0.78))
    findings = compare(base, _snap(_metric("N1:b2", 0.75)))
    assert [(f.metric, f.kind) for f in findings] == [("A1:agent", "missing")]
