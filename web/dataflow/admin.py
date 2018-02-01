from django.contrib import admin
from dataflow.models import *


@admin.register(DeviceGroup)
class DeviceGroupAdmin(admin.ModelAdmin):
    pass


@admin.register(DeviceType)
class DeviceTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    pass


@admin.register(SensorType)
class SensorTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    pass


@admin.register(CommandTemplate)
class CommandTemplateAdmin(admin.ModelAdmin):
    pass


@admin.register(Command)
class CommandAdmin(admin.ModelAdmin):
    pass


@admin.register(CommandHistory)
class CommandHistoryAdmin(admin.ModelAdmin):
    pass


@admin.register(SensorHistory)
class SensorHistoryAdmin(admin.ModelAdmin):
    pass


@admin.register(DebugPacket)
class DebugPacketAdmin(admin.ModelAdmin):
    pass