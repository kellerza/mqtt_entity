# MQTT Entity helper library for Home Assistant
[![codecov](https://codecov.io/gh/kellerza/mqtt_entity/branch/main/graph/badge.svg?token=PG4N1YBUGW)](https://codecov.io/gh/kellerza/mqtt_entity)

A Python helper library to manage Home Assistant entities over MQTT.

Features:
- MQTT entity discovery info (persistent messages)
- Option to remove persistent discovery info
- Availability management
- Manage entities per device
- Entities modelled as classes
- Supported entities:
  - Read-only: Sensor, BinarySensor
  - Read & write: Select, Switch, Number
- Asyncio based

MQTTClient based on paho-mqtt.

## Why?

This MQTT code was included in several of my home Assistant addons (SMA-EM / Sunsynk) and finally decided to extract it in a separate library to leverage recent updates & features like discovery removal.

Alternatives options (not based on asyncio)
- https://pypi.org/project/ha-mqtt-discoverable/
- https://pypi.org/project/homeassistant-mqtt-binding/

## Credits

@Ivan-L contributed some of the writable entities to the Sunsynk addon project
