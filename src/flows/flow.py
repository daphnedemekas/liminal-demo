"""Flow DAG definitions for multi-step agent execution."""
from typing import Any, Optional, List, Dict, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Flow(list):
    """Convenience wrapper for flow step lists."""
    
    def __init__(self, *steps):
        if len(steps) == 1:
            value = steps[0]
            if isinstance(value, str):
                super().__init__([value])
                return
            if isinstance(value, (list, tuple)):
                super().__init__(value)
                return
        super().__init__(steps)


class StepConfig(BaseModel):
    """Configuration for a flow step."""
    
    model_config = ConfigDict(extra="forbid")
    
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    voice: Optional[List[str]] = None
    interactive: Optional[bool] = None


class JoinConfig(BaseModel):
    """Configuration for joining fork outcomes."""
    
    model_config = ConfigDict(extra="forbid")
    
    step: Optional[str] = None
    agent_model: Optional[str] = None
    voice: Optional[List[str]] = None
    
    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data):
        if isinstance(data, str):
            return {"step": data}
        return data


class Choose(BaseModel):
    """Prompt-driven choice between named subflows."""
    
    model_config = ConfigDict(extra="forbid")
    
    options: Dict[str, List[Any]]
    output: Optional[str] = None
    prompt: Optional[str] = None


class Join(BaseModel):
    """Join forked outputs into a single changeset."""
    
    model_config = ConfigDict(extra="forbid")
    
    join: JoinConfig = Field(default_factory=lambda: JoinConfig(step="synthesize"))


class FlowStep(BaseModel):
    """A single step in a flow, which can be a step, flow, fork, choose, or join."""
    
    model_config = ConfigDict(extra="forbid")
    
    step: Optional[str] = None
    flow: Optional[str] = None
    fork: Optional[List["FlowStep"]] = None
    config: Optional[StepConfig] = None
    choose: Optional[Choose] = None
    join: Optional[Join] = None
    
    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data):
        if isinstance(data, str):
            return {"step": data}
        if isinstance(data, Choose):
            return {"choose": data}
        if isinstance(data, Join):
            return {"join": data}
        return data
    
    def to_dict(self) -> Union[Dict[str, Any], str]:
        """Convert to dictionary representation."""
        return _step_to_data(self)
    
    @classmethod
    def from_dict(cls, data: Union[Dict[str, Any], str]) -> "FlowStep":
        """Create from dictionary representation."""
        return cls.model_validate(data)


class FlowDef(BaseModel):
    """Complete flow definition with name and steps."""
    
    model_config = ConfigDict(extra="forbid")
    
    name: str
    steps: List[FlowStep]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "steps": [_step_to_data(step) for step in self.steps],
        }
    
    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "FlowDef":
        """Create from dictionary representation."""
        payload = {"name": name, **data}
        return cls.model_validate(payload)


# Rebuild models to handle forward references
FlowStep.model_rebuild()


def _step_to_data(step: FlowStep) -> Union[Dict[str, Any], str]:
    """Convert FlowStep to dictionary or string representation."""
    if step.choose:
        return {"choose": _choose_to_data(step.choose)}
    if step.join:
        return {"join": _join_to_data(step.join)}
    if step.fork is not None:
        return {"fork": [_step_to_data(s) for s in step.fork]}
    
    if step.flow:
        data: Dict[str, Any] = {"flow": step.flow}
    elif step.step:
        data = {"step": step.step}
    else:
        return {}
    
    if step.config:
        config_data = step.config.model_dump(exclude_none=True)
        if config_data:
            data["config"] = config_data
    
    if data == {"step": step.step}:
        return step.step or ""
    
    return data


def _choose_to_data(choose: Choose) -> Dict[str, Any]:
    """Convert Choose to dictionary."""
    return choose.model_dump(exclude_none=True)


def _join_to_data(join: Join) -> Dict[str, Any]:
    """Convert Join to dictionary."""
    return join.model_dump(exclude_none=True)

