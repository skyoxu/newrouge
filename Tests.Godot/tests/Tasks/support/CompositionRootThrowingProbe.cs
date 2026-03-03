using System;
using Godot;

public partial class CompositionRootThrowingProbe : Node
{
    private bool _invoked;

    public bool InjectCompositionPorts(
        Node _timePort,
        Node _inputPort,
        Node _resourceLoaderPort,
        Node _dataStorePort,
        Node _loggerPort,
        Node _eventBusPort
    )
    {
        _invoked = true;
        throw new InvalidOperationException("simulated-throwing-hook");
    }

    public bool WasInvoked() => _invoked;
}
