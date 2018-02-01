# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-08-24 03:17
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dataflow', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Packet',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('received', models.DateTimeField(auto_now=True, verbose_name='\u0412\u0440\u0435\u043c\u044f \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u044f')),
                ('data', models.TextField(verbose_name='\u0421\u043e\u0434\u0435\u0440\u0436\u0438\u043c\u043e\u0435')),
            ],
            options={
                'verbose_name': '\u041e\u0442\u043b\u0430\u0434\u043e\u0447\u043d\u044b\u0439 \u043f\u0430\u043a\u0435\u0442',
                'verbose_name_plural': '\u041e\u0442\u043b\u0430\u0434\u043e\u0447\u043d\u044b\u0435 \u043f\u0430\u043a\u0435\u0442\u044b',
            },
        ),
        migrations.AlterField(
            model_name='device',
            name='mac',
            field=models.CharField(blank=True, max_length=18, null=True, verbose_name='MAC-\u0430\u0434\u0440\u0435\u0441'),
        ),
        migrations.AlterField(
            model_name='device',
            name='title',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='\u0418\u043c\u044f'),
        ),
        migrations.AddField(
            model_name='packet',
            name='device',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dataflow.Device'),
        ),
    ]