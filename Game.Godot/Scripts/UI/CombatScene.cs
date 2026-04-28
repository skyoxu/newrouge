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
    private HBoxContainer _cardButtonRow = default!;
    private Label _enemyStatusTitleLabel = default!;
    private Label _enemyNameValue = default!;
    private Label _enemyHpValue = default!;
    private Label _enemyBlockValue = default!;
    private Label _enemyStatusValue = default!;
    private Button _startTurnButton = default!;
    private Button _playSelectedCardButton = default!;
    private Button _endTurnButton = default!;
    private Label _turnTitleLabel = default!;
    private Label _actionHintLabel = default!;
    private Label _handTitleLabel = default!;

    private readonly List<string> _dispatchedCommands = new();
    private static readonly JsonSerializerOptions SnapshotJsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };
    private static readonly JsonDocumentOptions SafeJsonDocumentOptions = new()
    {
        MaxDepth = 128,
    };
    private int _coreStateMutationCount;
    private int _turnIndex = 1;
    private int _acceptedCommandFeedbackCount;
    private string _latestCommandOutcomeState = "none";
    private int _playerBlock;
    private int _exhaustPileCount;
    private int _enemyIntentTurnIndex;
    private const string DefaultEnemyId = "enemy_m1_slime";
    private readonly Dictionary<string, EnemyCombatState> _enemyCombatById = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Dictionary<string, int>> _enemyStatusStacksByEnemy = new(StringComparer.Ordinal);
    private readonly Dictionary<string, int> _playerStatusStacks = new(StringComparer.Ordinal);
    private readonly Dictionary<string, CardDefinitionRuntime> _cardDefinitionsByLookup = new(StringComparer.Ordinal);
    private string _selectedEnemyTargetId = string.Empty;
    private bool _hasPendingInvalidTargetSelection;
    private readonly Dictionary<string, EnemyIntentState> _enemyIntentByEnemy = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Texture2D> _enemyIntentTextureCache = new(StringComparer.Ordinal);
    private static readonly Dictionary<string, Dictionary<string, string>> FeedbackTextMapsByLocale = new(StringComparer.OrdinalIgnoreCase);
    private bool _cardDefinitionAutoLoadEnabledForTest = true;
    private static readonly string[] CardDefinitionCandidatePaths =
    {
        "res://Game.Core/Data/m1-card-definitions.json",
    };
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
        _cardButtonRow = GetNode<HBoxContainer>("HUD/CardButtonRow");
        _enemyStatusTitleLabel = GetNode<Label>("HUD/EnemyStatusPanel/EnemyStatusTitle");
        _enemyNameValue = GetNode<Label>("HUD/EnemyStatusPanel/EnemyNameValue");
        _enemyHpValue = GetNode<Label>("HUD/EnemyStatusPanel/EnemyHpValue");
        _enemyBlockValue = GetNode<Label>("HUD/EnemyStatusPanel/EnemyBlockValue");
        _enemyStatusValue = GetNode<Label>("HUD/EnemyStatusPanel/EnemyStatusValue");
        _startTurnButton = GetNode<Button>("HUD/TurnControls/StartTurnButton");
        _playSelectedCardButton = GetNode<Button>("HUD/TurnControls/PlaySelectedCardButton");
        _endTurnButton = GetNode<Button>("HUD/TurnControls/EndTurnButton");
        _turnTitleLabel = GetNode<Label>("HUD/TurnTitleLabel");
        _actionHintLabel = GetNode<Label>("HUD/ActionHintLabel");
        _handTitleLabel = GetNode<Label>("HUD/HandTitleLabel");

        _startTurnButton.Pressed += OnStartTurnPressed;
        _playSelectedCardButton.Pressed += OnPlaySelectedCardPressed;
        _endTurnButton.Pressed += OnEndTurnPressed;
        _startTurnButton.Visible = false;
        _startTurnButton.Text = ResolveUiText("combat.turn.start");
        _playSelectedCardButton.Text = ResolveUiText("combat.action.play_selected");
        _endTurnButton.Text = ResolveUiText("combat.turn.end");
        _turnTitleLabel.Text = ResolveUiText("combat.turn.title");
        _actionHintLabel.Text = ResolveUiText("combat.action.hint");
        _handTitleLabel.Text = ResolveUiText("combat.hand.title");
        _enemyStatusTitleLabel.Text = ResolveUiText("combat.enemy.title");
        _enemyIntentTitleLabel.Text = ResolveUiText("combat.intent.title");
        _feedbackMessageLabel.Text = string.Empty;
        ApplyDefaultM1CombatSnapshotIfEmpty();
        ApplyDefaultM1EnemyStateIfEmpty();
        ApplyDefaultM1EnemyIntentIfEmpty();
        EnsureCardDefinitionsLoaded();
        EnsureDefaultHandSelection();
    }

    public override void _ExitTree()
    {
        if (_startTurnButton is not null)
        {
            _startTurnButton.Pressed -= OnStartTurnPressed;
        }

        if (_playSelectedCardButton is not null)
        {
            _playSelectedCardButton.Pressed -= OnPlaySelectedCardPressed;
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
            { "exhaust", _exhaustPileCount.ToString(CultureInfo.InvariantCulture) },
            { "turnState", _turnStateValue.Text },
            { "selectedCommandState", _latestCommandOutcomeState },
            { "selectedEnemyTargetId", _selectedEnemyTargetId },
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
        if (actionName == "end_turn")
        {
            ResolveEndTurn();
            return true;
        }

        AppendCommandFeedback(actionName, accepted: true);
        return true;
    }

    public bool RequestTurnActionForTest(string actionName)
    {
        return RequestTurnAction(actionName);
    }

    public bool TryApplyCardDefinitionsContractJsonForTest(string definitionsJson)
    {
        if (string.IsNullOrWhiteSpace(definitionsJson))
        {
            return false;
        }

        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(definitionsJson, SafeJsonDocumentOptions);
        }
        catch (JsonException)
        {
            return false;
        }

        using (document)
        {
            if (!document.RootElement.TryGetProperty("cards", out var cards) || cards.ValueKind != JsonValueKind.Array)
            {
                return false;
            }

            _cardDefinitionsByLookup.Clear();
            foreach (var cardNode in cards.EnumerateArray())
            {
                if (!TryBuildCardDefinition(cardNode, out var parsedDefinition))
                {
                    continue;
                }

                RegisterCardDefinition(parsedDefinition);
            }
        }

        if (_cardDefinitionsByLookup.Count <= 0)
        {
            return false;
        }

        var handCards = new List<string>();
        for (var index = 0; index < _handCards.ItemCount; index++)
        {
            handCards.Add(_handCards.GetItemText(index));
        }

        RebuildCardButtons(handCards);
        return true;
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
        return TryPlayCard("strike");
    }

    public bool RequestPlaySelectedCardForTest()
    {
        return RequestPlaySelectedCard();
    }

    public bool RequestPlaySelectedCard()
    {
        var selectedItems = _handCards.GetSelectedItems();
        if (selectedItems.Length <= 0)
        {
            AppendCommandFeedback("play_card", accepted: false, refusalReasonKey: "combat.feedback.refusal_reason.no_card_selected");
            return false;
        }

        var selectedIndex = selectedItems[0];
        if (selectedIndex < 0 || selectedIndex >= _handCards.ItemCount)
        {
            AppendCommandFeedback("play_card", accepted: false, refusalReasonKey: "combat.feedback.refusal_reason.no_card_selected");
            return false;
        }

        var accepted = TryPlayCard(_handCards.GetItemText(selectedIndex), selectedIndex);
        if (accepted)
        {
            _dispatchedCommands.Add("play_card");
        }

        return accepted;
    }

    private bool TryPlayCard(string cardName, int selectedIndex = 0)
    {
        var normalizedCard = cardName.Trim();
        var handCards = new List<string>();
        for (var index = 0; index < _handCards.ItemCount; index++)
        {
            handCards.Add(_handCards.GetItemText(index));
        }

        if (selectedIndex < 0 || selectedIndex >= handCards.Count)
        {
            AppendCommandFeedback(normalizedCard, accepted: false, refusalReasonKey: "combat.feedback.refusal_reason.no_card_selected");
            return false;
        }

        if (!TryResolveCardDefinition(normalizedCard, out var definition))
        {
            AppendCommandFeedback(normalizedCard, accepted: false, refusalReasonKey: "combat.feedback.refusal_reason.missing_card_definition");
            return false;
        }

        if (!TryParseIntLabel(_energyValue, out var energy) || energy < definition.Cost)
        {
            AppendCommandFeedback(normalizedCard, accepted: false, refusalReasonKey: "combat.feedback.refusal_reason.insufficient_energy");
            return false;
        }

        string targetEnemyId = string.Empty;
        if (CardDefinitionRequiresEnemyTarget(definition) && !TryResolveSelectedAliveTarget(out targetEnemyId))
        {
            AppendCommandFeedback(normalizedCard, accepted: false, refusalReasonKey: "combat.feedback.refusal_reason.invalid_target");
            return false;
        }

        var difficulty = TryParseIntLabel(_difficultyValue, out var parsedDifficulty) ? parsedDifficulty : 0;
        var playerHp = TryParseIntLabel(_playerHpValue, out var parsedHp) ? parsedHp : 0;
        var drawPile = TryParseIntLabel(_drawPileValue, out var parsedDraw) ? parsedDraw : 0;
        var discardPile = TryParseIntLabel(_discardPileValue, out var parsedDiscard) ? parsedDiscard : 0;

        var result = ResolveCardEffect(definition, targetEnemyId);
        handCards.RemoveAt(selectedIndex);
        var remainingEnergy = energy - definition.Cost;
        if (result.MovedToExhaust)
        {
            _exhaustPileCount += 1;
        }

        var nextDiscardPile = result.MovedToExhaust ? discardPile : discardPile + 1;
        ApplyCoreSnapshot(new CombatHudSnapshot(
            handCards,
            remainingEnergy,
            drawPile,
            nextDiscardPile,
            difficulty,
            playerHp,
            _turnStateValue.Text));
        AppendCommandFeedback(normalizedCard, accepted: true, detail: BuildAcceptedCardDetail(result, remainingEnergy, definition.Cost));
        TryAutoCompleteVictoryRoute();
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

    public string GetEnemyHpTextForTest()
    {
        return _enemyHpValue.Text;
    }

    public string GetEnemyHpTextByIdForTest(string enemyId)
    {
        if (string.IsNullOrWhiteSpace(enemyId) || !_enemyCombatById.TryGetValue(enemyId.Trim(), out var state))
        {
            return string.Empty;
        }

        return $"{state.CurrentHp}/{state.MaxHp}";
    }

    public string GetEnemyStatusTextForTest()
    {
        return _enemyStatusValue.Text;
    }

    public string GetEnemyStatusForTest(string enemyId)
    {
        if (string.IsNullOrWhiteSpace(enemyId) || !_enemyCombatById.TryGetValue(enemyId, out var state))
        {
            return string.Empty;
        }

        return state.Status;
    }

    public int GetDiscardPileCountForTest()
    {
        return TryParseIntLabel(_discardPileValue, out var value) ? value : 0;
    }

    public int GetExhaustPileCountForTest()
    {
        return _exhaustPileCount;
    }

    public int GetPlayerBlockForTest()
    {
        return _playerBlock;
    }

    public void ClearCardDefinitionsForTest()
    {
        _cardDefinitionsByLookup.Clear();
    }

    public void SetCardDefinitionAutoLoadEnabledForTest(bool enabled)
    {
        _cardDefinitionAutoLoadEnabledForTest = enabled;
        if (enabled && _cardDefinitionsByLookup.Count <= 0)
        {
            EnsureCardDefinitionsLoaded();
        }
    }

    public string GetPlayerStatusSummaryForTest()
    {
        if (_playerStatusStacks.Count <= 0)
        {
            return string.Empty;
        }

        var parts = new List<string>();
        foreach (var (statusId, stacks) in _playerStatusStacks)
        {
            parts.Add($"{statusId}:{stacks}");
        }

        parts.Sort(StringComparer.Ordinal);
        return string.Join(",", parts);
    }

    public global::Godot.Collections.Array<string> GetAvailableEnemyTargetIdsForTest()
    {
        var ids = new global::Godot.Collections.Array<string>();
        foreach (var enemyId in GetAliveEnemyIds())
        {
            ids.Add(enemyId);
        }

        return ids;
    }

    public bool SetTargetEnemyIdForTest(string enemyId)
    {
        return TrySelectEnemyTarget(enemyId);
    }

    public string GetSelectedEnemyTargetIdForTest()
    {
        return _selectedEnemyTargetId;
    }

    public bool SetEnemyHpForTest(string enemyId, int currentHp, int maxHp)
    {
        if (string.IsNullOrWhiteSpace(enemyId) || maxHp <= 0 || currentHp < 0)
        {
            return false;
        }

        var hasEnemy = _enemyCombatById.TryGetValue(enemyId, out var existingState);
        var state = hasEnemy && existingState is not null
            ? existingState
            : new EnemyCombatState(enemyId, ResolveUiText("enemy.act1.slime_scout.name"), maxHp, 0, ResolveUiText("combat.enemy.status.none"));

        var clampedHp = Math.Min(maxHp, currentHp);
        _enemyCombatById[enemyId] = state with { CurrentHp = clampedHp, MaxHp = maxHp };
        if (clampedHp <= 0)
        {
            RemoveEnemyFromActiveSets(enemyId);
        }

        RefreshPrimaryEnemyPanel();
        return true;
    }

    public global::Godot.Collections.Dictionary RequestVictoryRouteToRewardForTest()
    {
        if (GetAliveEnemyIds().Count > 0)
        {
            return new global::Godot.Collections.Dictionary
            {
                { "ok", false },
                { "reason", "enemies-still-alive" },
            };
        }

        var main = ResolveMainRouteOwner();
        if (main is null || !main.HasMethod("CompleteMapNodeFlowForTest"))
        {
            return new global::Godot.Collections.Dictionary
            {
                { "ok", false },
                { "reason", "route-owner-unavailable" },
            };
        }

        return main.Call("CompleteMapNodeFlowForTest").AsGodotDictionary();
    }

    public void RefreshLocaleForTest()
    {
        _startTurnButton.Text = ResolveUiText("combat.turn.start");
        _playSelectedCardButton.Text = ResolveUiText("combat.action.play_selected");
        _endTurnButton.Text = ResolveUiText("combat.turn.end");
        _turnTitleLabel.Text = ResolveUiText("combat.turn.title");
        _actionHintLabel.Text = ResolveUiText("combat.action.hint");
        _handTitleLabel.Text = ResolveUiText("combat.hand.title");
        _enemyStatusTitleLabel.Text = ResolveUiText("combat.enemy.title");
        _enemyIntentTitleLabel.Text = ResolveUiText("combat.intent.title");
        var handCards = new List<string>();
        for (var index = 0; index < _handCards.ItemCount; index++)
        {
            handCards.Add(_handCards.GetItemText(index));
        }

        RebuildCardButtons(handCards);
        RefreshDefaultM1EnemyStateLocale();
        RefreshEnemyIntentRows();
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

    private void OnPlaySelectedCardPressed()
    {
        RequestPlaySelectedCard();
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
        _coreStateMutationCount += 1;
        RebuildCardButtons(snapshot.HandCards);
        EnsureDefaultHandSelection();
    }

    private void ResolveEndTurn()
    {
        var handCards = new List<string>();
        for (var index = 0; index < _handCards.ItemCount; index++)
        {
            handCards.Add(_handCards.GetItemText(index));
        }

        var difficulty = TryParseIntLabel(_difficultyValue, out var parsedDifficulty) ? parsedDifficulty : 0;
        var playerHp = TryParseIntLabel(_playerHpValue, out var parsedHp) ? parsedHp : 0;
        var drawPile = TryParseIntLabel(_drawPileValue, out var parsedDraw) ? parsedDraw : 0;
        var discardPile = TryParseIntLabel(_discardPileValue, out var parsedDiscard) ? parsedDiscard : 0;
        var incomingDamage = 6;
        var damageTaken = Math.Max(0, incomingDamage - _playerBlock);
        var nextPlayerHp = Math.Max(0, playerHp - damageTaken);

        _playerBlock = 0;
        _turnIndex += 1;
        ApplyCoreSnapshot(new CombatHudSnapshot(
            new List<string> { "Strike", "Defend", "Strike" },
            3,
            drawPile,
            discardPile + handCards.Count,
            difficulty,
            nextPlayerHp,
            "PlayerTurn"));
        ApplyDefaultM1EnemyIntentIfEmpty();
        AppendCommandFeedback("end_turn", accepted: true, detail: $"Enemy dealt {damageTaken} damage. Turn {_turnIndex} started.");
        if (nextPlayerHp <= 0)
        {
            TryAutoCompleteDefeatRoute("Player HP reached zero.");
        }
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
                var separator = locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase) ? "：" : ": ";
                message = $"{message.TrimEnd('.', '。')}{separator}{reasonText}";
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

    private CardEffectResult ResolveCardEffect(CardDefinitionRuntime definition, string targetEnemyId)
    {
        var dealtDamage = 0;
        if (definition.Target.Equals("all_enemies", StringComparison.OrdinalIgnoreCase))
        {
            foreach (var enemyId in GetAliveEnemyIds())
            {
                dealtDamage += ApplyDamageToEnemy(enemyId, definition.Damage);
            }
        }
        else if (definition.Damage > 0 && definition.Target.Equals("enemy", StringComparison.OrdinalIgnoreCase))
        {
            dealtDamage += ApplyDamageToEnemy(targetEnemyId, definition.Damage);
        }

        if (definition.Block > 0)
        {
            _playerBlock += definition.Block;
        }

        var statusDetail = string.Empty;
        if (definition.StatusStacks > 0 && !string.IsNullOrWhiteSpace(definition.StatusId))
        {
            if (definition.Target.Equals("self", StringComparison.OrdinalIgnoreCase))
            {
                ApplyStatusToPlayer(definition.StatusId, definition.StatusStacks);
                statusDetail = $"applied {definition.StatusId} +{definition.StatusStacks} to self";
            }
            else if (definition.Target.Equals("all_enemies", StringComparison.OrdinalIgnoreCase))
            {
                foreach (var enemyId in GetAliveEnemyIds())
                {
                    ApplyStatusToEnemy(enemyId, definition.StatusId, definition.StatusStacks);
                }

                statusDetail = $"applied {definition.StatusId} +{definition.StatusStacks} to all_enemies";
            }
            else
            {
                var resolvedEnemyId = string.IsNullOrWhiteSpace(targetEnemyId) ? DefaultEnemyId : targetEnemyId.Trim();
                ApplyStatusToEnemy(resolvedEnemyId, definition.StatusId, definition.StatusStacks);
                statusDetail = $"applied {definition.StatusId} +{definition.StatusStacks} to {resolvedEnemyId}";
            }
        }

        return new CardEffectResult(
            Damage: dealtDamage,
            Block: definition.Block,
            StatusDetail: statusDetail,
            MovedToExhaust: definition.Exhaust);
    }

    private int ApplyDamageToEnemy(string enemyId, int damage)
    {
        var resolvedEnemyId = string.IsNullOrWhiteSpace(enemyId) ? DefaultEnemyId : enemyId.Trim();
        if (!_enemyCombatById.TryGetValue(resolvedEnemyId, out var enemyState))
        {
            enemyState = new EnemyCombatState(resolvedEnemyId, ResolveUiText("enemy.act1.slime_scout.name"), 32, 0, ResolveUiText("combat.enemy.status.none"));
        }

        var currentHp = enemyState.CurrentHp;
        var maxHp = Math.Max(1, enemyState.MaxHp);
        var remainingHp = Math.Max(0, currentHp - Math.Max(0, damage));
        var actualDamage = Math.Max(0, currentHp - remainingHp);
        _enemyCombatById[resolvedEnemyId] = enemyState with { CurrentHp = remainingHp, MaxHp = maxHp };
        if (remainingHp <= 0)
        {
            RemoveEnemyFromActiveSets(resolvedEnemyId);
        }

        RefreshPrimaryEnemyPanel();
        return actualDamage;
    }

    private static (int Current, int Max) ParseEnemyHp(string text)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return (32, 32);
        }

        var parts = text.Split('/', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 2
            && int.TryParse(parts[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out var current)
            && int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out var max))
        {
            return (Math.Max(0, current), Math.Max(1, max));
        }

        return (32, 32);
    }

    private static string BuildAcceptedCardDetail(CardEffectResult result, int remainingEnergy, int paidCost)
    {
        var parts = new List<string>();
        if (result.Damage > 0)
        {
            parts.Add($"dealt {result.Damage} damage");
        }

        if (result.Block > 0)
        {
            parts.Add($"gained {result.Block} block");
        }

        if (!string.IsNullOrWhiteSpace(result.StatusDetail))
        {
            parts.Add(result.StatusDetail);
        }

        parts.Add(result.MovedToExhaust ? "moved to exhaust" : "moved to discard");
        parts.Add($"Energy -{paidCost} (remaining {remainingEnergy}).");
        return string.Join("; ", parts);
    }

    private static bool CardDefinitionRequiresEnemyTarget(CardDefinitionRuntime definition)
    {
        return definition.Target.Equals("enemy", StringComparison.OrdinalIgnoreCase);
    }

    private bool TryResolveCardDefinition(string cardName, out CardDefinitionRuntime definition)
    {
        EnsureCardDefinitionsLoaded();
        var key = NormalizeCardLookupKey(cardName);
        return _cardDefinitionsByLookup.TryGetValue(key, out definition!);
    }

    private void EnsureCardDefinitionsLoaded()
    {
        if (_cardDefinitionsByLookup.Count > 0)
        {
            return;
        }

        if (!_cardDefinitionAutoLoadEnabledForTest)
        {
            return;
        }

        _ = TryLoadCardDefinitionsFromData();
    }

    private bool TryLoadCardDefinitionsFromData()
    {
        foreach (var path in CardDefinitionCandidatePaths)
        {
            if (!FileAccess.FileExists(path))
            {
                continue;
            }

            using var file = FileAccess.Open(path, FileAccess.ModeFlags.Read);
            if (file is null)
            {
                continue;
            }

            JsonDocument document;
            try
            {
                document = JsonDocument.Parse(file.GetAsText(), SafeJsonDocumentOptions);
            }
            catch (JsonException)
            {
                continue;
            }

            using (document)
            {
                if (!document.RootElement.TryGetProperty("cards", out var cards) || cards.ValueKind != JsonValueKind.Array)
                {
                    continue;
                }

                foreach (var cardNode in cards.EnumerateArray())
                {
                    if (!TryBuildCardDefinition(cardNode, out var parsedDefinition))
                    {
                        continue;
                    }

                    RegisterCardDefinition(parsedDefinition);
                }
            }

            if (_cardDefinitionsByLookup.Count > 0)
            {
                return true;
            }
        }

        return false;
    }

    private bool TryBuildCardDefinition(JsonElement cardNode, out CardDefinitionRuntime definition)
    {
        definition = default!;
        if (!cardNode.TryGetProperty("id", out var idNode) || idNode.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        var id = idNode.GetString()?.Trim() ?? string.Empty;
        if (id.Length <= 0)
        {
            return false;
        }

        var target = cardNode.TryGetProperty("target", out var targetNode) && targetNode.ValueKind == JsonValueKind.String
            ? targetNode.GetString()?.Trim() ?? "enemy"
            : "enemy";
        var type = cardNode.TryGetProperty("type", out var typeNode) && typeNode.ValueKind == JsonValueKind.String
            ? typeNode.GetString()?.Trim() ?? "unknown"
            : "unknown";
        var nameKey = cardNode.TryGetProperty("name_key", out var nameKeyNode) && nameKeyNode.ValueKind == JsonValueKind.String
            ? nameKeyNode.GetString()?.Trim() ?? string.Empty
            : string.Empty;
        var descriptionKey = cardNode.TryGetProperty("description_key", out var descriptionNode) && descriptionNode.ValueKind == JsonValueKind.String
            ? descriptionNode.GetString()?.Trim() ?? string.Empty
            : string.Empty;
        var cost = cardNode.TryGetProperty("cost", out var costNode) && costNode.ValueKind == JsonValueKind.Number
            ? Math.Max(0, costNode.GetInt32())
            : 1;

        var damage = 0;
        var block = 0;
        var rage = 0;
        if (cardNode.TryGetProperty("base_effect", out var effectNode) && effectNode.ValueKind == JsonValueKind.Object)
        {
            if (effectNode.TryGetProperty("damage", out var damageNode) && damageNode.ValueKind == JsonValueKind.Number)
            {
                damage = Math.Max(0, damageNode.GetInt32());
            }

            if (effectNode.TryGetProperty("block", out var blockNode) && blockNode.ValueKind == JsonValueKind.Number)
            {
                block = Math.Max(0, blockNode.GetInt32());
            }

            if (effectNode.TryGetProperty("rage", out var rageNode) && rageNode.ValueKind == JsonValueKind.Number)
            {
                rage = Math.Max(0, rageNode.GetInt32());
            }
        }

        var statusId = rage > 0 ? "status.rage" : string.Empty;
        var exhaust = false;
        if (cardNode.TryGetProperty("exhaust", out var cardExhaustNode))
        {
            exhaust = cardExhaustNode.ValueKind switch
            {
                JsonValueKind.True => true,
                JsonValueKind.False => false,
                _ => exhaust,
            };
        }

        if (effectNode.ValueKind == JsonValueKind.Object
            && effectNode.TryGetProperty("exhaust", out var effectExhaustNode))
        {
            exhaust = effectExhaustNode.ValueKind switch
            {
                JsonValueKind.True => true,
                JsonValueKind.False => false,
                _ => exhaust,
            };
        }

        definition = new CardDefinitionRuntime(id, target, type, nameKey, descriptionKey, cost, damage, block, statusId, rage, exhaust);
        return true;
    }

    private void RegisterCardDefinition(CardDefinitionRuntime definition)
    {
        RegisterCardLookup(definition.Id, definition);
        RegisterCardLookup(definition.Id[(definition.Id.LastIndexOf('.') + 1)..], definition);

        var nameKey = string.IsNullOrWhiteSpace(definition.NameKey) ? $"{definition.Id}.name" : definition.NameKey;
        var enMap = GetFeedbackTextMap("en");
        if (enMap.TryGetValue(nameKey, out var enName))
        {
            RegisterCardLookup(enName, definition);
        }

        var zhMap = GetFeedbackTextMap("zh-cn");
        if (zhMap.TryGetValue(nameKey, out var zhName))
        {
            RegisterCardLookup(zhName, definition);
        }
    }

    private void RegisterCardLookup(string key, CardDefinitionRuntime definition)
    {
        var normalized = NormalizeCardLookupKey(key);
        if (normalized.Length <= 0)
        {
            return;
        }

        _cardDefinitionsByLookup[normalized] = definition;
    }

    private static string NormalizeCardLookupKey(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return string.Empty;
        }

        var chars = new List<char>(raw.Length);
        foreach (var ch in raw.Trim())
        {
            if (char.IsWhiteSpace(ch) || ch == '_' || ch == '-' || ch == '.')
            {
                continue;
            }

            chars.Add(char.ToLowerInvariant(ch));
        }

        return new string(chars.ToArray());
    }

    private void ApplyStatusToEnemy(string enemyId, string statusId, int stacks)
    {
        if (string.IsNullOrWhiteSpace(enemyId) || !_enemyCombatById.TryGetValue(enemyId, out var enemyState))
        {
            return;
        }

        if (!_enemyStatusStacksByEnemy.TryGetValue(enemyId, out var statusMap))
        {
            statusMap = new Dictionary<string, int>(StringComparer.Ordinal);
            _enemyStatusStacksByEnemy[enemyId] = statusMap;
        }

        statusMap.TryGetValue(statusId, out var current);
        statusMap[statusId] = current + stacks;
        _enemyCombatById[enemyId] = enemyState with { Status = BuildStatusSummary(statusMap) };
        RefreshPrimaryEnemyPanel();
    }

    private void ApplyStatusToPlayer(string statusId, int stacks)
    {
        _playerStatusStacks.TryGetValue(statusId, out var current);
        _playerStatusStacks[statusId] = current + stacks;
    }

    private string BuildStatusSummary(IReadOnlyDictionary<string, int> statusMap)
    {
        if (statusMap.Count <= 0)
        {
            return ResolveUiText("combat.enemy.status.none");
        }

        var parts = new List<string>();
        foreach (var (statusId, stacks) in statusMap)
        {
            parts.Add($"{statusId} +{stacks}");
        }

        parts.Sort(StringComparer.Ordinal);
        return string.Join(", ", parts);
    }

    private bool TryResolveSelectedAliveTarget(out string enemyId)
    {
        enemyId = string.Empty;
        if (_hasPendingInvalidTargetSelection)
        {
            _hasPendingInvalidTargetSelection = false;
            return false;
        }

        var selected = _selectedEnemyTargetId.Trim();
        if (selected.Length > 0)
        {
            if (_enemyCombatById.TryGetValue(selected, out var selectedState) && selectedState.CurrentHp > 0)
            {
                enemyId = selected;
                return true;
            }

            // Selected target became illegal (dead/disconnected). Clear selection deterministically.
            _selectedEnemyTargetId = string.Empty;
            return false;
        }

        return false;
    }

    private bool TrySelectEnemyTarget(string enemyId)
    {
        if (string.IsNullOrWhiteSpace(enemyId))
        {
            return false;
        }

        var normalized = enemyId.Trim();
        if (!_enemyCombatById.TryGetValue(normalized, out var state) || state.CurrentHp <= 0)
        {
            _hasPendingInvalidTargetSelection = true;
            return false;
        }

        _selectedEnemyTargetId = normalized;
        _hasPendingInvalidTargetSelection = false;
        RefreshPrimaryEnemyPanel();
        return true;
    }

    private List<string> GetAliveEnemyIds()
    {
        var ids = new List<string>();
        foreach (var (enemyId, state) in _enemyCombatById)
        {
            if (state.CurrentHp > 0)
            {
                ids.Add(enemyId);
            }
        }

        return ids;
    }

    private void RemoveEnemyFromActiveSets(string enemyId)
    {
        _enemyIntentByEnemy.Remove(enemyId);
        _enemyStatusStacksByEnemy.Remove(enemyId);
        if (string.Equals(_selectedEnemyTargetId, enemyId, StringComparison.Ordinal))
        {
            _selectedEnemyTargetId = string.Empty;
        }

        RefreshEnemyIntentRows();
    }

    private void RefreshPrimaryEnemyPanel()
    {
        var aliveEnemies = GetAliveEnemyIds();
        if (aliveEnemies.Count <= 0)
        {
            _enemyNameValue.Text = "--";
            _enemyHpValue.Text = "0/0";
            _enemyBlockValue.Text = "0";
            _enemyStatusValue.Text = ResolveUiText("combat.enemy.status.none");
            return;
        }

        var preferredId = _selectedEnemyTargetId;
        if (string.IsNullOrWhiteSpace(preferredId) || !_enemyCombatById.TryGetValue(preferredId, out var preferredState) || preferredState.CurrentHp <= 0)
        {
            preferredId = aliveEnemies[0];
            preferredState = _enemyCombatById[preferredId];
        }

        _enemyNameValue.Text = preferredState.Name;
        _enemyHpValue.Text = $"{preferredState.CurrentHp}/{preferredState.MaxHp}";
        _enemyBlockValue.Text = preferredState.Block.ToString(CultureInfo.InvariantCulture);
        _enemyStatusValue.Text = preferredState.Status;
    }

    private void TryAutoCompleteVictoryRoute()
    {
        if (GetAliveEnemyIds().Count > 0)
        {
            return;
        }

        var main = ResolveMainRouteOwner();
        if (main is not null && main.HasMethod("CompleteMapNodeFlowForTest"))
        {
            main.CallDeferred("CompleteMapNodeFlowForTest");
        }
    }

    private void TryAutoCompleteDefeatRoute(string reason)
    {
        var main = ResolveMainRouteOwner();
        if (main is not null && main.HasMethod("HandleCombatDefeatForTest"))
        {
            main.CallDeferred("HandleCombatDefeatForTest", reason);
        }
    }

    private Node? ResolveMainRouteOwner()
    {
        Node? current = this;
        while (current is not null)
        {
            if (current.HasMethod("CompleteMapNodeFlowForTest"))
            {
                return current;
            }

            current = current.GetParent();
        }

        var root = GetTree()?.Root;
        return root?.GetNodeOrNull<Node>("/root/Main");
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
                "combat.feedback.refusal_reason.missing_card_definition" => "missing card definition",
                "combat.invalid_action" => "invalid action",
                _ => "invalid action",
            };
        }

        return mapped.Trim();
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
            "combat.action.play_selected" => isZh ? "打出选中卡牌" : "Play Selected Card",
            "combat.action.hint" => isZh ? "选择一张手牌，然后点击“打出选中卡牌”；没有合适操作时点击“结束回合”。" : "Select a card, then click Play Selected Card. Click End Turn when you are done.",
            "combat.hand.title" => isZh ? "手牌" : "Hand",
            "combat.enemy.title" => isZh ? "敌人" : "Enemy",
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

            var textKey = preview.TextKey ?? string.Empty;
            var state = new EnemyIntentState(
                EnemyId: preview.EnemyId,
                IconId: preview.IconId ?? string.Empty,
                TextKey: textKey,
                Description: ResolveIntentDescription(textKey),
                Turn: _enemyIntentTurnIndex);
            _enemyIntentByEnemy[preview.EnemyId] = state;
            AddEnemyIntentRow(state);
        }

        _enemyIntentList.Visible = _enemyIntentByEnemy.Count > 0;
    }

    private void ApplyDefaultM1CombatSnapshotIfEmpty()
    {
        if (_handCards.ItemCount > 0)
        {
            return;
        }

        ApplyCoreSnapshot(new CombatHudSnapshot(
            new List<string> { "Strike", "Defend", "Strike" },
            3,
            7,
            0,
            1,
            80,
            "PlayerTurn"));
    }

    private void ApplyDefaultM1EnemyStateIfEmpty()
    {
        if (_enemyCombatById.Count > 0)
        {
            return;
        }

        _enemyCombatById[DefaultEnemyId] = new EnemyCombatState(
            DefaultEnemyId,
            ResolveUiText("enemy.act1.slime_scout.name"),
            32,
            0,
            ResolveUiText("combat.enemy.status.none"));
        _selectedEnemyTargetId = DefaultEnemyId;
        RefreshPrimaryEnemyPanel();
    }

    private void RefreshDefaultM1EnemyStateLocale()
    {
        if (_enemyCombatById.Count <= 0)
        {
            return;
        }

        foreach (var enemyId in new List<string>(_enemyCombatById.Keys))
        {
            var state = _enemyCombatById[enemyId];
            _enemyCombatById[enemyId] = state with
            {
                Name = ResolveUiText("enemy.act1.slime_scout.name"),
                Status = ResolveUiText("combat.enemy.status.none"),
            };
        }

        RefreshPrimaryEnemyPanel();
    }

    private void ApplyDefaultM1EnemyIntentIfEmpty()
    {
        if (_enemyIntentByEnemy.Count > 0)
        {
            return;
        }

        ApplyEnemyIntentPreview(new List<EnemyIntentPreviewItemPayload>
        {
            new("enemy_m1_slime", "icon_sword", "combat.intent.attack_6"),
        });
    }

    private void RebuildCardButtons(IReadOnlyList<string> handCards)
    {
        foreach (var child in _cardButtonRow.GetChildren())
        {
            _cardButtonRow.RemoveChild(child);
            child.QueueFree();
        }

        for (var index = 0; index < handCards.Count; index++)
        {
            var cardName = handCards[index];
            var cardIndex = index;
            var button = new Button
            {
                Name = $"CardButton_{index}",
                Text = BuildCardButtonText(cardName),
                CustomMinimumSize = new Vector2(128, 56),
                SizeFlagsHorizontal = SizeFlags.ShrinkBegin,
            };
            button.Pressed += () =>
            {
                _handCards.DeselectAll();
                _handCards.Select(cardIndex);
                RequestPlaySelectedCard();
            };
            _cardButtonRow.AddChild(button);
        }
    }

    private string BuildCardButtonText(string cardName)
    {
        if (!TryResolveCardDefinition(cardName, out var definition))
        {
            return cardName;
        }

        var displayName = ResolveCardDisplayName(definition);
        var typeText = string.IsNullOrWhiteSpace(definition.Type) ? "unknown" : definition.Type;
        var effectSummary = ResolveCardEffectSummary(definition);
        return $"{displayName}\nCost {definition.Cost} | {typeText}\n{effectSummary}";
    }

    private static string ResolveCardDisplayName(CardDefinitionRuntime definition)
    {
        if (!string.IsNullOrWhiteSpace(definition.NameKey))
        {
            var localized = ResolveFeedbackTemplate(definition.NameKey);
            if (!string.Equals(localized, definition.NameKey, StringComparison.Ordinal))
            {
                return localized;
            }
        }

        var lastDot = definition.Id.LastIndexOf('.');
        return lastDot >= 0 && lastDot < definition.Id.Length - 1
            ? definition.Id[(lastDot + 1)..]
            : definition.Id;
    }

    private static string ResolveCardEffectSummary(CardDefinitionRuntime definition)
    {
        if (!string.IsNullOrWhiteSpace(definition.DescriptionKey))
        {
            var localized = ResolveFeedbackTemplate(definition.DescriptionKey);
            if (!string.Equals(localized, definition.DescriptionKey, StringComparison.Ordinal))
            {
                return localized;
            }
        }

        var parts = new List<string>();
        if (definition.Damage > 0)
        {
            parts.Add($"Deal {definition.Damage} damage.");
        }

        if (definition.Block > 0)
        {
            parts.Add($"Gain {definition.Block} block.");
        }

        if (definition.StatusStacks > 0 && !string.IsNullOrWhiteSpace(definition.StatusId))
        {
            parts.Add($"Apply {definition.StatusId} +{definition.StatusStacks}.");
        }

        if (parts.Count <= 0)
        {
            parts.Add("No effect summary.");
        }

        return string.Join(" ", parts);
    }

    private void RefreshEnemyIntentRows()
    {
        foreach (var child in _enemyIntentList.GetChildren())
        {
            _enemyIntentList.RemoveChild(child);
            child.QueueFree();
        }

        foreach (var (enemyId, state) in _enemyIntentByEnemy)
        {
            var refreshed = state with { Description = ResolveIntentDescription(state.TextKey) };
            _enemyIntentByEnemy[enemyId] = refreshed;
            AddEnemyIntentRow(refreshed);
        }

        _enemyIntentList.Visible = _enemyIntentByEnemy.Count > 0;
    }

    private void EnsureDefaultHandSelection()
    {
        if (_handCards.ItemCount <= 0 || _handCards.GetSelectedItems().Length > 0)
        {
            return;
        }

        _handCards.Select(0);
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
        string TextKey,
        string Description,
        int Turn
    );

    private sealed record EnemyCombatState(
        string EnemyId,
        string Name,
        int CurrentHp,
        int Block,
        string Status,
        int MaxHp = 32
    );

    private sealed record CardEffectResult(int Damage, int Block, string StatusDetail, bool MovedToExhaust);
    private sealed record CardDefinitionRuntime(
        string Id,
        string Target,
        string Type,
        string NameKey,
        string DescriptionKey,
        int Cost,
        int Damage,
        int Block,
        string StatusId,
        int StatusStacks,
        bool Exhaust);
}
