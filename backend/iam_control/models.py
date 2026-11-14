from django.db import models


class RuntimeState(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    mode = models.CharField(max_length=10, default="frozen")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1), name="iam_control_singleton"
            ),
            models.CheckConstraint(
                condition=models.Q(mode__in=["frozen", "service", "legacy"]),
                name="iam_control_mode",
            ),
        ]
