#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.db import models
from django.utils import timezone


class DeviceGroup(models.Model):
    title = models.CharField(u'Название', max_length=255)

    class Meta:
        verbose_name = u'Группа устройств'
        verbose_name_plural = u'Группы устройств'

    def __unicode__(self):
        return u"%s" % self.title


class DeviceType(models.Model):
    title = models.CharField(u'Название', max_length=255)
    script = models.TextField(u'Скрипт запуска', null=True, blank=True,
                              help_text = u"Поле в данное время никак не используется")

    class Meta:
        verbose_name = u'Тип устройства'
        verbose_name_plural = u'Типы устройств'

    def __unicode__(self):
        return u"%s" % self.title


class Device(models.Model):
    title = models.CharField(u'Имя', max_length=255, null=True, blank=True)
    device_type = models.ForeignKey(DeviceType, null=True, blank=True)
    device_group = models.ForeignKey(DeviceGroup, null=True, blank=True)
    identifier = models.IntegerField(u'ID', unique=True)
    mac = models.CharField(u'MAC-адрес', max_length=18, null=True, blank=True)
    ip = models.GenericIPAddressField(u'IP-адрес', null=True, blank=True)
    port = models.IntegerField(u'Порт', null=True, blank=True)
    is_online = models.BooleanField(u'В сети', default=False)
    last_online = models.DateTimeField(u'Время последней связи', null=True, blank=True)

    class Meta:
        verbose_name = u'Устройство'
        verbose_name_plural = u'Устройства'

    def __unicode__(self):
        return u"[ID%s] %s" % (self.identifier, self.title)


class DebugPacket(models.Model):
    PROTOCOL_TCP = 1
    PROTOCOL_UDP = 2

    PROTOCOLS = (
        (PROTOCOL_TCP, u'TCP'),
        (PROTOCOL_UDP, u'UDP')
    )
    device = models.ForeignKey(Device, blank=True, null=True)
    received = models.DateTimeField(u'Время получения', auto_now=True)
    protocol = models.IntegerField(u'Протокол', choices=PROTOCOLS, default=None, blank=True, null=True)
    ip = models.GenericIPAddressField(u'IP-адрес', null=True, blank=True)
    port = models.IntegerField(u'Порт', null=True, blank=True)
    prefix = models.CharField(u'Назначение', max_length=3, null=True, blank=True)
    data = models.TextField(u'Содержимое')

    class Meta:
        verbose_name = u'Дебаг'
        verbose_name_plural = u'Дебаг'

    def __unicode__(self):
        return u"от %s в %s" % (self.device, self.received.strftime("%H:%M:%S (UTC) %d.%m.%Y"))


class SensorType(models.Model):
    title = models.CharField(u'Название', max_length=255)
    start = models.IntegerField(u'Стартовый байт', null=True, blank=True)
    length = models.IntegerField(u'Длина', null=True, blank=True)
    template = models.CharField(u'STRUCT-шаблон', max_length=255)
    unit = models.CharField(u'Единица измерения', max_length=255)

    class Meta:
        verbose_name = u'Тип сенсора'
        verbose_name_plural = u'Типы сенсоров'

    def __unicode__(self):
        return u"%s" % self.title


class Sensor(models.Model):
    device = models.ForeignKey(Device, related_name="sensors")
    sensor_type = models.ForeignKey(SensorType)
    identifier = models.IntegerField(u'ID сенсора',
                                     help_text=u"Используется для идентификации DAT-пакета, дублируется в пределах устройства",
                                     default=1)
    title = models.CharField(u'Название', max_length=255)

    class Meta:
        verbose_name = u'Сенсор'
        verbose_name_plural = u'Сенсоры'

    def __unicode__(self):
        return u"%s на %s (%s)" % (self.sensor_type, self.device, self.title)


class SensorHistory(models.Model):
    sensor = models.ForeignKey(Sensor)
    time = models.DateTimeField(u'Время выполнения', auto_now=True)
    result = models.TextField(u'Значение', null=True, blank=True)

    class Meta:
        verbose_name = u'Значение сенсора'
        verbose_name_plural = u'Значения сенсоров'

    def __unicode__(self):
        return u"[%s] %s" % (self.time.strftime("%H:%M:%S (UTC) %d.%m.%Y"), self.sensor)


class CommandTemplate(models.Model):
    title = models.CharField(u'Название', max_length=255)
    script = models.TextField(u'Скрипт', null=True, blank=True)

    class Meta:
        verbose_name = u'Шаблон команды'
        verbose_name_plural = u'Шаблоны команд'

    def __unicode__(self):
        return u"%s" % self.title


class Command(models.Model):

    ON_CONNECT = 1
    ON_CRON = 2
    ON_SENSOR = 3
    ON_SAVE = 4

    EXEC_TYPES = (
        (ON_CONNECT, u'При появлении в сети'),
        (ON_CRON, u'По cron'),
        (ON_SENSOR, u'По значению сенсора'),
        (ON_SAVE, u'Незамедлительно'),
    )

    COMPARE_E = 1
    COMPARE_NE = 2
    COMPARE_GT = 3
    COMPARE_LT = 4
    COMPARE_GTE = 5
    COMPARE_LTE = 6

    COMPARE_TYPES = (
        (COMPARE_E, u'Равно'),
        (COMPARE_NE, u'Не равно'),
        (COMPARE_GT, u'Больше'),
        (COMPARE_GTE, u'Больше либо равно'),
        (COMPARE_LT, u'Меньше'),
        (COMPARE_LTE, u'Меньше либо равно'),
    )

    template = models.ForeignKey(CommandTemplate)
    device = models.ForeignKey(Device, related_name="commands")
    order = models.IntegerField(u'Порядок выполнения', null=True, blank=True)
    exec_type = models.IntegerField(u'Триггер выполнения', choices=EXEC_TYPES, default=ON_SAVE)
    exec_count = models.IntegerField(u'Количество выполнений', default=0)
    cron = models.TextField(u'Периодичность', help_text=u"Как в crontab, @reboot не используется", null=True, blank=True)
    sensor = models.ForeignKey(Sensor, related_name="commands", null=True, blank=True)
    compare_type = models.IntegerField(u'Сравнение значения сенсора', choices=COMPARE_TYPES, default=COMPARE_E)
    compare_with = models.CharField(u'Сравнить с', null=True, blank=True, max_length=255)

    class Meta:
        verbose_name = u'Команды'
        verbose_name_plural = u'Команды'
        ordering = ["order"]

    def __unicode__(self):
        return u"%s к %s" % (self.template, self.device)


class CommandHistory(models.Model):
    command = models.ForeignKey(Command)
    time = models.DateTimeField(u'Время выполнения', auto_now=True)
    success = models.BooleanField(u'Успешно', default=False)
    error_message = models.CharField(u'Сообщение об ошибке', null=True, blank=True, max_length=255)
    result = models.TextField(u'Результат', null=True, blank=True, max_length=4095)

    class Meta:
        verbose_name = u'Выполненная команда'
        verbose_name_plural = u'Выполненные команды'

    def __unicode__(self):
        return u"[%s] %s" % (self.time.strftime("%H:%M:%S (UTC) %d.%m.%Y"), self.command)
