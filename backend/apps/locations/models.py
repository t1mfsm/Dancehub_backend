from django.db import models


class City(models.Model):
    name = models.CharField(max_length=128, unique=True)

    class Meta:
        db_table = "cities"
        verbose_name = "Город"
        verbose_name_plural = "Города"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

