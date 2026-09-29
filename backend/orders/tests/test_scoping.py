"""Order data reaches only its owner: for_user(), IsOwner, and OwnedByUserMixin.

No endpoint serves order data yet, so test-only viewsets (urls.py in this folder) stand
in for the app's, one per model. The last tests keep every view scoped: they fail for
any view that doesn't use the mixin, unless it's listed as serving no order data.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import models
from django.http import HttpResponse
from django.urls import URLResolver, get_resolver, include, path
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from accounts.tests.factories import UserFactory
from accounts.views import SessionView, google_callback, google_login
from core.views import health
from orders.models import AnomalyFlag, Order, OwnedQuerySet, Rate, Shipment
from orders.permissions import IsOwner, OwnedByUserMixin

from .factories import AnomalyFlagFactory, OrderFactory, RateFactory, ShipmentFactory

pytestmark = pytest.mark.django_db


@dataclass(frozen=True)
class Kind:
    """One of the order models, as these tests create and request it."""

    model: type[models.Model]
    factory: Callable[..., models.Model]
    # The factory argument that sets the owner.
    owner: str
    # The model's viewset in urls.py.
    route: str

    def create(self, user: Any) -> models.Model:
        return self.factory(**{self.owner: user})


@pytest.fixture(
    params=[
        Kind(Order, OrderFactory, "user", "orders"),
        Kind(Shipment, ShipmentFactory, "order__user", "shipments"),
        Kind(Rate, RateFactory, "shipment__order__user", "rates"),
        Kind(AnomalyFlag, AnomalyFlagFactory, "order__user", "anomaly-flags"),
    ],
    ids=lambda kind: kind.model.__name__,
)
def kind(request) -> Kind:
    return request.param


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def other_user():
    return UserFactory()


@pytest.fixture
def api(client, settings):
    """A test client for the test-only viewsets in urls.py."""
    settings.ROOT_URLCONF = "orders.tests.urls"
    return client


def as_request(user: Any) -> SimpleNamespace:
    """All that IsOwner reads of a request."""
    return SimpleNamespace(user=user)


# The querysets


@pytest.mark.parametrize(
    "model", list(apps.get_app_config("orders").get_models()), ids=lambda model: model.__name__
)
def test_every_order_model_leads_to_exactly_one_owner(model):
    # Each step of OWNER_PATH is a foreign key that can't be empty, and the last one
    # points to the user model, so every row has exactly one owner.
    assert isinstance(model._default_manager.all(), OwnedQuerySet)
    target = model
    for name in model.OWNER_PATH.split("__"):
        field = target._meta.get_field(name)
        assert isinstance(field, models.ForeignKey), f"{target.__name__}.{name}"
        assert not field.null, f"{target.__name__}.{name}"
        target = field.related_model
    assert target is get_user_model()


def test_for_user_keeps_only_the_users_own(kind, user, other_user):
    own = [kind.create(user), kind.create(user)]
    kind.create(other_user)

    assert set(kind.model.objects.for_user(user)) == set(own)


def test_for_user_finds_nothing_for_a_signed_out_visitor(kind, user):
    kind.create(user)

    assert not kind.model.objects.for_user(AnonymousUser()).exists()


# IsOwner


def test_is_owner_allows_only_the_owner(kind, user, other_user):
    # Loaded again, so IsOwner reads each step of the path from the database, as in a view.
    obj = kind.model.objects.get(pk=kind.create(user).pk)

    assert IsOwner().has_object_permission(as_request(user), None, obj)
    assert not IsOwner().has_object_permission(as_request(other_user), None, obj)


def test_is_owner_refuses_a_signed_out_visitor():
    assert not IsOwner().has_permission(as_request(AnonymousUser()), None)


# OwnedByUserMixin, through the test-only viewsets


def test_a_list_holds_only_the_users_own(api, kind, user, other_user):
    own = [kind.create(user), kind.create(user)]
    kind.create(other_user)
    api.force_login(user)

    response = api.get(f"/api/{kind.route}/")

    assert response.status_code == 200
    assert sorted(item["id"] for item in response.json()) == sorted(obj.pk for obj in own)


def test_a_user_reaches_their_own_object(api, kind, user):
    obj = kind.create(user)
    api.force_login(user)

    response = api.get(f"/api/{kind.route}/{obj.pk}/")

    assert response.status_code == 200
    assert response.json() == {"id": obj.pk}


def test_another_users_object_answers_404(api, kind, user, other_user):
    theirs = kind.create(other_user)
    api.force_login(user)
    url = f"/api/{kind.route}/{theirs.pk}/"

    response = api.get(url)
    deletion = api.delete(url)

    assert response.status_code == 404
    # The same answer as for an ID that doesn't exist, so it gives nothing away.
    assert response.json() == api.get(f"/api/{kind.route}/0/").json()
    assert deletion.status_code == 404
    assert kind.model.objects.filter(pk=theirs.pk).exists()


def test_signed_out_requests_get_401(api, kind, user):
    obj = kind.create(user)

    assert api.get(f"/api/{kind.route}/").status_code == 401
    assert api.get(f"/api/{kind.route}/{obj.pk}/").status_code == 401
    assert api.delete(f"/api/{kind.route}/{obj.pk}/").status_code == 401


def test_is_owner_refuses_what_an_unscoped_queryset_lets_through(api, user, other_user):
    theirs = OrderFactory(user=other_user)
    api.force_login(user)
    url = f"/api/unscoped-orders/{theirs.pk}/"

    assert api.get(url).status_code == 403
    assert api.delete(url).status_code == 403
    assert Order.objects.filter(pk=theirs.pk).exists()


def test_permission_classes_cant_open_a_view_to_signed_out_visitors(api, user):
    order = OrderFactory(user=user)

    assert api.get("/api/allow-any-orders/").status_code == 401
    assert api.get(f"/api/allow-any-orders/{order.pk}/").status_code == 401


# Every view is scoped

# The views that serve no order data, so they don't need OwnedByUserMixin, each with the
# reason. A view that reads or changes order data uses the mixin instead.
VIEWS_WITHOUT_ORDER_DATA = [
    # Open to everyone, and reads no user's data.
    health,
    # Signing in and out: each acts only on the request's own session and its user.
    google_login,
    google_callback,
    SessionView,
]


def views_missing_the_scope(url_patterns: list) -> list[str]:
    """The URLs whose views neither use the mixin nor are in VIEWS_WITHOUT_ORDER_DATA,
    as "route → view"."""
    allowed = {_view(view) for view in VIEWS_WITHOUT_ORDER_DATA}
    return [
        f"{route} → {view.__module__}.{view.__name__}"
        for route, view in _views(url_patterns)
        if view not in allowed and not _uses_the_mixin(view)
    ]


def _views(url_patterns: list, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """(route, view) for each URL, including those of included URLconfs.

    Skips the admin, which staff use to see everyone's data.
    """
    for pattern in url_patterns:
        route = prefix + str(pattern.pattern).removeprefix("^").removesuffix("$")
        if not isinstance(pattern, URLResolver):
            yield route, _view(pattern.callback)
        elif pattern.app_name != "admin":
            yield from _views(pattern.url_patterns, route)


def _view(callback: Any) -> Any:
    """The view behind a URL's callback: DRF's views and viewsets record their class as
    .cls, Django's class-based views as .view_class. A function view is its own."""
    return getattr(callback, "cls", None) or getattr(callback, "view_class", None) or callback


def _uses_the_mixin(view: Any) -> bool:
    """Whether the mixin comes before DRF's GenericAPIView in the view's classes.

    After it, DRF's own get_queryset() and get_permissions() run instead.
    """
    classes = getattr(view, "__mro__", ())
    return (
        OwnedByUserMixin in classes
        and GenericAPIView in classes
        and classes.index(OwnedByUserMixin) < classes.index(GenericAPIView)
    )


def test_every_view_is_scoped_or_serves_no_order_data():
    missing = views_missing_the_scope(get_resolver().url_patterns)

    assert not missing, (
        "These views neither use OwnedByUserMixin nor are in VIEWS_WITHOUT_ORDER_DATA: "
        f"{', '.join(missing)}. List the mixin ahead of DRF's classes in the view's bases. "
        "A view that serves no order data goes in VIEWS_WITHOUT_ORDER_DATA, with a comment "
        "saying why."
    )


class UnscopedViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Order.objects.all()


class MixinLastViewSet(viewsets.ReadOnlyModelViewSet, OwnedByUserMixin):
    queryset = Order.objects.all()


@api_view(["GET"])
def drf_function_view(request):
    return Response()


def django_view(request):
    return HttpResponse()


def test_the_guard_finds_each_view_that_skips_the_scope():
    url_patterns = [
        # The test-only viewsets use the mixin.
        path("", include("orders.tests.urls")),
        path("api/unscoped/", UnscopedViewSet.as_view({"get": "list"})),
        path("api/mixin-last/", MixinLastViewSet.as_view({"get": "list"})),
        path("api/drf-function/", drf_function_view),
        path("api/django/", django_view),
        # A view listed as serving no order data.
        path("api/health/", health),
        path("admin/", admin.site.urls),
    ]

    assert views_missing_the_scope(url_patterns) == [
        f"api/unscoped/ → {__name__}.UnscopedViewSet",
        f"api/mixin-last/ → {__name__}.MixinLastViewSet",
        f"api/drf-function/ → {__name__}.drf_function_view",
        f"api/django/ → {__name__}.django_view",
    ]
