"""Reviewed ergonomic type aliases for inline public OpenAPI unions."""

from __future__ import annotations

from typing import TypeAlias

from parampilot.models import (
    ActiveLearningStrategy,
    AdditiveSoboStrategy,
    AskResult,
    CustomSoboStrategy,
    DoEStrategy,
    EntingStrategy,
    FactorialStrategy,
    FractionalFactorialStrategy,
    LLMStrategy,
    MoboStrategy,
    MultiFidelityHVKGStrategy,
    MultiFidelityVarianceBasedStrategy,
    MultiplicativeAdditiveSoboStrategy,
    MultiplicativeSoboStrategy,
    PredictResult,
    QparegoStrategy,
    RandomStrategy,
    ShortestPathStrategy,
    SoboStrategy,
    StepwiseStrategy,
    TrainResult,
)

Strategy: TypeAlias = (
    ActiveLearningStrategy
    | AdditiveSoboStrategy
    | CustomSoboStrategy
    | DoEStrategy
    | EntingStrategy
    | FactorialStrategy
    | FractionalFactorialStrategy
    | LLMStrategy
    | MoboStrategy
    | MultiFidelityHVKGStrategy
    | MultiFidelityVarianceBasedStrategy
    | MultiplicativeAdditiveSoboStrategy
    | MultiplicativeSoboStrategy
    | QparegoStrategy
    | RandomStrategy
    | ShortestPathStrategy
    | SoboStrategy
    | StepwiseStrategy
)
JobResult: TypeAlias = TrainResult | AskResult | PredictResult

__all__ = ["JobResult", "Strategy"]
