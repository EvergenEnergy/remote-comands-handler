"""MQTT Writer module.

This module provides a client class for publishing messages to MQTT brokers.

"""

import logging

import paho.mqtt.client as mqtt

from app.message import ErrorMessage


class MqttWriter:
    _client: mqtt.Client

    def __init__(self, host: str, port: int, client: mqtt.Client) -> None:
        self.host = host
        self.port = port
        self._client = client
        self._client.on_publish = self._on_publish()

    def connect(self) -> None:
        try:
            self._client.connect(self.host, self.port)
            return True
        except OSError as e:
            ex = OSError(f"Cannot assign requested address: {self.host}:{self.port}")
            raise ex from e

    def publish(self, topic, payload):
        if self.connect():
            self._client.publish(topic, ErrorMessage.write(payload), qos=1)
            return
        logging.error(f"Failed to publish to {topic}: {payload}")

    def _on_publish(self):
        def inner(_client, _userdata, message_id):
            logging.debug(f"Published message with id {message_id}")

        return inner
