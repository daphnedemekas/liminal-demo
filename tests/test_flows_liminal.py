"""Tests for Liminal-specific flows."""
import pytest
from src.flows.liminal_flows import (
    discovery_flow,
    teaching_flow,
    adaptive_flow,
    parallel_ranker_flow,
)


def test_discovery_flow():
    """Test discovery flow definition."""
    flow = discovery_flow()
    
    assert flow.name == "discovery"
    assert len(flow.steps) == 3
    assert flow.steps[0].step == "goal_discovery"
    assert flow.steps[1].step == "teaching_discovery"
    assert flow.steps[2].step == "propose_curriculum"


def test_teaching_flow():
    """Test teaching flow definition."""
    flow = teaching_flow()
    
    assert flow.name == "teaching"
    assert len(flow.steps) == 4
    assert flow.steps[0].step == "assess_knowledge"
    assert flow.steps[1].step == "propose_curriculum"
    assert flow.steps[2].step == "negotiate_curriculum"
    assert flow.steps[3].step == "teach_curriculum"


def test_adaptive_flow():
    """Test adaptive flow definition."""
    flow = adaptive_flow()
    
    assert flow.name == "adaptive"
    assert len(flow.steps) == 1
    assert flow.steps[0].choose is not None
    assert len(flow.steps[0].choose.options) == 3
    assert "continue_discovery" in flow.steps[0].choose.options
    assert "propose_curriculum" in flow.steps[0].choose.options
    assert "start_teaching" in flow.steps[0].choose.options


def test_parallel_ranker_flow():
    """Test parallel ranker flow definition."""
    flow = parallel_ranker_flow()
    
    assert flow.name == "parallel_ranker"
    assert len(flow.steps) == 2
    assert flow.steps[0].fork is not None
    assert len(flow.steps[0].fork) == 3
    assert flow.steps[1].join is not None




