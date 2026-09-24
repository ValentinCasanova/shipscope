import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from accounts.models import GoogleCredential, User

from .factories import GoogleCredentialFactory, UserFactory


def test_django_uses_the_custom_user_model():
    assert get_user_model() is User


# Each statement that should fail runs in its own atomic block, so the failure rolls back
# only that block, not the whole test's transaction.


@pytest.mark.django_db
def test_a_user_has_at_most_one_google_credential():
    credential = GoogleCredentialFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        GoogleCredentialFactory(user=credential.user)


@pytest.mark.django_db
def test_a_google_account_is_linked_to_at_most_one_user():
    credential = GoogleCredentialFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        GoogleCredentialFactory(google_sub=credential.google_sub)


@pytest.mark.django_db
def test_a_google_credential_needs_a_google_account_id():
    with pytest.raises(IntegrityError), transaction.atomic():
        GoogleCredentialFactory(google_sub="")


@pytest.mark.django_db
def test_validation_reports_a_linked_google_account_on_its_field():
    credential = GoogleCredentialFactory()
    duplicate = GoogleCredential(user=UserFactory(), google_sub=credential.google_sub)

    with pytest.raises(ValidationError) as caught:
        duplicate.full_clean()

    assert caught.value.message_dict == {
        "google_sub": ["This Google account is already linked to another user."]
    }


@pytest.mark.django_db
def test_deleting_a_user_deletes_their_google_credential():
    credential = GoogleCredentialFactory()

    credential.user.delete()

    assert not GoogleCredential.objects.filter(pk=credential.pk).exists()
