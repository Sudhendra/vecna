"""Integration tests for substrate encryption at rest."""

import asyncio
import base64
import json
import os
import tempfile
from typing import Any, Dict

import pytest
from cryptography.fernet import InvalidToken

from vecna.core.hive_state import HiveState
from vecna.core.types import Fact, Belief
from vecna.security.encryption import (
    SubstrateEncryption,
    derive_key_from_password,
)
from vecna.core.encrypted_state_store import EncryptedStateStore


class TestKeyDerivation:
    """Tests for encryption key derivation."""

    def test_derive_key_produces_valid_fernet_key(self):
        """derive_key_from_password produces a valid 44-byte base64-encoded Fernet key."""
        key = derive_key_from_password("test-password", salt=b"fixed-salt-16b!!")
        # Fernet keys are 44 bytes of URL-safe base64 (encoding 32 raw bytes)
        decoded = base64.urlsafe_b64decode(key)
        assert len(decoded) == 32

    def test_same_password_same_key(self):
        """Same password and salt produce the same key."""
        salt = b"deterministic!!!"
        key1 = derive_key_from_password("mypassword", salt=salt)
        key2 = derive_key_from_password("mypassword", salt=salt)
        assert key1 == key2

    def test_different_password_different_key(self):
        """Different passwords produce different keys."""
        salt = b"same-salt-16bits"
        key1 = derive_key_from_password("password1", salt=salt)
        key2 = derive_key_from_password("password2", salt=salt)
        assert key1 != key2

    def test_different_salt_different_key(self):
        """Different salts produce different keys even with same password."""
        key1 = derive_key_from_password("password", salt=b"salt-AAAAAAAAAA16")
        key2 = derive_key_from_password("password", salt=b"salt-BBBBBBBBBB16")
        assert key1 != key2

    def test_default_salt_is_random(self):
        """When no salt is provided, a random one is generated (keys differ each call)."""
        key1 = derive_key_from_password("password")
        key2 = derive_key_from_password("password")
        assert key1 != key2


class TestSubstrateEncryptionJson:
    """Tests for SubstrateEncryption JSON operations."""

    def test_encrypt_decrypt_json_roundtrip(self):
        """encrypt_json and decrypt_json are inverse operations."""
        enc = SubstrateEncryption.from_password("test-secret", salt=b"test-salt-16byte")
        data: Dict[str, Any] = {"facts": [{"content": "test", "confidence": 0.9}]}
        encrypted = enc.encrypt_json(data)
        assert encrypted != json.dumps(data).encode()
        decrypted = enc.decrypt_json(encrypted)
        assert decrypted == data

    def test_encrypted_data_not_readable(self):
        """Encrypted output does not contain plaintext."""
        enc = SubstrateEncryption.from_password("secret", salt=b"salt-for-testing")
        data = {"sensitive": "this should be hidden"}
        encrypted = enc.encrypt_json(data)
        assert b"this should be hidden" not in encrypted

    def test_wrong_password_fails_decrypt(self):
        """Decryption with wrong password raises InvalidToken."""
        enc1 = SubstrateEncryption.from_password("correct", salt=b"salt1234salt1234")
        enc2 = SubstrateEncryption.from_password("wrong", salt=b"salt1234salt1234")
        data = {"key": "value"}
        encrypted = enc1.encrypt_json(data)
        with pytest.raises(InvalidToken):
            enc2.decrypt_json(encrypted)

    def test_encrypt_json_handles_nested_structures(self):
        """encrypt_json handles nested dicts, lists, numbers, booleans, nulls."""
        enc = SubstrateEncryption.from_password("nest-test", salt=b"salt-for-nesting")
        data: Dict[str, Any] = {
            "string": "hello",
            "number": 42,
            "float": 3.14,
            "bool": True,
            "null": None,
            "list": [1, 2, 3],
            "nested": {"a": {"b": "c"}},
        }
        encrypted = enc.encrypt_json(data)
        decrypted = enc.decrypt_json(encrypted)
        assert decrypted == data

    def test_decrypt_json_corrupted_data_raises_error(self):
        """Decrypting corrupted bytes raises InvalidToken."""
        enc = SubstrateEncryption.from_password("test", salt=b"salt-16-bytes!!!")
        with pytest.raises(InvalidToken):
            enc.decrypt_json(b"this is not encrypted data at all")


class TestEncryptedStateStore:
    """Tests for encrypted file-based state persistence."""

    def test_save_and_load_state(self):
        """State survives save/load cycle with encryption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.enc")
            store = EncryptedStateStore(
                filepath=filepath,
                password="test-pass",
            )
            state = HiveState()
            state.add_fact(
                Fact(
                    content="Encrypted fact",
                    confidence=0.95,
                    source_model="test",
                )
            )
            state.add_belief(
                Belief(
                    content="Encrypted belief",
                    confidence=0.8,
                )
            )
            store.save(state)
            assert os.path.exists(filepath)

            loaded = store.load()
            assert len(loaded.facts) == 1
            assert loaded.facts[0].content == "Encrypted fact"
            assert loaded.facts[0].confidence == 0.95
            assert len(loaded.beliefs) == 1
            assert loaded.beliefs[0].content == "Encrypted belief"

    def test_encrypted_file_not_plaintext(self):
        """Saved file does not contain plaintext state data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.enc")
            store = EncryptedStateStore(
                filepath=filepath,
                password="secret-key",
            )
            state = HiveState()
            state.add_fact(
                Fact(
                    content="Super secret fact",
                    confidence=0.99,
                    source_model="test",
                )
            )
            store.save(state)
            with open(filepath, "rb") as f:
                raw = f.read()
            assert b"Super secret fact" not in raw

    def test_load_nonexistent_returns_empty_state(self):
        """Loading from nonexistent file returns fresh HiveState."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EncryptedStateStore(
                filepath=os.path.join(tmpdir, "nonexistent_state.enc"),
                password="test",
            )
            state = store.load()
            # Amendment 9: Assert specific empty-state fields, not just isinstance
            assert state.facts == []
            assert state.beliefs == []
            assert state.goals == []
            assert state.hypotheses == []
            assert state.version == 0

    def test_save_overwrites_existing(self):
        """Second save overwrites the first."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.enc")
            store = EncryptedStateStore(
                filepath=filepath,
                password="test-pass",
            )
            state1 = HiveState()
            state1.add_fact(
                Fact(
                    content="First version",
                    confidence=0.9,
                    source_model="test",
                )
            )
            store.save(state1)

            state2 = HiveState()
            state2.add_fact(
                Fact(
                    content="Second version",
                    confidence=0.95,
                    source_model="test",
                )
            )
            store.save(state2)

            loaded = store.load()
            assert len(loaded.facts) == 1
            assert loaded.facts[0].content == "Second version"
            assert loaded.facts[0].confidence == 0.95

    def test_save_load_preserves_version(self):
        """State version is preserved through encryption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.enc")
            store = EncryptedStateStore(
                filepath=filepath,
                password="test",
            )
            state = HiveState()
            state.add_fact(
                Fact(
                    content="Version test",
                    confidence=0.9,
                    source_model="test",
                )
            )
            original_version = state.version
            store.save(state)
            loaded = store.load()
            assert loaded.version == original_version


class TestEncryptedStateStoreErrors:
    """Error path tests for EncryptedStateStore (Amendment 10: 4+ error tests)."""

    def test_decrypt_with_wrong_key(self):
        """Encrypt with password A, load with password B raises clear error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.enc")
            store_a = EncryptedStateStore(filepath=filepath, password="password-A")
            store_b = EncryptedStateStore(filepath=filepath, password="password-B")

            state = HiveState()
            state.add_fact(Fact(content="secret data", confidence=0.9, source_model="test"))
            store_a.save(state)

            with pytest.raises(InvalidToken):
                store_b.load()

    def test_load_corrupted_file(self):
        """Loading a file with garbage bytes raises InvalidToken, not crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.enc")
            with open(filepath, "wb") as f:
                f.write(b"this is garbage data, not encrypted at all!!!")

            store = EncryptedStateStore(filepath=filepath, password="test")
            with pytest.raises(InvalidToken):
                store.load()

    def test_key_rotation_preserves_data(self):
        """Rotate encryption key: load with old key, save with new key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.enc")
            old_store = EncryptedStateStore(filepath=filepath, password="old-password")

            state = HiveState()
            state.add_fact(Fact(content="Important data", confidence=0.95, source_model="test"))
            old_store.save(state)

            # Load with old key
            loaded = old_store.load()
            assert loaded.facts[0].content == "Important data"

            # Save with new key (rotation)
            new_filepath = os.path.join(tmpdir, "state_new.enc")
            new_store = EncryptedStateStore(filepath=new_filepath, password="new-password")
            new_store.save(loaded)

            # Verify new key works
            reloaded = new_store.load()
            assert reloaded.facts[0].content == "Important data"
            assert reloaded.facts[0].confidence == 0.95

            # Verify old key cannot read new file
            old_store_on_new = EncryptedStateStore(filepath=new_filepath, password="old-password")
            with pytest.raises(InvalidToken):
                old_store_on_new.load()

    def test_concurrent_save_load(self):
        """Concurrent save and load operations don't corrupt data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.enc")
            store = EncryptedStateStore(filepath=filepath, password="concurrent-test")

            # Initial save
            state = HiveState()
            state.add_fact(Fact(content="Concurrent fact", confidence=0.9, source_model="test"))
            store.save(state)

            async def save_load_cycle(iteration: int) -> HiveState:
                """Save a unique state, then load it back."""
                cycle_store = EncryptedStateStore(
                    filepath=os.path.join(tmpdir, f"state_{iteration}.enc"),
                    password="concurrent-test",
                )
                cycle_state = HiveState()
                cycle_state.add_fact(
                    Fact(
                        content=f"Fact from iteration {iteration}",
                        confidence=0.9,
                        source_model="test",
                    )
                )
                cycle_store.save(cycle_state)
                return cycle_store.load()

            async def run_concurrent() -> None:
                tasks = [save_load_cycle(i) for i in range(50)]
                results = await asyncio.gather(*tasks)
                # Assert no data loss: each result has exactly one fact with correct content
                for i, result in enumerate(results):
                    assert len(result.facts) == 1
                    assert result.facts[0].content == f"Fact from iteration {i}"

            asyncio.run(run_concurrent())

    def test_save_creates_parent_directories(self):
        """Save creates parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "nested", "deep", "state.enc")
            store = EncryptedStateStore(filepath=filepath, password="test")
            state = HiveState()
            store.save(state)
            assert os.path.exists(filepath)

    def test_load_empty_file_raises_error(self):
        """Loading a zero-byte file raises InvalidToken."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.enc")
            with open(filepath, "wb") as f:
                f.write(b"")

            store = EncryptedStateStore(filepath=filepath, password="test")
            with pytest.raises(InvalidToken):
                store.load()
