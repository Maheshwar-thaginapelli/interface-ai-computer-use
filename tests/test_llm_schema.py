from app.llm import _openai_strict_schema


def _assert_strict_objects(node: object) -> None:
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            assert node.get("additionalProperties") is False
            assert node.get("required") == list(properties)
        assert "default" not in node
        for value in node.values():
            _assert_strict_objects(value)
    elif isinstance(node, list):
        for value in node:
            _assert_strict_objects(value)


def test_agent_decision_openai_schema_is_strict() -> None:
    schema = _openai_strict_schema()
    _assert_strict_objects(schema)
