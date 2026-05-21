using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
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
    private Label _edgeLegendLabel = default!;
    private VBoxContainer _routeEdgeContainer = default!;
    private Button _combatButton = default!;
    private Button _eventButton = default!;
    private Button _shopButton = default!;
    private Button _restButton = default!;
    private string _lastLocale = string.Empty;
    private string _lastInvokedAction = string.Empty;
    private static readonly string[] DefaultNodeOrder = { "combat", "event", "shop", "rest" };
    private static readonly string[] ActConfigCandidatePaths =
    {
        "res://Game.Core/Data/act1-config.json",
        "res://../Game.Core/Data/act1-config.json",
    };
    private static readonly List<RouteNode> FallbackRouteNodes = new()
    {
        new("combat-01", "combat", 1, "F1 Combat", "F1 战斗"),
        new("event-02", "event", 2, "F2 Event", "F2 事件"),
        new("combat-02", "combat", 2, "F2 Combat", "F2 战斗"),
        new("shop-03", "shop", 3, "F3 Shop", "F3 商店"),
        new("combat-03", "combat", 3, "F3 Reward Fight", "F3 奖励战斗"),
        new("rest-04", "rest", 4, "F4 Rest", "F4 休息"),
        new("boss-05", "combat", 5, "F5 Boss", "F5 首领"),
    };
    private static readonly List<RouteEdge> FallbackRouteEdges = new()
    {
        new("combat-01", "event-02", 1, 2),
        new("combat-01", "combat-02", 1, 2),
        new("event-02", "shop-03", 2, 3),
        new("combat-02", "combat-03", 2, 3),
        new("shop-03", "rest-04", 3, 4),
        new("combat-03", "rest-04", 3, 4),
        new("rest-04", "boss-05", 4, 5),
    };
    private readonly List<RouteNode> _routeNodes;
    private readonly List<RouteEdge> _routeEdges;
    private readonly Dictionary<string, Button> _routeButtonsById = new(StringComparer.Ordinal);
    private static readonly Color NodeStateReachableColor = new(0.78f, 1.0f, 0.78f, 1.0f);
    private static readonly Color NodeStateLockedColor = new(0.66f, 0.66f, 0.66f, 1.0f);
    private static readonly Color NodeStateCompletedColor = new(0.66f, 0.86f, 1.0f, 1.0f);
    private static readonly Color NodeStateSelectedPathColor = new(1.0f, 0.88f, 0.55f, 1.0f);
    private static readonly Color EdgeStateReachableColor = new(0.78f, 1.0f, 0.78f, 1.0f);
    private static readonly Color EdgeStateLockedColor = new(0.70f, 0.70f, 0.70f, 1.0f);
    private static readonly Color EdgeStateCompletedColor = new(0.66f, 0.86f, 1.0f, 1.0f);
    private static readonly Color EdgeStateSelectedPathColor = new(1.0f, 0.88f, 0.55f, 1.0f);

    private sealed record RouteNode(string Id, string Type, int Floor, string EnglishLabel, string ChineseLabel);
    private sealed record RouteEdge(string FromId, string ToId, int FromFloor, int ToFloor);

    public MapScene()
    {
        var graph = LoadRouteGraph();
        _routeNodes = graph.Nodes;
        _routeEdges = graph.Edges;
    }

    public override void _Ready()
    {
        _titleLabel = GetNode<Label>("title_label");
        _hintLabel = GetNode<Label>("hint_label");
        _feedbackLabel = GetNode<Label>("feedback_label");
        _nodeLegendLabel = GetNode<Label>("node_legend_label");
        _edgeLegendLabel = GetNode<Label>("edge_legend_label");
        _routeEdgeContainer = GetNode<VBoxContainer>("RouteEdgeContainer");
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
        return _routeNodes.Count == 0 ? 0 : _routeNodes.Max(node => node.Floor);
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
        RefreshEdgeLegend();
        RefreshEdgeVisuals();
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

    public global::Godot.Collections.Array<global::Godot.Collections.Dictionary> GetRouteEdgesForTest()
    {
        var completedNodeOrder = ResolveCompletedNodeOrder();
        var completedEdgeKeys = BuildCompletedEdgeKeys(completedNodeOrder);
        var selectedNodeId = ResolveSelectedNodeId();
        var reachableFloor = ResolveCurrentReachableFloor();
        var result = new global::Godot.Collections.Array<global::Godot.Collections.Dictionary>();
        foreach (var edge in _routeEdges)
        {
            var state = ResolveEdgeVisualState(
                edge.FromId,
                edge.ToId,
                reachableFloor,
                selectedNodeId,
                completedEdgeKeys,
                completedNodeOrder.Count);
            result.Add(new global::Godot.Collections.Dictionary
            {
                { "from", edge.FromId },
                { "to", edge.ToId },
                { "from_floor", edge.FromFloor },
                { "to_floor", edge.ToFloor },
                { "state", state },
            });
        }

        return result;
    }

    public global::Godot.Collections.Dictionary GetRouteNodeStatesForTest()
    {
        var completedNodeOrder = ResolveCompletedNodeOrder();
        var completedNodeIds = new HashSet<string>(completedNodeOrder, StringComparer.Ordinal);
        var reachableFloor = ResolveCurrentReachableFloor();
        var selectedNodeId = ResolveSelectedNodeId();
        var result = new global::Godot.Collections.Dictionary();
        foreach (var node in _routeNodes)
        {
            var state = ResolveNodeVisualState(node, reachableFloor, selectedNodeId, completedNodeIds);
            result[node.Id] = state;
        }

        return result;
    }

    private bool IsRouteNodeReachable(RouteNode node)
    {
        var reachableFloor = ResolveCurrentReachableFloor();
        if (node.Floor != reachableFloor)
        {
            return false;
        }

        if (reachableFloor == 1)
        {
            var hasOutgoing = _routeEdges.Exists(edge => string.Equals(edge.FromId, node.Id, StringComparison.Ordinal));
            var hasIncoming = _routeEdges.Exists(edge => string.Equals(edge.ToId, node.Id, StringComparison.Ordinal));
            return hasOutgoing && !hasIncoming;
        }

        var selectedNodeId = ResolveSelectedNodeId();
        if (string.IsNullOrWhiteSpace(selectedNodeId))
        {
            return false;
        }

        return _routeEdges.Exists(edge =>
            string.Equals(edge.FromId, selectedNodeId, StringComparison.Ordinal)
            && string.Equals(edge.ToId, node.Id, StringComparison.Ordinal));
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

    private string ResolveSelectedNodeId()
    {
        var main = ResolveMainController();
        if (main is null || !main.HasMethod("GetMapRouteLastSelectedNodeIdForTest"))
        {
            return string.Empty;
        }

        var selected = main.Call("GetMapRouteLastSelectedNodeIdForTest");
        return selected.VariantType == Variant.Type.String ? selected.AsString() : string.Empty;
    }

    private List<string> ResolveCompletedNodeOrder()
    {
        var main = ResolveMainController();
        if (main is null || !main.HasMethod("GetMapRouteCompletedNodeIdsForTest"))
        {
            return new List<string>();
        }

        var value = main.Call("GetMapRouteCompletedNodeIdsForTest");
        if (value.VariantType != Variant.Type.Array)
        {
            return new List<string>();
        }

        var result = new List<string>();
        foreach (var item in value.AsGodotArray())
        {
            var nodeId = item.AsString().Trim();
            if (!string.IsNullOrWhiteSpace(nodeId))
            {
                result.Add(nodeId);
            }
        }

        return result;
    }

    private static HashSet<string> BuildCompletedEdgeKeys(List<string> completedNodeOrder)
    {
        var keys = new HashSet<string>(StringComparer.Ordinal);
        for (var i = 0; i + 1 < completedNodeOrder.Count; i++)
        {
            keys.Add(BuildEdgeKey(completedNodeOrder[i], completedNodeOrder[i + 1]));
        }

        return keys;
    }

    private static string BuildEdgeKey(string fromId, string toId)
    {
        return $"{fromId}->{toId}";
    }

    private string ResolveNodeVisualState(
        RouteNode node,
        int reachableFloor,
        string selectedNodeId,
        HashSet<string> completedNodeIds)
    {
        if (completedNodeIds.Contains(node.Id))
        {
            return "completed";
        }

        if (IsRouteNodeReachable(node))
        {
            if (!string.IsNullOrWhiteSpace(selectedNodeId) && reachableFloor > 1)
            {
                return "selected-path";
            }

            return "reachable";
        }

        return "locked";
    }

    private string ResolveEdgeVisualState(
        string fromId,
        string toId,
        int reachableFloor,
        string selectedNodeId,
        HashSet<string> completedEdgeKeys,
        int completedNodeCount)
    {
        var fromNode = ResolveRouteNode(fromId);
        var toNode = ResolveRouteNode(toId);
        if (fromNode is null || toNode is null)
        {
            return "locked";
        }

        var edgeKey = BuildEdgeKey(fromId, toId);
        if (completedEdgeKeys.Contains(edgeKey))
        {
            return "completed";
        }

        if (completedNodeCount == 0 && fromNode.Floor == 1 && toNode.Floor == 2)
        {
            return "reachable";
        }

        if (!string.IsNullOrWhiteSpace(selectedNodeId)
            && string.Equals(fromId, selectedNodeId, StringComparison.Ordinal)
            && toNode.Floor == reachableFloor)
        {
            return "selected-path";
        }

        return "locked";
    }

    private void RefreshRouteTree(string locale)
    {
        var reachableFloor = ResolveCurrentReachableFloor();
        var selectedNodeId = ResolveSelectedNodeId();
        var completedNodeIds = new HashSet<string>(ResolveCompletedNodeOrder(), StringComparer.Ordinal);
        var zh = locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase);
        foreach (var node in _routeNodes)
        {
            if (!_routeButtonsById.TryGetValue(node.Id, out var button) || button is null)
            {
                continue;
            }

            var state = ResolveNodeVisualState(node, reachableFloor, selectedNodeId, completedNodeIds);
            button.Text = zh ? node.ChineseLabel : node.EnglishLabel;
            button.Disabled = string.Equals(state, "locked", StringComparison.Ordinal);
            button.TooltipText = $"state:{state}";
            button.Modulate = ResolveNodeStateColor(state);
        }
    }

    private void RefreshEdgeLegend()
    {
        if (_edgeLegendLabel is null)
        {
            return;
        }

        var completedNodeOrder = ResolveCompletedNodeOrder();
        var completedEdgeKeys = BuildCompletedEdgeKeys(completedNodeOrder);
        var selectedNodeId = ResolveSelectedNodeId();
        var reachableFloor = ResolveCurrentReachableFloor();
        var edgeItems = new List<string>();
        foreach (var edge in _routeEdges)
        {
            var state = ResolveEdgeVisualState(
                edge.FromId,
                edge.ToId,
                reachableFloor,
                selectedNodeId,
                completedEdgeKeys,
                completedNodeOrder.Count);
            edgeItems.Add($"{edge.FromId}->{edge.ToId}({state})");
        }

        _edgeLegendLabel.Text = string.Join(" | ", edgeItems);
    }

    private void RefreshEdgeVisuals()
    {
        if (_routeEdgeContainer is null)
        {
            return;
        }

        var completedNodeOrder = ResolveCompletedNodeOrder();
        var completedEdgeKeys = BuildCompletedEdgeKeys(completedNodeOrder);
        var selectedNodeId = ResolveSelectedNodeId();
        var reachableFloor = ResolveCurrentReachableFloor();
        foreach (var edge in _routeEdges)
        {
            var edgeName = edge.FromId.Replace('-', '_') + "__" + edge.ToId.Replace('-', '_');
            var edgeLabel = _routeEdgeContainer.GetNodeOrNull<Label>(edgeName);
            if (edgeLabel is null)
            {
                continue;
            }

            var state = ResolveEdgeVisualState(
                edge.FromId,
                edge.ToId,
                reachableFloor,
                selectedNodeId,
                completedEdgeKeys,
                completedNodeOrder.Count);
            edgeLabel.Text = $"{edge.FromId} -> {edge.ToId}";
            edgeLabel.TooltipText = $"state:{state}";
            edgeLabel.Modulate = ResolveEdgeStateColor(state);
        }
    }

    private static Color ResolveEdgeStateColor(string state)
    {
        return state switch
        {
            "reachable" => EdgeStateReachableColor,
            "completed" => EdgeStateCompletedColor,
            "selected-path" => EdgeStateSelectedPathColor,
            _ => EdgeStateLockedColor,
        };
    }

    private static Color ResolveNodeStateColor(string state)
    {
        return state switch
        {
            "reachable" => NodeStateReachableColor,
            "completed" => NodeStateCompletedColor,
            "selected-path" => NodeStateSelectedPathColor,
            _ => NodeStateLockedColor,
        };
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

    private static (List<RouteNode> Nodes, List<RouteEdge> Edges) LoadRouteGraph()
    {
        foreach (var candidate in ActConfigCandidatePaths)
        {
            try
            {
                var absolutePath = ProjectSettings.GlobalizePath(candidate);
                if (!File.Exists(absolutePath))
                {
                    continue;
                }

                var json = File.ReadAllText(absolutePath);
                if (string.IsNullOrWhiteSpace(json))
                {
                    continue;
                }

                using var document = JsonDocument.Parse(json, new JsonDocumentOptions
                {
                    MaxDepth = 128,
                });
                if (!document.RootElement.TryGetProperty("node_graph", out var nodeGraph)
                    || nodeGraph.ValueKind != JsonValueKind.Object
                    || !nodeGraph.TryGetProperty("nodes", out var nodesElement)
                    || nodesElement.ValueKind != JsonValueKind.Array)
                {
                    continue;
                }

                var nodes = new List<RouteNode>();
                var edges = new List<RouteEdge>();
                var floorLookup = new Dictionary<string, int>(StringComparer.Ordinal);

                foreach (var nodeElement in nodesElement.EnumerateArray())
                {
                    if (nodeElement.ValueKind != JsonValueKind.Object)
                    {
                        continue;
                    }

                    var id = ReadRequiredString(nodeElement, "id");
                    var type = ReadRequiredString(nodeElement, "type");
                    var floor = ReadRequiredInt(nodeElement, "floor");
                    if (string.IsNullOrWhiteSpace(id) || string.IsNullOrWhiteSpace(type) || floor <= 0)
                    {
                        continue;
                    }

                    var normalizedType = NormalizeRouteType(type);
                    var fallbackEnglishLabel = BuildFloorLabel(floor, normalizedType, id);
                    var englishLabel = ReadOptionalString(nodeElement, "label_en", fallbackEnglishLabel);
                    var chineseLabel = ReadOptionalString(nodeElement, "label_zh", englishLabel);
                    nodes.Add(new RouteNode(id, normalizedType, floor, englishLabel, chineseLabel));
                    floorLookup[id] = floor;
                }

                if (nodes.Count == 0)
                {
                    continue;
                }

                foreach (var nodeElement in nodesElement.EnumerateArray())
                {
                    if (nodeElement.ValueKind != JsonValueKind.Object)
                    {
                        continue;
                    }

                    var fromId = ReadRequiredString(nodeElement, "id");
                    if (string.IsNullOrWhiteSpace(fromId)
                        || !floorLookup.TryGetValue(fromId, out var fromFloor)
                        || !nodeElement.TryGetProperty("next", out var nextElement)
                        || nextElement.ValueKind != JsonValueKind.Array)
                    {
                        continue;
                    }

                    foreach (var nextNode in nextElement.EnumerateArray())
                    {
                        if (nextNode.ValueKind != JsonValueKind.String)
                        {
                            continue;
                        }

                        var toId = nextNode.GetString()?.Trim() ?? string.Empty;
                        if (string.IsNullOrWhiteSpace(toId) || !floorLookup.TryGetValue(toId, out var toFloor))
                        {
                            continue;
                        }

                        edges.Add(new RouteEdge(fromId, toId, fromFloor, toFloor));
                    }
                }

                if (edges.Count == 0)
                {
                    continue;
                }

                return (
                    nodes.OrderBy(node => node.Floor).ThenBy(node => node.Id, StringComparer.Ordinal).ToList(),
                    edges.OrderBy(edge => edge.FromFloor).ThenBy(edge => edge.FromId, StringComparer.Ordinal).ThenBy(edge => edge.ToId, StringComparer.Ordinal).ToList());
            }
            catch
            {
                // Fallback to the legacy graph if the act config cannot be parsed.
            }
        }

        return (
            FallbackRouteNodes.Select(node => node with { }).ToList(),
            FallbackRouteEdges.Select(edge => edge with { }).ToList());
    }

    private static string ReadRequiredString(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var value) || value.ValueKind != JsonValueKind.String)
        {
            return string.Empty;
        }

        return value.GetString()?.Trim() ?? string.Empty;
    }

    private static string ReadOptionalString(JsonElement element, string propertyName, string fallback)
    {
        var value = ReadRequiredString(element, propertyName);
        return string.IsNullOrWhiteSpace(value) ? fallback : value;
    }

    private static int ReadRequiredInt(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var value) || value.ValueKind != JsonValueKind.Number)
        {
            return 0;
        }

        return value.TryGetInt32(out var result) ? result : 0;
    }

    private static string NormalizeRouteType(string type)
    {
        var normalized = type.Trim().ToLowerInvariant();
        return normalized == "boss" ? "combat" : normalized;
    }

    private static string BuildFloorLabel(int floor, string type, string nodeId)
    {
        var suffix = type switch
        {
            "combat" => "Combat",
            "event" => "Event",
            "shop" => "Shop",
            "rest" => "Rest",
            _ => nodeId,
        };

        return $"F{floor} {suffix}";
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
