# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-08-24 03:20
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dataflow', '0002_auto_20160824_0617'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Packet',
            new_name='DebugPacket',
        ),
    ]
