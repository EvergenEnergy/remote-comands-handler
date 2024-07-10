import os
import time
import json
import random

import pytest
from pytest import approx

import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

from app.configuration import Configuration


@pytest.fixture(scope="module")
def mqtt_client():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect("localhost", 1883, 60)
    yield client  # provide the client for tests
    client.disconnect()  # disconnect after tests


@pytest.fixture(scope="module")
def modbus_client():
    client = ModbusTcpClient("localhost", 5020)
    client.connect()
    yield client  # provide the client for tests
    client.close()  # close after tests


@pytest.fixture(scope="module")
def config():
    yield Configuration.from_file("tests/end-to-end/configuration.yaml")


def publish_message(mqtt_client: mqtt.Client, name: str, value: str):
    message_dictionary = [{"action": name, "value": value}]
    message = json.dumps(message_dictionary)

    mqtt_client.publish("commands/test", message)

    time.sleep(1)


@pytest.mark.end_to_end
@pytest.mark.parametrize("coil_value", [False, True])
def test_able_to_update_coil(
    mqtt_client: mqtt.Client,
    modbus_client: ModbusTcpClient,
    config: Configuration,
    coil_value: bool,
):
    coil_name = "testCoil"
    publish_message(mqtt_client, coil_name, coil_value)

    coil = config.get_coil(coil_name)
    value = modbus_client.read_coils(coil.address[0], len(coil.address), 1)

    assert value.bits[0] is coil_value


@pytest.mark.end_to_end
def test_able_to_send_integer16(
    mqtt_client: mqtt.Client, modbus_client: ModbusTcpClient, config: Configuration
):
    reg_name = "testInt16Register"
    random_value = random.randint(20000, 30000)
    publish_message(mqtt_client, reg_name, random_value)

    register = config.get_holding_register(reg_name)
    value = modbus_client.read_holding_registers(
        register.address[0], len(register.address), 1
    )

    assert value.registers[0] == random_value


@pytest.mark.end_to_end
def test_able_to_send_float32(
    mqtt_client: mqtt.Client, modbus_client: ModbusTcpClient, config: Configuration
):
    reg_name = "testFloatRegister"
    random_value = random.uniform(20000, 30000)
    publish_message(mqtt_client, reg_name, random_value)

    register = config.get_holding_register(reg_name)
    value = modbus_client.read_holding_registers(
        register.address[0], len(register.address), 1
    )

    decoder = BinaryPayloadDecoder.fromRegisters(
        value.registers, Endian.BIG, wordorder=Endian.BIG
    )

    assert decoder.decode_32bit_float() == approx(random_value, rel=1e-6)


@pytest.mark.end_to_end
def test_able_to_send_command_with_float64(
    mqtt_client: mqtt.Client, modbus_client: ModbusTcpClient, config: Configuration
):
    reg_name = "testFloat64Register"
    random_value = random.uniform(200000, 300000)
    publish_message(mqtt_client, reg_name, random_value)

    register = config.get_holding_register(reg_name)
    value = modbus_client.read_holding_registers(
        register.address[0], len(register.address), 1
    )

    decoder = BinaryPayloadDecoder.fromRegisters(
        value.registers, Endian.BIG, wordorder=Endian.BIG
    )
    assert decoder.decode_64bit_float() == random_value


@pytest.mark.end_to_end
def test_able_to_send_integer64(
    mqtt_client: mqtt.Client, modbus_client: ModbusTcpClient, config: Configuration
):
    reg_name = "testInt64Register"
    random_value = random.randint(40000, 50000)
    publish_message(mqtt_client, reg_name, random_value)

    register = config.get_holding_register(reg_name)
    value = modbus_client.read_holding_registers(
        register.address[0], len(register.address), 1
    )

    decoder = BinaryPayloadDecoder.fromRegisters(
        value.registers, Endian.BIG, wordorder=Endian.BIG
    )

    assert decoder.decode_64bit_int() == random_value


@pytest.mark.end_to_end
def test_able_to_send_uint64(
    mqtt_client: mqtt.Client, modbus_client: ModbusTcpClient, config: Configuration
):
    reg_name = "testUInt64Register"
    random_value = random.randint(400000, 500000)
    publish_message(mqtt_client, reg_name, random_value)

    register = config.get_holding_register(reg_name)
    value = modbus_client.read_holding_registers(
        register.address[0], len(register.address), 1
    )

    decoder = BinaryPayloadDecoder.fromRegisters(
        value.registers, Endian.BIG, wordorder=Endian.BIG
    )

    assert decoder.decode_64bit_uint() == random_value


@pytest.mark.end_to_end
@pytest.mark.parametrize("scale_direction", ["up", "down"])
def test_scale_ints(
    mqtt_client: mqtt.Client,
    modbus_client: ModbusTcpClient,
    config: Configuration,
    scale_direction: str,
):
    reg_name = f"testScaled{scale_direction.title()}Int"
    register = config.get_holding_register(reg_name)

    test_values = {
        "up": [(256, 2560)],
        "down": [(2560, 2), (256, 0)],
    }
    for supplied, expected in test_values[scale_direction]:
        publish_message(mqtt_client, reg_name, supplied)

        value = modbus_client.read_holding_registers(
            register.address[0], len(register.address), 1
        )

        assert value.registers[0] == expected


@pytest.mark.end_to_end
@pytest.mark.parametrize("scale_direction", ["up", "down"])
def test_scale_floats(
    mqtt_client: mqtt.Client,
    modbus_client: ModbusTcpClient,
    config: Configuration,
    scale_direction: str,
):
    reg_name = f"testScaled{scale_direction.title()}Float"
    test_values = {
        "up": [(256.1, 25610), (0.0345, 3.45)],
        "down": [(2560, 25.6), (2.56, 0.0256)],
    }
    for supplied, expected in test_values[scale_direction]:
        publish_message(mqtt_client, reg_name, supplied)

        register = config.get_holding_register(reg_name)
        value = modbus_client.read_holding_registers(
            register.address[0], len(register.address), 1
        )

        decoder = BinaryPayloadDecoder.fromRegisters(
            value.registers, Endian.BIG, wordorder=Endian.BIG
        )

        assert decoder.decode_32bit_float() == approx(expected, rel=1e-6)


@pytest.mark.end_to_end
def test_invert(
    mqtt_client: mqtt.Client, modbus_client: ModbusTcpClient, config: Configuration
):
    reg_name = "testInvert"
    supplied = 897
    expected = -897
    publish_message(mqtt_client, reg_name, supplied)

    register = config.get_holding_register(reg_name)
    value = modbus_client.read_holding_registers(
        register.address[0], len(register.address), 1
    )
    decoder = BinaryPayloadDecoder.fromRegisters(
        value.registers, Endian.BIG, wordorder=Endian.BIG
    )
    assert decoder.decode_16bit_int() == expected

    reg_name = "testScaleAndInvert"
    supplied = 7368
    expected = -736.8
    publish_message(mqtt_client, reg_name, supplied)

    register = config.get_holding_register(reg_name)
    value = modbus_client.read_holding_registers(
        register.address[0], len(register.address), 1
    )
    decoder = BinaryPayloadDecoder.fromRegisters(
        value.registers, Endian.BIG, wordorder=Endian.BIG
    )

    assert decoder.decode_32bit_float() == approx(expected, rel=1e-6)


@pytest.mark.end_to_end
def test_read_error_messages(mqtt_client: mqtt.Client, modbus_client: ModbusTcpClient):
    # Subscribe to the error topic and write messages to file
    msg_log = "/tmp/message_log"
    if os.path.exists(msg_log):
        os.remove(msg_log)

    def read_error(_client, _userdata, message):
        # When we get an error message from MQTT, write it to file
        msg_str = message.payload.decode()
        msg_obj = json.loads(msg_str)
        with open(msg_log, "a") as err:
            err.write(f"{msg_str}\n")
        return msg_obj

    mqtt_client.subscribe("error/#")
    mqtt_client.on_message = read_error

    # Generate two error messages by sending bad commands
    def send_bad_command(msg_obj):
        message = json.dumps([msg_obj])
        mqtt_client.publish("commands/test", message)

    send_bad_command({"invalid": ["message", "structure"]})
    send_bad_command({"action": "NotARealCoil", "value": 0})
    # initial value will be valid but scaled-up value will exceed datatype
    send_bad_command({"action": "testScaledUpInt", "value": 30000})

    # Run the client loop to allow the callback to be executed
    mqtt_client.loop_start()
    time.sleep(1)
    mqtt_client.loop_stop()

    # Check the file for error messages
    with open(msg_log) as err_in:
        line1 = err_in.readline()
        line2 = err_in.readline()
        line3 = err_in.readline()
    assert "InvalidMessage" in line1
    assert "Message is missing required components" in line1
    assert "UnknownCommand" in line2
    assert "No coil or register found to match 'NotARealCoil'" in line2
    assert "InvalidMessage" in line3
    assert "format requires -32768 <= number <= 32767" in line3

    os.remove(msg_log)

    # Confirm that command subscription is still OK
    message_dictionary = {"action": "testCoil", "value": True}
    message = json.dumps(message_dictionary)
    mqtt_client.publish("commands/test", message)
    time.sleep(1)
    value = modbus_client.read_coils(504, 1, 1)
    assert value.bits[0] is True
