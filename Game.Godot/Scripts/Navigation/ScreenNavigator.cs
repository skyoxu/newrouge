using Godot;

namespace Game.Godot.Scripts.Navigation;

public partial class ScreenNavigator : Node
{
    [Export] public NodePath ScreenRootPath { get; set; } = new NodePath("../ScreenRoot");
    [Export] public NodePath OverlaysPath { get; set; } = new NodePath("../Overlays");
    [Export] public bool UseFadeTransition { get; set; } = true;
    [Export] public float FadeDurationSec { get; set; } = 0.25f;

    private Control? _root;
    private Control? _overlays;
    private Node? _current;
    private bool _busy;
    private readonly Godot.Collections.Array<string> _routeHistory = new();
    private string _currentScenePath = string.Empty;

    public override void _Ready()
    {
        _root = GetNodeOrNull<Control>(ScreenRootPath);
        if (_root == null)
        {
            GD.PushWarning("[Navigator] ScreenRoot not found; navigation disabled.");
        }
        _overlays = GetNodeOrNull<Control>(OverlaysPath);
    }

    public bool SwitchTo(string scenePath)
    {
        if (_busy) return false;
        if (_root == null) return false;
        var packed = ResourceLoader.Load<PackedScene>(scenePath);
        if (packed == null)
        {
            GD.PushWarning($"[Navigator] Scene not found: {scenePath}");
            return false;
        }
        if (UseFadeTransition && _overlays != null)
        {
            _ = FadeAndSwitch(packed, scenePath);
            return true;
        }
        DoSwitch(packed, scenePath);
        return true;
    }

    public Godot.Collections.Array<string> GetRouteHistoryForTest()
    {
        return new Godot.Collections.Array<string>(_routeHistory);
    }

    public string GetCurrentScenePathForTest()
    {
        return _currentScenePath;
    }

    public void ClearRouteHistoryForTest()
    {
        _routeHistory.Clear();
        _currentScenePath = string.Empty;
    }

    private void DoSwitch(PackedScene packed, string scenePath)
    {
        // Call Exit on current if present, then remove
        if (_current != null)
        {
            if (_current.HasMethod("Exit")) _current.CallDeferred("Exit");
            _current.QueueFree();
            _current = null;
        }
        var inst = packed.Instantiate();
        _root!.AddChild(inst);
        _current = inst;
        _currentScenePath = scenePath;
        _routeHistory.Add(scenePath);
        if (_current.HasMethod("Enter")) _current.CallDeferred("Enter");
    }

    private async System.Threading.Tasks.Task FadeAndSwitch(PackedScene packed, string scenePath)
    {
        if (_overlays == null)
        {
            DoSwitch(packed, scenePath);
            return;
        }
        _busy = true;
        var fade = new ColorRect
        {
            Name = "__ScreenFade__",
            Color = new Color(0, 0, 0, 0),
            MouseFilter = Control.MouseFilterEnum.Stop // block input during transition
        };
        fade.SetAnchorsPreset(Control.LayoutPreset.FullRect);
        _overlays.AddChild(fade);
        var tween = _overlays.CreateTween();
        tween.TweenProperty(fade, "color:a", 1.0, FadeDurationSec).SetTrans(Tween.TransitionType.Cubic).SetEase(Tween.EaseType.In);
        await ToSignal(tween, Tween.SignalName.Finished);

        // Switch content while fully faded
        DoSwitch(packed, scenePath);

        var tween2 = _overlays.CreateTween();
        tween2.TweenProperty(fade, "color:a", 0.0, FadeDurationSec).SetTrans(Tween.TransitionType.Cubic).SetEase(Tween.EaseType.Out);
        await ToSignal(tween2, Tween.SignalName.Finished);
        fade.QueueFree();
        _busy = false;
    }
}
