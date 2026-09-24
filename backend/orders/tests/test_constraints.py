"""The database itself refuses rows that break the schema's rules.

The factories save without Django's validation, as a bulk import or raw SQL would, so
each refusal here comes from PostgreSQL. Each test matches the constraint's name, so it
can't pass because a different rule refused the row.

Each statement that should fail runs in its own atomic block, so the failure rolls back
only that block, not the whole test's transaction.
"""

from decimal import Decimal

import pytest
from django.db import DataError, IntegrityError, transaction

from orders.models import Order

from .factories import AnomalyFlagFactory, OrderFactory, RateFactory, ShipmentFactory


@pytest.mark.django_db
def test_a_user_has_at_most_one_order_per_external_id():
    order = OrderFactory()

    with (
        pytest.raises(IntegrityError, match="orders_order_external_id_unique_per_user"),
        transaction.atomic(),
    ):
        OrderFactory(user=order.user, external_id=order.external_id)


@pytest.mark.django_db
def test_two_users_can_have_orders_with_the_same_external_id():
    order = OrderFactory()

    OrderFactory(external_id=order.external_id)

    assert Order.objects.filter(external_id=order.external_id).count() == 2


@pytest.mark.django_db
def test_an_order_has_at_most_one_shipment():
    shipment = ShipmentFactory()

    # PostgreSQL's name for the one-to-one field's UNIQUE.
    with pytest.raises(IntegrityError, match="orders_shipment_order_id_key"), transaction.atomic():
        ShipmentFactory(order=shipment.order)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("factory", "values", "constraint"),
    [
        pytest.param(
            OrderFactory,
            {"external_id": ""},
            "orders_order_external_id_not_empty",
            id="empty-external-id",
        ),
        pytest.param(
            OrderFactory, {"status": "shipped"}, "orders_order_status_valid", id="unknown-status"
        ),
        pytest.param(
            OrderFactory,
            {"recipient_country": "us"},
            "orders_order_recipient_country_valid",
            id="lowercase-country",
        ),
        pytest.param(
            OrderFactory,
            {"weight_oz": Decimal(0)},
            "orders_order_weight_oz_positive",
            id="weight-of-0",
        ),
        pytest.param(
            OrderFactory,
            {"length_in": Decimal(0)},
            "orders_order_length_in_positive",
            id="length-of-0",
        ),
        pytest.param(
            OrderFactory,
            {"width_in": Decimal(0)},
            "orders_order_width_in_positive",
            id="width-of-0",
        ),
        pytest.param(
            OrderFactory,
            {"height_in": Decimal("-1.00")},
            "orders_order_height_in_positive",
            id="negative-height",
        ),
        pytest.param(
            RateFactory,
            {"cost": Decimal("-0.01")},
            "orders_rate_cost_not_negative",
            id="negative-cost",
        ),
        pytest.param(
            RateFactory, {"currency": "usd"}, "orders_rate_currency_valid", id="lowercase-currency"
        ),
        pytest.param(
            AnomalyFlagFactory,
            {"severity": "critical"},
            "orders_anomalyflag_severity_valid",
            id="unknown-severity",
        ),
    ],
)
def test_the_database_refuses(factory, values, constraint):
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        factory(**values)


@pytest.mark.django_db
def test_a_country_code_has_at_most_two_letters():
    # The column's length refuses it before the check constraint would.
    with pytest.raises(DataError, match="value too long"), transaction.atomic():
        OrderFactory(recipient_country="USA")


@pytest.mark.django_db
def test_an_order_may_lack_its_weight_and_dimensions():
    order = OrderFactory(weight_oz=None, length_in=None, width_in=None, height_in=None)

    order.refresh_from_db()

    assert (order.weight_oz, order.length_in, order.width_in, order.height_in) == (None,) * 4


@pytest.mark.django_db
def test_a_rate_may_be_free():
    rate = RateFactory(cost=Decimal("0.00"))

    rate.refresh_from_db()

    assert rate.cost == 0
