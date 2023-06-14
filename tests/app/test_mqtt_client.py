"""Unit tests for the MqttClient class in the app.mqtt_client module."""

from unittest.mock import MagicMock, Mock
import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTTMessage
from app.mqtt_client import MqttClient
import pytest
import json


class TestMqttClient:
    def setup_class(self):
        self.mock_mqtt_client = MagicMock(spec=mqtt.Client)
        self.mqtt_client = MqttClient(
            port=1883, host="localhost", client=self.mock_mqtt_client
        )

    def test_run(self):
        topic_list = ["foo", "baa"]
        self.mqtt_client.subscribe_topics(topic_list)

        mock_modbus = Mock()
        self.mqtt_client.add_message_callback(mock_modbus.message_callback)

        def call_on_connect(*args):
            callback = self.mqtt_client._on_connect()
            callback(self.mock_mqtt_client, None, None, 0)

        # Assume connect method always successful
        self.mock_mqtt_client.connect.return_value = 0
        self.mock_mqtt_client.connect.side_effect = call_on_connect

        # Run the method
        self.mqtt_client.run()

        # Verify that connect was called with the correct parameters
        self.mock_mqtt_client.connect.assert_called_with("localhost", 1883)
        # and it called the callback which subscribed to our topics
        self.mock_mqtt_client.subscribe.call_count == len(topic_list)

        # Pretend that the MQTT broker received a message and our callback is called
        json_obj = {"action": "test_coil", "value": True}
        json_str = json.dumps(json_obj)
        paho_msg = MQTTMessage()
        paho_msg.payload = json_str.encode()
        self.mock_mqtt_client.on_message(self.mock_mqtt_client, None, paho_msg)
        mock_modbus.message_callback.assert_called_with(json_obj)

    def test_bad_message(self, caplog):
        def read_json(json_str):
            json.loads(json_str)

        self.mqtt_client.add_message_callback(read_json)
        self.mqtt_client.run()

        bad_json_str = "{'invalid', 'json'}"
        paho_msg = MQTTMessage()
        paho_msg.payload = bad_json_str.encode()
        self.mock_mqtt_client.on_message(self.mock_mqtt_client, None, paho_msg)
        msg_str = str(caplog.records[0].message)
        assert "Message is invalid JSON" in msg_str

        self.mqtt_client.stop()

    def test_fail_connect(self):
        self.mock_mqtt_client.connect.side_effect = OSError("could not connect")
        with pytest.raises(OSError) as ex:
            self.mqtt_client.run()
        assert "Cannot assign requested" in str(ex.value)

    def test_fail_connect_rc(self, caplog):
        def call_on_connect(*args):
            callback = self.mqtt_client._on_connect()
            callback(self.mock_mqtt_client, None, None, 1)
            assert str(caplog.records[0].message) == "Connection failed"

        self.mock_mqtt_client.connect.side_effect = call_on_connect
        self.mqtt_client.run()
        self.mqtt_client.stop()
