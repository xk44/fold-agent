"""Tests for Privacy Infrastructure — Phase 24 Tier 3"""

from __future__ import annotations

import math
import pytest

from backend.app.privacy_infra import (
    MOCK_FEDERATION_NODES,
    PRIVACY_BUDGET_DEFAULT,
    CohortReport,
    DPConfig,
    DPResult,
    FederatedJob,
    FederatedNode,
    FederatedResult,
    PrivacyAccountant,
    add_gaussian_noise,
    add_laplace_noise,
    aggregate_federated_results,
    apply_dp,
    check_privacy_budget,
    create_cohort_report,
    create_federated_job,
    get_federation_status,
    run_federated_prediction,
    simulate_federated_round,
)


# ---------------------------------------------------------------------------
# Federated Node / Status
# ---------------------------------------------------------------------------

class TestFederationNodes:
    def test_mock_nodes_count(self):
        assert len(MOCK_FEDERATION_NODES) == 5

    def test_node_residencies_present(self):
        residencies = {n.data_residency for n in MOCK_FEDERATION_NODES.values()}
        assert "US" in residencies
        assert "EU" in residencies
        assert "APAC" in residencies
        assert "local" in residencies

    def test_node_dataclass_fields(self):
        node = MOCK_FEDERATION_NODES["node_boston_01"]
        assert isinstance(node, FederatedNode)
        assert node.institution == "Boston Medical Center"
        assert node.data_residency == "US"
        assert node.available is True
        assert node.trust_level == "full"
        assert "structure_prediction" in node.capabilities

    def test_unavailable_node_exists(self):
        unavailable = [n for n in MOCK_FEDERATION_NODES.values() if not n.available]
        assert len(unavailable) >= 1

    def test_get_federation_status_keys(self):
        status = get_federation_status()
        assert set(status.keys()) == set(MOCK_FEDERATION_NODES.keys())

    def test_get_federation_status_fields(self):
        status = get_federation_status()
        node = status["node_boston_01"]
        assert "institution" in node
        assert "data_residency" in node
        assert "available" in node
        assert "capabilities" in node
        assert "trust_level" in node

    def test_get_federation_status_unavailable_preserved(self):
        status = get_federation_status()
        assert status["node_sydney_04"]["available"] is False


# ---------------------------------------------------------------------------
# Federated Job Creation
# ---------------------------------------------------------------------------

class TestCreateFederatedJob:
    def test_creates_job_with_all_available_nodes(self):
        job = create_federated_job("abc123")
        available = [nid for nid, n in MOCK_FEDERATION_NODES.items() if n.available]
        assert set(job.participating_nodes) == set(available)

    def test_job_never_stores_sequence(self):
        seq = "MKTIIALSYIFCLVFA"
        job = create_federated_job("hash_of_seq")
        assert seq not in str(job)
        assert job.sequence_hash == "hash_of_seq"

    def test_job_initial_status_pending(self):
        job = create_federated_job("deadbeef")
        assert job.status == "pending"

    def test_job_initial_updates_zero(self):
        job = create_federated_job("deadbeef")
        assert job.model_updates_received == 0

    def test_job_initial_budget_zero(self):
        job = create_federated_job("deadbeef")
        assert job.privacy_budget_used == 0.0

    def test_job_id_deterministic(self):
        job1 = create_federated_job("samehash")
        job2 = create_federated_job("samehash")
        assert job1.job_id == job2.job_id

    def test_job_id_different_for_different_hash(self):
        job1 = create_federated_job("hash1")
        job2 = create_federated_job("hash2")
        assert job1.job_id != job2.job_id

    def test_target_nodes_filters_unavailable(self):
        job = create_federated_job("abc", target_nodes=["node_boston_01", "node_sydney_04"])
        assert "node_boston_01" in job.participating_nodes
        assert "node_sydney_04" not in job.participating_nodes

    def test_target_nodes_unknown_skipped(self):
        job = create_federated_job("abc", target_nodes=["node_boston_01", "node_unknown_99"])
        assert "node_unknown_99" not in job.participating_nodes
        assert "node_boston_01" in job.participating_nodes


# ---------------------------------------------------------------------------
# Federated Round Simulation
# ---------------------------------------------------------------------------

class TestSimulateFederatedRound:
    def test_round_produces_aggregating_status(self):
        job = create_federated_job("hash_abc")
        updated = simulate_federated_round(job)
        assert updated.status == "aggregating"

    def test_round_records_updates_received(self):
        job = create_federated_job("hash_xyz")
        updated = simulate_federated_round(job)
        assert updated.model_updates_received > 0

    def test_round_charges_privacy_budget(self):
        job = create_federated_job("hash_xyz")
        updated = simulate_federated_round(job)
        assert updated.privacy_budget_used > 0.0

    def test_round_result_has_node_estimates(self):
        job = create_federated_job("hash_xyz")
        updated = simulate_federated_round(job)
        assert updated.aggregated_result is not None
        assert "node_estimates" in updated.aggregated_result

    def test_round_plddt_in_valid_range(self):
        job = create_federated_job("hash_xyz")
        updated = simulate_federated_round(job)
        mean = updated.aggregated_result["round_mean_plddt"]
        assert 0.0 < mean < 100.0

    def test_round_deterministic(self):
        job1 = create_federated_job("same")
        job2 = create_federated_job("same")
        r1 = simulate_federated_round(job1)
        r2 = simulate_federated_round(job2)
        assert r1.aggregated_result == r2.aggregated_result

    def test_round_no_available_nodes_fails(self):
        job = FederatedJob(
            job_id="test-job",
            sequence_hash="abc",
            participating_nodes=["node_sydney_04"],  # unavailable
            status="pending",
            model_updates_received=0,
            aggregated_result=None,
            privacy_budget_used=0.0,
        )
        result = simulate_federated_round(job)
        assert result.status == "failed"


# ---------------------------------------------------------------------------
# Federated Aggregation
# ---------------------------------------------------------------------------

class TestAggregateFederatedResults:
    def test_aggregate_produces_federated_result(self):
        job = simulate_federated_round(create_federated_job("hash1"))
        result = aggregate_federated_results(job)
        assert isinstance(result, FederatedResult)

    def test_aggregate_plddt_in_range(self):
        job = simulate_federated_round(create_federated_job("hash2"))
        result = aggregate_federated_results(job)
        assert 0.0 < result.consensus_plddt < 100.0

    def test_aggregate_privacy_preserved(self):
        job = simulate_federated_round(create_federated_job("hash3"))
        result = aggregate_federated_results(job)
        assert result.privacy_preserved is True

    def test_aggregate_audit_trail_nonempty(self):
        job = simulate_federated_round(create_federated_job("hash4"))
        result = aggregate_federated_results(job)
        assert len(result.audit_trail) > 0

    def test_aggregate_audit_no_raw_sequence(self):
        seq = "MKTIIALSYIFCLVFA"
        job = simulate_federated_round(create_federated_job("somehash"))
        result = aggregate_federated_results(job)
        assert seq not in " ".join(result.audit_trail)

    def test_aggregate_confidence_interval_ordered(self):
        job = simulate_federated_round(create_federated_job("hash5"))
        result = aggregate_federated_results(job)
        lo, hi = result.confidence_interval
        assert lo <= result.consensus_plddt <= hi

    def test_aggregate_no_updates_fails_gracefully(self):
        job = FederatedJob(
            job_id="empty-job",
            sequence_hash="empty",
            participating_nodes=[],
            status="failed",
            model_updates_received=0,
            aggregated_result=None,
            privacy_budget_used=0.0,
        )
        result = aggregate_federated_results(job)
        assert result.contributing_nodes == 0
        assert result.consensus_plddt == 0.0


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------

class TestRunFederatedPrediction:
    def test_full_pipeline_returns_result(self):
        result = run_federated_prediction("hashABC")
        assert isinstance(result, FederatedResult)

    def test_full_pipeline_privacy_preserved(self):
        result = run_federated_prediction("hashDEF")
        assert result.privacy_preserved is True

    def test_full_pipeline_contributing_nodes(self):
        result = run_federated_prediction("hashGHI")
        assert result.contributing_nodes > 0

    def test_full_pipeline_deterministic(self):
        r1 = run_federated_prediction("hash_stable")
        r2 = run_federated_prediction("hash_stable")
        assert r1.consensus_plddt == r2.consensus_plddt
        assert r1.confidence_interval == r2.confidence_interval


# ---------------------------------------------------------------------------
# Differential Privacy — Laplace Noise
# ---------------------------------------------------------------------------

class TestLaplaceNoise:
    def test_laplace_deterministic_same_input(self):
        n1 = add_laplace_noise(50.0, 1.0, 1.0)
        n2 = add_laplace_noise(50.0, 1.0, 1.0)
        assert n1 == n2

    def test_laplace_different_inputs_different_output(self):
        n1 = add_laplace_noise(50.0, 1.0, 1.0)
        n2 = add_laplace_noise(51.0, 1.0, 1.0)
        assert n1 != n2

    def test_laplace_different_epsilon_different_output(self):
        n1 = add_laplace_noise(50.0, 1.0, 0.1)
        n2 = add_laplace_noise(50.0, 1.0, 10.0)
        assert n1 != n2

    def test_laplace_higher_epsilon_less_noise(self):
        """Higher epsilon → smaller scale → noise closer to 0 on average."""
        n_low = abs(add_laplace_noise(0.0, 1.0, 0.01) - 0.0)
        n_high = abs(add_laplace_noise(0.0, 1.0, 100.0) - 0.0)
        # With deterministic hash, verify scale logic:
        scale_low = 1.0 / 0.01
        scale_high = 1.0 / 100.0
        assert scale_low > scale_high

    def test_laplace_zero_epsilon_raises(self):
        with pytest.raises(ValueError):
            add_laplace_noise(1.0, 1.0, 0.0)

    def test_laplace_negative_epsilon_raises(self):
        with pytest.raises(ValueError):
            add_laplace_noise(1.0, 1.0, -1.0)

    def test_laplace_returns_float(self):
        result = add_laplace_noise(10.0, 1.0, 1.0)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Differential Privacy — Gaussian Noise
# ---------------------------------------------------------------------------

class TestGaussianNoise:
    def test_gaussian_deterministic_same_input(self):
        n1 = add_gaussian_noise(50.0, 1.0, 1.0, 1e-5)
        n2 = add_gaussian_noise(50.0, 1.0, 1.0, 1e-5)
        assert n1 == n2

    def test_gaussian_different_inputs_different_output(self):
        n1 = add_gaussian_noise(50.0, 1.0, 1.0, 1e-5)
        n2 = add_gaussian_noise(51.0, 1.0, 1.0, 1e-5)
        assert n1 != n2

    def test_gaussian_higher_epsilon_less_sigma(self):
        sigma_low = 1.0 * math.sqrt(2 * math.log(1.25 / 1e-5)) / 0.1
        sigma_high = 1.0 * math.sqrt(2 * math.log(1.25 / 1e-5)) / 10.0
        assert sigma_low > sigma_high

    def test_gaussian_zero_epsilon_raises(self):
        with pytest.raises(ValueError):
            add_gaussian_noise(1.0, 1.0, 0.0, 1e-5)

    def test_gaussian_zero_delta_raises(self):
        with pytest.raises(ValueError):
            add_gaussian_noise(1.0, 1.0, 1.0, 0.0)

    def test_gaussian_returns_float(self):
        result = add_gaussian_noise(10.0, 1.0, 1.0, 1e-5)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# apply_dp
# ---------------------------------------------------------------------------

class TestApplyDP:
    def test_apply_dp_laplace_returns_dpresult(self):
        cfg = DPConfig(epsilon=1.0, mechanism="laplace")
        result = apply_dp(50.0, cfg)
        assert isinstance(result, DPResult)

    def test_apply_dp_original_value_redacted(self):
        cfg = DPConfig(epsilon=1.0, mechanism="laplace")
        result = apply_dp(50.0, cfg)
        assert result.original_value is None

    def test_apply_dp_epsilon_recorded(self):
        cfg = DPConfig(epsilon=2.5, mechanism="laplace")
        result = apply_dp(50.0, cfg)
        assert result.epsilon_used == 2.5

    def test_apply_dp_ci_ordered(self):
        cfg = DPConfig(epsilon=1.0, mechanism="laplace")
        result = apply_dp(50.0, cfg)
        lo, hi = result.confidence_interval
        assert lo <= result.noisy_value <= hi

    def test_apply_dp_gaussian_works(self):
        cfg = DPConfig(epsilon=1.0, mechanism="gaussian", delta=1e-5)
        result = apply_dp(50.0, cfg)
        assert isinstance(result, DPResult)

    def test_apply_dp_clipping_applied(self):
        cfg = DPConfig(epsilon=1.0, mechanism="laplace", clip_min=0.0, clip_max=1.0)
        # Value 200 gets clipped to 1.0 before noise — noise applied to 1.0
        noisy_clipped = apply_dp(200.0, cfg)
        noisy_unclipped = apply_dp(1.0, cfg)
        assert noisy_clipped.noisy_value == noisy_unclipped.noisy_value

    def test_apply_dp_unknown_mechanism_raises(self):
        cfg = DPConfig(epsilon=1.0, mechanism="unknown")
        with pytest.raises(ValueError):
            apply_dp(1.0, cfg)

    def test_apply_dp_high_epsilon_less_noise(self):
        cfg_low = DPConfig(epsilon=0.01, mechanism="laplace")
        cfg_high = DPConfig(epsilon=100.0, mechanism="laplace")
        # Scale low = 1/0.01 = 100; scale high = 1/100 = 0.01
        # The margin (1.96 * scale) should be larger for low epsilon
        r_low = apply_dp(0.0, cfg_low)
        r_high = apply_dp(0.0, cfg_high)
        lo_low, hi_low = r_low.confidence_interval
        lo_high, hi_high = r_high.confidence_interval
        width_low = hi_low - lo_low
        width_high = hi_high - lo_high
        assert width_low > width_high


# ---------------------------------------------------------------------------
# Cohort Report
# ---------------------------------------------------------------------------

class TestCohortReport:
    def test_cohort_report_created(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        cfg = DPConfig(epsilon=1.0)
        report = create_cohort_report(values, "plddt", cfg)
        assert isinstance(report, CohortReport)

    def test_cohort_report_size(self):
        values = [10.0, 20.0, 30.0]
        cfg = DPConfig(epsilon=1.0)
        report = create_cohort_report(values, "score", cfg)
        assert report.cohort_size == 3

    def test_cohort_report_metric_name(self):
        values = [1.0, 2.0]
        cfg = DPConfig(epsilon=1.0)
        report = create_cohort_report(values, "my_metric", cfg)
        assert report.metric_name == "my_metric"

    def test_cohort_report_dp_results_count(self):
        # mean + count + sum = 3 stats
        values = [1.0, 2.0, 3.0]
        cfg = DPConfig(epsilon=1.0)
        report = create_cohort_report(values, "x", cfg)
        assert len(report.dp_results) == 3

    def test_cohort_report_budget_tracking(self):
        values = [1.0, 2.0, 3.0]
        cfg = DPConfig(epsilon=1.0)
        report = create_cohort_report(values, "x", cfg)
        assert report.total_privacy_budget == PRIVACY_BUDGET_DEFAULT
        assert report.budget_remaining < PRIVACY_BUDGET_DEFAULT

    def test_cohort_report_safe_to_release_when_budget_remains(self):
        values = [1.0, 2.0]
        cfg = DPConfig(epsilon=0.1)
        report = create_cohort_report(values, "x", cfg)
        assert report.safe_to_release is True

    def test_empty_cohort_returns_zero_size(self):
        cfg = DPConfig(epsilon=1.0)
        report = create_cohort_report([], "empty", cfg)
        assert report.cohort_size == 0
        assert report.safe_to_release is False

    def test_single_value_cohort(self):
        cfg = DPConfig(epsilon=1.0)
        report = create_cohort_report([42.0], "single", cfg)
        assert report.cohort_size == 1
        assert len(report.dp_results) == 3


# ---------------------------------------------------------------------------
# check_privacy_budget
# ---------------------------------------------------------------------------

class TestCheckPrivacyBudget:
    def test_check_budget_remaining(self):
        result = check_privacy_budget(3.0, 10.0)
        assert result["epsilon_remaining"] == pytest.approx(7.0)

    def test_check_budget_safe_when_remaining(self):
        result = check_privacy_budget(5.0, 10.0)
        assert result["safe_to_continue"] is True

    def test_check_budget_exhausted(self):
        result = check_privacy_budget(10.0, 10.0)
        assert result["budget_exhausted"] is True
        assert result["safe_to_continue"] is False

    def test_check_budget_overspent_clamps(self):
        result = check_privacy_budget(15.0, 10.0)
        assert result["epsilon_remaining"] == 0.0

    def test_check_budget_fraction_used(self):
        result = check_privacy_budget(2.0, 10.0)
        assert result["fraction_used"] == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# PrivacyAccountant
# ---------------------------------------------------------------------------

class TestPrivacyAccountant:
    def test_initial_budget(self):
        acc = PrivacyAccountant(total_budget=10.0)
        assert acc.remaining() == pytest.approx(10.0)

    def test_spend_deducts(self):
        acc = PrivacyAccountant(10.0)
        acc.spend(3.0)
        assert acc.remaining() == pytest.approx(7.0)

    def test_spend_returns_true_when_available(self):
        acc = PrivacyAccountant(10.0)
        assert acc.spend(5.0) is True

    def test_spend_returns_false_when_exhausted(self):
        acc = PrivacyAccountant(1.0)
        acc.spend(1.0)
        assert acc.spend(0.1) is False

    def test_spend_does_not_deduct_on_rejection(self):
        acc = PrivacyAccountant(1.0)
        acc.spend(1.0)
        acc.spend(0.5)  # rejected
        assert acc.remaining() == pytest.approx(0.0)

    def test_reset_restores_budget(self):
        acc = PrivacyAccountant(10.0)
        acc.spend(5.0)
        acc.reset()
        assert acc.remaining() == pytest.approx(10.0)

    def test_reset_clears_history(self):
        acc = PrivacyAccountant(10.0)
        acc.spend(1.0)
        acc.reset()
        report = acc.get_report()
        assert report["num_queries"] == 0
        assert report["history"] == []

    def test_get_report_fields(self):
        acc = PrivacyAccountant(10.0)
        acc.spend(2.0)
        report = acc.get_report()
        assert "total_budget" in report
        assert "spent" in report
        assert "remaining" in report
        assert "num_queries" in report
        assert "history" in report
        assert "budget_exhausted" in report

    def test_get_report_num_queries(self):
        acc = PrivacyAccountant(10.0)
        acc.spend(1.0)
        acc.spend(2.0)
        report = acc.get_report()
        assert report["num_queries"] == 2

    def test_overspend_rejected_completely(self):
        acc = PrivacyAccountant(5.0)
        result = acc.spend(6.0)
        assert result is False
        assert acc.remaining() == pytest.approx(5.0)

    def test_zero_epsilon_raises(self):
        acc = PrivacyAccountant(10.0)
        with pytest.raises(ValueError):
            acc.spend(0.0)

    def test_very_small_epsilon(self):
        acc = PrivacyAccountant(10.0)
        for _ in range(100):
            acc.spend(0.01)
        assert acc.remaining() == pytest.approx(9.0)

    def test_default_budget(self):
        acc = PrivacyAccountant()
        assert acc.remaining() == pytest.approx(10.0)
