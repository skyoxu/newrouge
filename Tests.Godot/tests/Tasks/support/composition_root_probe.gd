extends Node

var injected := false
var ports := {}

func InjectCompositionPorts(time_port, input_port, resource_loader_port, data_store_port, logger_port, event_bus_port) -> void:
    injected = true
    ports = {
        "time": time_port,
        "input": input_port,
        "resourceLoader": resource_loader_port,
        "dataStore": data_store_port,
        "logger": logger_port,
        "eventBus": event_bus_port
    }

func has_non_null_port(port_name: String) -> bool:
    return ports.has(port_name) and ports[port_name] != null
