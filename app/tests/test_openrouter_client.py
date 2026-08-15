"""
Tests for the shared OpenRouter client (openrouter_client.py). Covers
the "HTTP 200 but not actually a completion" cases that previously
caused a raw, unhandled KeyError to escape to callers — see
brandos.weekly_review / brandos.project_suggester for how those get
turned into their own domain errors.

Run with:  python -m pytest app/tests/test_openrouter_client.py -v
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from brandos.openrouter_client import call_openrouter_json


def _fake_response(json_body: dict, status_ok: bool = True):
    resp = MagicMock()
    resp.json.return_value = json_body
    resp.raise_for_status.return_value = None if status_ok else (_ for _ in ()).throw(Exception("http error"))
    return resp


class TestCallOpenrouterJson:
    def test_happy_path_returns_parsed_json(self):
        fake_json = json.dumps({"summary": "all good"})
        resp = _fake_response({"choices": [{"message": {"content": fake_json}}]})
        with patch("brandos.openrouter_client.requests.post", return_value=resp):
            result = call_openrouter_json(
                system_prompt="sys", user_prompt="usr", api_key="key", model="model"
            )
        assert result == {"summary": "all good"}

    def test_error_payload_raises_value_error_not_keyerror(self):
        # OpenRouter can return HTTP 200 with an {"error": ...} body
        # (rate limit, model unavailable) instead of raising at the
        # HTTP level. This must not surface as a raw KeyError.
        resp = _fake_response({"error": {"message": "Rate limit exceeded, try again later"}})
        with patch("brandos.openrouter_client.requests.post", return_value=resp):
            with pytest.raises(ValueError, match="Rate limit exceeded"):
                call_openrouter_json(
                    system_prompt="sys", user_prompt="usr", api_key="key", model="model"
                )

    def test_error_payload_as_plain_string_raises_value_error(self):
        resp = _fake_response({"error": "something went wrong"})
        with patch("brandos.openrouter_client.requests.post", return_value=resp):
            with pytest.raises(ValueError, match="something went wrong"):
                call_openrouter_json(
                    system_prompt="sys", user_prompt="usr", api_key="key", model="model"
                )

    def test_missing_choices_raises_value_error_not_keyerror(self):
        resp = _fake_response({"some": "unexpected shape"})
        with patch("brandos.openrouter_client.requests.post", return_value=resp):
            with pytest.raises(ValueError, match="no choices"):
                call_openrouter_json(
                    system_prompt="sys", user_prompt="usr", api_key="key", model="model"
                )

    def test_empty_choices_list_raises_value_error(self):
        resp = _fake_response({"choices": []})
        with patch("brandos.openrouter_client.requests.post", return_value=resp):
            with pytest.raises(ValueError, match="no choices"):
                call_openrouter_json(
                    system_prompt="sys", user_prompt="usr", api_key="key", model="model"
                )

    def test_default_timeout_is_30_seconds(self):
        fake_json = json.dumps({"a": 1})
        resp = _fake_response({"choices": [{"message": {"content": fake_json}}]})
        with patch("brandos.openrouter_client.requests.post", return_value=resp) as mock_post:
            call_openrouter_json(system_prompt="sys", user_prompt="usr", api_key="key", model="model")
        assert mock_post.call_args.kwargs["timeout"] == 30
