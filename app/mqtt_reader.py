"""MQTT Reader module.

This module provides a client class for subscribing to topics and receiving messages from MQTT brokers.

"""

import logging
from typing import Callable

import paho.mqtt.client as mqtt

from app.message import CommandMessage, CommandMessageList
from app.configuration import Configuration
from app.exceptions import InvalidMessageError, UnknownCommandError
from app.error_handler import ErrorHandler


def _decode_message(message):
    return message.payload.decode()


class MqttReader:
    def __init__(
        self,
        configuration: Configuration,
        client: mqtt.Client,
        error_handler: ErrorHandler,
    ) -> None:
        self.configuration = configuration
        self.error_handler = error_handler
        self._on_message_callbacks = []
        self._client = client

        self._host = configuration.get_mqtt_settings().host
        self._port = configuration.get_mqtt_settings().port
        self._topics = [configuration.mqtt_settings.command_topic]

    def add_message_callback(self, f: Callable[[str], None]):
        self._on_message_callbacks.append(f)

    def connect(self) -> None:
        try:
            self._client.connect(self._host, self._port)
            return True
        except OSError as e:
            ex = OSError(f"Cannot connect to MQTT broker at {self._host}:{self._port}")
            raise ex from e

    def stop(self) -> None:
        self._client.disconnect()

    def run(self) -> None:
        """Run the MQTT client.

        This method blocks the execution and keeps the client connected to the MQTT broker.
        """
        self._client.on_connect = self._on_connect()
        self._client.on_disconnect = self._on_disconnect()
        self._client.on_message = self._on_message()

        self.connect()

        logging.info("Service started")
        self._client.loop_forever()

    def _on_message(self):
        def inner(_client, _userdata, message):
            msg_topic = message.topic
            msg_str = ""
            msg_obj_list = []
            try:
                try:
                    msg_str = _decode_message(message)
                    msg_list = CommandMessageList.read(msg_str)
                    for msg_dict in msg_list:
                        msg_obj = CommandMessage(
                            msg_dict["action"], msg_dict["value"], self.configuration
                        )
                        msg_obj.validate()
                        msg_obj.transform()
                        msg_obj_list.append(msg_obj)
                except InvalidMessageError as ex:
                    self.error_handler.publish(
                        self.error_handler.Category.INVALID_MESSAGE, str(ex)
                    )
                    return
                except UnknownCommandError as ex:
                    self.error_handler.publish(
                        self.error_handler.Category.UNKNOWN_COMMAND, str(ex)
                    )
                    return
                for msg_obj in msg_obj_list:
                    for callback in self._on_message_callbacks:
                        callback(msg_obj)
            # In general it's not good practice to catch Exception, but we're doing so here
            # in order to trap unhandled exceptions occurring within message processing,
            # and prevent them rising up to the main loop.
            # If these occur, the cause should be identified and code changed to catch them.
            except Exception as ex:
                logging.error(f"Encountered error {ex} on topic {msg_topic}")
                logging.info(msg_str)
                self.error_handler.publish(
                    self.error_handler.Category.UNHANDLED, str(ex)
                )

        return inner

    def _on_connect(self):
        def inner(client, _userdata, _flags, reason_code, _properties):
            if reason_code == 0:
                logging.info("Connected to MQTT broker")
                for topic in self._topics:
                    logging.info("Subscribing to topic: %s", topic)
                    client.subscribe(topic)
            else:
                logging.error(f"Problem connecting to MQTT broker: {reason_code}")

        return inner

    def _on_disconnect(self):
        def inner(client, _userdata, reason_code, _properties):
            if reason_code > 0:
                logging.error(f"MQTT client has disconnected: {reason_code}")

        return inner
