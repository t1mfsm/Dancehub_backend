"""
Кастомная пагинация DRF под формат контракта фронта: `{items, total}`.
Параметры query: `page` (с 1), `perPage` (при renderer-е camel-case фронт шлёт
именно `perPage`, а парсер переведёт в `per_page`).
"""

from collections import OrderedDict

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class CustomPagination(PageNumberPagination):
    page_size = 9
    page_size_query_param = "per_page"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("items", data),
                    ("total", self.page.paginator.count),
                    ("page", self.page.number),
                    ("perPage", self.page.paginator.per_page),
                ]
            )
        )
