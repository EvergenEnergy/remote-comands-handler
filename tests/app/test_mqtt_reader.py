"""Unit tests for the MqttReader class in the app.mqtt_reader module."""

from unittest.mock import MagicMock, Mock
import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTTMessage
from app.message import CommandMessage
from app.mqtt_reader import MqttReader
from app.error_handler import ErrorHandler
from app.configuration import Configuration
import pytest
import json


class TestMqttReader:
    def setup_method(self):
        self.mock_mqtt_client = MagicMock(spec=mqtt.Client)
        self.mock_error_handler = MagicMock(spec=ErrorHandler)
        self.configuration = Configuration.from_file(
            "tests/config/example_configuration.yaml"
        )
        self.mqtt_reader = MqttReader(
            configuration=self.configuration,
            client=self.mock_mqtt_client,
            error_handler=self.mock_error_handler,
        )

    def test_run(self):
        mock_modbus = Mock()
        self.mqtt_reader.add_message_callback(mock_modbus.message_callback)

        def call_on_connect(*args):
            callback = self.mqtt_reader._on_connect()
            callback(self.mock_mqtt_client, None, None, 0, None)

        # Assume connect method always successful
        self.mock_mqtt_client.connect.return_value = 0
        self.mock_mqtt_client.connect.side_effect = call_on_connect

        # Run the method
        self.mqtt_reader.run()

        # Verify that connect was called with the parameters from the example config
        self.mock_mqtt_client.connect.assert_called_with("mqtt.host", 9000)
        # and it called the callback which subscribed to our topics
        self.mock_mqtt_client.subscribe.call_count == 1

        # Pretend that the MQTT broker received a message and our callback is called
        json_obj = [{"action": "evgBatteryModeCoil", "value": True}]
        json_str = json.dumps(json_obj)
        msg_obj = CommandMessage(
            json_obj[0]["action"], json_obj[0]["value"], self.configuration
        )
        paho_msg = MQTTMessage()
        paho_msg.payload = json_str.encode()
        self.mock_mqtt_client.on_message(self.mock_mqtt_client, None, paho_msg)
        mocked_args, _ = mock_modbus.message_callback.call_args
        mocked_obj = mocked_args[0]
        assert mocked_obj.name == msg_obj.name
        assert mocked_obj.input_type == msg_obj.input_type

    def test_bad_message(self):
        def read_json(json_str):
            json.loads(json_str)

        self.mqtt_reader.add_message_callback(read_json)
        self.mqtt_reader.run()

        bad_json_str = "{'invalid', 'json'}"
        paho_msg = MQTTMessage()
        paho_msg.payload = bad_json_str.encode()
        self.mock_mqtt_client.on_message(self.mock_mqtt_client, None, paho_msg)
        self.mock_error_handler.publish.assert_called_with(
            self.mock_error_handler.Category.INVALID_MESSAGE,
            "Message is invalid JSON syntax: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)",  # noqa
        )

        bad_json_str = '["list","without","dict"]'
        paho_msg = MQTTMessage()
        paho_msg.payload = bad_json_str.encode()
        self.mock_mqtt_client.on_message(self.mock_mqtt_client, None, paho_msg)
        self.mock_error_handler.publish.assert_called_with(
            self.mock_error_handler.Category.INVALID_MESSAGE,
            "Message object must be a dict",
        )

        bad_json_str = '[{"action":"but no value"}]'
        paho_msg = MQTTMessage()
        paho_msg.payload = bad_json_str.encode()
        self.mock_mqtt_client.on_message(self.mock_mqtt_client, None, paho_msg)
        self.mock_error_handler.publish.assert_called_with(
            self.mock_error_handler.Category.INVALID_MESSAGE,
            "Message is missing required components 'action' and/or 'value'",
        )

        self.mqtt_reader.stop()

    def test_unknown_message(self):
        self.mqtt_reader.run()

        unknown_msg = json.dumps([{"action": "noSuchCoil", "value": False}])
        paho_msg = MQTTMessage()
        paho_msg.payload = unknown_msg.encode()
        self.mock_mqtt_client.on_message(self.mock_mqtt_client, None, paho_msg)
        self.mock_error_handler.publish.assert_called_with(
            self.mock_error_handler.Category.UNKNOWN_COMMAND,
            "No coil or register found to match 'noSuchCoil'",
        )

        self.mqtt_reader.stop()

    def test_fail_connect(self):
        self.mock_mqtt_client.connect.side_effect = OSError("could not connect")
        with pytest.raises(OSError) as ex:
            self.mqtt_reader.run()
        assert "Cannot connect to MQTT broker" in str(ex.value)

    def test_disconnect(self, caplog):
        self.mock_mqtt_client.connect.return_value = 0
        self.mqtt_reader.run()
        callback = self.mock_mqtt_client.on_disconnect
        callback(self.mock_mqtt_client, None, 1, None)
        assert "MQTT client has disconnected: 1" == str(caplog.records[0].message)

    def test_fail_connect_rc(self, caplog):
        def call_on_connect(*args):
            callback = self.mqtt_reader._on_connect()
            callback(self.mock_mqtt_client, None, None, 1, None)

        self.mock_mqtt_client.connect.side_effect = call_on_connect
        self.mqtt_reader.run()
        self.mqtt_reader.stop()
        assert "Problem connecting to MQTT broker: 1" == str(caplog.records[0].message)

    def test_unhandled_exception(self):
        def process_message(json_str):
            raise RuntimeError("didn't expect that!")

        self.mqtt_reader.add_message_callback(process_message)
        self.mqtt_reader.run()

        paho_msg = MQTTMessage()
        json_str = json.dumps([{"action": "evgBatteryModeCoil", "value": True}])
        paho_msg.payload = json_str.encode()
        self.mock_mqtt_client.on_message(self.mock_mqtt_client, None, paho_msg)
        self.mock_error_handler.publish.assert_called_with(
            self.mock_error_handler.Category.UNHANDLED, "didn't expect that!"
        )

        self.mqtt_reader.stop()
