# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-09-06 01:56
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dataflow', '0018_auto_20160906_0442'),
    ]

    operations = [
        migrations.AddField(
            model_name='command',
            name='compare_with',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='\u0421\u0440\u0430\u0432\u043d\u0438\u0442\u044c \u0441'),
        ),
    ]
