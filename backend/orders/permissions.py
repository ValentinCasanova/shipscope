"""Keeping each user's order data to that user, in every API view that serves it."""

from django.db import models
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView


class IsOwner(IsAuthenticated):
    """Allows only signed-in users, and each only their own objects.

    The second of two checks. OwnedByUserMixin first narrows the view's queryset to the
    user's objects, which also covers lists: DRF checks object permissions only on single
    objects. If a view fetches another user's object some other way, this still refuses
    it, with a 403.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: models.Model) -> bool:
        return _owner_id(obj) == request.user.pk


def _owner_id(obj: models.Model) -> int:
    """The ID of obj's owner, following its model's OWNER_PATH, the path for_user() filters on.

    For a rate, rate.shipment.order.user_id. The last step reads the foreign key's column,
    so the user isn't loaded.
    """
    *relations, owner_field = type(obj).OWNER_PATH.split("__")
    for relation in relations:
        obj = getattr(obj, relation)
    return getattr(obj, obj._meta.get_field(owner_field).attname)


class OwnedByUserMixin:
    """Scopes a DRF generic view or viewset to the signed-in user's own objects.

    List it ahead of DRF's classes, or DRF's get_queryset() runs instead of this one:

        class OrderViewSet(OwnedByUserMixin, viewsets.ModelViewSet):
            queryset = Order.objects.all()

    - get_queryset() keeps only the user's objects, so a list holds only theirs, and
      another user's object answers 404, like one that doesn't exist. A 403 would confirm
      that it exists.
    - The view's permissions gain IsOwner, whatever permission_classes says.

    Start every query from self.get_queryset() or self.get_object(), never from
    Model.objects, and extend get_queryset() through super(). orders/tests/test_scoping.py
    fails for any view that doesn't use this mixin, unless it's listed as serving no
    order data.
    """

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().for_user(self.request.user)

    def get_permissions(self) -> list[BasePermission]:
        return [*super().get_permissions(), IsOwner()]
