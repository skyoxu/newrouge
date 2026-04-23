using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.Json;
using Godot;
using Game.Core.Contracts.Combat;

namespace Game.Godot.Scripts.UI;

public partial class CombatScene : Control
{
    [Signal]
    public delegate void TurnActionRequestedEventHandler(string actionName);

    private ItemList _handCards = default!;
    private Label _difficultyValue = default!;
    private Label _playerHpValue = default!;
    private Label _energyValue = default!;
    private Label _drawPileValue = default!;
    private Label _discardPileValue = default!;
    private Label _turnStateValue = default!;
    private Label _feedbackMessageLabel = default!;
    private ItemList _feedbackHistoryList = default!;
    private Label _enemyIntentTitleLabel = default!;
    private VBoxContainer _enemyIntentList = default!;
    private Button _startTurnButton = default!;
    private Button _endTurnButton = default!;
    private Label _turnTitleLabel = default!;

    private readonly List<string> _dispatchedCommands = new();
    private static readonly JsonSerializerOptions SnapshotJsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };
    private int _coreStateMutationCount;
    private int _turnIndex = 1;
    private int _acceptedCommandFeedbackCount;
    private string _latestCommandOutcomeState = "none";
    private int _enemyIntentTurnIndex;
    private readonly Dictionary<string, EnemyIntentState> _enemyIntentByEnemy = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Texture2D> _enemyIntentTextureCache = new(StringComparer.Ordinal);
    private static readonly Dictionary<string, Dictionary<string, string>> FeedbackTextMapsByLocale = new(StringComparer.OrdinalIgnoreCase);
    private Texture2D? _enemyIntentFallbackTexture;

    public override void _Ready()
    {
        _handCards = GetNode<ItemList>("HUD/HandCards");
        _difficultyValue = GetNode<Label>("HUD/DifficultyValue");
        _playerHpValue = GetNode<Label>("HUD/PlayerHpValue");
        _energyValue = GetNode<Label>("HUD/EnergyValue");
        _drawPileValue = GetNode<Label>("HUD/DrawPileValue");
        _discardPileValue = GetNode<Label>("HUD/DiscardPileValue");
        _turnStateValue = GetNode<Label>("HUD/TurnStateValue");
        _feedbackMessageLabel = GetNode<Label>("HUD/FeedbackMessageLabel");
        _feedbackHistoryList = GetNode<ItemList>("HUD/FeedbackHistoryList");
        _enemyIntentTitleLabel = GetNode<Label>("HUD/EnemyIntentPanel/EnemyIntentTitle");
        _enemyIntentList = GetNode<VBoxContainer>("HUD/EnemyIntentPanel/EnemyIntentList");
        _startTurnButton = GetNode<Button>("HUD/TurnControls/StartTurnButton");
        _endTurnButton = GetNode<Button>("HUD/TurnControls/EndTurnButton");
        _turnTitleLabel = GetNode<Label>("HUD/TurnTitleLabel");

        _startTurnButton.Pressed += OnStartTurnPressed;
        _endTurnButton.Pressed += OnEndTurnPressed;
        _startTurnButton.Text = ResolveUiText("combat.turn.start");
        _endTurnButton.Text = ResolveUiText("combat.turn.end");
        _turnTitleLabel.Text = ResolveUiText("combat.turn.title");
        _enemyIntentTitleLabel.Text = ResolveUiText("combat.intent.title");
        _feedbackMessageLabel.Text = string.Empty;
    }

    public override void _ExitTree()
    {
        if (_startTurnButton is not null)
        {
            _startTurnButton.Pressed -= OnStartTurnPressed;
        }

        if (_endTurnButton is not null)
        {
            _endTurnButton.Pressed -= OnEndTurnPressed;
        }
    }

    public bool TryApplyCoreSnapshotData(global::Godot.Collections.Array handCards, int energy, int drawPile, int discardPile)
    {
        if (handCards is null || energy < 0 || drawPile < 0 || discardPile < 0)
        {
            return false;
        }

        ApplyCoreSnapshotData(handCards, energy, drawPile, discardPile);
        return true;
    }

    public bool TryApplyCoreSnapshotContractJson(string snapshotJson)
    {
        if (string.IsNullOrWhiteSpace(snapshotJson))
        {
            return false;
        }

        CombatHudSnapshotPayload? payload;
        try
        {
            payload = JsonSerializer.Deserialize<CombatHudSnapshotPayload>(snapshotJson, SnapshotJsonOptions);
        }
        catch (JsonException)
        {
            return false;
        }

        if (
            payload is null
            || payload.HandCards is null
            || payload.Energy < 0
            || payload.DrawPileCount < 0
            || payload.DiscardPileCount < 0
            || payload.Difficulty < 0
            || payload.PlayerHp < 0)
        {
            return false;
        }

        ApplyCoreSnapshot(new CombatHudSnapshot(
            payload.HandCards,
            payload.Energy,
            payload.DrawPileCount,
            payload.DiscardPileCount,
            payload.Difficulty,
            payload.PlayerHp,
            payload.TurnState ?? string.Empty));
        return true;
    }

    public void ApplyCoreSnapshotData(global::Godot.Collections.Array handCards, int energy, int drawPile, int discardPile)
    {
        var snapshotCards = new List<string>();
        foreach (var card in handCards)
        {
            snapshotCards.Add(card.ToString());
        }

        ApplyCoreSnapshot(new CombatHudSnapshot(snapshotCards, energy, drawPile, discardPile));
    }

    public void ApplySnapshotForTest(global::Godot.Collections.Array handCards, int energy, int drawPile, int discardPile)
    {
        ApplyCoreSnapshotData(handCards, energy, drawPile, discardPile);
    }

    public global::Godot.Collections.Dictionary CaptureUiStateForTest()
    {
        var hand = new global::Godot.Collections.Array<string>();
        for (var index = 0; index < _handCards.ItemCount; index++)
        {
            hand.Add(_handCards.GetItemText(index));
        }

        return new global::Godot.Collections.Dictionary
        {
            { "hand", hand },
            { "difficulty", _difficultyValue.Text },
            { "playerHp", _playerHpValue.Text },
            { "energy", _energyValue.Text },
            { "draw", _drawPileValue.Text },
            { "discard", _discardPileValue.Text },
            { "turnState", _turnStateValue.Text },
            { "selectedCommandState", _latestCommandOutcomeState },
        };
    }

    public bool RequestTurnAction(string actionName)
    {
        if (actionName != "start_turn" && actionName != "end_turn")
        {
            AppendCommandFeedback(actionName, accepted: false, refusalReasonKey: "combat.invalid_action");
            return false;
        }

        _dispatchedCommands.Add(actionName);
        EmitSignal(SignalName.TurnActionRequested, actionName);
        AppendCommandFeedback(actionName, accepted: true);
        return true;
    }

    public bool RequestTurnActionForTest(string actionName)
    {
        return RequestTurnAction(actionName);
    }

    public global::Godot.Collections.Array<string> GetDispatchedCommandsForTest()
    {
        var commands = new global::Godot.Collections.Array<string>();
        foreach (var action in _dispatchedCommands)
        {
            commands.Add(action);
        }

        return commands;
    }

    public void ApplyCommandFeedbackForTest(string commandName, bool accepted)
    {
        AppendCommandFeedback(commandName, accepted);
    }

    public void ApplyHoverPreviewForTest(string previewId)
    {
        _ = previewId;
    }

    public void ApplyTargetInspectionForTest(string targetId)
    {
        _ = targetId;
    }

    public string GetLatestFeedbackMessageForTest()
    {
        return _feedbackMessageLabel.Text;
    }

    public global::Godot.Collections.Array<string> GetFeedbackHistoryForTest()
    {
        var history = new global::Godot.Collections.Array<string>();
        for (var index = 0; index < _feedbackHistoryList.ItemCount; index++)
        {
            history.Add(_feedbackHistoryList.GetItemText(index));
        }

        return history;
    }

    public int GetAcceptedCommandCountForTest()
    {
        return _acceptedCommandFeedbackCount;
    }

    public string GetSelectedCommandStateForTest()
    {
        return _latestCommandOutcomeState;
    }

    public bool TryApplyAcceptedStrikeForTest()
    {
        if (!TryParseIntLabel(_energyValue, out var energy) || energy <= 0)
        {
            AppendCommandFeedback("strike", accepted: false, refusalReasonKey: "combat.feedback.refusal_reason.insufficient_energy");
            return false;
        }

        var handCards = new List<string>();
        for (var index = 0; index < _handCards.ItemCount; index++)
        {
            handCards.Add(_handCards.GetItemText(index));
        }

        var difficulty = TryParseIntLabel(_difficultyValue, out var parsedDifficulty) ? parsedDifficulty : 0;
        var playerHp = TryParseIntLabel(_playerHpValue, out var parsedHp) ? parsedHp : 0;
        var drawPile = TryParseIntLabel(_drawPileValue, out var parsedDraw) ? parsedDraw : 0;
        var discardPile = TryParseIntLabel(_discardPileValue, out var parsedDiscard) ? parsedDiscard : 0;

        var remainingEnergy = energy - 1;
        ApplyCoreSnapshot(new CombatHudSnapshot(
            handCards,
            remainingEnergy,
            drawPile,
            discardPile,
            difficulty,
            playerHp,
            _turnStateValue.Text));
        AppendCommandFeedback("strike", accepted: true, detail: BuildAcceptedStrikeDetail(remainingEnergy));
        return true;
    }

    public int GetCoreStateMutationCountForTest()
    {
        return _coreStateMutationCount;
    }

    public int GetTurnIndexForTest()
    {
        return _turnIndex;
    }

    public string ResolveLocalizedTextForTest(string localizationKey)
    {
        return ResolveFeedbackTemplate(localizationKey);
    }

    public string GetTurnTitleTextForTest()
    {
        return _turnTitleLabel.Text;
    }

    public string GetEndTurnButtonTextForTest()
    {
        return _endTurnButton.Text;
    }

    public void RefreshLocaleForTest()
    {
        _startTurnButton.Text = ResolveUiText("combat.turn.start");
        _endTurnButton.Text = ResolveUiText("combat.turn.end");
        _turnTitleLabel.Text = ResolveUiText("combat.turn.title");
        _enemyIntentTitleLabel.Text = ResolveUiText("combat.intent.title");
    }

    public bool TryApplyEnemyIntentPreviewContractJson(string intentJson)
    {
        if (string.IsNullOrWhiteSpace(intentJson))
        {
            return false;
        }

        EnemyIntentContractPayload? payload;
        try
        {
            payload = JsonSerializer.Deserialize<EnemyIntentContractPayload>(intentJson, SnapshotJsonOptions);
        }
        catch (JsonException)
        {
            return false;
        }

        if (payload?.EnemyIntents is null)
        {
            return false;
        }

        ApplyEnemyIntentPreview(payload.EnemyIntents);
        return true;
    }

    public bool HasEnemyIntentForTest(string enemyId)
    {
        return !string.IsNullOrWhiteSpace(enemyId) && _enemyIntentByEnemy.ContainsKey(enemyId);
    }

    public string GetEnemyIntentIconIdForTest(string enemyId)
    {
        if (string.IsNullOrWhiteSpace(enemyId) || !_enemyIntentByEnemy.TryGetValue(enemyId, out var state))
        {
            return string.Empty;
        }

        return state.IconId;
    }

    public string GetEnemyIntentDescriptionForTest(string enemyId)
    {
        if (string.IsNullOrWhiteSpace(enemyId) || !_enemyIntentByEnemy.TryGetValue(enemyId, out var state))
        {
            return string.Empty;
        }

        return state.Description;
    }

    public int GetEnemyIntentTurnForTest(string enemyId)
    {
        if (string.IsNullOrWhiteSpace(enemyId) || !_enemyIntentByEnemy.TryGetValue(enemyId, out var state))
        {
            return 0;
        }

        return state.Turn;
    }

    public int GetEnemyIntentRowCountForTest()
    {
        return _enemyIntentByEnemy.Count;
    }

    public bool IsEnemyIntentPanelVisibleForTest()
    {
        return _enemyIntentList.Visible;
    }

    public bool HasEnemyIntentIconTextureForTest(string enemyId)
    {
        var iconSlot = FindEnemyIntentIconSlot(enemyId);
        return iconSlot?.Texture is not null;
    }

    private void OnStartTurnPressed()
    {
        RequestTurnAction("start_turn");
    }

    private void OnEndTurnPressed()
    {
        RequestTurnAction("end_turn");
    }

    public void ApplyCoreSnapshot(CombatHudSnapshot snapshot)
    {
        _handCards.Clear();
        foreach (var card in snapshot.HandCards)
        {
            _handCards.AddItem(card);
        }

        _difficultyValue.Text = snapshot.Difficulty.ToString();
        _playerHpValue.Text = snapshot.PlayerHp.ToString();
        _energyValue.Text = snapshot.Energy.ToString();
        _drawPileValue.Text = snapshot.DrawPileCount.ToString();
        _discardPileValue.Text = snapshot.DiscardPileCount.ToString();
        _turnStateValue.Text = string.IsNullOrWhiteSpace(snapshot.TurnState)
            ? _turnTitleLabel.Text
            : snapshot.TurnState;
    }

    private void AppendCommandFeedback(string commandName, bool accepted, string? detail = null, string? refusalReasonKey = null)
    {
        var normalizedCommand = string.IsNullOrWhiteSpace(commandName) ? "unknown" : commandName;
        var localizationKey = accepted ? "combat.feedback.accepted" : "combat.feedback.refused";
        var locale = NormalizeLocale(TranslationServer.GetLocale());
        var localizedTemplate = ResolveFeedbackTemplate(localizationKey);
        if (locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase)
            && (string.Equals(localizedTemplate, localizationKey, StringComparison.Ordinal)
                || localizedTemplate.Contains("accepted", StringComparison.OrdinalIgnoreCase)
                || localizedTemplate.Contains("refused", StringComparison.OrdinalIgnoreCase)))
        {
            localizedTemplate = accepted ? "命令'{0}'已接受。" : "命令'{0}'被拒绝。";
        }

        var message = string.Equals(localizedTemplate, localizationKey, StringComparison.Ordinal)
            ? accepted
                ? $"Command '{normalizedCommand}' accepted."
                : $"Command '{normalizedCommand}' refused."
            : string.Format(CultureInfo.CurrentCulture, localizedTemplate, normalizedCommand);

        if (!accepted)
        {
            var reasonText = ResolveRefusalReasonText(normalizedCommand, refusalReasonKey);
            if (!string.IsNullOrWhiteSpace(reasonText))
            {
                message = $"{message.TrimEnd('.', '。')}: {reasonText}.";
            }
        }

        if (accepted)
        {
            _acceptedCommandFeedbackCount += 1;
            _latestCommandOutcomeState = $"accepted:{normalizedCommand}";
        }

        var finalMessage = string.IsNullOrWhiteSpace(detail)
            ? message
            : $"{message} {detail}";

        _feedbackMessageLabel.Text = finalMessage;
        _feedbackHistoryList.AddItem(message);
    }

    private static string BuildAcceptedStrikeDetail(int remainingEnergy)
    {
        var locale = NormalizeLocale(TranslationServer.GetLocale());
        if (locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase))
        {
            return $"能量-1（剩余{remainingEnergy}）";
        }

        return $"Energy -1 (remaining {remainingEnergy}).";
    }

    private static string ResolveRefusalReasonKey(string normalizedCommand, string? refusalReasonKey)
    {
        if (!string.IsNullOrWhiteSpace(refusalReasonKey))
        {
            return refusalReasonKey.Trim();
        }

        if (normalizedCommand.Contains("target", StringComparison.OrdinalIgnoreCase))
        {
            return "combat.feedback.refusal_reason.invalid_target";
        }

        if (normalizedCommand.Contains("energy", StringComparison.OrdinalIgnoreCase))
        {
            return "combat.feedback.refusal_reason.insufficient_energy";
        }

        return "combat.feedback.refusal_reason.invalid_action";
    }

    private static string ResolveRefusalReasonText(string normalizedCommand, string? refusalReasonKey)
    {
        var reasonKey = ResolveRefusalReasonKey(normalizedCommand, refusalReasonKey);
        var mapped = ResolveFeedbackTemplate(reasonKey);
        if (string.Equals(mapped, reasonKey, StringComparison.Ordinal))
        {
            mapped = reasonKey switch
            {
                "combat.feedback.refusal_reason.insufficient_energy" => "insufficient energy",
                "combat.feedback.refusal_reason.invalid_target" => "invalid target",
                "combat.invalid_action" => "invalid action",
                _ => "invalid action",
            };
        }

        return mapped.Trim().TrimEnd('.', '。');
    }

    private static string ResolveUiText(string localizationKey)
    {
        var resolved = ResolveFeedbackTemplate(localizationKey);
        if (!string.Equals(resolved, localizationKey, StringComparison.Ordinal))
        {
            return resolved;
        }

        var locale = NormalizeLocale(TranslationServer.GetLocale());
        var isZh = locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase);
        return localizationKey switch
        {
            "combat.turn.start" => isZh ? "开始回合" : "Start Turn",
            "combat.turn.end" => isZh ? "结束回合" : "End Turn",
            "combat.turn.title" => isZh ? "当前回合" : "Current Turn",
            "combat.intent.title" => isZh ? "敌方意图" : "Enemy Intent",
            _ => localizationKey,
        };
    }

    private static string ResolveFeedbackTemplate(string localizationKey)
    {
        if (string.IsNullOrWhiteSpace(localizationKey))
        {
            return string.Empty;
        }

        var locale = NormalizeLocale(TranslationServer.GetLocale());
        var map = GetFeedbackTextMap(locale);
        if (map.TryGetValue(localizationKey, out var mappedValue) && !string.IsNullOrWhiteSpace(mappedValue))
        {
            return mappedValue;
        }

        var localized = TranslationServer.Translate(localizationKey);
        if (!string.Equals(localized, localizationKey, StringComparison.Ordinal))
        {
            return localized;
        }

        if (!string.Equals(locale, "en", StringComparison.OrdinalIgnoreCase))
        {
            var fallback = GetFeedbackTextMap("en");
            if (fallback.TryGetValue(localizationKey, out var fallbackValue) && !string.IsNullOrWhiteSpace(fallbackValue))
            {
                return fallbackValue;
            }
        }

        return localizationKey;
    }

    private static Dictionary<string, string> GetFeedbackTextMap(string locale)
    {
        if (FeedbackTextMapsByLocale.TryGetValue(locale, out var cached))
        {
            return cached;
        }

        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        var path = locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase)
            ? "res://Game.Godot/Translations/zh-CN.csv"
            : "res://Game.Godot/Translations/en.csv";
        if (!FileAccess.FileExists(path))
        {
            path = locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase)
                ? "res://../Game.Godot/Translations/zh-CN.csv"
                : "res://../Game.Godot/Translations/en.csv";
        }

        if (!FileAccess.FileExists(path))
        {
            FeedbackTextMapsByLocale[locale] = map;
            return map;
        }

        using var file = FileAccess.Open(path, FileAccess.ModeFlags.Read);
        if (file is null)
        {
            FeedbackTextMapsByLocale[locale] = map;
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

        FeedbackTextMapsByLocale[locale] = map;
        return map;
    }

    private void ApplyEnemyIntentPreview(IReadOnlyList<EnemyIntentPreviewItemPayload> previews)
    {
        _enemyIntentTurnIndex += 1;
        _enemyIntentByEnemy.Clear();
        foreach (var child in _enemyIntentList.GetChildren())
        {
            child.QueueFree();
        }

        foreach (var preview in previews)
        {
            if (string.IsNullOrWhiteSpace(preview.EnemyId))
            {
                continue;
            }

            var state = new EnemyIntentState(
                EnemyId: preview.EnemyId,
                IconId: preview.IconId ?? string.Empty,
                Description: ResolveIntentDescription(preview.TextKey),
                Turn: _enemyIntentTurnIndex);
            _enemyIntentByEnemy[preview.EnemyId] = state;
            AddEnemyIntentRow(state);
        }

        _enemyIntentList.Visible = _enemyIntentByEnemy.Count > 0;
    }

    private void AddEnemyIntentRow(EnemyIntentState state)
    {
        var row = new HBoxContainer
        {
            Name = $"EnemyIntent_{state.EnemyId}",
            SizeFlagsHorizontal = SizeFlags.ExpandFill,
        };
        var iconSlot = new TextureRect
        {
            Name = "IconSlot",
            CustomMinimumSize = new Vector2(20, 20),
            ExpandMode = TextureRect.ExpandModeEnum.FitWidthProportional,
            StretchMode = TextureRect.StretchModeEnum.KeepCentered,
            TooltipText = state.IconId,
            Texture = ResolveEnemyIntentTexture(state.IconId),
        };
        iconSlot.SetMeta("icon_id", state.IconId);

        var iconIdLabel = new Label
        {
            Name = "IconIdLabel",
            Text = state.IconId,
        };
        var descriptionLabel = new Label
        {
            Name = "DescriptionLabel",
            Text = state.Description,
            SizeFlagsHorizontal = SizeFlags.ExpandFill,
        };

        row.SetMeta("enemy_id", state.EnemyId);
        row.SetMeta("turn", state.Turn);
        row.AddChild(iconSlot);
        row.AddChild(iconIdLabel);
        row.AddChild(descriptionLabel);
        _enemyIntentList.AddChild(row);
    }

    private TextureRect? FindEnemyIntentIconSlot(string enemyId)
    {
        if (string.IsNullOrWhiteSpace(enemyId))
        {
            return null;
        }

        foreach (var child in _enemyIntentList.GetChildren())
        {
            if (child is not HBoxContainer row || !row.HasMeta("enemy_id"))
            {
                continue;
            }

            var rowEnemyId = row.GetMeta("enemy_id").AsString();
            if (!string.Equals(rowEnemyId, enemyId, StringComparison.Ordinal))
            {
                continue;
            }

            return row.GetNodeOrNull<TextureRect>("IconSlot");
        }

        return null;
    }

    private Texture2D ResolveEnemyIntentTexture(string iconId)
    {
        var iconKey = iconId ?? string.Empty;
        if (_enemyIntentTextureCache.TryGetValue(iconKey, out var cachedTexture))
        {
            return cachedTexture;
        }

        var resolved = TryLoadEnemyIntentTexture(iconKey) ?? EnsureEnemyIntentFallbackTexture();
        _enemyIntentTextureCache[iconKey] = resolved;
        return resolved;
    }

    private static Texture2D? TryLoadEnemyIntentTexture(string iconKey)
    {
        foreach (var path in BuildEnemyIntentTextureCandidates(iconKey))
        {
            if (!ResourceLoader.Exists(path))
            {
                continue;
            }

            if (ResourceLoader.Load(path) is Texture2D texture)
            {
                return texture;
            }
        }

        return null;
    }

    private static IEnumerable<string> BuildEnemyIntentTextureCandidates(string iconKey)
    {
        if (string.IsNullOrWhiteSpace(iconKey))
        {
            yield break;
        }

        if (iconKey.StartsWith("res://", StringComparison.Ordinal))
        {
            yield return iconKey;
            yield break;
        }

        yield return $"res://Game.Godot/Assets/UI/EnemyIntent/{iconKey}.png";
        yield return $"res://Game.Godot/Assets/UI/EnemyIntent/{iconKey}.webp";
        yield return $"res://Game.Godot/Assets/UI/EnemyIntent/{iconKey}.svg";
    }

    private Texture2D EnsureEnemyIntentFallbackTexture()
    {
        if (_enemyIntentFallbackTexture is not null)
        {
            return _enemyIntentFallbackTexture;
        }

        var image = Image.CreateEmpty(20, 20, false, Image.Format.Rgba8);
        image.Fill(new Color(0.55f, 0.57f, 0.61f, 1.0f));
        _enemyIntentFallbackTexture = ImageTexture.CreateFromImage(image);
        return _enemyIntentFallbackTexture;
    }

    private string ResolveIntentDescription(string textKey)
    {
        if (string.IsNullOrWhiteSpace(textKey))
        {
            return string.Empty;
        }

        return ResolveFeedbackTemplate(textKey);
    }

    private static bool TryParseIntLabel(Label label, out int value)
    {
        if (label is null)
        {
            value = 0;
            return false;
        }

        return int.TryParse(label.Text, NumberStyles.Integer, CultureInfo.InvariantCulture, out value);
    }

    private static string NormalizeLocale(string locale)
    {
        if (string.IsNullOrWhiteSpace(locale))
        {
            return "en";
        }

        return locale.Trim().Replace('_', '-').ToLowerInvariant();
    }

    private sealed record CombatHudSnapshotPayload(
        List<string>? HandCards,
        int Energy,
        int DrawPileCount,
        int DiscardPileCount,
        int Difficulty,
        int PlayerHp,
        string? TurnState
    );

    private sealed record EnemyIntentContractPayload(
        List<EnemyIntentPreviewItemPayload>? EnemyIntents
    );

    private sealed record EnemyIntentPreviewItemPayload(
        string EnemyId,
        string IconId,
        string TextKey
    );

    private sealed record EnemyIntentState(
        string EnemyId,
        string IconId,
        string Description,
        int Turn
    );
}
