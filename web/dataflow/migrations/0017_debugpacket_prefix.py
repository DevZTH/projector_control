# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-09-06 01:31
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dataflow', '0016_debugpacket_protocol'),
    ]

    operations = [
        migrations.AddField(
            model_name='debugpacket',
            name='prefix',
            field=models.CharField(blank=True, max_length=3, null=True, verbose_name='\u041d\u0430\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0435'),
        ),
    ]
