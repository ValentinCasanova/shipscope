from decimal import Decimal

import pytest
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db.models import Sum

from orders.models import AnomalyFlag, Order, Rate, Shipment

from .factories import (
    AnomalyFlagFactory,
    OrderFactory,
    RateFactory,
    ShipmentFactory,
    select_rate,
)


@pytest.mark.django_db
def test_a_cost_comes_back_as_the_exact_decimal():
    rate = RateFactory(cost=Decimal("7.58"))

    rate.refresh_from_db()

    assert isinstance(rate.cost, Decimal)
    assert rate.cost == Decimal("7.58")


@pytest.mark.django_db
def test_costs_add_up_exactly():
    RateFactory(cost=Decimal("0.10"))
    RateFactory(cost=Decimal("0.20"))

    total = Rate.objects.aggregate(total=Sum("cost"))["total"]

    # With floats, 0.1 + 0.2 is 0.30000000000000004.
    assert total == Decimal("0.30")


@pytest.mark.django_db
def test_deleting_the_selected_rate_clears_the_selection():
    rate = RateFactory()
    shipment = select_rate(rate)

    rate.delete()

    shipment.refresh_from_db()
    assert shipment.selected_rate is None


@pytest.mark.django_db
def test_deleting_an_order_deletes_its_shipment_rates_and_flags():
    shipment = select_rate(RateFactory())
    RateFactory(shipment=shipment)
    AnomalyFlagFactory(order=shipment.order)

    shipment.order.delete()

    assert not Shipment.objects.exists()
    assert not Rate.objects.exists()
    assert not AnomalyFlag.objects.exists()


@pytest.mark.django_db
def test_deleting_a_user_deletes_their_orders():
    order = OrderFactory()

    order.user.delete()

    assert not Order.objects.exists()


@pytest.mark.django_db
def test_validation_accepts_one_of_the_shipments_own_rates():
    rate = RateFactory()
    shipment = rate.shipment
    shipment.selected_rate = rate

    shipment.full_clean()


@pytest.mark.django_db
def test_validation_rejects_a_rate_of_another_shipment():
    shipment = ShipmentFactory()
    shipment.selected_rate = RateFactory()

    with pytest.raises(ValidationError) as caught:
        shipment.full_clean()

    assert caught.value.message_dict == {
        "selected_rate": ["Select one of this shipment's own rates."]
    }


@pytest.mark.django_db
def test_validation_reports_a_duplicate_external_id():
    order = OrderFactory()
    duplicate = OrderFactory.build(user=order.user, external_id=order.external_id)

    with pytest.raises(ValidationError) as caught:
        duplicate.full_clean()

    assert caught.value.message_dict == {
        NON_FIELD_ERRORS: ["You already have an order with this ID."]
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("factory", "field", "value", "message"),
    [
        pytest.param(
            OrderFactory,
            "recipient_country",
            "us",
            "Enter the country as a two-letter code in capitals, such as US.",
            id="lowercase-country",
        ),
        pytest.param(
            OrderFactory,
            "weight_oz",
            Decimal(0),
            "The weight must be greater than 0.",
            id="weight-of-0",
        ),
        pytest.param(
            OrderFactory,
            "length_in",
            Decimal(0),
            "The length must be greater than 0.",
            id="length-of-0",
        ),
        pytest.param(
            OrderFactory,
            "width_in",
            Decimal(0),
            "The width must be greater than 0.",
            id="width-of-0",
        ),
        pytest.param(
            OrderFactory,
            "height_in",
            Decimal(0),
            "The height must be greater than 0.",
            id="height-of-0",
        ),
        pytest.param(
            RateFactory,
            "cost",
            Decimal("-0.01"),
            "The cost can't be negative.",
            id="negative-cost",
        ),
        pytest.param(
            RateFactory,
            "currency",
            "usd",
            "Enter the currency as a three-letter code in capitals, such as USD.",
            id="lowercase-currency",
        ),
    ],
)
def test_validation_reports_the_constraints_message(factory, field, value, message):
    instance = factory()
    setattr(instance, field, value)

    with pytest.raises(ValidationError) as caught:
        instance.full_clean()

    assert caught.value.message_dict == {NON_FIELD_ERRORS: [message]}
