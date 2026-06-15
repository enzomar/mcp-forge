from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Parameter:
    name: str
    location: str
    required: bool
    schema: dict[str, Any]
    description: str = ""


@dataclass(slots=True)
class RequestBody:
    required: bool
    model_name: str | None
    description: str = ""


@dataclass(slots=True)
class ResponseSpec:
    status_code: str
    model_name: str | None
    description: str = ""


@dataclass(slots=True)
class Operation:
    operation_id: str
    method: str
    path: str
    summary: str
    description: str
    parameters: list[Parameter] = field(default_factory=list)
    request_body: RequestBody | None = None
    responses: list[ResponseSpec] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    resource: str = "default"
    dependencies: set[str] = field(default_factory=set)
    cacheable: bool = False
    invalidates: set[str] = field(default_factory=set)


@dataclass(slots=True)
class SecurityScheme:
    name: str
    type: str
    scheme: str | None = None
    in_: str | None = None


@dataclass(slots=True)
class APISpecIR:
    title: str
    version: str
    base_url: str
    schemas: dict[str, dict[str, Any]]
    operations: list[Operation]
    security_schemes: list[SecurityScheme]
