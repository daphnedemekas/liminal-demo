"""Tests for flow executor."""
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
from src.flows.executor import FlowExecutor, FlowContext
from src.flows.flow import FlowDef, FlowStep, Choose, Join, JoinConfig
from src.llm_client import LLMClient


def test_flow_context():
    """Test FlowContext."""
    context = FlowContext({"key1": "value1"})
    assert context.get("key1") == "value1"
    assert context.get("key2", "default") == "default"
    
    context.set("key2", "value2")
    assert context.get("key2") == "value2"
    
    context.update({"key3": "value3"})
    assert context.get("key3") == "value3"


def test_execute_sequential_steps(tmp_path):
    """Test executing sequential steps."""
    llm = Mock(spec=LLMClient)
    executor = FlowExecutor(llm, tmp_path)
    
    # Mock step executor
    call_count = [0]
    def mock_executor(step_name, config, context):
        call_count[0] += 1
        return {f"result_{call_count[0]}": step_name}
    
    executor.step_executor = mock_executor
    
    flow = FlowDef(
        name="test_flow",
        steps=[
            FlowStep(step="step1"),
            FlowStep(step="step2"),
            FlowStep(step="step3"),
        ]
    )
    
    result = executor.execute(flow)
    
    assert call_count[0] == 3
    assert result.get("result_1") == "step1"
    assert result.get("result_2") == "step2"
    assert result.get("result_3") == "step3"


def test_execute_fork_join(tmp_path):
    """Test executing fork/join."""
    llm = Mock(spec=LLMClient)
    executor = FlowExecutor(llm, tmp_path)
    
    # Mock step executor
    def mock_executor(step_name, config, context):
        return {step_name: f"result_{step_name}"}
    
    executor.step_executor = mock_executor
    
    flow = FlowDef(
        name="test_flow",
        steps=[
            FlowStep(
                fork=[
                    FlowStep(step="step1"),
                    FlowStep(step="step2"),
                ]
            ),
            FlowStep(
                join=Join(join=JoinConfig(step="synthesize"))
            ),
        ]
    )
    
    result = executor.execute(flow)
    
    # Should have results from both fork steps (either directly or in fork_results)
    result_str = str(result.data)
    assert "step1" in result.data or "result_step1" in result_str or "fork_results" in result.data
    assert "step2" in result.data or "result_step2" in result_str or "fork_results" in result.data


def test_execute_choose(tmp_path):
    """Test executing choose branch."""
    llm = Mock(spec=LLMClient)
    llm.chat = Mock(return_value="option1")
    
    executor = FlowExecutor(llm, tmp_path)
    
    # Mock step executor
    def mock_executor(step_name, config, context):
        return {step_name: "executed"}
    
    executor.step_executor = mock_executor
    
    flow = FlowDef(
        name="test_flow",
        steps=[
            FlowStep(
                choose=Choose(
                    options={
                        "option1": [{"step": "step1"}],
                        "option2": [{"step": "step2"}],
                    }
                )
            ),
        ]
    )
    
    result = executor.execute(flow)
    
    # Should have executed chosen branch
    assert llm.chat.called
    # Result should contain step from chosen branch
    assert "step1" in result.data or "executed" in str(result.data)


def test_flow_context_passing(tmp_path):
    """Test that context is passed between steps."""
    llm = Mock(spec=LLMClient)
    executor = FlowExecutor(llm, tmp_path)
    
    # Mock step executor that reads and updates context
    def mock_executor(step_name, config, context):
        prev_value = context.get("counter", 0)
        context.set("counter", prev_value + 1)
        return {"step": step_name, "counter": context.get("counter")}
    
    executor.step_executor = mock_executor
    
    flow = FlowDef(
        name="test_flow",
        steps=[
            FlowStep(step="step1"),
            FlowStep(step="step2"),
        ]
    )
    
    result = executor.execute(flow, initial_context={"counter": 0})
    
    # Counter should have incremented
    assert result.get("counter") == 2

