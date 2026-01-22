"""Tests for flow definitions."""
import pytest
from src.flows.flow import (
    Flow,
    FlowStep,
    FlowDef,
    Choose,
    Join,
    JoinConfig,
    StepConfig,
)


def test_flow_creation():
    """Test creating a Flow."""
    flow = Flow("step1", "step2", "step3")
    assert len(flow) == 3
    assert flow[0] == "step1"


def test_flow_from_list():
    """Test creating Flow from list."""
    flow = Flow(["step1", "step2"])
    assert len(flow) == 2


def test_flow_step_from_string():
    """Test creating FlowStep from string."""
    step = FlowStep.from_dict("test_step")
    assert step.step == "test_step"
    assert step.flow is None
    assert step.fork is None


def test_flow_step_from_dict():
    """Test creating FlowStep from dictionary."""
    step = FlowStep.from_dict({"step": "test_step", "config": {"model": "gpt-4"}})
    assert step.step == "test_step"
    assert step.config is not None
    assert step.config.model == "gpt-4"


def test_flow_step_with_config():
    """Test FlowStep with StepConfig."""
    config = StepConfig(model="gpt-4", temperature=0.7)
    step = FlowStep(step="test_step", config=config)
    assert step.step == "test_step"
    assert step.config.model == "gpt-4"


def test_flow_step_fork():
    """Test FlowStep with fork."""
    fork_steps = [
        FlowStep(step="step1"),
        FlowStep(step="step2")
    ]
    step = FlowStep(fork=fork_steps)
    assert step.fork is not None
    assert len(step.fork) == 2


def test_flow_step_choose():
    """Test FlowStep with Choose."""
    choose = Choose(
        options={
            "option1": [FlowStep(step="step1")],
            "option2": [FlowStep(step="step2")]
        }
    )
    step = FlowStep(choose=choose)
    assert step.choose is not None
    assert len(step.choose.options) == 2


def test_flow_step_join():
    """Test FlowStep with Join."""
    join = Join(join=JoinConfig(step="synthesize"))
    step = FlowStep(join=join)
    assert step.join is not None
    assert step.join.join.step == "synthesize"


def test_flow_def():
    """Test FlowDef creation."""
    steps = [
        FlowStep(step="step1"),
        FlowStep(step="step2")
    ]
    flow_def = FlowDef(name="test_flow", steps=steps)
    assert flow_def.name == "test_flow"
    assert len(flow_def.steps) == 2


def test_flow_def_to_dict():
    """Test FlowDef serialization."""
    steps = [FlowStep(step="step1")]
    flow_def = FlowDef(name="test_flow", steps=steps)
    data = flow_def.to_dict()
    assert data["name"] == "test_flow"
    assert len(data["steps"]) == 1


def test_flow_def_from_dict():
    """Test FlowDef deserialization."""
    data = {
        "name": "test_flow",
        "steps": [{"step": "step1"}]
    }
    flow_def = FlowDef.from_dict("test_flow", data)
    assert flow_def.name == "test_flow"
    assert len(flow_def.steps) == 1

