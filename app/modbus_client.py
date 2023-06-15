"""Modbus Client module.

This module provides a client class for interacting with Modbus devices using the Modbus TCP protocol.
The `ModbusClient` class encapsulates the functionality of the Modbus client, including the ability
to write coils and registers.

Example:
    Instantiate a `ModbusClient` object with a configuration and a Modbus TCP client:

    ```
    configuration = Configuration(...)
    modbus_client = ModbusTcpClient(...)
    client = ModbusClient(configuration, modbus_client)

    client.write_coil("coil_name", True)
    client.write_coils("coil_name", [True, False, True])
    client.write_register("register_name", 123)
    ```

Note:
    This module requires the `pymodbus` package to be installed.

"""

import logging

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
from app.configuration import Configuration, HoldingRegister
from app.payload_builder import PayloadBuilder
from app.exceptions import UnknownCommandError, ModbusClientError, InvalidMessageError
from app.error_handler import ErrorHandler


class ModbusClient:
    _client: ModbusTcpClient

    def __init__(
        self,
        configuration: Configuration,
        error_handler: ErrorHandler,
        modbus_client: ModbusTcpClient = None,
    ) -> None:
        self.configuration = configuration
        self.error_handler = error_handler
        self._client = modbus_client or ModbusTcpClient(
            configuration.get_modbus_settings().host,
            port=configuration.get_modbus_settings().port,
        )

    def write_coils(self, name: str, value: list[bool]):
        coil_configuration = self.configuration.get_coil(name)
        if coil_configuration:
            try:
                self._client.connect()
                self._client.write_coils(coil_configuration.address[0], value)
                self._client.close()
                logging.debug(f"wrote to coil {name}, value: {value!r}")
                return len(value)
            except ModbusException as ex:
                self.error_handler.publish(ex)
                raise ModbusClientError(ex)
        return 0

    def write_coil(self, name: str, value: bool):
        coil_configuration = self.configuration.get_coil(name)
        if coil_configuration:
            try:
                self._client.connect()
                self._client.write_coil(coil_configuration.address[0], value, 1)
                self._client.close()
                logging.debug(f"wrote to coil {name}, value: {value!r}")
                return 1
            except ModbusException as ex:
                self.error_handler.publish(ex)
                raise ModbusClientError(ex)
        return 0

    def write_register(self, name: str, value):
        holding_register_configuration = self.configuration.get_holding_register(name)
        if holding_register_configuration:
            try:
                payload = _build_register_payload(holding_register_configuration, value)
            except Exception as ex:
                self.error_handler.publish(ex)
                raise InvalidMessageError(ex)
            try:
                self._client.connect()
                self._client.write_registers(
                    holding_register_configuration.address[0], payload, 1
                )
                self._client.close()
                logging.debug(f"wrote to register {name}, value: {value!r}")
                return 1
            except ModbusException as ex:
                self.error_handler.publish(ex)
                raise ModbusClientError(ex)
        return 0

    def write_command(self, name: str, value):
        sent = 0

        coil_configuration = self.configuration.get_coil(name)
        if coil_configuration:
            sent += self.write_coil(name, bool(value))

        holding_register_configuration = self.configuration.get_holding_register(name)
        if holding_register_configuration:
            sent += self.write_register(name, value)

        if sent == 0:
            ex = UnknownCommandError(name)
            self.error_handler.publish(ex)
            raise ex


def _build_register_payload(holding_register: HoldingRegister, value):
    payload_builder = PayloadBuilder()
    payload_builder.set_data_type(holding_register.data_type)
    payload_builder.set_value(value)
    payload_builder.set_memory_order(holding_register.memory_order)
    return payload_builder.build()
