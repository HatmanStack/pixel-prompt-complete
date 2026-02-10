"""
Type definitions for Pixel Prompt v2 backend.

Provides TypedDict definitions for structured dicts and Protocol
contracts for handler functions.
"""

from typing import Dict, List, Literal, Protocol, Union

from typing_extensions import NotRequired, TypedDict


class HandlerSuccess(TypedDict):
    status: Literal['success']
    image: str  # base64
    model: str
    provider: str


class HandlerError(TypedDict):
    status: Literal['error']
    error: str
    model: str
    provider: str


HandlerResult = Union[HandlerSuccess, HandlerError]


class ModelConfigDict(TypedDict):
    id: str
    provider: str
    api_key: NotRequired[str]


class IterationData(TypedDict):
    index: int
    status: Literal['in_progress', 'completed', 'error']
    prompt: str
    startedAt: str
    imageKey: NotRequired[str]
    completedAt: NotRequired[str]
    error: NotRequired[str]
    duration: NotRequired[float]
    isOutpaint: bool
    outpaintPreset: NotRequired[str]


class ModelData(TypedDict):
    enabled: bool
    status: str
    iterationCount: int
    iterations: List[IterationData]


class SessionData(TypedDict):
    sessionId: str
    status: str
    version: int
    prompt: str
    createdAt: str
    updatedAt: str
    models: Dict[str, ModelData]


class GenerateHandler(Protocol):
    def __call__(
        self, config: ModelConfigDict, prompt: str, params: dict
    ) -> HandlerResult: ...


class IterateHandler(Protocol):
    def __call__(
        self,
        config: ModelConfigDict,
        source_image: Union[str, bytes],
        prompt: str,
        context: List[dict],
    ) -> HandlerResult: ...


class OutpaintHandler(Protocol):
    def __call__(
        self,
        config: ModelConfigDict,
        source_image: Union[str, bytes],
        preset: str,
        prompt: str,
    ) -> HandlerResult: ...
