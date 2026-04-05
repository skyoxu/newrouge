using System;
using Godot;
using Godot.Collections;
using Game.Core.Contracts;
using Game.Core.Contracts.Interfaces;
using Game.Core.Services;
using Game.Godot.Adapters;

namespace Game.Godot.Scripts.UI;

[GlobalClass]
public partial class Task9RngStateProbe : Node
{
    private static readonly string[] StreamNames =
    {
        RngStreamType.Run,
        RngStreamType.Combat,
        RngStreamType.Event,
        RngStreamType.Loot,
        RngStreamType.Shop,
        RngStreamType.Offer,
    };

    private IRngStreamRegistry _registry = new RngStreamRegistry(20260404);
    private EventBusAdapter? _eventBus;
    private Callable _eventCallable = default!;

    public override void _Ready()
    {
        _eventCallable = new Callable(this, nameof(OnDomainEventEmitted));
        _eventBus = GetNodeOrNull<EventBusAdapter>("/root/EventBus");
        if (_eventBus != null)
        {
            _eventBus.Connect(EventBusAdapter.SignalName.DomainEventEmitted, _eventCallable);
        }
    }

    public override void _ExitTree()
    {
        if (_eventBus != null
            && _eventBus.IsConnected(EventBusAdapter.SignalName.DomainEventEmitted, _eventCallable))
        {
            _eventBus.Disconnect(EventBusAdapter.SignalName.DomainEventEmitted, _eventCallable);
        }
    }

    public void ResetWithSeed(int seed = 20260404)
    {
        _registry = new RngStreamRegistry(seed);
    }

    public Dictionary CapturePositions()
    {
        var positions = new Dictionary();
        foreach (var streamName in StreamNames)
        {
            positions[streamName] = _registry.GetPosition(streamName);
        }

        return positions;
    }

    public Dictionary CaptureSnapshots()
    {
        var snapshots = new Dictionary();
        foreach (var streamName in StreamNames)
        {
            snapshots[streamName] = _registry.Snapshot(streamName);
        }

        return snapshots;
    }

    public void ExecutePureUiAction()
    {
        // Pure UI action path must not mutate deterministic RNG streams.
    }

    public void TriggerGameplayRoll()
    {
        _ = _registry.NextInt(RngStreamType.Combat, 0, 100);
    }

    private void OnDomainEventEmitted(
        string type,
        string source,
        string dataJson,
        string id,
        string specVersion,
        string dataContentType,
        string timestampIso)
    {
        if (string.Equals(type, "ui.menu.start", StringComparison.Ordinal))
        {
            TriggerGameplayRoll();
            return;
        }

        ExecutePureUiAction();
    }
}
