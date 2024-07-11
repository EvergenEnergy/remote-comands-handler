"""Message decoding and validation module.

This module encapsulates the functionality required to read and validate an incoming MQTT message.
"""

import json
from json import JSONDecodeError
import logging
from pydantic import validate_call, ValidationError

from app.exceptions import InvalidMessageError, UnknownCommandError
from app.configuration import Configuration, InputTypes


class CommandMessageList:
    """Create a CommandMessage object and retrieve its configuration."""

    @classmethod
    def read(cls, message_str: str):
        try:
            message_list = json.loads(message_str)
        except JSONDecodeError as ex:
            raise InvalidMessageError(f"Message is invalid JSON syntax: {ex}")

        for message_obj in message_list:
            if not isinstance(message_obj, dict):
                raise InvalidMessageError("Message object must be a dict")
            if not message_obj.get("action") or "value" not in message_obj:
                raise InvalidMessageError(
                    "Message is missing required components 'action' and/or 'value'"
                )
        return message_list


class CommandMessage:
    """Create a CommandMessage object and retrieve its configuration."""

    def __init__(self, name: str, value, configuration: Configuration) -> None:
        self.name = name
        self.value = value
        self.configuration = configuration.get_coil(
            self.name
        ) or configuration.get_holding_register(self.name)
        if self.configuration:
            self.input_type = self.configuration.input_type
        else:
            raise UnknownCommandError(self.name)

    def validate(self):
        MessageValidator.validate(self.input_type, self.value)

    def transform(self):
        if self.input_type == InputTypes.REGISTER:
            self.value = MessageTransformer.transform(self.configuration, self.value)
            MessageValidator.validate(self.input_type, self.value)


class MessageValidator:
    @classmethod
    @validate_call
    def is_bool(cls, value: bool) -> bool:
        return True

    @classmethod
    def validate(cls, input_type, value):
        if input_type == InputTypes.COIL:
            try:
                cls.is_bool(value)
            except ValidationError:
                raise InvalidMessageError(
                    f"The {input_type.lower()} value {value!r} is invalid."
                )

        # TODO validate register inputs


class MessageTransformer:
    @classmethod
    def transform(cls, configuration, value):
        tvalue = value
        if configuration.scale:
            value = configuration.scale * value
            if "INT" in configuration.data_type:
                value = int(value)
        if configuration.invert_sign:
            value = -1 * value
        logging.debug(
            f"transformed value {value} with config {configuration} to {tvalue}"
        )
        return value


class ErrorMessage:
    """Write an object in JSON format."""

    @classmethod
    def write(cls, message: dict):
        try:
            return json.dumps(message)
        except (TypeError, ValueError, OverflowError) as ex:
            logging.error(f"Couldn't write message {message}")
            raise InvalidMessageError(f"JSON object cannot be serialised: {ex}")
