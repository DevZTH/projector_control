# -*- coding: utf-8 -*-
from django.http import HttpResponse


def index_view(request):
    return HttpResponse(u'<strong style="color: orange;">Упс! Пока нет данных для отображения.</strong><br><em>Возможно стоит подождать или проверить конфигурацию в <a href="/admin/">интерфейсе администрирования</a></em>')
