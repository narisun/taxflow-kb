"""Tests for SSN and DOB field validators."""
import pytest
from pydantic import ValidationError

from api.models.client import ClientCreate, ClientUpdate


class TestSSNValidation:
    def test_valid_ssn_with_dashes(self):
        c = ClientCreate(name="Test", primary_ssn="123-45-6789")
        assert c.primary_ssn == "123-45-6789"

    def test_valid_ssn_digits_only(self):
        c = ClientCreate(name="Test", primary_ssn="123456789")
        assert c.primary_ssn == "123456789"

    def test_none_ssn_allowed(self):
        c = ClientCreate(name="Test", primary_ssn=None)
        assert c.primary_ssn is None

    def test_blank_ssn_becomes_none(self):
        c = ClientCreate(name="Test", primary_ssn="   ")
        assert c.primary_ssn is None

    def test_invalid_ssn_too_short(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientCreate(name="Test", primary_ssn="12345")

    def test_invalid_ssn_letters(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientCreate(name="Test", primary_ssn="abc-de-fghi")

    def test_invalid_ssn_all_zeros(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientCreate(name="Test", primary_ssn="000-00-0000")

    def test_invalid_ssn_area_666(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientCreate(name="Test", primary_ssn="666-12-3456")

    def test_invalid_ssn_area_900_plus(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientCreate(name="Test", primary_ssn="900-12-3456")

    def test_spouse_ssn_validated_too(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientCreate(name="Test", spouse_ssn="bad")

    def test_update_model_validates_ssn(self):
        with pytest.raises(ValidationError, match="SSN"):
            ClientUpdate(primary_ssn="bad")


class TestDOBValidation:
    def test_valid_dob_iso(self):
        c = ClientCreate(name="Test", primary_dob="1990-06-15")
        assert c.primary_dob == "1990-06-15"

    def test_none_dob_allowed(self):
        c = ClientCreate(name="Test", primary_dob=None)
        assert c.primary_dob is None

    def test_invalid_dob_format(self):
        with pytest.raises(ValidationError, match="DOB"):
            ClientCreate(name="Test", primary_dob="06/15/1990")

    def test_invalid_dob_not_a_date(self):
        with pytest.raises(ValidationError, match="DOB"):
            ClientCreate(name="Test", primary_dob="not-a-date")
