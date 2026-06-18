"""
Encryption utilities for sensitive data using Fernet symmetric encryption.

This module provides:
- Fernet-based encryption/decryption for sensitive configuration data
- Key derivation from application SECRET_KEY
- JSON serialization support for complex config objects
"""
import json
import base64
from typing import Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings
from app.core.logging import logger


class EncryptionService:
    """
    Service for encrypting and decrypting sensitive configuration data.

    Uses Fernet symmetric encryption with a key derived from the application SECRET_KEY.
    """

    def __init__(self):
        """Initialize encryption service with derived Fernet key."""
        # Derive a 32-byte key from SECRET_KEY using PBKDF2HMAC
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'genai_kb_salt',  # Static salt for deterministic key derivation
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(settings.SECRET_KEY.encode()))
        self.fernet = Fernet(key)
        logger.debug("Encryption service initialized")
    
    def encrypt_config(self, config: Dict[str, Any]) -> str:
        """
        Encrypt a configuration dictionary.
        
        Args:
            config: Dictionary containing configuration data
            
        Returns:
            Encrypted string (base64 encoded)
            
        Raises:
            ValueError: If config cannot be serialized to JSON
        """
        try:
            # Convert dict to JSON string
            config_json = json.dumps(config)
            
            # Encrypt the JSON string
            encrypted_bytes = self.fernet.encrypt(config_json.encode())
            
            # Return as string
            encrypted_str = encrypted_bytes.decode()
            
            logger.debug(f"Config encrypted successfully (length: {len(encrypted_str)})")
            return encrypted_str
            
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to encrypt config: {e}")
            raise ValueError(f"Config encryption failed: {e}")
    
    def decrypt_config(self, encrypted_config: str) -> Dict[str, Any]:
        """
        Decrypt an encrypted configuration string.
        
        Args:
            encrypted_config: Encrypted configuration string
            
        Returns:
            Decrypted configuration dictionary
            
        Raises:
            ValueError: If decryption or JSON parsing fails
        """
        try:
            # Decrypt the string
            decrypted_bytes = self.fernet.decrypt(encrypted_config.encode())
            
            # Parse JSON
            config = json.loads(decrypted_bytes.decode())
            
            logger.debug("Config decrypted successfully")
            return config
            
        except Exception as e:
            logger.error(f"Failed to decrypt config: {e}")
            raise ValueError(f"Config decryption failed: {e}")
    
    def encrypt_string(self, plaintext: str) -> str:
        """
        Encrypt a plain string.
        
        Args:
            plaintext: String to encrypt
            
        Returns:
            Encrypted string (base64 encoded)
        """
        encrypted_bytes = self.fernet.encrypt(plaintext.encode())
        return encrypted_bytes.decode()
    
    def decrypt_string(self, ciphertext: str) -> str:
        """
        Decrypt an encrypted string.
        
        Args:
            ciphertext: Encrypted string to decrypt
            
        Returns:
            Decrypted plain string
        """
        decrypted_bytes = self.fernet.decrypt(ciphertext.encode())
        return decrypted_bytes.decode()


# Global encryption service instance
encryption_service = EncryptionService()
