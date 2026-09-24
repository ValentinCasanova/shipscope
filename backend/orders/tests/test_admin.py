"""The orders admin: its lists stay cheap, and its forms explain what they refuse.

config/tests/test_admin.py already renders each model's list, search, and add pages.
"""

from decimal import Decimal

import pytest
from django.contrib.admin.templatetags.admin_urls import admin_urlname
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from pytest_django.asserts import assertContains

from orders.models import Order

from .factories import (
    AnomalyFlagFactory,
    OrderFactory,
    RateFactory,
    ShipmentFactory,
    select_rate,
)


@pytest.fixture
def order(db) -> Order:
    """An order, its shipment with two rates, one of them selected, and an anomaly flag."""
    shipment = select_rate(RateFactory())
    RateFactory(shipment=shipment, carrier="UPS", service="Ground", cost=Decimal("9.10"))
    AnomalyFlagFactory(order=shipment.order)
    return shipment.order


@pytest.mark.parametrize(
    ("model", "add_row"),
    [
        pytest.param("order", OrderFactory, id="orders"),
        # With a selected rate: Django's list follows only foreign keys that can't be
        # null unless list_select_related names the others.
        pytest.param("shipment", lambda: select_rate(RateFactory()), id="shipments"),
        pytest.param("rate", RateFactory, id="rates"),
        pytest.param("anomalyflag", AnomalyFlagFactory, id="anomaly-flags"),
    ],
)
def test_a_list_takes_as_many_queries_for_many_rows_as_for_one(
    superuser_client, django_assert_num_queries, model, add_row
):
    url = reverse(f"admin:orders_{model}_changelist")
    # Each row gets its own user and, below it, its own order and shipment, so a column
    # that loads a related row once per row shows up as extra queries.
    add_row()
    with CaptureQueriesContext(connection) as one_row:
        superuser_client.get(url)
    for _ in range(4):
        add_row()

    with django_assert_num_queries(len(one_row)):
        superuser_client.get(url)


@pytest.mark.parametrize(
    "get_object",
    [
        pytest.param(lambda order: order, id="order"),
        pytest.param(lambda order: order.shipment, id="shipment"),
        pytest.param(lambda order: order.shipment.selected_rate, id="rate"),
        pytest.param(lambda order: order.anomaly_flags.get(), id="anomaly-flag"),
    ],
)
def test_change_page_renders(superuser_client, order, get_object):
    obj = get_object(order)

    response = superuser_client.get(reverse(admin_urlname(obj._meta, "change"), args=[obj.pk]))

    assert response.status_code == 200


def test_an_order_page_shows_its_flags_and_links_to_its_shipment(superuser_client, order):
    response = superuser_client.get(reverse("admin:orders_order_change", args=[order.pk]))

    assertContains(response, order.anomaly_flags.get().reason)
    assertContains(response, reverse("admin:orders_shipment_change", args=[order.shipment.pk]))


def test_an_order_page_without_a_shipment_links_to_adding_one(superuser_client):
    order = OrderFactory()

    response = superuser_client.get(reverse("admin:orders_order_change", args=[order.pk]))

    assertContains(response, reverse("admin:orders_shipment_add") + f"?order={order.pk}")


def test_the_order_form_explains_a_duplicate_external_id(superuser_client):
    order = OrderFactory()

    response = superuser_client.post(
        reverse("admin:orders_order_add"),
        {
            "user": order.user.pk,
            "external_id": order.external_id,
            "recipient_name": "Grace Hopper",
            "recipient_street1": "2 Main St",
            "recipient_city": "Arlington",
            "recipient_country": "US",
            "status": "pending",
            # The anomaly flags inline, with no flags.
            "anomaly_flags-TOTAL_FORMS": "0",
            "anomaly_flags-INITIAL_FORMS": "0",
        },
    )

    # A 200 with the form again, not a 500 from the database's IntegrityError.
    assertContains(response, "You already have an order with this ID.")
    assert Order.objects.count() == 1


def test_the_selected_rate_menu_offers_only_the_shipments_own_rates(superuser_client, order):
    RateFactory()  # Another shipment's rate.

    response = superuser_client.get(
        reverse("admin:orders_shipment_change", args=[order.shipment.pk])
    )

    menu = response.context["adminform"].form.fields["selected_rate"]
    assert set(menu.queryset) == set(order.shipment.rates.all())


def test_the_shipment_form_refuses_another_shipments_rate(superuser_client):
    shipment = ShipmentFactory()
    other_shipments_rate = RateFactory()

    response = superuser_client.post(
        reverse("admin:orders_shipment_change", args=[shipment.pk]),
        {
            "order": shipment.order.pk,
            "selected_rate": other_shipments_rate.pk,
            # The rates inline, left as it is.
            "rates-TOTAL_FORMS": "0",
            "rates-INITIAL_FORMS": "0",
        },
    )

    assertContains(response, "Select a valid choice.")
    shipment.refresh_from_db()
    assert shipment.selected_rate is None


def test_a_rate_keeps_its_shipment(superuser_client):
    rate = RateFactory()

    response = superuser_client.get(reverse("admin:orders_rate_change", args=[rate.pk]))

    assert "shipment" not in response.context["adminform"].form.fields
