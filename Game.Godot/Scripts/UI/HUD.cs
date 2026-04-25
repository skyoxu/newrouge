using Godot;
using Game.Core.Contracts;
using Game.Core.Contracts.Save;
using Game.Core.Contracts.Interfaces;
using Game.Core.State;
using Game.Godot.Adapters;
using Game.Godot.Autoloads;
using System;
using System.Collections.Generic;
using System.Text.Json;

namespace Game.Godot.Scripts.UI;

public partial class HUD : Control
{
    private Label _score = default!;
    private Label _health = default!;
    private Label _gold = default!;
    private Label _difficulty = default!;
    private Control _runSummaryPanel = default!;
    private Label _summaryTitle = default!;
    private Label _summaryDifficulty = default!;
    private Label _summaryOutcome = default!;
    private Label _summaryNodeProgress = default!;
    private Label _summaryReason = default!;
    private EventBusAdapter? _eventBus;
    private Callable _domainEventCallable = default!;
    private RunDifficultyLockPolicy _difficultyPolicy = new();
    private ISaveService? _saveService;
    private string _summaryOutcomeText = string.Empty;
    private string _summaryNodeProgressText = string.Empty;
    private string _summaryReasonText = string.Empty;
    private static Dictionary<string, string>? _textFallbacks;
    private static readonly JsonDocumentOptions EventJsonOptions = new()
    {
        MaxDepth = 16
    };
    private const string DifficultyLabelKey = "ui.difficulty.label";
    private const string RunSummaryTitleKey = "ui.run.summary.title";
    private const string RunSummaryOutcomeLabelKey = "ui.run.summary.outcome";
    private const string RunSummaryNodeProgressLabelKey = "ui.run.summary.node_progress";
    private const string RunSummaryReasonLabelKey = "ui.run.summary.reason";

    public override void _Ready()
    {
        _score = GetNode<Label>("TopBar/HBox/ScoreLabel");
        _health = GetNode<Label>("TopBar/HBox/HealthLabel");
        _gold = GetNode<Label>("TopBar/HBox/GoldLabel");
        _difficulty = GetNode<Label>("TopBar/HBox/DifficultyLabel");
        _runSummaryPanel = GetNode<Control>("RunSummaryPanel");
        _summaryTitle = GetNode<Label>("RunSummaryPanel/VBox/TitleLabel");
        _summaryDifficulty = GetNode<Label>("RunSummaryPanel/VBox/SummaryDifficultyLabel");
        _summaryOutcome = GetNode<Label>("RunSummaryPanel/VBox/SummaryOutcomeLabel");
        _summaryNodeProgress = GetNode<Label>("RunSummaryPanel/VBox/SummaryNodeProgressLabel");
        _summaryReason = GetNode<Label>("RunSummaryPanel/VBox/SummaryReasonLabel");
        _domainEventCallable = new Callable(this, nameof(OnDomainEventEmitted));
        _saveService = CompositionRoot.Instance?.SaveService;

        DisableAutoTranslationForManagedText();
        _runSummaryPanel.Visible = false;
        _summaryTitle.Text = ResolveVisibleText(RunSummaryTitleKey);
        SetRunSummaryText("Unknown", 0, "No stored run summary reason.");
        _difficultyPolicy = new RunDifficultyLockPolicy(RunDifficultyState.GetConfirmedDifficulty());
        _ = ApplyDifficultySelection(_difficultyPolicy.SelectedDifficultyId);

        _eventBus = GetNodeOrNull<EventBusAdapter>("/root/EventBus");
        if (_eventBus != null)
        {
            _eventBus.Connect(EventBusAdapter.SignalName.DomainEventEmitted, _domainEventCallable);
        }
    }

    private void DisableAutoTranslationForManagedText()
    {
        _score.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        _health.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        _gold.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        _difficulty.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        _summaryTitle.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        _summaryDifficulty.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        _summaryOutcome.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        _summaryNodeProgress.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
        _summaryReason.AutoTranslateMode = AutoTranslateModeEnum.Disabled;
    }

    public override void _ExitTree()
    {
        try
        {
            if (_eventBus != null
                && GodotObject.IsInstanceValid(_eventBus)
                && _eventBus.IsConnected(EventBusAdapter.SignalName.DomainEventEmitted, _domainEventCallable))
            {
                _eventBus.Disconnect(EventBusAdapter.SignalName.DomainEventEmitted, _domainEventCallable);
            }
        }
        catch (ObjectDisposedException)
        {
            // Test teardown can free the EventBus before this HUD leaves the tree.
        }
    }

    private void OnDomainEventEmitted(string type, string source, string dataJson, string id, string specVersion, string dataContentType, string timestampIso)
    {
        if (type == EventTypes.RunDifficultySelected)
        {
            try
            {
                using var doc = JsonDocument.Parse(dataJson, EventJsonOptions);
                if (!TryReadDifficultyId(doc.RootElement, out var difficultyId))
                {
                    GD.PushWarning("[HUD] Missing difficulty_id in run difficulty event payload.");
                    return;
                }

                if (!ApplyDifficultySelection(difficultyId))
                {
                    GD.PushWarning($"[HUD] Ignored run difficulty update after lock (requested={difficultyId}, selected={_difficultyPolicy.SelectedDifficultyId}).");
                }
            }
            catch (JsonException ex)
            {
                GD.PushWarning($"[HUD] Invalid run difficulty payload: {ex.Message}");
            }
        }
        else if (type == EventTypes.RunStarted || type == "run.started")
        {
            _difficultyPolicy.Lock();
            RunDifficultyState.SetConfirmedDifficulty(_difficultyPolicy.SelectedDifficultyId);
        }
        else if (type == EventTypes.ScoreUpdated || type == "score.changed")
        {
            try
            {
                using var doc = JsonDocument.Parse(dataJson, EventJsonOptions);
                int v = 0;
                if (doc.RootElement.TryGetProperty("value", out var val)) v = val.GetInt32();
                else if (doc.RootElement.TryGetProperty("score", out var sc)) v = sc.GetInt32();
                _score.Text = $"Score: {v}";
            }
            catch (JsonException ex)
            {
                GD.PushWarning($"[HUD] Invalid score event payload: {ex.Message}");
            }
        }
        else if (type == EventTypes.HealthUpdated || type == "player.health.changed")
        {
            try
            {
                using var doc = JsonDocument.Parse(dataJson, EventJsonOptions);
                int v = 0;
                if (doc.RootElement.TryGetProperty("value", out var val)) v = val.GetInt32();
                else if (doc.RootElement.TryGetProperty("health", out var hp)) v = hp.GetInt32();
                _health.Text = $"HP: {v}";
            }
            catch (JsonException ex)
            {
                GD.PushWarning($"[HUD] Invalid health event payload: {ex.Message}");
            }
        }
        else if (type == "core.gold.updated" || type == "player.gold.changed")
        {
            try
            {
                using var doc = JsonDocument.Parse(dataJson, EventJsonOptions);
                int v = 0;
                if (doc.RootElement.TryGetProperty("value", out var val)) v = val.GetInt32();
                else if (doc.RootElement.TryGetProperty("gold", out var gold)) v = gold.GetInt32();
                _gold.Text = $"Gold: {v}";
            }
            catch (JsonException ex)
            {
                GD.PushWarning($"[HUD] Invalid gold event payload: {ex.Message}");
            }
        }
        else if (type == EventTypes.CombatEnded || type == "combat.ended")
        {
            _runSummaryPanel.Visible = true;
            _summaryDifficulty.Text = _difficulty.Text;
            _ = RefreshRunSummaryMetadataAsync();
        }
    }

    public void SetScore(int v) => _score.Text = $"Score: {v}";
    public void SetHealth(int v) => _health.Text = $"HP: {v}";
    public void SetGold(int v) => _gold.Text = $"Gold: {v}";

    public string GetHudDifficultyTextForTest() => _difficulty.Text;

    public string GetSummaryDifficultyTextForTest() => _summaryDifficulty.Text;

    public bool IsRunSummaryVisibleForTest() => _runSummaryPanel.Visible;

    public string GetSummaryOutcomeTextForTest() => _summaryOutcomeText;

    public string GetSummaryNodeProgressTextForTest() => _summaryNodeProgressText;

    public string GetSummaryReasonTextForTest() => _summaryReasonText;

    private bool ApplyDifficultySelection(int difficultyId)
    {
        if (!_difficultyPolicy.SelectDifficulty(difficultyId))
        {
            return false;
        }

        var selectedDifficultyId = _difficultyPolicy.SelectedDifficultyId;
        var labelText = ResolveVisibleText(DifficultyLabelKey);
        var difficultyText = ResolveVisibleText($"ui.difficulty.{selectedDifficultyId}");
        var hudText = string.IsNullOrWhiteSpace(labelText)
            ? difficultyText
            : $"{labelText}: {difficultyText}";
        _difficulty.Text = hudText;
        _summaryDifficulty.Text = hudText;

        return true;
    }

    private async System.Threading.Tasks.Task RefreshRunSummaryMetadataAsync()
    {
        if (_saveService is null)
        {
            return;
        }

        RunSummaryMetadata? metadata;
        try
        {
            metadata = await _saveService.ReadRunSummaryMetadataAsync().ConfigureAwait(true);
        }
        catch (Exception ex)
        {
            GD.PushWarning($"[HUD] Failed to read run summary metadata: {ex.Message}");
            return;
        }

        if (metadata is null || metadata.OwnerSurface != RunSummaryOwnerSurface.HudOverlay)
        {
            return;
        }

        CallDeferred(
            nameof(ApplyRunSummaryMetadataDeferred),
            metadata.DifficultyId,
            metadata.Outcome,
            metadata.NodeProgress,
            metadata.FailureOrRecoveryReason);
    }

    public void ShowRunSummaryForTest(string outcome, int nodeProgress, string reason)
    {
        _runSummaryPanel.Visible = true;
        ApplyRunSummaryMetadataDeferred(_difficultyPolicy.SelectedDifficultyId, outcome, nodeProgress, reason);
    }

    private void ApplyRunSummaryMetadataDeferred(int difficultyId, string outcome, int nodeProgress, string reason)
    {
        if (!_difficultyPolicy.IsLocked && difficultyId >= 1 && difficultyId <= 10)
        {
            _ = ApplyDifficultySelection(difficultyId);
        }

        SetRunSummaryText(outcome, nodeProgress, reason);
    }

    private void SetRunSummaryText(string outcome, int nodeProgress, string reason)
    {
        _summaryOutcomeText = FormatRunSummaryLine(RunSummaryOutcomeLabelKey, outcome);
        _summaryNodeProgressText = FormatRunSummaryLine(RunSummaryNodeProgressLabelKey, nodeProgress.ToString());
        _summaryReasonText = FormatRunSummaryLine(RunSummaryReasonLabelKey, reason);

        _summaryOutcome.Text = _summaryOutcomeText;
        _summaryNodeProgress.Text = _summaryNodeProgressText;
        _summaryReason.Text = _summaryReasonText;
    }

    private static string FormatRunSummaryLine(string labelKey, string value)
    {
        var label = ResolveVisibleText(labelKey);
        if (string.IsNullOrWhiteSpace(label) || string.Equals(label, labelKey, StringComparison.Ordinal))
        {
            label = labelKey switch
            {
                RunSummaryOutcomeLabelKey => "Outcome",
                RunSummaryNodeProgressLabelKey => "Node Progress",
                RunSummaryReasonLabelKey => "Reason",
                _ => "Summary",
            };
        }

        return $"{label}: {value}";
    }

    private static bool TryReadDifficultyId(JsonElement payload, out int difficultyId)
    {
        difficultyId = 0;
        if (!payload.TryGetProperty("difficulty_id", out var node))
        {
            return false;
        }

        if (node.ValueKind == JsonValueKind.Number)
        {
            return node.TryGetInt32(out difficultyId);
        }

        if (node.ValueKind == JsonValueKind.String && int.TryParse(node.GetString(), out var parsed))
        {
            difficultyId = parsed;
            return true;
        }

        return false;
    }

    private static string ResolveVisibleText(string keyOrText)
    {
        if (string.IsNullOrWhiteSpace(keyOrText))
        {
            return string.Empty;
        }

        var localized = TranslationServer.Translate(keyOrText);
        if (!string.Equals(localized, keyOrText, StringComparison.Ordinal))
        {
            return localized;
        }

        _textFallbacks ??= LoadTextFallbacks();
        if (_textFallbacks.TryGetValue(keyOrText, out var fallback) && !string.IsNullOrWhiteSpace(fallback))
        {
            return fallback;
        }

        return keyOrText;
    }

    private static Dictionary<string, string> LoadTextFallbacks()
    {
        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        const string path = "res://Game.Godot/Translations/en.csv";
        if (!FileAccess.FileExists(path))
        {
            return map;
        }

        using var file = FileAccess.Open(path, FileAccess.ModeFlags.Read);
        if (file is null)
        {
            return map;
        }

        var raw = file.GetAsText();
        foreach (var line in raw.Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            var trimmed = line.Trim();
            if (string.IsNullOrWhiteSpace(trimmed) || trimmed.StartsWith("key,value", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var sep = trimmed.IndexOf(',');
            if (sep <= 0 || sep >= trimmed.Length - 1)
            {
                continue;
            }

            var key = trimmed[..sep].Trim();
            var value = trimmed[(sep + 1)..].Trim();
            if (!string.IsNullOrWhiteSpace(key) && !string.IsNullOrWhiteSpace(value))
            {
                map[key] = value;
            }
        }

        return map;
    }
}
