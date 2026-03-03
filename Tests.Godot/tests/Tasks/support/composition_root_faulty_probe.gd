extends Node

var invoked := false

func InjectCompositionPorts(_time_port, _input_port, _resource_loader_port, _data_store_port, _logger_port, _event_bus_port) -> bool:
    invoked = true
    return false
