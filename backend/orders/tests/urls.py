"""Test-only viewsets of the order models, behind OwnedByUserMixin as the app's will be.

No endpoint serves order data yet, so test_scoping.py serves these in place of the
app's URLs.
"""

from django.urls import include, path
from rest_framework import mixins, serializers, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.routers import SimpleRouter

from orders.models import AnomalyFlag, Order, Rate, Shipment
from orders.permissions import OwnedByUserMixin


class IdSerializer(serializers.Serializer):
    """Only each object's ID, which is all the tests compare."""

    id = serializers.IntegerField(read_only=True)


class OwnedViewSet(OwnedByUserMixin, mixins.DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    """Lists, shows, and deletes objects."""

    serializer_class = IdSerializer


class OrderViewSet(OwnedViewSet):
    queryset = Order.objects.all()


class ShipmentViewSet(OwnedViewSet):
    queryset = Shipment.objects.all()


class RateViewSet(OwnedViewSet):
    queryset = Rate.objects.all()


class AnomalyFlagViewSet(OwnedViewSet):
    queryset = AnomalyFlag.objects.all()


# Two mistakes the mixin should survive.


class UnscopedOrderViewSet(OrderViewSet):
    """Replaces get_queryset() without calling super(), so its queryset isn't scoped."""

    def get_queryset(self):
        return Order.objects.all()


class AllowAnyOrderViewSet(OrderViewSet):
    """Tries to open itself to signed-out visitors."""

    permission_classes = [AllowAny]


router = SimpleRouter()
router.register("orders", OrderViewSet)
router.register("shipments", ShipmentViewSet)
router.register("rates", RateViewSet)
router.register("anomaly-flags", AnomalyFlagViewSet)
router.register("unscoped-orders", UnscopedOrderViewSet, basename="unscoped-order")
router.register("allow-any-orders", AllowAnyOrderViewSet, basename="allow-any-order")

urlpatterns = [path("api/", include(router.urls))]
