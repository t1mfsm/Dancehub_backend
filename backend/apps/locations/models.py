from django.db import models


class City(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.TextField(unique=True)

    class Meta:
        db_table = "cities"
        managed = False
        ordering = ["name"]
        verbose_name = "Город"
        verbose_name_plural = "Города"

    def __str__(self) -> str:
        return self.name
