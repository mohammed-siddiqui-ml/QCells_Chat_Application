"""
Unit tests for EncryptionService (app/core/encryption.py)

Test coverage:
- TC-001: Encrypt and decrypt configuration dictionaries
- TC-002: Encryption determinism (multiple encryptions with same key)
- TC-003: Encrypt and decrypt individual strings
"""
import pytest
from app.core.encryption import encryption_service


class TestEncryptionService:
    """Test cases for EncryptionService"""

    def test_encrypt_decrypt_config(self):
        """
        TC-001: Encrypt and decrypt configuration dictionaries
        
        Verifies that:
        - Config dict can be encrypted to a string
        - Encrypted string is not plaintext
        - Decrypted config matches original exactly
        """
        # Test data
        original_config = {
            "url": "https://test.com",
            "token": "secret123",
            "nested": {
                "key": "value"
            }
        }
        
        # Encrypt
        encrypted = encryption_service.encrypt_config(original_config)
        
        # Verify encrypted is a string and not plaintext
        assert isinstance(encrypted, str)
        assert "secret123" not in encrypted
        assert "https://test.com" not in encrypted
        
        # Decrypt
        decrypted = encryption_service.decrypt_config(encrypted)
        
        # Verify match
        assert decrypted == original_config
        assert decrypted["url"] == "https://test.com"
        assert decrypted["token"] == "secret123"
        assert decrypted["nested"]["key"] == "value"

    def test_encryption_determinism(self):
        """
        TC-002: Encryption determinism
        
        Verifies that:
        - Same config encrypted twice produces different ciphertexts (Fernet uses random IV)
        - Both decrypt to the same original value
        """
        config = {"api_key": "test_key_123"}
        
        # Encrypt twice
        encrypted1 = encryption_service.encrypt_config(config)
        encrypted2 = encryption_service.encrypt_config(config)
        
        # Fernet uses random IV, so ciphertexts should differ
        assert encrypted1 != encrypted2
        
        # But both decrypt to the same value
        decrypted1 = encryption_service.decrypt_config(encrypted1)
        decrypted2 = encryption_service.decrypt_config(encrypted2)
        
        assert decrypted1 == decrypted2
        assert decrypted1 == config

    def test_encrypt_decrypt_string(self):
        """
        TC-003: Encrypt and decrypt individual strings
        
        Verifies:
        - String encryption/decryption works correctly
        - Encrypted string is not plaintext
        """
        original = "sensitive_password"
        
        # Encrypt
        encrypted = encryption_service.encrypt_string(original)
        
        # Verify not plaintext
        assert isinstance(encrypted, str)
        assert "sensitive_password" not in encrypted
        
        # Decrypt
        decrypted = encryption_service.decrypt_string(encrypted)
        
        # Verify match
        assert decrypted == original

    def test_empty_config_encryption(self):
        """
        Edge case: Encrypt empty configuration
        """
        empty_config = {}
        
        encrypted = encryption_service.encrypt_config(empty_config)
        decrypted = encryption_service.decrypt_config(encrypted)
        
        assert decrypted == empty_config

    def test_complex_nested_config(self):
        """
        Edge case: Encrypt deeply nested configuration
        """
        complex_config = {
            "level1": {
                "level2": {
                    "level3": {
                        "secret": "deep_secret",
                        "list": [1, 2, 3],
                        "boolean": True
                    }
                }
            }
        }
        
        encrypted = encryption_service.encrypt_config(complex_config)
        decrypted = encryption_service.decrypt_config(encrypted)
        
        assert decrypted == complex_config
        assert decrypted["level1"]["level2"]["level3"]["secret"] == "deep_secret"

    def test_encrypt_string_with_special_characters(self):
        """
        Edge case: Encrypt strings with special characters
        """
        special_string = "Test@123!#$%^&*()_+-=[]{}|;':\",./<>?"
        
        encrypted = encryption_service.encrypt_string(special_string)
        decrypted = encryption_service.decrypt_string(encrypted)
        
        assert decrypted == special_string

    def test_decrypt_invalid_string_raises_error(self):
        """
        Error case: Decrypting invalid encrypted string should raise exception
        """
        with pytest.raises(Exception):
            encryption_service.decrypt_string("invalid_encrypted_string")

    def test_decrypt_invalid_config_raises_error(self):
        """
        Error case: Decrypting invalid config string should raise exception
        """
        with pytest.raises(Exception):
            encryption_service.decrypt_config("invalid_encrypted_config")
