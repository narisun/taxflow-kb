"""Tests for PII encryption service."""
import pytest
from datetime import date
from cryptography.fernet import Fernet


@pytest.fixture
def encryptor():
    from api.services.pii.encryptor import PIIEncryptor
    key = Fernet.generate_key()
    return PIIEncryptor(key)


class TestEncryptDecrypt:
    def test_roundtrip(self, encryptor):
        plaintext = "123456789"
        encrypted = encryptor.encrypt(plaintext)
        assert isinstance(encrypted, bytes)
        assert encrypted != plaintext.encode()
        assert encryptor.decrypt(encrypted) == plaintext

    def test_different_encryptions_differ(self, encryptor):
        a = encryptor.encrypt("test")
        b = encryptor.encrypt("test")
        assert a != b

    def test_empty_string(self, encryptor):
        encrypted = encryptor.encrypt("")
        assert encryptor.decrypt(encrypted) == ""

    def test_json_roundtrip(self, encryptor):
        data = {"box1_wages": "85000", "employer_name": "ACME"}
        encrypted = encryptor.encrypt_json(data)
        assert isinstance(encrypted, bytes)
        result = encryptor.decrypt_json(encrypted)
        assert result == data

    def test_json_empty_dict(self, encryptor):
        encrypted = encryptor.encrypt_json({})
        assert encryptor.decrypt_json(encrypted) == {}

    def test_wrong_key_fails(self):
        from api.services.pii.encryptor import PIIEncryptor
        key1 = Fernet.generate_key()
        key2 = Fernet.generate_key()
        enc1 = PIIEncryptor(key1)
        enc2 = PIIEncryptor(key2)
        encrypted = enc1.encrypt("secret")
        with pytest.raises(Exception):
            enc2.decrypt(encrypted)


class TestMasking:
    def test_mask_ssn(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_ssn("123456789") == "***-**-6789"

    def test_mask_ssn_short(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_ssn("1234") == "***-**-1234"

    def test_mask_ssn_none(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_ssn(None) == ""

    def test_mask_dob(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_dob(date(1985, 3, 15)) == "**/**/1985"

    def test_mask_dob_none(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_dob(None) == ""

    def test_mask_address(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_address("123 Main St") == "123 M***"

    def test_mask_address_short(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_address("A") == "A***"

    def test_mask_address_none(self):
        from api.services.pii.encryptor import PIIEncryptor
        assert PIIEncryptor.mask_address(None) == ""


class TestGetEncryptor:
    def test_dev_key_used_when_no_env(self):
        from api.services.pii.encryptor import get_pii_encryptor
        enc = get_pii_encryptor()
        encrypted = enc.encrypt("test")
        assert enc.decrypt(encrypted) == "test"
