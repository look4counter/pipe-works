"""Pipeline lifecycle state model."""

from __future__ import annotations

from enum import Enum


class PipelineState(str, Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    DRAINING = "draining"
    STOPPED = "stopped"
    ERROR = "error"
    RECONNECTING = "reconnecting"


ALLOWED_TRANSITIONS: dict[PipelineState, set[PipelineState]] = {
    PipelineState.CREATED: {PipelineState.STARTING, PipelineState.ERROR},
    PipelineState.STARTING: {PipelineState.RUNNING, PipelineState.ERROR},
    PipelineState.RUNNING: {
        PipelineState.DRAINING,
        PipelineState.RECONNECTING,
        PipelineState.ERROR,
    },
    PipelineState.RECONNECTING: {PipelineState.RUNNING, PipelineState.DRAINING, PipelineState.ERROR},
    PipelineState.DRAINING: {PipelineState.STOPPED, PipelineState.ERROR},
    PipelineState.STOPPED: {PipelineState.STARTING},
    PipelineState.ERROR: {PipelineState.STARTING},
}


class Lifecycle:
    """Small transition guard for runtime state."""

    def __init__(self) -> None:
        self.state = PipelineState.CREATED

    def transition(self, next_state: PipelineState) -> None:
        allowed = ALLOWED_TRANSITIONS[self.state]
        if next_state not in allowed:
            raise ValueError(f"invalid lifecycle transition {self.state.value} -> {next_state.value}")
        self.state = next_state
