"""The admin's pages work for every registered model, including models added later."""

import pytest
from django.apps import apps
from django.contrib import admin
from django.urls import reverse

REGISTERED_MODELS = [model for model in apps.get_models() if admin.site.is_registered(model)]


@pytest.mark.parametrize("model", REGISTERED_MODELS, ids=lambda model: model._meta.label)
@pytest.mark.parametrize(
    ("page", "query"),
    [
        pytest.param("changelist", "", id="list"),
        # Django checks search_fields only when a search runs.
        pytest.param("changelist", "?q=x", id="search"),
        pytest.param("add", "", id="add"),
    ],
)
def test_page_renders_for_a_superuser(superuser_client, model, page, query):
    url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_{page}")

    response = superuser_client.get(url + query)

    assert response.status_code == 200
