from __future__ import annotations

from copy import deepcopy

from agentshield.detectors import CompositePrivacyDetector
from agentshield.detectors.sensitive_data import regulation_candidate_mappings


def test_email_detection_in_unstructured_text() -> None:
    result = CompositePrivacyDetector().detect("Contact alice@example.test for support")
    assert result.contains_personal_data
    assert "email" in result.categories
    assert result.confidence >= 0.99


def test_phone_detection_in_unstructured_text() -> None:
    result = CompositePrivacyDetector().detect("Call +86 138-0013-8000 tomorrow")
    assert result.contains_personal_data
    assert "phone" in result.categories


def test_structured_personal_fields_cover_required_categories() -> None:
    payload = {
        "customer_name": "Alice",
        "postal_address": "1 Example Road",
        "date_of_birth": "1990-01-01",
        "location": "Shanghai",
        "account_id": "acct-42",
        "passport_number": "P1234567",
    }
    result = CompositePrivacyDetector().detect(payload)
    assert {"name", "address", "date_of_birth", "location", "account_identifier", "government_identifier"} <= set(result.categories)


def test_safe_public_content_is_not_classified_as_personal() -> None:
    result = CompositePrivacyDetector().detect({"customer_count": 42, "region": "EU"})
    assert not result.contains_personal_data
    assert not result.contains_sensitive_personal_data
    assert result.categories == ()


def test_sensitive_categories_and_regulation_candidates_are_separate() -> None:
    result = CompositePrivacyDetector().detect(
        {"diagnosis": "asthma", "bank_account": "DE00 TEST", "latitude": 31.2}
    )
    assert result.contains_sensitive_personal_data
    assert {"health", "financial", "precise_location"} <= set(result.sensitive_categories)
    mappings = regulation_candidate_mappings(result)
    assert mappings["gdpr_special_category_candidate"]
    assert mappings["pipl_sensitive_candidate"]


def test_confidence_and_payload_free_evidence() -> None:
    result = CompositePrivacyDetector().detect({"email": "alice@example.test"})
    assert result.evidence
    assert all(item.path and item.detector and item.reason for item in result.evidence)
    assert "alice@example.test" not in repr(result.evidence)
    assert len(result.content_sha256) == 64


def test_detector_does_not_mutate_raw_content() -> None:
    payload = {"records": [{"name": "Alice", "phone": "+49 30 123456"}]}
    original = deepcopy(payload)
    CompositePrivacyDetector().detect(payload)
    assert payload == original


def test_redacted_structured_value_is_not_still_personal() -> None:
    result = CompositePrivacyDetector().detect({"email": "[REDACTED]", "phone": "***"})
    assert not result.contains_personal_data

