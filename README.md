# MQTT Entity helper library for Home Assistant

[![codecov](https://codecov.io/gh/kellerza/mqtt_entity/branch/main/graph/badge.svg?token=PG4N1YBUGW)](https://codecov.io/gh/kellerza/mqtt_entity)

A Python helper library to manage Home Assistant entities over MQTT.

Features:

- MQTT client based on paho-mqtt
- Manage MQTT discovery info (adding/removing entities)
- MQTTDevice class to manage devices
  - Availability management
  - Manage entities per device
- Entities modelled as classes:
  - Read-only: Sensor, BinarySensor
  - Read & write: Select, Switch, Number
  - MQTT device event
- Asyncio based
- Helper for Home Assistant addon configuration (optional)

## Why?

This MQTT code was included in several of my home Assistant addons (SMA-EM / Sunsynk). It is easier to update a single library & add new features, like discovery removal.

Alternatives options (not based on asyncio)

- <https://pypi.org/project/ha-mqtt-discoverable/>
- <https://pypi.org/project/homeassistant-mqtt-binding/>

## Credits

@Ivan-L contributed some of the writable entities to the Sunsynk addon project

## Release

Semantic versioning is used for release.

To create a new release, include a commit with a :dolphin: emoji as a prefix in the commit message. This will trigger a release on the master branch.

```bash
# Patch
git commit -m ":dolphin: Release 0.0.x"

# Minor
git commit -m ":rocket: Release 0.x.0"
```
