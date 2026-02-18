"""Tests for security hardening — encryption at rest and privacy tier filtering."""

import pytest
from cryptography.fernet import InvalidToken

from vecna.security.encryption import SubstrateEncryption
from vecna.security.privacy import PrivacyTier, PrivacyFilter


class TestSubstrateEncryption:
    """Tests for Fernet-based substrate encryption."""

    def test_encrypt_decrypt_roundtrip(self):
        enc = SubstrateEncryption.generate()
        plaintext = "sensitive user data"
        ciphertext = enc.encrypt(plaintext)
        assert ciphertext != plaintext
        decrypted = enc.decrypt(ciphertext)
        assert decrypted == plaintext

    def test_different_encryptions_differ(self):
        """Fernet uses random IV, so same plaintext produces different ciphertext."""
        enc = SubstrateEncryption.generate()
        ct1 = enc.encrypt("hello")
        ct2 = enc.encrypt("hello")
        assert ct1 != ct2

    def test_key_from_password(self):
        enc = SubstrateEncryption.from_password("my-secure-password", salt=b"test-salt-16bytes")
        plaintext = "secret"
        ct = enc.encrypt(plaintext)
        assert enc.decrypt(ct) == plaintext

    def test_same_password_same_salt_produces_same_key(self):
        """Deterministic key derivation from same password + salt."""
        enc1 = SubstrateEncryption.from_password("pass", salt=b"salt1234salt1234")
        enc2 = SubstrateEncryption.from_password("pass", salt=b"salt1234salt1234")
        ct = enc1.encrypt("test")
        assert enc2.decrypt(ct) == "test"

    def test_different_passwords_cannot_decrypt(self):
        """Decryption with a different password-derived key should fail."""
        enc1 = SubstrateEncryption.from_password("password-A", salt=b"salt1234salt1234")
        enc2 = SubstrateEncryption.from_password("password-B", salt=b"salt1234salt1234")
        ct = enc1.encrypt("confidential")
        with pytest.raises(InvalidToken):
            enc2.decrypt(ct)

    def test_unicode_roundtrip(self):
        enc = SubstrateEncryption.generate()
        plaintext = "Unicode: \u2603 \U0001f525 \u00e9\u00e8\u00ea"
        ct = enc.encrypt(plaintext)
        assert enc.decrypt(ct) == plaintext

    def test_empty_string_roundtrip(self):
        enc = SubstrateEncryption.generate()
        ct = enc.encrypt("")
        assert enc.decrypt(ct) == ""

    def test_long_string_roundtrip(self):
        enc = SubstrateEncryption.generate()
        plaintext = "x" * 100_000
        ct = enc.encrypt(plaintext)
        assert enc.decrypt(ct) == plaintext

    def test_ciphertext_is_base64_encoded_string(self):
        """Fernet ciphertext is a URL-safe base64-encoded string."""
        enc = SubstrateEncryption.generate()
        ct = enc.encrypt("hello")
        # Fernet tokens start with 'gAAAAA' (version byte 0x80 + timestamp)
        assert ct.startswith("gAAAAA")
        # Must be decodable back to the original
        assert enc.decrypt(ct) == "hello"

    def test_generate_produces_different_keys(self):
        enc1 = SubstrateEncryption.generate()
        enc2 = SubstrateEncryption.generate()
        ct = enc1.encrypt("test")
        # Different keys should not decrypt each other's ciphertext
        with pytest.raises(InvalidToken):
            enc2.decrypt(ct)


class TestSubstrateEncryptionErrors:
    """Error and edge-case tests (Amendment 10)."""

    def test_decrypt_invalid_ciphertext_raises_invalid_token(self):
        enc = SubstrateEncryption.generate()
        with pytest.raises(InvalidToken):
            enc.decrypt("not-valid-ciphertext")

    def test_decrypt_corrupted_ciphertext_raises_invalid_token(self):
        enc = SubstrateEncryption.generate()
        ct = enc.encrypt("hello")
        # Corrupt the ciphertext by flipping characters
        corrupted = ct[:10] + "AAAA" + ct[14:]
        with pytest.raises(InvalidToken):
            enc.decrypt(corrupted)

    def test_decrypt_empty_ciphertext_raises_invalid_token(self):
        enc = SubstrateEncryption.generate()
        with pytest.raises(InvalidToken):
            enc.decrypt("")

    def test_from_password_different_salt_produces_different_key(self):
        enc1 = SubstrateEncryption.from_password("same-pass", salt=b"salt-AAAAAAAAAA16")
        enc2 = SubstrateEncryption.from_password("same-pass", salt=b"salt-BBBBBBBBBB16")
        ct = enc1.encrypt("secret")
        with pytest.raises(InvalidToken):
            enc2.decrypt(ct)


class TestPrivacyTiers:
    """Tests for PrivacyTier enum behavior."""

    def test_local_only_not_shared(self):
        assert not PrivacyTier.LOCAL_ONLY.can_send_to_cloud()

    def test_processable_can_be_processed(self):
        assert PrivacyTier.PROCESSABLE.can_send_to_cloud()

    def test_shareable_can_be_shared(self):
        assert PrivacyTier.SHAREABLE.can_send_to_cloud()

    def test_tier_values(self):
        assert PrivacyTier.LOCAL_ONLY.value == "local_only"
        assert PrivacyTier.PROCESSABLE.value == "processable"
        assert PrivacyTier.SHAREABLE.value == "shareable"

    def test_tier_from_value(self):
        assert PrivacyTier("local_only") is PrivacyTier.LOCAL_ONLY
        assert PrivacyTier("processable") is PrivacyTier.PROCESSABLE
        assert PrivacyTier("shareable") is PrivacyTier.SHAREABLE


class TestPrivacyFilter:
    """Tests for PrivacyFilter cloud filtering."""

    def test_filter_for_cloud_removes_local_only(self):
        pf = PrivacyFilter()
        facts = [
            {"content": "User's SSN is 123-45-6789", "privacy_tier": "local_only"},
            {"content": "Python is interpreted", "privacy_tier": "shareable"},
        ]
        filtered = pf.filter_for_cloud(facts)
        assert len(filtered) == 1
        assert filtered[0]["content"] == "Python is interpreted"
        assert "SSN" not in filtered[0]["content"]

    def test_filter_for_cloud_keeps_processable(self):
        pf = PrivacyFilter()
        facts = [
            {"content": "User prefers dark mode", "privacy_tier": "processable"},
        ]
        filtered = pf.filter_for_cloud(facts)
        assert len(filtered) == 1
        assert filtered[0]["content"] == "User prefers dark mode"

    def test_filter_for_cloud_keeps_shareable(self):
        pf = PrivacyFilter()
        facts = [
            {"content": "2+2=4", "privacy_tier": "shareable"},
        ]
        filtered = pf.filter_for_cloud(facts)
        assert len(filtered) == 1

    def test_filter_defaults_to_shareable_for_missing_tier(self):
        pf = PrivacyFilter()
        facts = [{"content": "no tier specified"}]
        filtered = pf.filter_for_cloud(facts)
        assert len(filtered) == 1

    def test_filter_empty_list(self):
        pf = PrivacyFilter()
        filtered = pf.filter_for_cloud([])
        assert filtered == []

    def test_filter_all_local_only(self):
        pf = PrivacyFilter()
        facts = [
            {"content": "secret1", "privacy_tier": "local_only"},
            {"content": "secret2", "privacy_tier": "local_only"},
        ]
        filtered = pf.filter_for_cloud(facts)
        assert filtered == []

    def test_filter_preserves_original_list(self):
        """Filtering should not mutate the input list."""
        pf = PrivacyFilter()
        facts = [
            {"content": "local", "privacy_tier": "local_only"},
            {"content": "cloud", "privacy_tier": "shareable"},
        ]
        original_length = len(facts)
        pf.filter_for_cloud(facts)
        assert len(facts) == original_length

    def test_filter_preserves_extra_fields(self):
        """Items passing the filter should retain all their fields."""
        pf = PrivacyFilter()
        facts = [
            {
                "content": "data",
                "privacy_tier": "shareable",
                "source": "test",
                "confidence": 0.9,
            },
        ]
        filtered = pf.filter_for_cloud(facts)
        assert len(filtered) == 1
        assert filtered[0]["source"] == "test"
        assert filtered[0]["confidence"] == 0.9


class TestPrivacyFilterEdgeCases:
    """Edge cases for privacy filtering (Amendment 10)."""

    def test_filter_with_unknown_tier_value(self):
        """Items with unrecognized privacy_tier values should pass through (not local_only)."""
        pf = PrivacyFilter()
        facts = [{"content": "unknown tier", "privacy_tier": "custom_tier"}]
        filtered = pf.filter_for_cloud(facts)
        assert len(filtered) == 1

    def test_filter_with_none_tier(self):
        """None privacy_tier should be treated as shareable (default)."""
        pf = PrivacyFilter()
        facts = [{"content": "none tier", "privacy_tier": None}]
        filtered = pf.filter_for_cloud(facts)
        assert len(filtered) == 1

    def test_filter_mixed_tiers(self):
        """Verify correct filtering with all three tiers present."""
        pf = PrivacyFilter()
        facts = [
            {"content": "local", "privacy_tier": "local_only"},
            {"content": "process", "privacy_tier": "processable"},
            {"content": "share", "privacy_tier": "shareable"},
        ]
        filtered = pf.filter_for_cloud(facts)
        assert len(filtered) == 2
        contents = [f["content"] for f in filtered]
        assert "process" in contents
        assert "share" in contents
        assert "local" not in contents
