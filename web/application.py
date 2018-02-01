#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import struct
from enum import Enum
from twisted.internet.protocol import DatagramProtocol, Protocol, ReconnectingClientFactory
from twisted.internet import reactor, task, error
from twisted.web.wsgi import WSGIResource
from twisted.web.server import Site
from crcmod import mkCrcFun
from crontab import CronTab
import django
from django.utils import timezone

UDP_BROADCAST = 49200
UDP_DATA = 49201
UDP_SOCKS = 49202
TCP_PORT = 23
SERVER_IP = chr(192) + chr(168) + chr(0) + chr(23)

ALREADY_CONNECTED_LIMIT_TO_RESET = 5
DISCONNECT_ON_CONNECTION_LOST = True
DISCONNECT_ON_WRONG_ID = True
DISCONNECT_ON_DUPLICATE = True
DISCONNECT_ON_MAX_RETRIES = True

DO_NOTHING_DIVIDER = 4.0

TIMEOUT_BEFORE_RETRY = 1
MAX_RETRY_COUNT = 20

SUCCESS_DATA = '\x00'

ECHO_INTERVAL = 30 #None for never
ECHO_DATA = "HI!"

MAX_TCP_WAITING_FOR_REPLY = 60
MAX_TCP_RECONNECT_RETRIES = 10
MAX_TCP_RECONNECT_DELAY = 240

UNCONFIGURED_IDENTIFIER = 65535
SERVER_IDENTIFIER = 0

COMMAND_QUEUE_CHECK_INTERVAL = 0.1
COMMAND_QUEUE_LENGTH_MAX = 20
COMMAND_QUEUE_CLEAR_ON_CONNECT = True


os.environ['DJANGO_SETTINGS_MODULE'] = 'web.settings'

from web.wsgi import application as django_app

django.setup()

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from dataflow.models import Device as DBDevice
from dataflow.models import Command as DBCommand
from dataflow.models import CommandHistory as DBCommandHistory
from dataflow.models import DebugPacket as DBDebugPacket
from dataflow.models import Sensor as DBSensor
from dataflow.models import SensorHistory as DBSensorHistory

calc_crc8 = mkCrcFun(poly=0x107, initCrc=255, rev=False, xorOut=0)


class PacketType(Enum):
    broadcast = 'SIG'
    data = 'DAT'
    command = 'CMD'
    command_reply = 'REP'


class CommandCodes(Enum):
    do_nothing = 0xff #server command!
    echo = 0x00
    reboot = 0xfe
    connect_to = 0x02
    mac_set = 0x01
    mac_get = 0x07
    ip_set = 0x03
    port_set = 0x0a
    id_get = 0x08
    id_set = 0x09
    pin_configure = 0x04
    pin_write = 0x05
    pin_read = 0x06
    sensor_activate = 0x10
    ir_read = 0x22
    ir_write = 0x23
    serial1_set_speed = 0x30
    serial1_send = 0x31
    serial2_set_speed = 0x32
    serial2_send = 0x33


class Packet(object):

    @staticmethod
    def is_valid_packet(packet):
        is_crc_ok = ord(packet[-1]) == calc_crc8(packet[:-1])
        is_data_ok = (packet.startswith(PacketType.broadcast) and len(packet) == 6) or (len(packet) > 10)
        return is_crc_ok and is_data_ok

    def __init__(self, raw_packet="", packet_data="", packet_type=PacketType.broadcast, packet_id=0,
                 device_id=UNCONFIGURED_IDENTIFIER, command=CommandCodes.do_nothing, wait_for_next=False):

        self._raw_packet = raw_packet
        self._packet_data = packet_data
        self._packet_type = packet_type
        self._packet_id = packet_id
        self._device_id = int(device_id)
        self._command = command
        self._wait_for_next = wait_for_next

        if raw_packet:
            self._is_valid = Packet.is_valid_packet(raw_packet)
            self._crc = raw_packet[-1]
            if self._is_valid:
                self._device_id = struct.unpack('<H', raw_packet[3:5])[0]
                self._packet_data_length = 0
                if not raw_packet.startswith(PacketType.broadcast):
                    self._packet_data_length = len(raw_packet) - 9
                    self._packet_data = raw_packet[9:-1]
                    self._packet_type = raw_packet[:3]
                    self._packet_id = ord(raw_packet[5])
                    self._command = ord(raw_packet[8])
                    self._wait_for_next = ord(raw_packet[6]) == 0

        else:
            self._is_valid = True
            self._packet_data_length = len(self._packet_data) + 1
            self._refresh_packet_data()

    def _refresh_packet_data(self):
        if self._raw_packet:
            self._raw_packet = ""
            self._is_valid = True
        self._crc = calc_crc8(self._build_packet())

    def _build_packet(self):
        data = self._packet_type
        data += struct.pack('<H', self._device_id)
        if not self._packet_type.startswith(PacketType.broadcast):
            data += chr(self._packet_id)
            data += '\x01' if self._wait_for_next else '\x00'
            data += chr(self._packet_data_length)
            data += chr(self._command)
            data += self._packet_data
        return data

    def build_packet(self):
        return self._build_packet() + chr(self._crc)

    @property
    def raw_packet(self):
        if self._raw_packet:
            return self._raw_packet
        else:
            return self.build_packet()

    @property
    def packet_data_length(self):
        return self._packet_data_length

    @property
    def crc(self):
        return self._crc

    @property
    def is_valid(self):
        return self._is_valid

    @property
    def packet_data(self):
        return self._packet_data

    @packet_data.setter
    def packet_data(self, value):
        self._packet_data = value
        self._packet_data_length = len(self._packet_data) + 1
        self._refresh_packet_data()

    @property
    def device_id(self):
        return self._device_id

    @device_id.setter
    def device_id(self, value):
        self._device_id = value
        self._refresh_packet_data()

    @property
    def packet_id(self):
        return self._packet_id

    @packet_id.setter
    def packet_id(self, value):
        self._packet_id = value
        self._refresh_packet_data()

    @property
    def command(self):
        return self._command

    @command.setter
    def command(self, value):
        self._command = value
        self._refresh_packet_data()

    @property
    def packet_type(self):
        return self._packet_type

    @packet_type.setter
    def packet_type(self, value):
        self._packet_type = value
        self._refresh_packet_data()

    @property
    def wait_for_next(self):
        return self._wait_for_next

    @wait_for_next.setter
    def wait_for_next(self, value):
        self._wait_for_next = value
        self._refresh_packet_data()


def is_valid_packet(packet):
    is_crc_ok = ord(packet[-1]) == calc_crc8(packet[-1])
    is_data_ok = (packet.startswith('SIG') and len(packet) == 6) or (len(packet) > 10)
    return is_crc_ok and is_data_ok


def create_packet():
    pass


def stringify(p=''):
    res = ''
    for c in p:
        res += '%02x ' % ord(c)
    return res


def unstringify(p=''):
    try:
        return "".join(map(lambda x: chr(int(x, 16)), p.strip().split(" ")))
    except ValueError:
        return ""


def debug_print(data="", prepend="", hex_byte=0, crc=False):
    if settings.DEBUG:
        crc_d = ""
        s_message = "[%s] " % timezone.now()

        if prepend:
            s_message += "{%s} " % prepend

        if crc:
            crc_d = data[-1]
            data = data[:-1]

        if data:
            if hex_byte > 0:
                s_message += 'DATA: %s HEX: %s ' % (data[:hex_byte], stringify(data[hex_byte:]))
            else:
                s_message += 'DATA: %s ' % data

        if crc:
            s_message += "CRC: getted = %02x, calculated = %02x" % (ord(crc_d), calc_crc8(data))

        print(s_message)


class DeviceBase(object):
    pass


class MetaDevice(type):

    device_classes = {}

    def __init__(cls, cls_name, cls_bases, cls_dict):

        super(MetaDevice, cls).__init__(cls_name, cls_bases, cls_dict)

        if cls_name not in MetaDevice.device_classes:
            MetaDevice.device_classes[cls_name] = cls
            #TODO: get all known instances
            cls.devices = {}

    def __call__(cls, *args, **kwargs):
        device_id = kwargs.get('device_id', UNCONFIGURED_IDENTIFIER)
        if device_id not in cls.devices:
            device = super(MetaDevice, cls).__call__(*args, **kwargs)
            cls.devices[device_id] = device
        else:
            device = cls.devices[device_id]
        return device


class Device(DeviceBase):
    __metaclass__ = MetaDevice

    @classmethod
    def exists(cls, device_id):
        return device_id in cls.devices

    @classmethod
    def get_by_pk(cls, pk):
        device = None
        for device_id in cls.devices:
            device_to_check = cls.devices[device_id]
            if device_to_check.pk == pk:
                device = device_to_check
                break
        return device

    @classmethod
    def get_cronjob_and_device_by_command_pk(cls, pk):
        cronjob = None
        device = None
        for device_id in cls.devices:
            device_to_check = cls.devices[device_id]
            if pk in device_to_check.cronjobs:
                device = device_to_check
                cronjob = device.cronjobs[pk]
                break
        return cronjob, device

    def __init__(self, device_id=UNCONFIGURED_IDENTIFIER, ip=None, mac=None, port=None, is_online=False, udp_handshake=None):
        self._ip = ip
        self._mac = mac
        self._device_id = device_id
        self._pk = None
        self._port = port
        self._is_online = is_online
        self.udp_handshake = udp_handshake
        self._commands_queue = []
        self.cronjobs = {}
        self.device_instance = None
        if device_id != SERVER_IDENTIFIER:
            try:
                self.device_instance = DBDevice.objects.get(identifier=device_id)
            except DBDevice.DoesNotExist:
                self.device_instance = DBDevice(identifier=device_id, title="Неизвестная")
                self.device_instance.save()
            self._pk = self.device_instance.pk

            self.device_instance.mac = self.mac
            self.device_instance.ip = self.ip
            self.device_instance.port = self.port
            self.device_instance.is_online = self.is_online

            self.device_instance.save()

            # self.push_command(CommandCodes.connect_to, SERVER_IP)

            def add_echo(d):
                if len(d.commands_queue) == 0:
                    d.push_command(CommandCodes.echo, ECHO_DATA)

            if ECHO_INTERVAL is not None:
                task.LoopingCall(add_echo, self).start(ECHO_INTERVAL)

        debug_print(prepend="Device #%s created!" % self._device_id)

    @property
    def commands_queue(self):
        return self._commands_queue

    def set_online(self):

        if COMMAND_QUEUE_CLEAR_ON_CONNECT:
            self._commands_queue = []

        def get_mac_cb(_self):
            def set_mac(data):
                _self.mac = stringify(data[1:])
                if _self.device_instance is not None:
                    for command in _self.device_instance.commands.filter(exec_type=DBCommand.ON_CONNECT):
                        print "Add transaction #%s: %s" % (command.pk, command.template.script)
                        _self.push_command(command_instance=command, transaction=command.template.script)

                    for command in _self.device_instance.commands.filter(exec_type=DBCommand.ON_CRON):
                        print "Schedule transaction #%s: %s" % (command.pk, command.template.script)
                        _self.push_cronjob(command_instance=command)

            def get_mac(data):
                if data[1:] != SUCCESS_DATA:
                    print "Cannot set server IP!"
                self.push_command(CommandCodes.mac_get, callback=set_mac, retry_on_fail=True)

            return get_mac

        self.is_online = True
        self.push_command(CommandCodes.connect_to, SERVER_IP, retry_on_fail=True, callback=get_mac_cb(self))

    def remove_cronjob(self, pk=None, command_instance=None):
        if command_instance is None and pk is None:
            return False
        elif pk is None:
            pk = command_instance.pk

        if pk in self.cronjobs:
            cronjob = self.cronjobs[pk]
            try:
                if cronjob["timeout"] is not None:
                    cronjob["timeout"].cancel()
                    cronjob["timeout"] = None
            except error.AlreadyCalled:
                pass
            del self.cronjobs[pk]
            return True
        else:
            return False

    def push_cronjob(self, command_instance=None, pk=None):
        if command_instance is None and pk is None:
            return False
        elif pk is None:
            pk = command_instance.pk

        if pk in self.cronjobs:
            self.remove_cronjob(pk=pk)

        command_instance = DBCommand.objects.filter(pk=pk).filter(exec_type=DBCommand.ON_CRON).first()
        if command_instance is None:
            return False
        else:
            def crontab_command_f(_self, _pk):
                def crontab_command():
                    _command_instance = _self.device_instance.commands.filter(pk=pk).filter(exec_type=DBCommand.ON_CRON).first()
                    if _command_instance is None:
                        _self.remove_cronjob(_pk)
                        return False
                    else:
                        if _self.is_online:
                            _self.push_command(transaction=_command_instance.template.script, command_instance=_command_instance)
                        crontab = CronTab(_command_instance.cron)
                        timeout = reactor.callLater(crontab.next(), crontab_command_f(_self, _pk))
                        _self.cronjobs[_pk] = {"timeout": timeout,
                                               "crontab": crontab,
                                               "command_instance": _command_instance}
                    return True
                return crontab_command

            crontab = CronTab(command_instance.cron)
            timeout = reactor.callLater(crontab.next(), crontab_command_f(self, pk))
            self.cronjobs[pk] = {"timeout": timeout,
                                 "crontab": crontab,
                                 "command_instance": command_instance}
            return True

    def push_command(self, command=None, data="", command_instance=None, clearable=True, retry_on_fail=False, device_id=None,
                     callback=None, transaction=None):

        if transaction is not None and not isinstance(transaction, list):
            if "\n" in transaction:
                transaction = filter(lambda x: x, map(lambda x: unstringify(x), transaction.strip().split("\n")))
            else:
                data = transaction
                transaction = None

        if transaction is None and command is None:
            if data:
                tmp = unstringify(data)
                if tmp is not None:
                    data = tmp
                command = ord(data[0])
                data = data[1:]
            else:
                return False

        self._commands_queue.append({"timestamp": timezone.now(),
                                     "command": command if transaction is None else "",
                                     "command_instance": command_instance,
                                     "transaction": transaction,
                                     "data": data if transaction is None else "",
                                     "retry_on_fail": retry_on_fail,
                                     "device_id": device_id if device_id is not None else self.device_id,
                                     "clearable": clearable,
                                     "callback": callback})

        i = 0
        while i < len(self._commands_queue) and len(self._commands_queue) > COMMAND_QUEUE_LENGTH_MAX:
            if self._commands_queue[i]["clearable"]:
                try:
                    self._commands_queue.remove(i)
                except ValueError:
                    break
            else:
                i += 1

        return True

    def pop_command(self):
        if len(self._commands_queue) == 0:
            return None
        else:
            return self._commands_queue.pop(0)

    @property
    def pk(self):
        return self._pk

    @property
    def mac(self):
        return self._mac

    @mac.setter
    def mac(self, value):
        if value and value != self._mac:
            old = self._mac
            self._mac = value
            if self.device_instance is not None and self.device_instance.mac != value:
                self.device_instance.mac = value
                self.device_instance.save()
            else:
                def set_cb(_self, _old):
                    def _set(data):
                        if data[1:] != SUCCESS_DATA:
                            _self.mac = _old
                            print "Cannot set MAC!"
                        else:
                            self.push_command(CommandCodes.reboot)
                    return _set

                self.push_command(CommandCodes.mac_set, unstringify(value), retry_on_fail=True, callback=set_cb(self, old))

    @property
    def ip(self):
        return self._ip

    @ip.setter
    def ip(self, value):
        if value and value != self._ip:
            self._ip = value
            if self.device_instance is not None and self.device_instance.ip != value:
                self.device_instance.ip = value
                self.device_instance.save()
            else:
                def set_cb():
                    def _set(data):
                        if data[1:] != SUCCESS_DATA:
                            print "Cannot set IP!"
                    return _set

                self.push_command(CommandCodes.ip_set, "".join(map(lambda x: chr(int(x)), value.split('.'))),
                                  callback=set_cb())

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, value):
        if 0 < value < 65535 and value != self._port:
            old = self._port
            self._port = value
            if self.device_instance is not None and self.device_instance.port != value:
                self.device_instance.port = value
                self.device_instance.save()
            else:
                def set_cb(_self, _old):
                    def _set(data):
                        if data[1:] != SUCCESS_DATA:
                            _self.port = _old
                            print "Cannot set port!"
                        else:
                            self.push_command(CommandCodes.reboot)
                    return _set

                self.push_command(CommandCodes.port_set, struct.pack("<H", value), retry_on_fail=True,
                                  callback=set_cb(self, old))

    @property
    def is_online(self):
        return self._is_online

    @is_online.setter
    def is_online(self, value):
        if value is not None and value != self._is_online:
            self._is_online = value
            if self.device_instance is not None:
                self.device_instance.is_online = value
                self.device_instance.save()

    @property
    def device_id(self):
        return self._device_id

    @device_id.setter
    def device_id(self, value):
        if 0 < value < 65535 and value != self._device_id:
            del Device.devices[self._device_id]
            old = self._device_id
            self._device_id = value
            Device.devices[self._device_id] = self
            if DBDevice.objects.filter(identifier=value).first() is None:
                if self.device_instance is not None:
                    self.device_instance.identifier = value
                    self.device_instance.save()
            else:
                def set_cb(_self, _old):
                    def _set(data):
                        if data[1:] != SUCCESS_DATA:
                            _self.device_id = _old
                            print "Cannot set device ID!"
                        else:
                            if self.udp_handshake is not None:
                                self.udp_handshake.change_device_id(old, value)
                    return _set

                self.push_command(CommandCodes.id_set, struct.pack("<H", value), device_id=old, retry_on_fail=True,
                                  callback=set_cb(self, old))


@receiver(post_save, sender=DBDevice, dispatch_uid="update_device")
def update_device(sender, instance, **kwargs):
    device = Device.get_by_pk(instance.pk)
    if device is not None:
        device.device_instance = instance

        if instance.ip is not None and instance.ip != device.ip:
            device.ip = instance.ip

        if instance.mac is not None and instance.mac != device.mac:
            device.mac = instance.mac

        if instance.port is not None and instance.port != device.port:
            device.port = instance.port

        if instance.identifier is not None and instance.identifier != device.device_id:
            device.device_id = instance.identifier


@receiver(post_save, sender=DBCommand, dispatch_uid="update_device")
def update_commands(sender, instance, **kwargs):
    device = Device.get_by_pk(instance.device.pk)
    if instance.exec_type == DBCommand.ON_SAVE and instance.exec_count < 1:
        if device is not None:
            device.push_command(transaction=instance.template.script, command_instance=instance)
    elif instance.exec_type == DBCommand.ON_CRON:
        (cronjob, device_old) = Device.get_cronjob_and_device_by_command_pk(instance.pk)
        if device_old is not None and device_old != device:
            device_old.remove_cronjob(pk=instance.pk)
        device.push_cronjob(pk=instance.pk)


class TCPReceiver(Protocol):
    def __init__(self, addr, device):
        self.buffer = ""
        self.buffer_length = 0
        self.addr = addr
        self.waiting_for_reply = False
        self.waiting_timeout = None
        self.retry_timeout = None
        self.sleep_timeout = None
        self.check_command_timeout = None
        self.retry_count = 0
        self.is_connected = False
        print "TCP Create!"
        self.device = device
        self.command = None
        self.packet_id = 0

    def forgot_packet(self):
        self.receive_packet()

    def send_packet(self):
        if not self.waiting_for_reply:

            command = self.command or self.device.pop_command()
            if command is not None and self.is_connected:

                self.command = command
                if not "result" in self.command:
                    self.command["result"] = ""

                if not self.command["command"] and not self.command["data"]:
                    if self.command["transaction"]:
                        while self.command["transaction"]:
                            c = self.command["transaction"].pop(0)
                            if c:
                                self.command["command"] = ord(c[0])
                                self.command["data"] = c[1:]
                                break
                    if not self.command["command"]:
                        self.command["command"] = CommandCodes.do_nothing

                if self.command["command"] != CommandCodes.do_nothing:
                    packet = Packet(device_id=SERVER_IDENTIFIER, command=command["command"],
                                    packet_id=self.packet_id, packet_data=command["data"],
                                    packet_type=PacketType.command)

                    debug_print(packet.raw_packet, "CMD (send) %s" % self.addr, 3, True)
                    self.transport.write(packet.raw_packet)
                    dp = DBDebugPacket(data=stringify(packet.raw_packet), device=self.device.device_instance,
                                       ip=self.device.ip, port=self.device.port, protocol=DBDebugPacket.PROTOCOL_TCP,
                                       prefix=packet.raw_packet[:3])
                    dp.save()

                    self.waiting_for_reply = True
                    self.waiting_timeout = reactor.callLater(MAX_TCP_WAITING_FOR_REPLY, self.forgot_packet)
                else:
                    fake_packet = Packet(device_id=self.command["device_id"], command=self.command["command"],
                                         packet_data="\x00", packet_type=PacketType.command_reply,
                                         packet_id=self.packet_id)
                    self.sleep_timeout = reactor.callLater(ord(self.command["data"][0])/DO_NOTHING_DIVIDER
                                                           if self.command["data"] else 0,
                                                           self.receive_packet, fake_packet.raw_packet)

            else:
                self.check_command_timeout = reactor.callLater(COMMAND_QUEUE_CHECK_INTERVAL, self.send_packet)

    def receive_packet(self, raw=""):

        success = False
        packet = None
        error_message = ""
        disconnect = False
        command_done = False
        wait_delay = 0

        if self.waiting_timeout is not None:
            try:
                self.waiting_timeout.cancel()
            except error.AlreadyCalled:
                pass

            self.waiting_for_reply = False
            self.waiting_timeout = None

        self.waiting_for_reply = False

        if self.retry_timeout is not None:
            try:
                self.retry_timeout.cancel()
            except error.AlreadyCalled:
                pass

            self.retry_timeout = None

        if raw:
            packet = Packet(raw_packet=raw)
            if packet.is_valid:
                if packet.packet_type == PacketType.command_reply:
                    if self.command is not None:
                        if self.command["device_id"] == packet.device_id:
                            if self.command["command"] == packet.command:
                                if packet.packet_id == self.packet_id:
                                    success = True
                                    self.retry_count = 0
                                    debug_print(packet.raw_packet, "REP (OK) %s" % self.addr, 3, True)
                                else:
                                    error_message = "REP (wrong packet ID (expected) %s != %s (got)) %s" %\
                                                    (self.packet_id, packet.packet_id, self.addr)
                            else:
                                error_message = "REP (wrong command code (expected) %s != %s (got)) %s" %\
                                                (self.command["command"], packet.command, self.addr)
                        else:
                            error_message = "REP (wrong device ID (expected) %s != %s (got)) %s" %\
                                            (self.command["device_id"], packet.device_id, self.addr)
                            if DISCONNECT_ON_WRONG_ID:
                                disconnect = True
                    else:
                        error_message = "REP (WE'RE NOT WAITING FOR REPLY!) %s" % self.addr
                        if DISCONNECT_ON_DUPLICATE:
                            disconnect = True
                else:
                    error_message = "REP (invalid type (expected) %s != %s (got)) %s" %\
                                    (PacketType.command_reply, packet.packet_type, self.addr)
            else:
                error_message = "REP (invalid packet) %s" % self.addr

            dp = DBDebugPacket(data=stringify(packet.raw_packet), device=self.device.device_instance,
                               ip=self.device.ip, port=self.device.port, protocol=DBDebugPacket.PROTOCOL_TCP,
                               prefix=packet.raw_packet[:3])
            dp.save()
        else:
            error_message = "REP (timeout reached) %s" % self.addr

        self.packet_id += 1
        if self.packet_id > 255:
            self.packet_id = 0

        if error_message:
            if packet:
                debug_print(packet.raw_packet, error_message, 3, True)
            else:
                debug_print(prepend=error_message)

        if disconnect:
            self.lose_connection()

        if success:
            self.command["result"] += stringify(chr(packet.command) + packet.packet_data) + "\r\n"
            if not self.command["transaction"]:
                command_done = True
            else:
                self.command["command"] = None
                self.command["data"] = None

        elif self.command is not None:
            if self.command["retry_on_fail"]:
                if TIMEOUT_BEFORE_RETRY:
                    self.retry_count += 1
                    if self.retry_count > MAX_RETRY_COUNT:
                        command_done = True
                    else:
                        wait_delay = TIMEOUT_BEFORE_RETRY
                else:
                    command_done = True
            else:
                command_done = True
        else:
            command_done = False

        if command_done:
            self.command["result"] = self.command["result"].strip()
            if self.command["command_instance"] is not None:
                ci = self.command["command_instance"]
                ci.exec_count += 1
                ci.save()
                ch = DBCommandHistory(command=self.command["command_instance"],
                                      success=success,
                                      error_message=error_message,
                                      result=self.command["result"].strip())
                ch.save()
            if self.command["callback"] is not None:
                if "\n" in self.command["result"]:
                    result_raw = map(lambda x: unstringify(x), self.command["result"].strip().split("\n"))
                else:
                    result_raw = unstringify(self.command["result"])
                self.command["callback"](result_raw)
            self.command = None

        reactor.callLater(wait_delay, self.send_packet)

    def connectionMade(self):
        self.device.set_online()
        self.is_connected = True
        self.buffer = ""
        self.buffer_length = 0
        self.send_packet()

    def lose_connection(self):
        try:
            if self.retry_timeout is not None:
                self.retry_timeout.cancel()
                self.retry_timeout = None
        except error.AlreadyCalled:
            pass

        try:
            if self.sleep_timeout is not None:
                self.sleep_timeout.cancel()
                self.sleep_timeout = None
        except error.AlreadyCalled:
            pass

        try:
            self.waiting_for_reply = False
            if self.waiting_timeout is not None:
                self.waiting_timeout.cancel()
                self.waiting_timeout = None
        except error.AlreadyCalled:
            pass

        try:
            if self.check_command_timeout is not None:
                self.check_command_timeout.cancel()
                self.check_command_timeout = None
        except error.AlreadyCalled:
            pass

        self.transport.loseConnection()

    def connectionLost(self, reason):
        self.device.is_online = False
        self.is_connected = False

    def dataReceived(self, data):
        p = ""
        self.buffer += data

        if len(self.buffer) > 3 and self.buffer.find(PacketType.command_reply) != -1:
            self.buffer = self.buffer[self.buffer.find(PacketType.command_reply):]

        if self.buffer.startswith(PacketType.command_reply):
            if self.buffer_length == 0:
                if len(self.buffer) >= 8:
                    self.buffer_length = ord(self.buffer[7]) + 9

            if self.buffer_length and self.buffer_length <= len(self.buffer):
                p = self.buffer
                self.buffer = self.buffer[self.buffer_length:]
                self.buffer_length = 0

        if p:
            self.receive_packet(p)


class TCPClientFactory(ReconnectingClientFactory):

    maxRetries = MAX_TCP_RECONNECT_RETRIES
    maxDelay = MAX_TCP_RECONNECT_DELAY

    def __init__(self, device, disconnect_callback):
        self.receiver = None
        self.addr = None
        self.fail_count = 0
        self.device = device
        self.disconnect_callback = disconnect_callback

    def startedConnecting(self, connector):
        pass
        # print('Started to connect.')

    def buildProtocol(self, addr):
        # print('Resetting reconnection delay')
        self.resetDelay()
        _receiver = TCPReceiver(addr, self.device)
        self.receiver = _receiver
        self.addr = addr
        return _receiver

    def clientConnectionLost(self, connector, reason):
        # print('Lost connection.  Reason:', reason)
        if DISCONNECT_ON_CONNECTION_LOST:
            if self.receiver is not None:
                self.receiver.lose_connection()
            self.disconnect_callback()
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        # print('Connection failed. Reason:', reason)
        if DISCONNECT_ON_CONNECTION_LOST:
            if self.receiver is not None:
                self.receiver.lose_connection()
            self.disconnect_callback()
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)


class UDPHandshake(DatagramProtocol):

    def __init__(self):
        self.found_devices_by_id = {}
        self.found_devices_by_host_and_port = {}

    def change_device_id(self, old, new):
        if old in self.found_devices_by_id:
            self.found_devices_by_id[new] = self.found_devices_by_id[old]
            self.found_devices_by_id[new]["device_id"] = new
            del self.found_devices_by_id[old]

    def disconnect_by_id(self, device_id):
        # print "Disconnect #%s (%s:%s)" % (device_id, self.found_devices[device_id]["host"], self.found_devices[device_id]["port"])
        if device_id in self.found_devices_by_id:
            self.found_devices_by_id[device_id]["factory"].stopTrying()
            client = self.found_devices_by_id[device_id]["client"]
            del self.found_devices_by_host_and_port["%s:%s" % (self.found_devices_by_id[device_id]["host"],
                                                               self.found_devices_by_id[device_id]["port"])]
            del self.found_devices_by_id[device_id]
            client.disconnect()

    def disconnect_by_host_and_port(self, host, port):
        # print "Disconnect #%s (%s:%s)" % (device_id, self.found_devices[device_id]["host"], self.found_devices[device_id]["port"])
        host_and_port = "%s:%s" % (host, port)
        if host_and_port in self.found_devices_by_host_and_port:
            self.found_devices_by_host_and_port[host_and_port]["factory"].stopTrying()
            client = self.found_devices_by_host_and_port[host_and_port]["client"]
            del self.found_devices_by_id[self.found_devices_by_host_and_port[host_and_port]["device_id"]]
            del self.found_devices_by_host_and_port[host_and_port]
            client.disconnect()

    def datagramReceived(self, data, (host, port)):
        host_and_port = "%s:%s" % (host, port)
        packet = Packet(raw_packet=data)
        d = None
        if packet.is_valid:
            if packet.packet_type == PacketType.broadcast:
                print "DATAGRAM create!"
                d = Device(device_id=packet.device_id, ip=host, port=port, udp_handshake=self)

                if d.udp_handshake is None:
                    d.udp_handshake = self
                if packet.device_id in self.found_devices_by_id and\
                        (host != self.found_devices_by_id[packet.device_id]["host"] or
                         port != self.found_devices_by_id[packet.device_id]["port"]):
                    d.ip = host
                    d.port = port
                    self.disconnect_by_id(packet.device_id)

                elif host_and_port in self.found_devices_by_host_and_port and\
                        packet.device_id != self.found_devices_by_host_and_port[host_and_port]["device_id"]:
                    d.ip = host
                    d.port = port
                    self.disconnect_by_host_and_port(host, port)

                if packet.device_id in self.found_devices_by_id:
                    self.found_devices_by_id[packet.device_id]["wrong_brd_count"] += 1
                    if self.found_devices_by_id[packet.device_id]["wrong_brd_count"] > ALREADY_CONNECTED_LIMIT_TO_RESET:
                        debug_print(packet.raw_packet, "SIG (TOO MANY, RESET) %s:%s" % (host, port), 3, True)
                        self.disconnect_by_id(packet.device_id)

                if packet.device_id not in self.found_devices_by_id:
                    def disconnect_clb(_self, device):
                        def f():
                            _self.disconnect_by_id(device.device_id)
                        return f

                    debug_print(packet.raw_packet, "SIG (NEW) %s:%s" % (host, port), 3, True)
                    tcp_client = TCPClientFactory(d, disconnect_clb(self, d))
                    self.found_devices_by_id[packet.device_id] = {"client": reactor.connectTCP(host, port, tcp_client),
                                                                  "factory": tcp_client,
                                                                  "device_id": packet.device_id,
                                                                  "host": host,
                                                                  "port": port,
                                                                  "wrong_brd_count": 0}
                    self.found_devices_by_host_and_port["%s:%s" % (host, port)] =\
                        self.found_devices_by_id[packet.device_id]

                else:
                    debug_print(packet.raw_packet, "SIG (ALREADY CONNECTED) %s:%s" % (host, port), 3, True)
            else:
                debug_print(prepend="Wrong usage of the handshake port!")
        else:
            debug_print(prepend="Invalid packet received on handshake port!")

        dp = DBDebugPacket(data=stringify(packet.raw_packet), device=d.device_instance if d is not None else None,
                           ip=host, port=port, protocol=DBDebugPacket.PROTOCOL_UDP, prefix=packet.raw_packet[:3])
        dp.save()


class UDPData(DatagramProtocol):

    def __init__(self):
        pass

    def datagramReceived(self, data, (host, port)):
        packet = Packet(raw_packet=data)
        d = None
        if packet.is_valid:
            if packet.packet_type == PacketType.data:
                d = Device(device_id=packet.device_id)
                if d.device_instance is not None:
                    for sensor in d.device_instance.sensors.all():
                        if sensor.identifier == packet.command:
                            r = packet.packet_data[sensor.sensor_type.start:][:sensor.sensor_type.length]
                            try:
                                i = struct.unpack(sensor.sensor_type.template, r)[0]
                                t = type(i)
                                sh = DBSensorHistory(sensor=sensor, result="%s %s" % (i, sensor.sensor_type.unit))
                                sh.save()
                                for command in sensor.commands.filter(compare_with__isnull=False):
                                    try:
                                        c = t("%s" % command.compare_with)
                                        if (command.compare_type == DBCommand.COMPARE_E and i == c) or \
                                           (command.compare_type == DBCommand.COMPARE_NE and i != c) or \
                                           (command.compare_type == DBCommand.COMPARE_GT and i > c) or \
                                           (command.compare_type == DBCommand.COMPARE_GTE and i >= c) or \
                                           (command.compare_type == DBCommand.COMPARE_LT and i < c) or \
                                           (command.compare_type == DBCommand.COMPARE_LTE and i <= c):
                                            d.push_command(command_instance=command,
                                                           transaction=command.template.script)

                                    except ValueError:
                                        debug_print(prepend="Wrong compare type (%s) or value (%s) for #%s" %
                                                            (t, command.compare_with, sensor.pk))
                            except struct.error:
                                debug_print(prepend="Wrong struct template (%s) or value (%s) for #%s" %
                                                    (sensor.sensor_type.template, stringify(r),
                                                     sensor.pk))
                debug_print(packet.raw_packet, "DAT %s:%s" % (host, port), 3, True)
            else:
                debug_print(prepend="Wrong usage of the data port!")
        else:
            debug_print(prepend="Invalid packet received on data port!")

        dp = DBDebugPacket(data=stringify(packet.raw_packet), device=d.device_instance if d is not None else None,
                           ip=host, port=port, protocol=DBDebugPacket.PROTOCOL_UDP, prefix=packet.raw_packet[:3])
        dp.save()


wsgi_site = Site(WSGIResource(reactor, reactor.getThreadPool(), django_app))
reactor.listenTCP(80, wsgi_site)
reactor.listenUDP(UDP_BROADCAST, UDPHandshake())
reactor.listenUDP(UDP_DATA, UDPData())


reactor.run()

