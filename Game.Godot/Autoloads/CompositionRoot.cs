using System;
using Game.Core.Ports;
using Game.Core.Contracts.Interfaces;
using Godot;

namespace Game.Godot.Autoloads;

/// <summary>
/// Composition root for adapter layer. Provides port implementations
/// backed by Godot APIs and wires global event bus/logging.
/// Configure this class as an Autoload (Singleton) in project.godot.
/// </summary>
public partial class CompositionRoot : Node
{
    public const string InjectionHookMethodName = "InjectCompositionPorts";
    public const int InjectionHookParameterCount = 6;

    public static CompositionRoot? Instance { get; private set; }

    public ITime Time { get; private set; } = default!;
    public IInput Input { get; private set; } = default!;
    public IResourceLoader ResourceLoader { get; private set; } = default!;
    public IDataStore DataStore { get; private set; } = default!;
    public ILogger Logger { get; private set; } = default!;
    public IEventBus EventBus { get; private set; } = default!;

    private Adapters.TimeAdapter? _timeAdapter;
    private Adapters.InputAdapter? _inputAdapter;
    private Adapters.ResourceLoaderAdapter? _resourceLoaderAdapter;
    private Adapters.DataStoreAdapter? _dataStoreAdapter;
    private Adapters.LoggerAdapter? _loggerAdapter;
    private Adapters.EventBusAdapter? _eventBusAdapter;

    private readonly global::Godot.Collections.Array<string> _initializationErrors = new();
    private readonly global::Godot.Collections.Array<string> _injectionErrors = new();
    private bool _initialized;

    public override void _EnterTree()
    {
        Instance = this;
        if (!_initialized)
        {
            InitializeAdapters();
        }
    }

    public override void _Ready()
    {
        if (_initialized) return;
        InitializeAdapters();
    }

    private void InitializeAdapters()
    {
        if (_initialized)
        {
            return;
        }

        try
        {
            // Create adapter nodes as children to ensure lifecycle managed by scene tree.
            _timeAdapter = new Adapters.TimeAdapter();
            _inputAdapter = new Adapters.InputAdapter();
            _resourceLoaderAdapter = new Adapters.ResourceLoaderAdapter();
            _dataStoreAdapter = new Adapters.DataStoreAdapter();
            _loggerAdapter = new Adapters.LoggerAdapter();
            _eventBusAdapter = new Adapters.EventBusAdapter();

            AddChild(_timeAdapter);
            AddChild(_inputAdapter);
            AddChild(_resourceLoaderAdapter);
            AddChild(_dataStoreAdapter);
            AddChild(_loggerAdapter);
            AddChild(_eventBusAdapter);

            Time = _timeAdapter;
            Input = _inputAdapter;
            ResourceLoader = _resourceLoaderAdapter;
            DataStore = _dataStoreAdapter;
            Logger = _loggerAdapter;
            EventBus = _eventBusAdapter;

            _initialized = true;
        }
        catch (Exception ex)
        {
            _initializationErrors.Add(ex.Message);
            GD.PushError($"[CompositionRoot] initialization failed: {ex.Message}");
        }
    }

    // Expose a simple status map for GDScript without accessing C# properties directly
    public global::Godot.Collections.Dictionary PortsStatus()
    {
        var d = new global::Godot.Collections.Dictionary
        {
            { "time", Time != null },
            { "input", Input != null },
            { "resourceLoader", ResourceLoader != null },
            { "dataStore", DataStore != null },
            { "logger", Logger != null },
            { "eventBus", EventBus != null },
        };
        return d;
    }

    public bool HasInitializationErrors() => _initializationErrors.Count > 0;

    public global::Godot.Collections.Array<string> InitializationErrors()
    {
        var result = new global::Godot.Collections.Array<string>();
        foreach (var error in _initializationErrors)
        {
            result.Add(error);
        }

        return result;
    }

    public bool HasInjectionErrors() => _injectionErrors.Count > 0;

    public global::Godot.Collections.Array<string> InjectionErrors()
    {
        var result = new global::Godot.Collections.Array<string>();
        foreach (var error in _injectionErrors)
        {
            result.Add(error);
        }

        return result;
    }

    public void ClearInjectionErrors() => _injectionErrors.Clear();

    public bool InjectNode(Node target)
    {
        if (!_initialized || HasInitializationErrors())
        {
            return false;
        }

        if (target == null)
        {
            return false;
        }

        if (!HasValidInjectionHook(target))
        {
            var nodeName = string.IsNullOrWhiteSpace(target.Name) ? "<unnamed>" : target.Name.ToString();
            var message = $"InjectNode rejected invalid hook signature for {nodeName}";
            _injectionErrors.Add(message);
            GD.PushError($"[CompositionRoot] {message}");
            return false;
        }

        if (_timeAdapter is null
            || _inputAdapter is null
            || _resourceLoaderAdapter is null
            || _dataStoreAdapter is null
            || _loggerAdapter is null
            || _eventBusAdapter is null)
        {
            return false;
        }

        try
        {
            var result = target.Call(
                InjectionHookMethodName,
                _timeAdapter,
                _inputAdapter,
                _resourceLoaderAdapter,
                _dataStoreAdapter,
                _loggerAdapter,
                _eventBusAdapter
            );

            if (result.VariantType == Variant.Type.Bool && !result.AsBool())
            {
                var nodeName = string.IsNullOrWhiteSpace(target.Name) ? "<unnamed>" : target.Name.ToString();
                var message = $"InjectNode returned false for {nodeName}";
                _injectionErrors.Add(message);
                GD.PushError($"[CompositionRoot] {message}");
                return false;
            }

            return true;
        }
        catch (Exception ex)
        {
            var nodeName = string.IsNullOrWhiteSpace(target.Name) ? "<unnamed>" : target.Name.ToString();
            var message = $"InjectNode failed for {nodeName}: {ex.GetType().Name}: {ex.Message}";
            _injectionErrors.Add(message);
            GD.PushError($"[CompositionRoot] {message}");
            return false;
        }
    }

    private static bool HasValidInjectionHook(Node target)
    {
        if (!target.HasMethod(InjectionHookMethodName))
        {
            return false;
        }

        var methods = target.GetMethodList();
        foreach (var item in methods)
        {
            if (item is not global::Godot.Collections.Dictionary method)
            {
                continue;
            }

            var name = method.ContainsKey("name") ? method["name"].ToString() : null;
            if (!string.Equals(name, InjectionHookMethodName, StringComparison.Ordinal))
            {
                continue;
            }

            if (!method.ContainsKey("args"))
            {
                return InjectionHookParameterCount == 0;
            }

            var argsVariant = method["args"];
            if (argsVariant.VariantType != Variant.Type.Array)
            {
                return false;
            }

            var args = argsVariant.AsGodotArray();
            return args.Count == InjectionHookParameterCount;
        }

        return false;
    }
}
