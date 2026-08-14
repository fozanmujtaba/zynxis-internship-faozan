"""Tests for the secret scanner, including that it never echoes a live key."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auditor.secrets import scan_text, shannon_entropy


def rules(text: str) -> list[str]:
    return [f.rule for f in scan_text("f.py", text)]


def test_aws_key_detected():
    assert "SEC-AWS" in rules('key = "AKIAIOSFODNN7EXAMPLE"\n')


def test_private_key_block_detected():
    assert "SEC-PRIVKEY" in rules("-----BEGIN RSA PRIVATE KEY-----\n")


def test_db_url_with_password_detected():
    assert "SEC-DBURL" in rules('DSN = "postgresql://admin:hunter2@db.internal:5432/app"\n')


def test_placeholders_are_ignored():
    assert rules('api_key = "your_key_here"') == []
    assert rules('token = "${GITHUB_TOKEN}"') == []
    assert rules('password = "changeme"') == []


def test_secret_is_redacted_in_the_snippet():
    """A report that reproduces the credential defeats its own purpose."""
    secret = "AKIAIOSFODNN7EXAMPLE"
    findings = scan_text("f.py", f'key = "{secret}"')
    assert findings, "expected the AWS key to be detected"
    assert secret not in findings[0].snippet
    assert "*" in findings[0].snippet


def test_entropy_separates_random_from_english():
    assert shannon_entropy("aaaaaaaa") < 1.0
    assert shannon_entropy("kJ8$xQ2mZp7#Lw9v") > 3.0
