# tests/test_polling.py
from dokploy_ctl.dokploy import ContainerInfo
from dokploy_ctl.polling import check_stall, detect_phase, detect_transitions


def _container(cid, service, state="running", health="healthy"):
    return ContainerInfo(
        container_id=cid,
        service=service,
        state=state,
        health=health,
        image="img",
        uptime="2h",
        raw_status=f"Up 2h ({health})",
    )


def test_detect_transitions_disappeared():
    prev = [_container("aaa", "worker"), _container("bbb", "db")]
    curr = [_container("bbb", "db")]
    transitions = detect_transitions(prev, curr)
    assert any("worker" in t and "gone" in t for t in transitions)


def test_detect_transitions_appeared():
    prev = [_container("bbb", "db")]
    curr = [_container("bbb", "db"), _container("ccc", "worker", state="running", health="starting")]
    transitions = detect_transitions(prev, curr)
    assert any("worker" in t and "appeared" in t for t in transitions)


def test_detect_transitions_state_changed():
    prev = [_container("aaa", "worker", health="starting")]
    curr = [_container("aaa", "worker", health="healthy")]
    transitions = detect_transitions(prev, curr)
    assert any("worker" in t and "starting" in t and "healthy" in t for t in transitions)


def test_detect_transitions_no_change():
    prev = [_container("aaa", "worker")]
    curr = [_container("aaa", "worker")]
    transitions = detect_transitions(prev, curr)
    assert transitions == []


def test_detect_phase_shutdown():
    pre_deploy_ids = {"aaa", "bbb"}
    current = [_container("aaa", "worker")]  # bbb gone, no new
    phase = detect_phase(pre_deploy_ids, current)
    assert phase == "graceful shutdown"


def test_detect_phase_pulling():
    pre_deploy_ids = {"aaa", "bbb"}
    current = []  # all gone
    phase = detect_phase(pre_deploy_ids, current)
    assert phase == "image pull / startup"


def test_detect_phase_starting():
    pre_deploy_ids = {"aaa", "bbb"}
    current = [_container("ccc", "worker", health="starting"), _container("ddd", "db", health="healthy")]
    phase = detect_phase(pre_deploy_ids, current)
    assert phase == "containers starting"


def test_detect_phase_healthy():
    pre_deploy_ids = {"aaa", "bbb"}
    current = [_container("ccc", "worker"), _container("ddd", "db")]
    phase = detect_phase(pre_deploy_ids, current)
    assert phase == "healthy"


def test_detect_phase_rolling():
    pre_deploy_ids = {"aaa"}
    current = [_container("aaa", "worker-old"), _container("bbb", "worker-new", health="starting")]
    phase = detect_phase(pre_deploy_ids, current)
    assert phase == "rolling update"


def test_check_stall_no_stall():
    assert check_stall(last_transition_time=100.0, now=150.0, threshold=90) is False


def test_check_stall_stalled():
    assert check_stall(last_transition_time=100.0, now=200.0, threshold=90) is True
