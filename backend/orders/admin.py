from django import forms
from django.contrib import admin
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html

from .models import AnomalyFlag, Order, Rate, Shipment

# Foreign keys use autocomplete fields, which load matching rows as you type, instead of
# menus that list every user, order, or shipment.


class AnomalyFlagInline(admin.TabularInline):
    model = AnomalyFlag
    extra = 0
    readonly_fields = ["created_at"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "external_id",
        "user",
        "recipient_name",
        "recipient_country",
        "status",
        "created_at",
    ]
    list_filter = ["status", "recipient_country"]
    list_select_related = ["user"]
    search_fields = ["external_id", "recipient_name", "recipient_postal_code"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
    autocomplete_fields = ["user"]
    readonly_fields = ["shipment_link", "created_at", "updated_at"]
    inlines = [AnomalyFlagInline]

    @admin.display(description="shipment")
    def shipment_link(self, order: Order) -> str:
        if order.pk is None:
            return self.get_empty_value_display()
        try:
            shipment = order.shipment
        except Shipment.DoesNotExist:
            url = reverse("admin:orders_shipment_add") + f"?order={order.pk}"
            return format_html('<a href="{}">Add a shipment</a>', url)
        url = reverse("admin:orders_shipment_change", args=[shipment.pk])
        return format_html('<a href="{}">{}</a>', url, shipment)


class RateInline(admin.TabularInline):
    model = Rate
    extra = 0


class ShipmentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Offer only this shipment's own rates, the rule Shipment.clean() enforces. A new
        # shipment has none yet.
        self.fields["selected_rate"].queryset = (
            self.instance.rates.all() if self.instance.pk else Rate.objects.none()
        )


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    form = ShipmentForm
    list_display = ["__str__", "easypost_id", "selected_rate", "created_at"]
    list_filter = [("selected_rate", admin.EmptyFieldListFilter)]
    # __str__ shows the order's external ID.
    list_select_related = ["order", "selected_rate"]
    search_fields = ["order__external_id", "easypost_id"]
    ordering = ["-created_at"]
    autocomplete_fields = ["order"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [RateInline]


@admin.register(Rate)
class RateAdmin(admin.ModelAdmin):
    list_display = [
        "carrier",
        "service",
        "cost",
        "currency",
        "delivery_days",
        "shipment",
        "fetched_at",
    ]
    list_filter = ["carrier", "currency"]
    # The shipment's name shows its order's external ID.
    list_select_related = ["shipment__order"]
    search_fields = ["shipment__order__external_id", "carrier", "service"]
    ordering = ["-fetched_at"]
    autocomplete_fields = ["shipment"]

    def get_readonly_fields(self, request: HttpRequest, obj: Rate | None = None) -> list[str]:
        # A rate stays with the shipment it was quoted for, which may have selected it.
        return ["shipment"] if obj else []


@admin.register(AnomalyFlag)
class AnomalyFlagAdmin(admin.ModelAdmin):
    list_display = ["reason", "severity", "order", "created_at"]
    list_filter = ["severity"]
    list_select_related = ["order"]
    search_fields = ["order__external_id", "reason"]
    ordering = ["-created_at"]
    autocomplete_fields = ["order"]
    readonly_fields = ["created_at"]
