"""Orders from the connected Sheet, their EasyPost shipments and rates, and anomaly flags."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import Truncator

# Django doesn't enforce choices in the database, so a check constraint backs each set.
# The constraints need these classes, and a model's Meta can't see names defined in the
# model's body, so they live at module level.


class OrderStatus(models.TextChoices):
    PENDING = "pending"
    RATED = "rated"
    SELECTED = "selected"


class AnomalySeverity(models.TextChoices):
    INFO = "info"
    WARNING = "warning"


class Order(models.Model):
    """One row of the user's Sheet: where a parcel goes, and its weight and dimensions.

    Measurements use EasyPost's units, ounces and inches, and each field's name says
    which. A row may lack them, so they're nullable.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders"
    )
    external_id = models.CharField(
        "external ID", max_length=100, help_text="The order's ID in the Sheet."
    )
    recipient_name = models.CharField(max_length=255)
    recipient_street1 = models.CharField("recipient street 1", max_length=255)
    recipient_street2 = models.CharField("recipient street 2", max_length=255, blank=True)
    recipient_city = models.CharField(max_length=100)
    # Not every country has states or postal codes.
    recipient_state = models.CharField(max_length=100, blank=True)
    recipient_postal_code = models.CharField(max_length=20, blank=True)
    recipient_country = models.CharField(
        max_length=2, help_text="Two-letter ISO 3166-1 code, such as US."
    )
    weight_oz = models.DecimalField(
        "weight (oz)", max_digits=8, decimal_places=2, null=True, blank=True
    )
    length_in = models.DecimalField(
        "length (in)", max_digits=8, decimal_places=2, null=True, blank=True
    )
    width_in = models.DecimalField(
        "width (in)", max_digits=8, decimal_places=2, null=True, blank=True
    )
    height_in = models.DecimalField(
        "height (in)", max_digits=8, decimal_places=2, null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=OrderStatus, default=OrderStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # The Sheet sync's idempotency key: syncing a row again updates its order
            # instead of adding a copy.
            models.UniqueConstraint(
                fields=["user", "external_id"],
                name="orders_order_external_id_unique_per_user",
                violation_error_message="You already have an order with this ID.",
            ),
            # Field validation reports an empty ID or an unknown status before
            # constraints are checked, so these two need no message.
            models.CheckConstraint(
                condition=~models.Q(external_id=""),
                name="orders_order_external_id_not_empty",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=OrderStatus.values),
                name="orders_order_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(recipient_country__regex=r"^[A-Z]{2}$"),
                name="orders_order_recipient_country_valid",
                violation_error_message=(
                    "Enter the country as a two-letter code in capitals, such as US."
                ),
            ),
            # A NULL passes a check constraint, so a missing measurement is allowed.
            models.CheckConstraint(
                condition=models.Q(weight_oz__gt=0),
                name="orders_order_weight_oz_positive",
                violation_error_message="The weight must be greater than 0.",
            ),
            models.CheckConstraint(
                condition=models.Q(length_in__gt=0),
                name="orders_order_length_in_positive",
                violation_error_message="The length must be greater than 0.",
            ),
            models.CheckConstraint(
                condition=models.Q(width_in__gt=0),
                name="orders_order_width_in_positive",
                violation_error_message="The width must be greater than 0.",
            ),
            models.CheckConstraint(
                condition=models.Q(height_in__gt=0),
                name="orders_order_height_in_positive",
                violation_error_message="The height must be greater than 0.",
            ),
        ]

    def __str__(self) -> str:
        return f"Order {self.external_id}"


class Shipment(models.Model):
    """The order's shipment at EasyPost, which its rates were quoted for."""

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="shipment")
    easypost_id = models.CharField(
        "EasyPost ID",
        max_length=100,
        blank=True,
        help_text="EasyPost's shipment ID (shp_…). Blank until rates are fetched.",
    )
    # Deleting the selected rate clears the selection. No reverse accessor: a rate has
    # no use for the shipment that selected it, which is its own.
    selected_rate = models.ForeignKey(
        "Rate", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Shipment for order {self.order.external_id}"

    def clean(self) -> None:
        super().clean()
        # The foreign key only makes the database check that the rate exists. That it's
        # one of this shipment's own rates is a rule across two rows, which a check
        # constraint can't express. A new shipment has no rates yet.
        if (
            self.selected_rate_id is not None
            and not Rate.objects.filter(pk=self.selected_rate_id, shipment=self.pk).exists()
        ):
            raise ValidationError({"selected_rate": "Select one of this shipment's own rates."})


class Rate(models.Model):
    """One carrier and service option for a shipment, as EasyPost quoted it.

    A snapshot of EasyPost's answer when it was fetched, never edited afterwards.
    """

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="rates")
    carrier = models.CharField(max_length=100, help_text="Such as USPS.")
    service = models.CharField(max_length=100, help_text="Such as Priority.")
    # An exact decimal, never a float.
    cost = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(
        max_length=3, default="USD", help_text="Three-letter ISO 4217 code, such as USD."
    )
    # EasyPost leaves it empty for some services.
    delivery_days = models.PositiveSmallIntegerField(null=True, blank=True)
    # A default rather than auto_now_add, so tests can create stale rates.
    fetched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cost__gte=0),
                name="orders_rate_cost_not_negative",
                violation_error_message="The cost can't be negative.",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__regex=r"^[A-Z]{3}$"),
                name="orders_rate_currency_valid",
                violation_error_message=(
                    "Enter the currency as a three-letter code in capitals, such as USD."
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.carrier} {self.service}: {self.cost} {self.currency}"


class AnomalyFlag(models.Model):
    """One finding of the AI check on an order, such as a cost out of line with the parcel."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="anomaly_flags")
    severity = models.CharField(max_length=20, choices=AnomalySeverity)
    # The check's short explanation. Its tool schema should ask for the same limit.
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Field validation reports an unknown severity first, so no message.
            models.CheckConstraint(
                condition=models.Q(severity__in=AnomalySeverity.values),
                name="orders_anomalyflag_severity_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_severity_display()}: {Truncator(self.reason).chars(50)}"
