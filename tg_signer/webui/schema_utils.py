from typing import Any, Dict


def clean_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean JSON schema to be compatible with nicegui's json_editor.
    Removes 'format' keys which can cause rendering issues.
    """
    if not isinstance(schema, dict):
        return schema

    if "format" in schema:
        del schema["format"]

    for key, value in schema.items():
        if isinstance(value, dict):
            schema[key] = clean_schema(value)
        elif isinstance(value, list):
            schema[key] = [
                clean_schema(item) if isinstance(item, dict) else item for item in value
            ]

    return schema
