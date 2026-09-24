"""Test data for orders, their shipments and rates, and anomaly flags."""

from decimal import Decimal

import factory

from accounts.tests.factories import UserFactory
from orders.models import AnomalyFlag, AnomalySeverity, Order, Rate, Shipment


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    external_id = factory.Sequence(lambda n: f"#{1001 + n}")
    recipient_name = "Ada Lovelace"
    recipient_street1 = "1 Main St"
    recipient_city = "Boston"
    recipient_state = "MA"
    recipient_postal_code = "02108"
    recipient_country = "US"
    weight_oz = Decimal("12.00")
    length_in = Decimal("10.00")
    width_in = Decimal("8.00")
    height_in = Decimal("4.00")


class ShipmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Shipment

    order = factory.SubFactory(OrderFactory)


class RateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Rate

    shipment = factory.SubFactory(ShipmentFactory)
    carrier = "USPS"
    service = "Priority"
    cost = Decimal("7.58")
    delivery_days = 2


class AnomalyFlagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AnomalyFlag

    order = factory.SubFactory(OrderFactory)
    severity = AnomalySeverity.WARNING
    reason = "The rate costs far more than usual for a 12 oz parcel."


def select_rate(rate: Rate) -> Shipment:
    """Make the rate its shipment's selected rate, and return the shipment."""
    shipment = rate.shipment
    shipment.selected_rate = rate
    shipment.save()
    return shipment
