from __future__ import annotations

from pathlib import Path

from mcp_forge_generator.generator import generate_project


def test_generate_project_creates_required_files(tmp_path: Path) -> None:
    spec = tmp_path / "petstore.yaml"
    spec.write_text(
        """
openapi: 3.0.3
info:
  title: Pet API
  version: 1.0.0
servers:
  - url: https://example.com
paths:
  /users:
    get:
      operationId: listUsers
      summary: List users
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema:
                type: object
                properties:
                  items:
                    type: array
                    items:
                      type: string
  /users/{id}:
    get:
      operationId: getUser
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
""".strip(),
        encoding="utf-8",
    )

    out = tmp_path / "generated_server"
    generate_project(spec, out)

    required = {
        "main.py",
        "config_layer",
        "cache_layer",
        "auth_layer",
        "models_layer",
        "services_layer",
        "tools.py",
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
        "README.md",
        ".env.example",
    }

    assert required.issubset({p.name for p in out.iterdir()})
