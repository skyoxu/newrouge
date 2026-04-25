using System;
using System.Collections.Generic;
using System.IO;
using Godot;

namespace Game.Godot.Scripts.UI;

public partial class MapScene : Control
{
    private const string TitleKey = "ui.map.title";
    private const string HintKey = "ui.map.hint";
    private const string CombatActionKey = "ui.map.action.combat";
    private const string EventActionKey = "ui.map.action.event";
    private const string ShopActionKey = "ui.map.action.shop";
    private const string RestActionKey = "ui.map.action.rest";
    private const string ReadyFeedbackKey = "ui.map.feedback.ready";
    private const string LockedNodeFeedbackKey = "ui.map.feedback.locked_node";
    private const string InvalidBranchFeedbackKey = "ui.map.feedback.invalid_branch";
    private const string CompletedNodeFeedbackKey = "ui.map.feedback.completed_node";
    private const string ReturnedToMapFeedbackKey = "ui.map.feedback.returned_to_map";
    private const string MissingContentFeedbackKey = "ui.map.feedback.missing_content";

    private static readonly Dictionary<string, Dictionary<string, string>> TextMapsByLocale = new(StringComparer.OrdinalIgnoreCase);

    private Label _titleLabel = default!;
    private Label _hintLabel = default!;
    private Label _feedbackLabel = default!;
    private Label _nodeLegendLabel = default!;
    private Button _combatButton = default!;
    private Button _eventButton = default!;
    private Button _shopButton = default!;
    private Button _restButton = default!;
    private string _lastLocale = string.Empty;
    private string _lastInvokedAction = string.Empty;
    private static readonly string[] DefaultNodeOrder = { "combat", "event", "shop", "rest" };
    private readonly List<RouteNode> _routeNodes = new()
    {
        new("combat-01", "combat", 1, "F1 Combat", "F1 战斗"),
        new("event-02", "event", 2, "F2 Event", "F2 事件"),
        new("combat-02", "combat", 2, "F2 Combat", "F2 战斗"),
        new("shop-03", "shop", 3, "F3 Shop", "F3 商店"),
        new("combat-03", "combat", 3, "F3 Reward Fight", "F3 奖励战斗"),
        new("rest-04", "rest", 4, "F4 Rest", "F4 休息"),
        new("boss-05", "combat", 5, "F5 Boss", "F5 首领"),
    };
    private readonly Dictionary<string, Button> _routeButtonsById = new(StringComparer.Ordinal);

    private sealed record RouteNode(string Id, string Type, int Floor, string EnglishLabel, string ChineseLabel);

    public override void _Ready()
    {
        _titleLabel = GetNode<Label>("title_label");
        _hintLabel = GetNode<Label>("hint_label");
        _feedbackLabel = GetNode<Label>("feedback_label");
        _nodeLegendLabel = GetNode<Label>("node_legend_label");
        _combatButton = GetNode<Button>("ActionRow/btn_combat");
        _eventButton = GetNode<Button>("ActionRow/btn_event");
        _shopButton = GetNode<Button>("ActionRow/btn_shop");
        _restButton = GetNode<Button>("ActionRow/btn_rest");
        _combatButton.Pressed += OnCombatPressed;
        _eventButton.Pressed += OnEventPressed;
        _shopButton.Pressed += OnShopPressed;
        _restButton.Pressed += OnRestPressed;
        BindRouteTreeButtons();
        RefreshVisibleTextForTest();
    }

    public override void _ExitTree()
    {
        if (_combatButton is not null)
        {
            _combatButton.Pressed -= OnCombatPressed;
        }

        if (_eventButton is not null)
        {
            _eventButton.Pressed -= OnEventPressed;
        }

        if (_shopButton is not null)
        {
            _shopButton.Pressed -= OnShopPressed;
        }

        if (_restButton is not null)
        {
            _restButton.Pressed -= OnRestPressed;
        }

        _routeButtonsById.Clear();
    }

    public override void _Process(double _delta)
    {
        var locale = NormalizeLocale(TranslationServer.GetLocale());
        if (string.Equals(locale, _lastLocale, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        ApplyLocalizedText(locale);
    }

    public void RefreshVisibleTextForTest()
    {
        ApplyLocalizedText(NormalizeLocale(TranslationServer.GetLocale()));
    }

    public void RefreshLocaleForTest()
    {
        RefreshVisibleTextForTest();
    }

    public bool InvokeActionForTest(string action)
    {
        if (string.IsNullOrWhiteSpace(action))
        {
            return false;
        }

        var normalized = action.Trim().ToLowerInvariant();
        switch (normalized)
        {
            case "combat":
                _combatButton.EmitSignal(BaseButton.SignalName.Pressed);
                return true;
            case "event":
                _eventButton.EmitSignal(BaseButton.SignalName.Pressed);
                return true;
            case "shop":
                _shopButton.EmitSignal(BaseButton.SignalName.Pressed);
                return true;
            case "rest":
                _restButton.EmitSignal(BaseButton.SignalName.Pressed);
                return true;
            default:
                return false;
        }
    }

    public string GetLastInvokedActionForTest()
    {
        return _lastInvokedAction;
    }

    public int GetRouteTreeFloorCountForTest()
    {
        return 5;
    }

    public global::Godot.Collections.Array<string> GetReachableRouteNodeIdsForTest()
    {
        var result = new global::Godot.Collections.Array<string>();
        foreach (var node in _routeNodes)
        {
            if (IsRouteNodeReachable(node))
            {
                result.Add(node.Id);
            }
        }

        return result;
    }

    public global::Godot.Collections.Dictionary InvokeRouteNodeForTest(string nodeId)
    {
        var node = ResolveRouteNode(nodeId);
        if (node is null)
        {
            return new global::Godot.Collections.Dictionary
            {
                { "ok", false },
                { "reason", "unknown-node" },
                { "scene_path", string.Empty },
            };
        }

        if (!IsRouteNodeReachable(node))
        {
            ShowRouteFeedbackForTest("locked_node", node.Id);
            return new global::Godot.Collections.Dictionary
            {
                { "ok", false },
                { "reason", "node-not-reachable" },
                { "scene_path", string.Empty },
            };
        }

        return TryStartRoute(node.Id, node.Type);
    }

    public bool ShowRouteFeedbackForTest(string feedbackKind, string nodeId)
    {
        var key = NormalizeFeedbackKind(feedbackKind) switch
        {
            "locked_node" => LockedNodeFeedbackKey,
            "invalid_branch" => InvalidBranchFeedbackKey,
            "completed_node" => CompletedNodeFeedbackKey,
            "returned_to_map" => ReturnedToMapFeedbackKey,
            "missing_content" => MissingContentFeedbackKey,
            _ => ReadyFeedbackKey,
        };
        var node = string.IsNullOrWhiteSpace(nodeId) ? "node" : nodeId.Trim();
        _feedbackLabel.Text = ResolveVisibleText(key, _lastLocale).Replace("{0}", node, StringComparison.Ordinal);
        return true;
    }

    public string GetFeedbackForTest()
    {
        return _feedbackLabel.Text ?? string.Empty;
    }

    private void ApplyLocalizedText(string locale)
    {
        _lastLocale = locale;
        _titleLabel.Text = ResolveVisibleText(TitleKey, locale);
        _hintLabel.Text = ResolveVisibleText(HintKey, locale);
        _combatButton.Text = ResolveVisibleTextOrFallback(CombatActionKey, locale, "Combat");
        _eventButton.Text = ResolveVisibleTextOrFallback(EventActionKey, locale, "Event");
        _shopButton.Text = ResolveVisibleTextOrFallback(ShopActionKey, locale, "Shop");
        _restButton.Text = ResolveVisibleTextOrFallback(RestActionKey, locale, "Rest");
        _nodeLegendLabel.Text = BuildNodeLegend(locale);
        RefreshRouteTree(locale);
        if (string.IsNullOrWhiteSpace(_feedbackLabel.Text) || string.Equals(_feedbackLabel.Text, ReadyFeedbackKey, StringComparison.Ordinal))
        {
            _feedbackLabel.Text = ResolveVisibleText(ReadyFeedbackKey, locale);
        }
    }

    private static string NormalizeFeedbackKind(string feedbackKind)
    {
        return string.IsNullOrWhiteSpace(feedbackKind)
            ? string.Empty
            : feedbackKind.Trim().Replace('-', '_').ToLowerInvariant();
    }

    private static string ResolveVisibleTextOrFallback(string key, string locale, string fallback)
    {
        var resolved = ResolveVisibleText(key, locale);
        if (string.Equals(resolved, key, StringComparison.Ordinal))
        {
            return fallback;
        }

        return resolved;
    }

    private void OnCombatPressed()
    {
        TryStartRoute("combat");
    }

    private void OnEventPressed()
    {
        TryStartRoute("event");
    }

    private void OnShopPressed()
    {
        TryStartRoute("shop");
    }

    private void OnRestPressed()
    {
        TryStartRoute("rest");
    }

    private void TryStartRoute(string action)
    {
        _ = TryStartRoute($"{action}-01", action);
    }

    private global::Godot.Collections.Dictionary TryStartRoute(string nodeId, string action)
    {
        _lastInvokedAction = action;

        var main = ResolveMainController();
        if (main == null || !main.HasMethod("StartMapNodeRouteForTest"))
        {
            _feedbackLabel.Text = ResolveVisibleText(MissingContentFeedbackKey, _lastLocale).Replace("{0}", action, StringComparison.Ordinal);
            return new global::Godot.Collections.Dictionary
            {
                { "ok", false },
                { "reason", "route-controller-missing" },
                { "scene_path", string.Empty },
            };
        }

        var resultVariant = main.Call("StartMapNodeRouteForTest", nodeId, action, true, string.Empty);
        if (resultVariant.VariantType != Variant.Type.Dictionary)
        {
            _feedbackLabel.Text = ResolveVisibleText(MissingContentFeedbackKey, _lastLocale).Replace("{0}", action, StringComparison.Ordinal);
            return new global::Godot.Collections.Dictionary
            {
                { "ok", false },
                { "reason", "route-result-invalid" },
                { "scene_path", string.Empty },
            };
        }

        var result = (global::Godot.Collections.Dictionary)resultVariant;
        var ok = result.ContainsKey("ok") && result["ok"].AsBool();
        if (ok)
        {
            _feedbackLabel.Text = ResolveVisibleText(ReturnedToMapFeedbackKey, _lastLocale).Replace("{0}", action, StringComparison.Ordinal);
            return result;
        }

        var reason = result.ContainsKey("reason") ? result["reason"].AsString() : string.Empty;
        if (string.Equals(reason, "unsupported-node-type", StringComparison.Ordinal))
        {
            _feedbackLabel.Text = ResolveVisibleText(MissingContentFeedbackKey, _lastLocale).Replace("{0}", action, StringComparison.Ordinal);
            return result;
        }

        if (!string.IsNullOrWhiteSpace(reason))
        {
            _feedbackLabel.Text = reason;
            return result;
        }

        _feedbackLabel.Text = ResolveVisibleText(MissingContentFeedbackKey, _lastLocale).Replace("{0}", action, StringComparison.Ordinal);
        return result;
    }

    private void BindRouteTreeButtons()
    {
        foreach (var node in _routeNodes)
        {
            var buttonName = node.Id.Replace('-', '_');
            var button = GetNodeOrNull<Button>($"RouteTree/Floor{node.Floor}/{buttonName}");
            if (button is null)
            {
                continue;
            }

            _routeButtonsById[node.Id] = button;
            button.Pressed += () => InvokeRouteNodeForTest(node.Id);
        }
    }

    private RouteNode? ResolveRouteNode(string nodeId)
    {
        if (string.IsNullOrWhiteSpace(nodeId))
        {
            return null;
        }

        var normalized = nodeId.Trim();
        foreach (var node in _routeNodes)
        {
            if (string.Equals(node.Id, normalized, StringComparison.Ordinal))
            {
                return node;
            }
        }

        return null;
    }

    private bool IsRouteNodeReachable(RouteNode node)
    {
        return node.Floor == ResolveCurrentReachableFloor();
    }

    private int ResolveCurrentReachableFloor()
    {
        var completed = ResolveCompletedNodeCount();
        return Math.Clamp(completed + 1, 1, 5);
    }

    private int ResolveCompletedNodeCount()
    {
        var main = ResolveMainController();
        if (main is null || !main.HasMethod("GetMapRouteCompletedNodeCountForTest"))
        {
            return 0;
        }

        var value = main.Call("GetMapRouteCompletedNodeCountForTest");
        return value.VariantType == Variant.Type.Int ? Math.Max(0, value.AsInt32()) : 0;
    }

    private Node? ResolveMainController()
    {
        Node? current = this;
        while (current is not null)
        {
            if (current.HasMethod("StartMapNodeRouteForTest"))
            {
                return current;
            }

            current = current.GetParent();
        }

        return GetNodeOrNull<Node>("/root/Main");
    }

    private void RefreshRouteTree(string locale)
    {
        var reachableFloor = ResolveCurrentReachableFloor();
        var zh = locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase);
        foreach (var node in _routeNodes)
        {
            if (!_routeButtonsById.TryGetValue(node.Id, out var button) || button is null)
            {
                continue;
            }

            button.Text = zh ? node.ChineseLabel : node.EnglishLabel;
            button.Disabled = node.Floor != reachableFloor;
        }
    }

    private string BuildNodeLegend(string locale)
    {
        var labels = new List<string>(DefaultNodeOrder.Length);
        foreach (var nodeType in DefaultNodeOrder)
        {
            labels.Add(ResolveVisibleText($"ui.map.action.{nodeType}", locale));
        }

        return string.Join(" -> ", labels);
    }

    private static string ResolveVisibleText(string key, string locale)
    {
        var map = GetTextMap(locale);
        if (map.TryGetValue(key, out var value) && !string.IsNullOrWhiteSpace(value))
        {
            return value;
        }

        if (!string.Equals(locale, "en", StringComparison.OrdinalIgnoreCase))
        {
            var fallback = GetTextMap("en");
            if (fallback.TryGetValue(key, out var fallbackValue) && !string.IsNullOrWhiteSpace(fallbackValue))
            {
                return fallbackValue;
            }
        }

        var localized = TranslationServer.Translate(key);
        return !string.Equals(localized, key, StringComparison.Ordinal) && IsReadableVisibleText(localized)
            ? localized
            : key;
    }

    private static bool IsReadableVisibleText(string value)
    {
        return !string.IsNullOrWhiteSpace(value)
            && !value.Contains("??", StringComparison.Ordinal)
            && !value.Contains('\uFFFD');
    }

    private static Dictionary<string, string> GetTextMap(string locale)
    {
        if (TextMapsByLocale.TryGetValue(locale, out var cached))
        {
            return cached;
        }

        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        var candidatePaths = locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase)
            ? new[] { "res://Game.Godot/Translations/zh-CN.csv", "res://../Game.Godot/Translations/zh-CN.csv" }
            : new[] { "res://Game.Godot/Translations/en.csv", "res://../Game.Godot/Translations/en.csv" };

        string? raw = null;
        foreach (var candidate in candidatePaths)
        {
            var absolutePath = ProjectSettings.GlobalizePath(candidate);
            if (!File.Exists(absolutePath))
            {
                continue;
            }

            raw = File.ReadAllText(absolutePath);
            break;
        }

        if (string.IsNullOrWhiteSpace(raw))
        {
            TextMapsByLocale[locale] = map;
            return map;
        }

        foreach (var line in raw.Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            var trimmed = line.Trim();
            if (string.IsNullOrWhiteSpace(trimmed) || trimmed.StartsWith("key,value", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var separator = trimmed.IndexOf(',');
            if (separator <= 0 || separator >= trimmed.Length - 1)
            {
                continue;
            }

            var mapKey = trimmed[..separator].Trim();
            var mapValue = trimmed[(separator + 1)..].Trim();
            if (!string.IsNullOrWhiteSpace(mapKey) && !string.IsNullOrWhiteSpace(mapValue))
            {
                map[mapKey] = mapValue;
            }
        }

        TextMapsByLocale[locale] = map;
        return map;
    }

    private static string NormalizeLocale(string locale)
    {
        if (string.IsNullOrWhiteSpace(locale))
        {
            return "en";
        }

        return locale.Trim().Replace('_', '-').ToLowerInvariant();
    }
}
