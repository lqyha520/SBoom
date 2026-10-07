"""从实际 FastAPI OpenAPI 模型生成三端共用 TypeScript 类型；--check 用于 CI。"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.main import app


def schema_type(schema: dict) -> str:
    if "$ref" in schema:
        return 'ApiSchemas[' + json.dumps(schema["$ref"].rsplit("/", 1)[-1]) + ']'
    if "enum" in schema:
        return " | ".join(json.dumps(value, ensure_ascii=False) for value in schema["enum"])
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    for field, operator in (("anyOf", " | "), ("oneOf", " | "), ("allOf", " & ")):
        if field in schema:
            return "(" + operator.join(schema_type(item) for item in schema[field]) + ")"
    kind = schema.get("type")
    if kind == "array":
        return "Array<" + schema_type(schema.get("items", {})) + ">"
    if kind == "object" or "properties" in schema:
        required = schema.get("required", [])
        fields = [json.dumps(name) + ("" if name in required else "?") + ": " + schema_type(value)
                  for name, value in sorted(schema.get("properties", {}).items())]
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            fields.append("[key: string]: " + schema_type(additional))
        elif additional is True or not fields:
            fields.append("[key: string]: unknown")
        return "{ " + "; ".join(fields) + " }"
    return {"integer": "number", "number": "number", "boolean": "boolean", "string": "string", "null": "null"}.get(str(kind), "unknown")


def generate() -> str:
    spec = app.openapi()
    lines = ["// 自动生成：python scripts/generate_api_types.py；请修改后端模型后重新生成。", "export interface ApiSchemas {"]
    for name, schema in sorted(spec.get("components", {}).get("schemas", {}).items()):
        lines.append("  " + json.dumps(name) + ": " + schema_type(schema))
    lines.append("}\n\nexport interface ApiOperations {")
    for path, operations in sorted(spec["paths"].items()):
        for method, value in sorted(operations.items()):
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            body = value.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            lines.append("  " + json.dumps(method.upper() + " " + path) + ": { body: " + schema_type(body) + " }")
    return "\n".join(lines + ["}", ""])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "shared" / "api-schema.ts"
    generated = generate()
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != generated:
            raise SystemExit("接口类型未同步，请运行 python scripts/generate_api_types.py")
    else:
        path.write_text(generated, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
