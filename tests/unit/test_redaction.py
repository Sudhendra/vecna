from vecna.tools.redaction import redact_all, redact_pii, redact_secrets


def test_redact_secrets_masks_password_and_api_key():
    text = "password=supersecret api_key=sk-test_123456"
    result = redact_secrets(text)
    assert "supersecret" not in result
    assert "sk-test_123456" not in result
    assert "[REDACTED_SECRET]" in result


def test_redact_pii_masks_email_and_phone():
    text = "email john.doe@example.com phone 415-555-2671"
    result = redact_pii(text)
    assert "john.doe@example.com" not in result
    assert "415-555-2671" not in result
    assert "[REDACTED_PII]" in result


def test_redact_all_combines_secret_and_pii_redaction():
    text = "token=abc123 email jane@example.com"
    result = redact_all(text)
    assert "abc123" not in result
    assert "jane@example.com" not in result
    assert "[REDACTED_SECRET]" in result
    assert "[REDACTED_PII]" in result
