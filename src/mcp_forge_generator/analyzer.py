from __future__ import annotations

import re
from typing import Any

from .spec_ir import APISpecIR, Operation, Parameter, RequestBody, ResponseSpec, SecurityScheme

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head")


def _pascal_case(value: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]", value)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _sanitize_operation_id(method: str, path: str) -> str:
    clean_path = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"{method.lower()}_{clean_path or 'root'}"


def _schema_ref_to_model(schema: dict[str, Any] | None) -> str | None:
    if not schema:
        return None
    ref = schema.get("$ref")
    if not ref:
        return None
    return ref.rsplit("/", 1)[-1]


def _derive_resource(path: str) -> str:
    for part in path.strip("/").split("/"):
        if part and not part.startswith("{"):
            return part
    return "default"


def _derive_dependencies(path: str) -> set[str]:
    deps: set[str] = set()
    for part in path.strip("/").split("/"):
        if part and not part.startswith("{"):
            deps.add(part)
    return deps or {"default"}


def _build_parameters(raw: list[dict[str, Any]]) -> list[Parameter]:
    out: list[Parameter] = []
    for p in raw:
        out.append(
            Parameter(
                name=p.get("name", "param"),
                location=p.get("in", "query"),
                required=bool(p.get("required", False)),
                schema=p.get("schema", {"type": "string"}),
                description=p.get("description", ""),
            )
        )
    return out


def _pick_json_schema(content: dict[str, Any]) -> dict[str, Any] | None:
    if "application/json" in content:
        json_obj = content["application/json"]
        if isinstance(json_obj, dict):
            schema = json_obj.get("schema")
            if isinstance(schema, dict):
                return schema
    for _, media_obj in content.items():
        if isinstance(media_obj, dict):
            schema = media_obj.get("schema")
            if isinstance(schema, dict):
                return schema
    return None


def build_ir(document: dict[str, Any]) -> APISpecIR:
    info = document.get("info", {}) if isinstance(document.get("info"), dict) else {}
    title = str(info.get("title", "Generated API"))
    version = str(info.get("version", "0.0.0"))

    servers = document.get("servers", []) if isinstance(document.get("servers"), list) else []
    base_url = ""
    if servers and isinstance(servers[0], dict):
        base_url = str(servers[0].get("url", ""))

    components = document.get("components", {}) if isinstance(document.get("components"), dict) else {}
    schemas = components.get("schemas", {}) if isinstance(components.get("schemas"), dict) else {}

    security_schemes_raw = (
        components.get("securitySchemes", {}) if isinstance(components.get("securitySchemes"), dict) else {}
    )
    security_schemes: list[SecurityScheme] = []
    for name, scheme in security_schemes_raw.items():
        if not isinstance(scheme, dict):
            continue
        security_schemes.append(
            SecurityScheme(
                name=name,
                type=str(scheme.get("type", "")),
                scheme=str(scheme.get("scheme")) if scheme.get("scheme") is not None else None,
                in_=str(scheme.get("in")) if scheme.get("in") is not None else None,
            )
        )

    operations: list[Operation] = []
    paths = document.get("paths", {}) if isinstance(document.get("paths"), dict) else {}

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        path_parameters = path_item.get("parameters", []) if isinstance(path_item.get("parameters"), list) else []

        for method in HTTP_METHODS:
            op_obj = path_item.get(method)
            if not isinstance(op_obj, dict):
                continue

            op_id = str(op_obj.get("operationId", _sanitize_operation_id(method, path)))
            summary = str(op_obj.get("summary", "")).strip()
            description = str(op_obj.get("description", "")).strip()
            raw_params = list(path_parameters)
            method_params = op_obj.get("parameters", [])
            if isinstance(method_params, list):
                raw_params.extend(method_params)

            params = _build_parameters([p for p in raw_params if isinstance(p, dict)])

            request_body: RequestBody | None = None
            op_request = op_obj.get("requestBody")
            if isinstance(op_request, dict):
                content = op_request.get("content", {})
                model_name: str | None = None
                if isinstance(content, dict):
                    schema = _pick_json_schema(content)
                    model_name = _schema_ref_to_model(schema)
                    if not model_name and isinstance(schema, dict):
                        model_name = f"{_pascal_case(op_id)}Request"
                        schemas[model_name] = schema
                request_body = RequestBody(
                    required=bool(op_request.get("required", False)),
                    model_name=model_name,
                    description=str(op_request.get("description", "")),
                )

            responses: list[ResponseSpec] = []
            raw_responses = op_obj.get("responses", {}) if isinstance(op_obj.get("responses"), dict) else {}
            for status_code, resp_obj in raw_responses.items():
                if not isinstance(resp_obj, dict):
                    continue
                content = resp_obj.get("content", {})
                model_name: str | None = None
                if isinstance(content, dict):
                    schema = _pick_json_schema(content)
                    model_name = _schema_ref_to_model(schema)
                    if not model_name and isinstance(schema, dict):
                        model_name = f"{_pascal_case(op_id)}Response{status_code}"
                        schemas[model_name] = schema
                responses.append(
                    ResponseSpec(
                        status_code=str(status_code),
                        model_name=model_name,
                        description=str(resp_obj.get("description", "")),
                    )
                )

            resource = _derive_resource(path)
            deps = _derive_dependencies(path)
            invalidates = {f"{resource}:*"} if method in {"post", "put", "patch", "delete"} else set()

            operations.append(
                Operation(
                    operation_id=op_id,
                    method=method.upper(),
                    path=path,
                    summary=summary,
                    description=description,
                    parameters=params,
                    request_body=request_body,
                    responses=responses,
                    tags=[str(tag) for tag in op_obj.get("tags", []) if isinstance(tag, str)],
                    resource=resource,
                    dependencies=deps,
                    cacheable=method == "get",
                    invalidates=invalidates,
                )
            )

    for op in operations:
        if not op.invalidates:
            continue
        recursive: set[str] = set(op.invalidates)
        for dep in op.dependencies:
            recursive.add(f"{dep}:*")
        op.invalidates = recursive

    return APISpecIR(
        title=title,
        version=version,
        base_url=base_url,
        schemas={k: v for k, v in schemas.items() if isinstance(v, dict)},
        operations=operations,
        security_schemes=security_schemes,
    )
