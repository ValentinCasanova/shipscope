from django.db import models


class Probe(models.Model):
    """Exists only to prove that CI rejects a model change without a migration."""

    name = models.CharField(max_length=10)

    def __str__(self) -> str:
        return self.name
