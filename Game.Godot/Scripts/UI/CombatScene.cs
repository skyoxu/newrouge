using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using Godot;
using Game.Core.Contracts.Combat;
using Game.Core.Services;

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
    private VBoxContainer _powerRelicPanel = default!;
    private Label _powerRelicTitleLabel = default!;
    private ItemList _powerParticipantList = default!;
    private ItemList _relicParticipantList = default!;
    private ItemList _potionParticipantList = default!;
    private HBoxContainer _cardButtonRow = default!;
    private Label _enemyStatusTitleLabel = default!;
    private PanelContainer _enemyPortraitFrame = default!;
    private ColorRect _enemyTargetHighlight = default!;
    private TextureRect _enemyPortrait = default!;
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
    private Label _debugScenePathLabel = default!;
    private Label _debugPortraitStatusLabel = default!;
    private Label _debugDragStateLabel = default!;
    private Label _debugMouseStateLabel = default!;
    private PanelContainer _dragCardGhost = default!;
    private Label _dragCardGhostTitle = default!;
    private Label _dragCardGhostCost = default!;
    private Label _dragCardGhostType = default!;
    private Label _dragCardGhostSummary = default!;

    private readonly List<string> _dispatchedCommands = new();
    private static readonly JsonSerializerOptions SnapshotJsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };
    private static readonly HashSet<string> AllowedStatusIds = new(StringComparer.Ordinal)
    {
        "status.rage",
        "status.strength",
        "status.weak",
        "status.vulnerable",
        "status.block",
        "status.poison",
        "status.temp_attack_up",
        "status.temp_attack_down",
        "status.temp_defense_up",
        "status.temp_defense_down",
        "status.bloodbeat",
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
    private int _enemyIntentSelectionRngCursor;
    private string _lastPlayCardExecutionFingerprint = string.Empty;
    private string _lastPlayCardOrderingKey = string.Empty;
    private readonly List<string> _lastPlayCardExecutedSteps = new();
    private readonly List<string> _presentationCueHistory = new();
    private readonly List<string> _sfxHookHistory = new();
    private readonly List<string> _missingSfxNoopHistory = new();
    private string _lastHoverPreviewText = string.Empty;
    private bool _isCardDragActive;
    private int _draggedHandIndex = -1;
    private string _draggedTargetEnemyId = string.Empty;
    private bool _wasLeftMousePressed;
    private bool _runtimePointerStateOverrideEnabled;
    private Vector2 _runtimePointerPositionOverride = Vector2.Zero;
    private bool _runtimePointerPressedOverride;
    private bool _reducedMotionForTest;
    private bool _simulateMissingSfxForTest;
    private int _lastPlayCardOverplayTax;
    private bool _lastPlayCardPipelineSuccess;
    private const string DefaultEnemyId = "enemy_m1_slime";
    private readonly Dictionary<string, EnemyCombatState> _enemyCombatById = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Dictionary<string, int>> _enemyStatusStacksByEnemy = new(StringComparer.Ordinal);
    private readonly Dictionary<string, int> _playerStatusStacks = new(StringComparer.Ordinal);
    private readonly Dictionary<string, CardDefinitionRuntime> _cardDefinitionsByLookup = new(StringComparer.Ordinal);
    private string _selectedEnemyTargetId = string.Empty;
    private bool _hasPendingInvalidTargetSelection;
    private readonly Dictionary<string, EnemyIntentState> _enemyIntentByEnemy = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Texture2D> _enemyIntentTextureCache = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> _powerInspectById = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> _relicInspectById = new(StringComparer.Ordinal);
    private readonly Dictionary<string, TriggerOrderItemPayload> _powerTriggerById = new(StringComparer.Ordinal);
    private readonly Dictionary<string, TriggerOrderItemPayload> _relicTriggerById = new(StringComparer.Ordinal);
    private readonly Dictionary<string, TriggerOrderItemPayload> _potionTriggerById = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> _powerOutcomeById = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> _relicOutcomeById = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> _potionOutcomeById = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> _potionInspectById = new(StringComparer.Ordinal);
    private readonly HashSet<string> _potionVisibleOnSurfaceIds = new(StringComparer.Ordinal);
    private bool _potionRuntimeClosureExecutedForTest;
    private readonly List<string> _lastPowerRelicTriggerOrder = new();
    private readonly List<string> _lastPowerRelicOutcomeMessages = new();
    private bool _sceneLocalEffectStackUsedForTest;
    private static readonly Dictionary<string, Dictionary<string, string>> FeedbackTextMapsByLocale = new(StringComparer.OrdinalIgnoreCase);
    private bool _cardDefinitionAutoLoadEnabledForTest = true;
    private bool _enemyIntentDefinitionAutoLoadEnabledForTest = true;
    private static readonly string[] CardDefinitionCandidatePaths =
    {
        "res://Game.Core/Data/m1-card-definitions.json",
        "res://../Game.Core/Data/m1-card-definitions.json",
    };
    private static readonly string[] EnemyIntentDefinitionCandidatePaths =
    {
        "res://Game.Core/Data/m1-enemy-intent-definitions.json",
    };
    private Texture2D? _enemyIntentFallbackTexture;
    private Texture2D? _enemyPortraitFallbackTexture;
    private bool _defeatResolvedForCurrentHpDrop;
    private int _hpChangedEmissionCount;
    private int _defeatEligibleTransitionCount;
    private int _defeatResolveCount;
    private int _unifiedHpUpdateEntryCount;
    private int _cardsPlayedThisTurn;
    private float _targetHighlightPulsePhase;
    private readonly CombatService _combatService = new();
    private string _lastResolvedEnemyPortraitPath = "unresolved";

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
        _powerRelicPanel = GetNode<VBoxContainer>("HUD/PowerRelicPanel");
        _powerRelicTitleLabel = GetNode<Label>("HUD/PowerRelicPanel/PowerRelicTitle");
        _powerParticipantList = GetNode<ItemList>("HUD/PowerRelicPanel/PowerParticipantList");
        _relicParticipantList = GetNode<ItemList>("HUD/PowerRelicPanel/RelicParticipantList");
        _potionParticipantList = GetNode<ItemList>("HUD/PowerRelicPanel/PotionParticipantList");
        _cardButtonRow = GetNode<HBoxContainer>("HUD/CardButtonRow");
        _enemyStatusTitleLabel = GetNode<Label>("HUD/EnemyStatusPanel/EnemyStatusTitle");
        _enemyPortraitFrame = GetNode<PanelContainer>("HUD/EnemyStatusPanel/EnemyPortraitFrame");
        _enemyTargetHighlight = GetNode<ColorRect>("HUD/EnemyStatusPanel/EnemyTargetHighlight");
        _enemyPortrait = GetNode<TextureRect>("HUD/EnemyStatusPanel/EnemyPortraitFrame/EnemyPortrait");
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
        _debugScenePathLabel = GetNode<Label>("HUD/DebugPanel/DebugMargin/DebugVBox/DebugScenePath");
        _debugPortraitStatusLabel = GetNode<Label>("HUD/DebugPanel/DebugMargin/DebugVBox/DebugPortraitStatus");
        _debugDragStateLabel = GetNode<Label>("HUD/DebugPanel/DebugMargin/DebugVBox/DebugDragState");
        _debugMouseStateLabel = GetNode<Label>("HUD/DebugPanel/DebugMargin/DebugVBox/DebugMouseState");
        _dragCardGhost = GetNode<PanelContainer>("HUD/DragCardGhost");
        _dragCardGhostTitle = GetNode<Label>("HUD/DragCardGhost/GhostMargin/GhostBody/GhostHeader/GhostHeaderRow/GhostTitle");
        _dragCardGhostCost = GetNode<Label>("HUD/DragCardGhost/GhostMargin/GhostBody/GhostHeader/GhostHeaderRow/GhostCostBadge/GhostCost");
        _dragCardGhostType = GetNode<Label>("HUD/DragCardGhost/GhostMargin/GhostBody/GhostMetaRow/GhostTypeBadge/GhostType");
        _dragCardGhostSummary = GetNode<Label>("HUD/DragCardGhost/GhostMargin/GhostBody/GhostSummary");

        _startTurnButton.Pressed += OnStartTurnPressed;
        _playSelectedCardButton.Pressed += OnPlaySelectedCardPressed;
        _endTurnButton.Pressed += OnEndTurnPressed;
        _handCards.ItemClicked += OnHandCardClicked;
        _handCards.GuiInput += OnHandCardsGuiInput;
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
        _powerRelicTitleLabel.Text = "Power/Relic/Potion Participants";
        _powerRelicPanel.Visible = false;
        ApplyDefaultM1CombatSnapshotIfEmpty();
        ApplyDefaultM1EnemyStateIfEmpty();
        ApplyDefaultM1EnemyIntentIfEmpty();
        EnsureCardDefinitionsLoaded();
        EnsureDefaultHandSelection();
        RefreshRuntimeDebugPanel();
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

        if (_handCards is not null)
        {
            _handCards.ItemClicked -= OnHandCardClicked;
            _handCards.GuiInput -= OnHandCardsGuiInput;
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
        ApplyPowerRelicParticipants(payload.Powers, payload.Relics, payload.Potions);
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
            return ResolveEndTurn();
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
        var selectedIndex = _isCardDragActive ? _draggedHandIndex : ResolveSelectedHandIndex();
        if (selectedIndex < 0 || selectedIndex >= _handCards.ItemCount)
        {
            _lastHoverPreviewText = string.Empty;
            return;
        }
        var cardName = _handCards.GetItemText(selectedIndex);
        if (!TryResolveCardDefinition(cardName, out var definition))
        {
            _lastHoverPreviewText = string.Empty;
            return;
        }
        var localizedEffect = ResolveFeedbackTemplate(definition.DescriptionKey);
        _lastHoverPreviewText =
            $"id={previewId};cost={definition.Cost};type={definition.Type};target={definition.Target};effect={localizedEffect}";
        PublishPresentationCue("card_preview");
    }

    public void CloseHoverPreviewForTest()
    {
        _lastHoverPreviewText = string.Empty;
        PublishPresentationCue("card_preview_closed");
    }

    public void ApplyTargetInspectionForTest(string targetId)
    {
        var normalized = string.IsNullOrWhiteSpace(targetId) ? string.Empty : targetId.Trim();
        if (!string.IsNullOrEmpty(normalized)
            && (_enemyIntentByEnemy.ContainsKey(normalized) || _enemyCombatById.ContainsKey(normalized)))
        {
            PublishPresentationCue("intent_detail_opened");
        }
        if (_isCardDragActive)
        {
            _draggedTargetEnemyId = normalized;
            _ = TrySelectEnemyTarget(normalized);
            UpdateActionHintForCurrentInteraction();
        }
        _ = TryInspectParticipant(targetId);
    }

    public void HideTargetInspectionForTest()
    {
        PublishPresentationCue("intent_detail_hidden");
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

    public string GetLastHoverPreviewTextForTest()
    {
        return _lastHoverPreviewText;
    }

    public bool BeginCardDragForTest(int handIndex)
    {
        return BeginCardDrag(handIndex);
    }

    public void HoverEnemyTargetForTest(string enemyId)
    {
        HoverEnemyTarget(enemyId);
    }

    public bool ReleaseDraggedCardForTest()
    {
        return ReleaseDraggedCard();
    }

    public void CancelCardDragForTest()
    {
        CancelCardDrag();
    }

    public bool IsCardDragActiveForTest()
    {
        return _isCardDragActive;
    }

    public int GetDraggedHandIndexForTest()
    {
        return _draggedHandIndex;
    }

    public string GetDraggedTargetEnemyIdForTest()
    {
        return _draggedTargetEnemyId;
    }

    public string GetActionHintTextForTest()
    {
        return _actionHintLabel.Text;
    }

    public bool IsEnemyTargetHighlightActiveForTest()
    {
        return _isCardDragActive
            && !string.IsNullOrWhiteSpace(_draggedTargetEnemyId)
            && _enemyCombatById.TryGetValue(_draggedTargetEnemyId, out var hoveredState)
            && hoveredState.CurrentHp > 0;
    }

    public bool IsDragGhostVisibleForTest()
    {
        return _dragCardGhost.Visible;
    }

    public string GetDragGhostTextForTest()
    {
        return _dragCardGhostTitle.Text;
    }

    public string GetRuntimeDebugSceneTextForTest()
    {
        return _debugScenePathLabel.Text;
    }

    public string GetRuntimeDebugPortraitTextForTest()
    {
        return _debugPortraitStatusLabel.Text;
    }

    public string GetRuntimeDebugDragTextForTest()
    {
        return _debugDragStateLabel.Text;
    }

    public void SetRuntimePointerStateForTest(Vector2 position, bool isLeftPressed)
    {
        _runtimePointerStateOverrideEnabled = true;
        _runtimePointerPositionOverride = position;
        _runtimePointerPressedOverride = isLeftPressed;
    }

    public bool SetRuntimePointerToHandCardForTest(int handIndex, bool isLeftPressed)
    {
        if (handIndex < 0 || handIndex >= _handCards.ItemCount)
        {
            return false;
        }

        SetRuntimePointerStateForTest(GetHandCardPointerForTest(handIndex), isLeftPressed);
        return true;
    }

    public bool SetRuntimePointerToEnemyTargetForTest(string enemyId, bool isLeftPressed)
    {
        var pointer = GetEnemyTargetPointerForTest(enemyId);
        if (pointer == Vector2.Zero)
        {
            return false;
        }

        SetRuntimePointerStateForTest(pointer, isLeftPressed);
        return true;
    }

    public void ClearRuntimePointerStateOverrideForTest()
    {
        _runtimePointerStateOverrideEnabled = false;
        _runtimePointerPositionOverride = Vector2.Zero;
        _runtimePointerPressedOverride = false;
    }

    public void AdvanceRuntimeInputFrameForTest()
    {
        ProcessRuntimePointerState();
        RefreshRuntimeDebugPanel();
    }

    public Vector2 GetHandCardPointerForTest(int handIndex)
    {
        if (handIndex < 0 || handIndex >= _handCards.ItemCount)
        {
            return Vector2.Zero;
        }

        var itemRect = _handCards.GetItemRect(handIndex);
        var candidateLocals = new[]
        {
            itemRect.Position + itemRect.Size / 2.0f,
            itemRect.Position + new Vector2(8.0f, 8.0f),
            itemRect.Position + new Vector2(Mathf.Max(8.0f, itemRect.Size.X - 8.0f), 8.0f),
            itemRect.Position + new Vector2(8.0f, Mathf.Max(8.0f, itemRect.Size.Y - 8.0f)),
        };

        foreach (var local in candidateLocals)
        {
            if (_handCards.GetItemAtPosition(local, true) == handIndex)
            {
                return _handCards.GlobalPosition + local;
            }
        }

        return _handCards.GlobalPosition + itemRect.Position + itemRect.Size / 2.0f;
    }

    public Vector2 GetEnemyPanelPointerForTest()
    {
        return _enemyStatusValue.GetParent<Control>().GetGlobalRect().GetCenter();
    }

    public Vector2 GetEnemyTargetPointerForTest(string enemyId)
    {
        if (string.IsNullOrWhiteSpace(enemyId))
        {
            return Vector2.Zero;
        }

        var normalizedEnemyId = enemyId.Trim();
        foreach (var child in _enemyIntentList.GetChildren())
        {
            if (child is not Control row || !row.HasMeta("enemy_id"))
            {
                continue;
            }

            if (string.Equals(row.GetMeta("enemy_id").AsString(), normalizedEnemyId, StringComparison.Ordinal))
            {
                return row.GetGlobalRect().GetCenter();
            }
        }

        if (_enemyCombatById.ContainsKey(normalizedEnemyId))
        {
            return GetEnemyPanelPointerForTest();
        }

        return Vector2.Zero;
    }

    public global::Godot.Collections.Array<string> GetPresentationCueHistoryForTest()
    {
        var cues = new global::Godot.Collections.Array<string>();
        foreach (var cue in _presentationCueHistory)
        {
            cues.Add(cue);
        }
        return cues;
    }

    public global::Godot.Collections.Array<string> GetSfxHookHistoryForTest()
    {
        var hooks = new global::Godot.Collections.Array<string>();
        foreach (var hook in _sfxHookHistory)
        {
            hooks.Add(hook);
        }
        return hooks;
    }

    public global::Godot.Collections.Array<string> GetMissingSfxNoopHistoryForTest()
    {
        var hooks = new global::Godot.Collections.Array<string>();
        foreach (var hook in _missingSfxNoopHistory)
        {
            hooks.Add(hook);
        }
        return hooks;
    }

    public void SetReducedMotionForTest(bool enabled)
    {
        _reducedMotionForTest = enabled;
    }

    public void SetSimulateMissingSfxForTest(bool enabled)
    {
        _simulateMissingSfxForTest = enabled;
    }

    public bool TryApplyAcceptedStrikeForTest()
    {
        return TryPlayCard("strike");
    }

    public bool RequestPlaySelectedCardForTest()
    {
        return RequestPlaySelectedCard();
    }

    public bool TryApplyPowerRelicParticipantsContractJsonForTest(string participantsJson)
    {
        if (string.IsNullOrWhiteSpace(participantsJson))
        {
            return false;
        }

        ParticipantsContractPayload? payload;
        try
        {
            payload = JsonSerializer.Deserialize<ParticipantsContractPayload>(participantsJson, SnapshotJsonOptions);
        }
        catch (JsonException)
        {
            return false;
        }

        if (payload is null)
        {
            return false;
        }

        ApplyPowerRelicParticipants(payload.Powers, payload.Relics, payload.Potions);
        return _powerInspectById.Count > 0 || _relicInspectById.Count > 0 || _potionInspectById.Count > 0;
    }

    public global::Godot.Collections.Array<string> GetVisiblePowerIdsForTest()
    {
        var ids = new global::Godot.Collections.Array<string>();
        foreach (var id in _powerInspectById.Keys.OrderBy(static item => item, StringComparer.Ordinal))
        {
            ids.Add(id);
        }

        return ids;
    }

    public global::Godot.Collections.Array<string> GetVisibleRelicIdsForTest()
    {
        var ids = new global::Godot.Collections.Array<string>();
        foreach (var id in _relicInspectById.Keys.OrderBy(static item => item, StringComparer.Ordinal))
        {
            ids.Add(id);
        }

        return ids;
    }

    public global::Godot.Collections.Array<string> GetVisiblePotionIdsForTest()
    {
        var ids = new global::Godot.Collections.Array<string>();
        foreach (var id in _potionVisibleOnSurfaceIds.OrderBy(static item => item, StringComparer.Ordinal))
        {
            ids.Add(id);
        }

        return ids;
    }

    public string GetParticipantInspectTextForTest(string participantId)
    {
        if (string.IsNullOrWhiteSpace(participantId))
        {
            return string.Empty;
        }

        var normalized = participantId.Trim();
        if (_powerInspectById.TryGetValue(normalized, out var powerInspect))
        {
            return powerInspect;
        }

        if (_relicInspectById.TryGetValue(normalized, out var relicInspect))
        {
            return relicInspect;
        }

        if (_potionInspectById.TryGetValue(normalized, out var potionInspect))
        {
            return potionInspect;
        }

        return string.Empty;
    }

    public bool WasPotionRuntimeClosureExecutedForTest()
    {
        return _potionRuntimeClosureExecutedForTest;
    }

    public bool HasPowerRelicSurfaceForTest()
    {
        return _powerRelicPanel.Visible;
    }

    public string GetPowerParticipantSurfaceTextForTest(string participantId)
    {
        if (string.IsNullOrWhiteSpace(participantId))
        {
            return string.Empty;
        }

        var normalized = participantId.Trim();
        return FindParticipantSurfaceText(_powerParticipantList, normalized);
    }

    public string GetRelicParticipantSurfaceTextForTest(string participantId)
    {
        if (string.IsNullOrWhiteSpace(participantId))
        {
            return string.Empty;
        }

        var normalized = participantId.Trim();
        return FindParticipantSurfaceText(_relicParticipantList, normalized);
    }

    public string GetPotionParticipantSurfaceTextForTest(string participantId)
    {
        if (string.IsNullOrWhiteSpace(participantId))
        {
            return string.Empty;
        }

        var normalized = participantId.Trim();
        return FindParticipantSurfaceText(_potionParticipantList, normalized);
    }

    public int GetPotionSurfaceIndexForTest(string participantId)
    {
        if (string.IsNullOrWhiteSpace(participantId))
        {
            return -1;
        }

        var normalized = participantId.Trim();
        for (var index = 0; index < _potionParticipantList.ItemCount; index++)
        {
            var itemText = _potionParticipantList.GetItemText(index);
            var itemId = ExtractParticipantIdFromSurfaceText(itemText);
            if (string.Equals(itemId, normalized, StringComparison.Ordinal))
            {
                return index;
            }
        }

        return -1;
    }

    public bool RequestPotionInspectBySurfaceIndexForTest(int index)
    {
        if (index < 0 || index >= _potionParticipantList.ItemCount)
        {
            return false;
        }

        var itemText = _potionParticipantList.GetItemText(index);
        var participantId = ExtractParticipantIdFromSurfaceText(itemText);
        return TryInspectParticipant(participantId);
    }

    public bool RequestPotionInspectFromSurfaceForTest(string participantId)
    {
        if (string.IsNullOrWhiteSpace(participantId))
        {
            return false;
        }

        var normalized = participantId.Trim();
        if (!_potionVisibleOnSurfaceIds.Contains(normalized))
        {
            return false;
        }

        if (string.IsNullOrWhiteSpace(FindParticipantSurfaceText(_potionParticipantList, normalized)))
        {
            return false;
        }

        return TryInspectParticipant(normalized);
    }

    public bool RequestPotionInspectFromCombatSurfaceActionForTest(string participantId)
    {
        if (string.IsNullOrWhiteSpace(participantId))
        {
            return false;
        }

        var normalized = participantId.Trim();
        if (!_potionInspectById.ContainsKey(normalized))
        {
            return false;
        }

        // Explicit combat-surface inspect action path: the action is reachable even when
        // a potion is not directly visible in the surface participant list.
        return TryInspectParticipant(normalized);
    }

    public int GetPotionPriorityForTest(string participantId)
    {
        if (string.IsNullOrWhiteSpace(participantId))
        {
            return -1;
        }

        var normalized = participantId.Trim();
        return _potionTriggerById.TryGetValue(normalized, out var payload) ? payload.Priority : -1;
    }

    public int GetPotionRegistrationOrderForTest(string participantId)
    {
        if (string.IsNullOrWhiteSpace(participantId))
        {
            return -1;
        }

        var normalized = participantId.Trim();
        return _potionTriggerById.TryGetValue(normalized, out var payload) ? payload.RegistrationOrder : -1;
    }

    public string GetPotionOutcomeMessageForTest(string participantId)
    {
        if (string.IsNullOrWhiteSpace(participantId))
        {
            return string.Empty;
        }

        var normalized = participantId.Trim();
        return _potionOutcomeById.TryGetValue(normalized, out var message) ? message : string.Empty;
    }

    public bool TryResolvePowerRelicTriggerOrderFromContractJsonForTest(string contractJson)
    {
        if (string.IsNullOrWhiteSpace(contractJson))
        {
            return false;
        }

        TriggerOrderContractPayload? payload;
        try
        {
            payload = JsonSerializer.Deserialize<TriggerOrderContractPayload>(contractJson, SnapshotJsonOptions);
        }
        catch (JsonException)
        {
            return false;
        }

        if (payload?.Triggers is null || payload.Triggers.Count <= 0)
        {
            return false;
        }

        var keys = new List<CombatTriggerOrderKey>();
        foreach (var item in payload.Triggers)
        {
            var sourceId = (item.SourceId ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(sourceId))
            {
                continue;
            }

            keys.Add(new CombatTriggerOrderKey(sourceId, item.Priority, item.RegistrationOrder));
        }

        if (keys.Count <= 0)
        {
            return false;
        }

        var ordered = PlayCardResolutionPipeline.ResolveTriggerOrder(keys);
        _lastPowerRelicTriggerOrder.Clear();
        foreach (var sourceId in ordered)
        {
            _lastPowerRelicTriggerOrder.Add(sourceId);
        }

        return true;
    }

    public global::Godot.Collections.Array<string> GetLastPowerRelicTriggerOrderForTest()
    {
        var order = new global::Godot.Collections.Array<string>();
        foreach (var sourceId in _lastPowerRelicTriggerOrder)
        {
            order.Add(sourceId);
        }

        return order;
    }

    public bool TryApplyPowerRelicOutcomeContractJsonForTest(string outcomesJson)
    {
        if (string.IsNullOrWhiteSpace(outcomesJson))
        {
            return false;
        }

        OutcomeContractPayload? payload;
        try
        {
            payload = JsonSerializer.Deserialize<OutcomeContractPayload>(outcomesJson, SnapshotJsonOptions);
        }
        catch (JsonException)
        {
            return false;
        }

        if (payload?.Outcomes is null || payload.Outcomes.Count <= 0)
        {
            return false;
        }

        var published = 0;
        foreach (var item in payload.Outcomes)
        {
            var sourceId = (item.SourceId ?? string.Empty).Trim();
            var message = (item.Message ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(sourceId) || string.IsNullOrWhiteSpace(message))
            {
                continue;
            }

            var canPublish =
                sourceId.StartsWith("Power.", StringComparison.Ordinal)
                || sourceId.StartsWith("Relic.", StringComparison.Ordinal);
            if (!canPublish)
            {
                continue;
            }

            PublishPowerRelicOutcomeMessage($"{sourceId}: {message}");
            published += 1;
        }

        return published > 0;
    }

    public global::Godot.Collections.Array<string> GetLastPowerRelicOutcomeMessagesForTest()
    {
        var messages = new global::Godot.Collections.Array<string>();
        foreach (var message in _lastPowerRelicOutcomeMessages)
        {
            messages.Add(message);
        }

        return messages;
    }

    public bool IsSceneLocalEffectStackUsedForTest()
    {
        return _sceneLocalEffectStackUsedForTest;
    }

    public string GetLastPlayCardExecutionFingerprintForTest()
    {
        return _lastPlayCardExecutionFingerprint;
    }

    public string GetLastPlayCardOrderingKeyForTest()
    {
        return _lastPlayCardOrderingKey;
    }

    public int GetLastPlayCardOverplayTaxForTest()
    {
        return _lastPlayCardOverplayTax;
    }

    public bool WasLastPlayCardPipelineSuccessfulForTest()
    {
        return _lastPlayCardPipelineSuccess;
    }

    public global::Godot.Collections.Array<string> GetLastPlayCardExecutedStepsForTest()
    {
        var steps = new global::Godot.Collections.Array<string>();
        foreach (var step in _lastPlayCardExecutedSteps)
        {
            steps.Add(step);
        }

        return steps;
    }

    public bool RequestPlaySelectedCard()
    {
        var selectedIndex = ResolveSelectedHandIndex();
        if (selectedIndex < 0)
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

        if (!IsCardStatusReferenceValid(definition))
        {
            AppendCommandFeedback(normalizedCard, accepted: false, refusalReasonKey: "combat.feedback.refusal_reason.invalid_status_reference");
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

        if (!TryParseIntLabel(_difficultyValue, out var difficulty)
            || !TryParseIntLabel(_playerHpValue, out var playerHp)
            || !TryParseIntLabel(_drawPileValue, out var drawPile)
            || !TryParseIntLabel(_discardPileValue, out var discardPile))
        {
            AppendCommandFeedback(normalizedCard, accepted: false, refusalReasonKey: "combat.invalid_action");
            return false;
        }

        var pipelineInput = BuildPlayCardPipelineInput(definition, energy);
        var pipelineResult = _combatService.PlayCard(pipelineInput);
        _lastPlayCardExecutionFingerprint = pipelineResult.ExecutionFingerprint;
        _lastPlayCardOrderingKey = pipelineResult.OrderingKey;
        _lastPlayCardOverplayTax = pipelineResult.OverplayTax;
        _lastPlayCardPipelineSuccess = pipelineResult.Success;
        _lastPlayCardExecutedSteps.Clear();
        foreach (var step in pipelineResult.ExecutedSteps)
        {
            _lastPlayCardExecutedSteps.Add(step.ToString());
        }
        if (!pipelineResult.Success)
        {
            AppendCommandFeedback(normalizedCard, accepted: false, refusalReasonKey: "combat.feedback.refusal_reason.insufficient_energy");
            return false;
        }

        var resolved = _combatService.ResolveCardRuntime(
            new CardResolutionInput(
                Target: definition.Target,
                TargetEnemyId: targetEnemyId,
                AliveEnemyCount: GetAliveEnemyIds().Count,
                ResolvedDamageFromPipeline: pipelineResult.StateAfter.FinalDamage,
                Block: definition.Block,
                StatusId: definition.StatusId,
                StatusStacks: definition.StatusStacks,
                Exhaust: definition.Exhaust));
        ResolvePowerRelicRuntimeForCardPlay();
        var result = ResolveCardEffect(definition, targetEnemyId, resolved);
        PublishPresentationCue("card_play_motion");
        PublishSfxHook("card_play");
        if (result.Damage > 0)
        {
            PublishPresentationCue("damage_number");
            PublishPresentationCue("hit_feedback");
            PublishSfxHook("hit");
        }
        if (result.Block > 0)
        {
            PublishPresentationCue("block_gain_number");
            PublishSfxHook("block");
        }
        handCards.RemoveAt(selectedIndex);
        var remainingEnergy = pipelineResult.StateAfter.Energy;
        _cardsPlayedThisTurn = pipelineResult.StateAfter.CardsPlayedThisTurn;
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
        ClearDragState(resetHint: false);
        UpdateActionHintForCurrentInteraction();
        AppendCommandFeedback(normalizedCard, accepted: true, detail: BuildAcceptedCardDetail(result, remainingEnergy, definition.Cost));
        TryAutoCompleteVictoryRoute();
        return true;
    }

    private void ResolvePowerRelicRuntimeForCardPlay()
    {
        var triggerKeys = new List<CombatTriggerOrderKey>();
        foreach (var payload in _relicTriggerById.Values)
        {
            if (!string.IsNullOrWhiteSpace(payload.SourceId))
            {
                triggerKeys.Add(new CombatTriggerOrderKey(payload.SourceId, payload.Priority, payload.RegistrationOrder));
            }
        }

        foreach (var payload in _powerTriggerById.Values)
        {
            if (!string.IsNullOrWhiteSpace(payload.SourceId))
            {
                triggerKeys.Add(new CombatTriggerOrderKey(payload.SourceId, payload.Priority, payload.RegistrationOrder));
            }
        }

        foreach (var payload in _potionTriggerById.Values)
        {
            if (!string.IsNullOrWhiteSpace(payload.SourceId))
            {
                triggerKeys.Add(new CombatTriggerOrderKey(payload.SourceId, payload.Priority, payload.RegistrationOrder));
            }
        }

        _lastPowerRelicTriggerOrder.Clear();
        if (triggerKeys.Count <= 0)
        {
            return;
        }

        var ordered = PlayCardResolutionPipeline.ResolveTriggerOrder(triggerKeys);
        foreach (var sourceId in ordered)
        {
            _lastPowerRelicTriggerOrder.Add(sourceId);

            var outcome = ResolveOutcomeMessageForSource(sourceId);
            if (!string.IsNullOrWhiteSpace(outcome))
            {
                PublishPowerRelicOutcomeMessage($"{sourceId}: {outcome}");
                if (sourceId.StartsWith("Potion.", StringComparison.Ordinal))
                {
                    _potionRuntimeClosureExecutedForTest = true;
                }
            }
        }
    }

    private static string FindParticipantSurfaceText(ItemList list, string participantId)
    {
        for (var index = 0; index < list.ItemCount; index++)
        {
            var text = list.GetItemText(index);
            if (string.IsNullOrWhiteSpace(text))
            {
                continue;
            }

            if (text.StartsWith($"{participantId}: ", StringComparison.Ordinal))
            {
                return text;
            }
        }

        return string.Empty;
    }

    private string ResolveOutcomeMessageForSource(string sourceId)
    {
        if (string.IsNullOrWhiteSpace(sourceId))
        {
            return string.Empty;
        }

        if (sourceId.StartsWith("Power.", StringComparison.Ordinal))
        {
            var id = sourceId["Power.".Length..];
            if (_powerOutcomeById.TryGetValue(id, out var powerOutcome))
            {
                return powerOutcome;
            }
        }

        if (sourceId.StartsWith("Relic.", StringComparison.Ordinal))
        {
            var id = sourceId["Relic.".Length..];
            if (_relicOutcomeById.TryGetValue(id, out var relicOutcome))
            {
                return relicOutcome;
            }
        }

        if (sourceId.StartsWith("Potion.", StringComparison.Ordinal))
        {
            var id = sourceId["Potion.".Length..];
            if (_potionOutcomeById.TryGetValue(id, out var potionOutcome))
            {
                return potionOutcome;
            }
        }

        return string.Empty;
    }

    private bool TryInspectParticipant(string targetId)
    {
        if (string.IsNullOrWhiteSpace(targetId))
        {
            return false;
        }

        var normalized = targetId.Trim();
        if (_powerInspectById.TryGetValue(normalized, out var powerInspect))
        {
            PublishPowerRelicOutcomeMessage(powerInspect);
            return true;
        }

        if (_relicInspectById.TryGetValue(normalized, out var relicInspect))
        {
            PublishPowerRelicOutcomeMessage(relicInspect);
            return true;
        }

        if (_potionInspectById.TryGetValue(normalized, out var potionInspect))
        {
            PublishPowerRelicOutcomeMessage(potionInspect);
            return true;
        }

        return false;
    }

    private static string ExtractParticipantIdFromSurfaceText(string surfaceText)
    {
        if (string.IsNullOrWhiteSpace(surfaceText))
        {
            return string.Empty;
        }

        var separator = surfaceText.IndexOf(": ", StringComparison.Ordinal);
        return separator > 0 ? surfaceText[..separator].Trim() : string.Empty;
    }

    public int GetCoreStateMutationCountForTest()
    {
        return _coreStateMutationCount;
    }

    public int GetCardsPlayedThisTurnForTest()
    {
        return _cardsPlayedThisTurn;
    }

    public int GetHpChangedEmissionCountForTest()
    {
        return _hpChangedEmissionCount;
    }

    public int GetDefeatEligibleTransitionCountForTest()
    {
        return _defeatEligibleTransitionCount;
    }

    public int GetDefeatResolveCountForTest()
    {
        return _defeatResolveCount;
    }

    public int GetUnifiedHpUpdateEntryCountForTest()
    {
        return _unifiedHpUpdateEntryCount;
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

    public void SetEnemyIntentDefinitionAutoLoadEnabledForTest(bool enabled)
    {
        _enemyIntentDefinitionAutoLoadEnabledForTest = enabled;
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

    public bool TryGenerateEnemyIntentPreviewFromAiDefinitionsContractJson(string definitionsJson)
    {
        if (string.IsNullOrWhiteSpace(definitionsJson))
        {
            AppendCommandFeedback("enemy_intent_preview", accepted: false, refusalReasonKey: "combat.invalid_action");
            return false;
        }

        EnemyIntentFromAiContractPayload? payload;
        try
        {
            payload = JsonSerializer.Deserialize<EnemyIntentFromAiContractPayload>(definitionsJson, SnapshotJsonOptions);
        }
        catch (JsonException)
        {
            AppendCommandFeedback("enemy_intent_preview", accepted: false, refusalReasonKey: "combat.invalid_action");
            return false;
        }

        if (payload is null)
        {
            AppendCommandFeedback("enemy_intent_preview", accepted: false, refusalReasonKey: "combat.invalid_action");
            return false;
        }

        if (!TryGenerateEnemyIntentPreviewFromAiPayload(payload))
        {
            AppendCommandFeedback("enemy_intent_preview", accepted: false, refusalReasonKey: "combat.invalid_action");
            return false;
        }

        return true;
    }

    public bool TryGenerateEnemyIntentPreviewFromAiDefinitionsContractJsonForTest(string definitionsJson)
    {
        return TryGenerateEnemyIntentPreviewFromAiDefinitionsContractJson(definitionsJson);
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

    public int GetCombatRngStreamPositionForTest()
    {
        return _enemyIntentSelectionRngCursor;
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
        _unifiedHpUpdateEntryCount += 1;
        var previousPlayerHp = TryParseIntLabel(_playerHpValue, out var parsedPreviousPlayerHp) ? parsedPreviousPlayerHp : snapshot.PlayerHp;

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
        TryResolveDefeatOnHpTransition(previousPlayerHp, snapshot.PlayerHp, "Player HP reached zero.");
    }

    private bool ResolveEndTurn()
    {
        var handCards = new List<string>();
        for (var index = 0; index < _handCards.ItemCount; index++)
        {
            handCards.Add(_handCards.GetItemText(index));
        }

        if (!TryParseIntLabel(_difficultyValue, out var difficulty)
            || !TryParseIntLabel(_playerHpValue, out var playerHp)
            || !TryParseIntLabel(_drawPileValue, out var drawPile)
            || !TryParseIntLabel(_discardPileValue, out var discardPile))
        {
            AppendCommandFeedback("end_turn", accepted: false, refusalReasonKey: "combat.invalid_action");
            return false;
        }

        var intentDamage = TryResolveIncomingEnemyDamageFromIntent();
        var incomingDamage = _combatService.ResolveEndTurnIncomingDamage(
            new EndTurnEnemyIntentInput(
                IntentDamage: intentDamage,
                FallbackDamage: _combatService.CalculateDamage(
                    new Game.Core.Domain.ValueObjects.Damage(6, Game.Core.Domain.ValueObjects.DamageType.Physical, false))));
        var nextHandCards = new List<string> { "Strike", "Defend", "Strike" };
        var progression = _combatService.ResolveEndTurnProgression(
            new EndTurnProgressionInput(
                Difficulty: difficulty,
                PlayerHp: playerHp,
                PlayerBlock: _playerBlock,
                DrawPileCount: drawPile,
                DiscardPileCount: discardPile,
                HandCount: handCards.Count,
                IncomingEnemyDamage: incomingDamage,
                NextHandCards: nextHandCards));

        _playerBlock = progression.NextPlayerBlock;
        _cardsPlayedThisTurn = 0;
        _turnIndex += 1;
        var statusTransitionDetail = ResolveEndTurnStatusTransitions();
        ApplyCoreSnapshot(new CombatHudSnapshot(
            progression.NextHandCards,
            progression.NextEnergy,
            progression.NextDrawPileCount,
            progression.NextDiscardPileCount,
            difficulty,
            progression.NextPlayerHp,
            "PlayerTurn"));
        ApplyDefaultM1EnemyIntentIfEmpty();
        PublishPresentationCue("enemy_action_feedback");
        PublishSfxHook("enemy_action");
        var detailParts = new List<string> { $"Enemy dealt {progression.DamageTaken} damage. Turn {_turnIndex} started." };
        if (!string.IsNullOrWhiteSpace(statusTransitionDetail))
        {
            detailParts.Add(statusTransitionDetail);
        }

        AppendCommandFeedback("end_turn", accepted: true, detail: string.Join(" ", detailParts));
        return true;
    }

    private int TryResolveIncomingEnemyDamageFromIntent()
    {
        if (string.IsNullOrWhiteSpace(_selectedEnemyTargetId)
            || !_enemyIntentByEnemy.TryGetValue(_selectedEnemyTargetId, out var intentState))
        {
            return 0;
        }

        var description = intentState.Description ?? string.Empty;
        var digits = new List<char>();
        foreach (var ch in description)
        {
            if (char.IsDigit(ch))
            {
                digits.Add(ch);
                continue;
            }

            if (digits.Count > 0)
            {
                break;
            }
        }

        if (digits.Count <= 0)
        {
            return 0;
        }

        return int.TryParse(new string(digits.ToArray()), NumberStyles.Integer, CultureInfo.InvariantCulture, out var value)
            ? Math.Max(0, value)
            : 0;
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
        if (!accepted)
        {
            PublishSfxHook("invalid_action");
        }
    }

    private void PublishPresentationCue(string cue)
    {
        if (string.IsNullOrWhiteSpace(cue))
        {
            return;
        }
        var normalized = cue.Trim();
        _presentationCueHistory.Add(normalized);
        if (_reducedMotionForTest)
        {
            _presentationCueHistory.Add($"reduced_motion:{normalized}");
        }
    }

    private void PublishSfxHook(string hook)
    {
        if (string.IsNullOrWhiteSpace(hook))
        {
            return;
        }
        var normalized = hook.Trim();
        if (_simulateMissingSfxForTest)
        {
            _missingSfxNoopHistory.Add(normalized);
            return;
        }
        _sfxHookHistory.Add(normalized);
    }

    private CardEffectResult ResolveCardEffect(CardDefinitionRuntime definition, string targetEnemyId, CardResolutionResult runtimeResult)
    {
        var dealtDamage = 0;
        if (definition.Target.Equals("all_enemies", StringComparison.OrdinalIgnoreCase))
        {
            foreach (var enemyId in GetAliveEnemyIds())
            {
                dealtDamage += ApplyDamageToEnemy(enemyId, runtimeResult.PerTargetDamage);
            }
        }
        else if (runtimeResult.PerTargetDamage > 0 && definition.Target.Equals("enemy", StringComparison.OrdinalIgnoreCase))
        {
            dealtDamage += ApplyDamageToEnemy(targetEnemyId, runtimeResult.PerTargetDamage);
        }

        if (runtimeResult.BlockGain > 0)
        {
            _playerBlock += runtimeResult.BlockGain;
        }

        if (definition.StatusStacks > 0 && !string.IsNullOrWhiteSpace(definition.StatusId))
        {
            if (definition.Target.Equals("self", StringComparison.OrdinalIgnoreCase))
            {
                ApplyStatusToPlayer(definition.StatusId, definition.StatusStacks);
            }
            else if (definition.Target.Equals("all_enemies", StringComparison.OrdinalIgnoreCase))
            {
                foreach (var enemyId in GetAliveEnemyIds())
                {
                    ApplyStatusToEnemy(enemyId, definition.StatusId, definition.StatusStacks);
                }
            }
            else
            {
                var resolvedEnemyId = string.IsNullOrWhiteSpace(targetEnemyId) ? DefaultEnemyId : targetEnemyId.Trim();
                ApplyStatusToEnemy(resolvedEnemyId, definition.StatusId, definition.StatusStacks);
            }
        }

        return new CardEffectResult(
            Damage: dealtDamage > 0 ? dealtDamage : runtimeResult.TotalDamage,
            Block: runtimeResult.BlockGain,
            StatusDetail: runtimeResult.StatusDetail,
            MovedToExhaust: runtimeResult.MoveToExhaust);
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

    private PlayCardPipelineInput BuildPlayCardPipelineInput(CardDefinitionRuntime definition, int currentEnergy)
    {
        var baseDamage = Math.Max(0, definition.Damage);
        var triggerN = 3;
        var taxPerCard = 2;
        return new PlayCardPipelineInput(
            DifficultyId: TryParseIntLabel(_difficultyValue, out var difficulty) ? difficulty : 1,
            CardsPlayedThisTurn: Math.Max(0, _cardsPlayedThisTurn),
            OverplayTriggerN: triggerN,
            OverplayTaxPerCard: taxPerCard,
            BaseCardCost: Math.Max(0, definition.Cost),
            EnergyBefore: Math.Max(0, currentEnergy),
            BaseDamage: baseDamage,
            Strength: 0,
            WeakMultiplier: 1.0,
            VulnerableMultiplier: 1.0,
            IsFixedDamage: false,
            CombatantId: "player",
            StableId: $"turn-{_turnIndex}");
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
        var explicitStatusId = string.Empty;
        var explicitStatusStacks = 0;
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

            if (effectNode.TryGetProperty("status_id", out var effectStatusIdNode) && effectStatusIdNode.ValueKind == JsonValueKind.String)
            {
                explicitStatusId = effectStatusIdNode.GetString()?.Trim() ?? string.Empty;
            }

            if (effectNode.TryGetProperty("status_stacks", out var effectStatusStacksNode) && effectStatusStacksNode.ValueKind == JsonValueKind.Number)
            {
                explicitStatusStacks = Math.Max(0, effectStatusStacksNode.GetInt32());
            }
        }

        if (cardNode.TryGetProperty("status_id", out var cardStatusIdNode) && cardStatusIdNode.ValueKind == JsonValueKind.String)
        {
            explicitStatusId = cardStatusIdNode.GetString()?.Trim() ?? explicitStatusId;
        }

        if (cardNode.TryGetProperty("status_stacks", out var cardStatusStacksNode) && cardStatusStacksNode.ValueKind == JsonValueKind.Number)
        {
            explicitStatusStacks = Math.Max(0, cardStatusStacksNode.GetInt32());
        }

        var statusId = rage > 0 ? "status.rage" : string.Empty;
        var statusStacks = rage;
        if (!string.IsNullOrWhiteSpace(explicitStatusId))
        {
            statusId = explicitStatusId;
            statusStacks = explicitStatusStacks;
        }

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

        definition = new CardDefinitionRuntime(id, target, type, nameKey, descriptionKey, cost, damage, block, statusId, statusStacks, exhaust);
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

    private string ResolveEndTurnStatusTransitions()
    {
        var details = new List<string>();
        var aliveEnemies = GetAliveEnemyIds();
        foreach (var enemyId in aliveEnemies)
        {
            if (!_enemyStatusStacksByEnemy.TryGetValue(enemyId, out var statusMap))
            {
                continue;
            }

            if (statusMap.Count <= 0)
            {
                continue;
            }

            var keys = new List<string>(statusMap.Keys);
            foreach (var statusId in keys)
            {
                if (ShouldDecayStatusAtEndTurn(statusId))
                {
                    if (!statusMap.TryGetValue(statusId, out var currentStacks))
                    {
                        continue;
                    }

                    var nextStacks = Math.Max(0, currentStacks - 1);
                    if (nextStacks <= 0)
                    {
                        statusMap.Remove(statusId);
                        details.Add($"expired {statusId} on {enemyId}");
                    }
                    else
                    {
                        statusMap[statusId] = nextStacks;
                        details.Add($"decayed {statusId} to {nextStacks} on {enemyId}");
                    }
                }
            }

            if (statusMap.Count <= 0)
            {
                _enemyStatusStacksByEnemy.Remove(enemyId);
                if (_enemyCombatById.TryGetValue(enemyId, out var emptyState))
                {
                    _enemyCombatById[enemyId] = emptyState with { Status = ResolveUiText("combat.enemy.status.none") };
                }
            }
            else if (_enemyCombatById.TryGetValue(enemyId, out var state))
            {
                _enemyCombatById[enemyId] = state with { Status = BuildStatusSummary(statusMap) };
            }
        }

        var playerStatusIds = new List<string>(_playerStatusStacks.Keys);
        foreach (var statusId in playerStatusIds)
        {
            if (!ShouldDecayStatusAtEndTurn(statusId))
            {
                continue;
            }

            if (!_playerStatusStacks.TryGetValue(statusId, out var currentStacks))
            {
                continue;
            }

            var nextStacks = Math.Max(0, currentStacks - 1);
            if (nextStacks <= 0)
            {
                _playerStatusStacks.Remove(statusId);
                details.Add($"expired {statusId} on self");
            }
            else
            {
                _playerStatusStacks[statusId] = nextStacks;
                details.Add($"decayed {statusId} to {nextStacks} on self");
            }
        }

        RefreshPrimaryEnemyPanel();
        return string.Join("; ", details);
    }

    private static bool ShouldDecayStatusAtEndTurn(string statusId)
    {
        if (string.IsNullOrWhiteSpace(statusId))
        {
            return false;
        }

        return statusId.StartsWith("status.temp_", StringComparison.OrdinalIgnoreCase)
               || string.Equals(statusId, "status.weak", StringComparison.OrdinalIgnoreCase)
               || string.Equals(statusId, "status.vulnerable", StringComparison.OrdinalIgnoreCase);
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
        UpdateActionHintForCurrentInteraction();
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
        UpdateActionHintForCurrentInteraction();
    }

    private void RefreshPrimaryEnemyPanel()
    {
        var aliveEnemies = GetAliveEnemyIds();
        if (aliveEnemies.Count <= 0)
        {
            _enemyPortrait.Texture = EnsureEnemyPortraitFallbackTexture();
            _lastResolvedEnemyPortraitPath = "fallback:empty";
            _enemyPortraitFrame.SelfModulate = Colors.White;
            _enemyTargetHighlight.Visible = false;
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

        _enemyPortrait.Texture = ResolveEnemyPortraitTexture(preferredId);
        _enemyNameValue.Text = preferredState.Name;
        _enemyHpValue.Text = $"{preferredState.CurrentHp}/{preferredState.MaxHp}";
        _enemyBlockValue.Text = preferredState.Block.ToString(CultureInfo.InvariantCulture);
        _enemyStatusValue.Text = preferredState.Status;
        RefreshEnemyTargetHighlight(preferredId);
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

    private void TryResolveDefeatOnHpTransition(int previousPlayerHp, int currentPlayerHp, string reason)
    {
        if (previousPlayerHp != currentPlayerHp)
        {
            _hpChangedEmissionCount += 1;
        }

        var transitionedToDefeat = previousPlayerHp > 0 && currentPlayerHp <= 0;
        if (transitionedToDefeat)
        {
            _defeatEligibleTransitionCount += 1;
        }

        if (transitionedToDefeat && !_defeatResolvedForCurrentHpDrop)
        {
            _defeatResolvedForCurrentHpDrop = true;
            _defeatResolveCount += 1;
            TryAutoCompleteDefeatRoute(reason);
            return;
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
                "combat.feedback.refusal_reason.invalid_status_reference" => "invalid status reference",
                "combat.invalid_action" => "invalid action",
                _ => "invalid action",
            };
        }

        return mapped.Trim();
    }

    private static bool IsCardStatusReferenceValid(CardDefinitionRuntime definition)
    {
        if (definition.StatusStacks <= 0)
        {
            return true;
        }

        if (string.IsNullOrWhiteSpace(definition.StatusId))
        {
            return false;
        }

        var statusId = definition.StatusId.Trim();
        return AllowedStatusIds.Contains(statusId);
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
            "combat.action.hint.drag_active" => isZh ? "拖拽手牌到敌人身上以打出。" : "Drag a card onto an enemy target.",
            "combat.action.hint.drag_release" => isZh ? "松开以打出这张牌。" : "Release to play this card.",
            "combat.action.hint.drag_invalid_target" => isZh ? "无效目标，请拖到可攻击的敌人身上。" : "Invalid target. Drag onto a living enemy.",
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

        var generated = TryGenerateEnemyIntentPreviewFromDataDefinitions();
        if (!generated)
        {
            _enemyIntentByEnemy.Clear();
            RefreshEnemyIntentRows();
        }
    }

    private bool TryGenerateEnemyIntentPreviewFromDataDefinitions()
    {
        if (!_enemyIntentDefinitionAutoLoadEnabledForTest)
        {
            return false;
        }

        foreach (var path in EnemyIntentDefinitionCandidatePaths)
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

            EnemyIntentFromAiContractPayload? payload;
            try
            {
                payload = JsonSerializer.Deserialize<EnemyIntentFromAiContractPayload>(file.GetAsText(), SnapshotJsonOptions);
            }
            catch (JsonException)
            {
                continue;
            }

            if (payload is null)
            {
                continue;
            }

            if (TryGenerateEnemyIntentPreviewFromAiPayload(payload))
            {
                return true;
            }
        }

        return false;
    }

    private bool TryGenerateEnemyIntentPreviewFromAiPayload(EnemyIntentFromAiContractPayload payload)
    {
        if (payload.Enemies is null || payload.Enemies.Count <= 0)
        {
            return false;
        }

        var combatState = string.IsNullOrWhiteSpace(payload.CombatState) ? "Opening" : payload.CombatState.Trim();
        var rngStreamBase = payload.RngStream ?? new List<int>();
        var selector = new EnemyIntentSelectionService();
        var previews = new List<EnemyIntentPreviewItemPayload>();

        foreach (var enemy in payload.Enemies)
        {
            if (string.IsNullOrWhiteSpace(enemy.EnemyId) || enemy.Intents is null || enemy.Intents.Count <= 0)
            {
                return false;
            }

            var intentById = new Dictionary<string, EnemyIntentFromAiBehaviorPayload>(StringComparer.Ordinal);
            var candidateIds = new List<string>();
            foreach (var intent in enemy.Intents)
            {
                if (string.IsNullOrWhiteSpace(intent.IntentId))
                {
                    continue;
                }

                var key = intent.IntentId.Trim();
                if (!intentById.ContainsKey(key))
                {
                    intentById[key] = intent;
                    candidateIds.Add(key);
                }
            }

            if (candidateIds.Count <= 0)
            {
                return false;
            }

            var pools = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
            {
                [combatState] = candidateIds,
            };
            var effectiveRngStream = new List<int>(rngStreamBase)
            {
                _enemyIntentSelectionRngCursor,
            };
            var selectedIntentId = selector.SelectIntent(enemy.EnemyId, combatState, pools, effectiveRngStream);
            if (!intentById.TryGetValue(selectedIntentId, out var selectedIntent))
            {
                return false;
            }

            previews.Add(new EnemyIntentPreviewItemPayload(
                enemy.EnemyId,
                selectedIntent.IconId ?? string.Empty,
                selectedIntent.TextKey ?? string.Empty));
        }

        if (previews.Count <= 0)
        {
            return false;
        }

        _enemyIntentSelectionRngCursor += 1;
        ApplyEnemyIntentPreview(previews);
        return true;
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
                CancelCardDrag();
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

    private static string ResolveCardTypeBadgeText(CardDefinitionRuntime definition)
    {
        if (string.IsNullOrWhiteSpace(definition.Type))
        {
            return string.Empty;
        }

        return definition.Type.Trim().ToUpperInvariant();
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
        UpdateActionHintForCurrentInteraction();
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (@event is InputEventMouseMotion motion && _isCardDragActive)
        {
            UpdateDragGhostPosition(motion.Position);
            var hoveredEnemy = ResolveEnemyTargetIdAtPosition(motion.Position);
            if (!string.Equals(hoveredEnemy, _draggedTargetEnemyId, StringComparison.Ordinal))
            {
                HoverEnemyTarget(hoveredEnemy);
            }
        }
    }

    public override void _Input(InputEvent @event)
    {
        _ = @event;
    }

    public override void _Process(double delta)
    {
        ProcessRuntimePointerState();

        if (_isCardDragActive)
        {
            UpdateDragGhostPosition(ResolveRuntimePointerPosition());
        }

        RefreshRuntimeDebugPanel();

        if (!_enemyTargetHighlight.Visible)
        {
            _targetHighlightPulsePhase = 0.0f;
            _enemyTargetHighlight.Modulate = Colors.White;
            return;
        }

        _targetHighlightPulsePhase += (float)delta * 5.0f;
        var pulse = 0.78f + (MathF.Sin(_targetHighlightPulsePhase) * 0.12f + 0.12f);
        _enemyTargetHighlight.Modulate = new Color(1.0f, 1.0f, 1.0f, pulse);
    }

    private void OnHandCardClicked(long index, Vector2 _atPosition, long mouseButtonIndex)
    {
        if (mouseButtonIndex != (long)MouseButton.Left)
        {
            return;
        }

        if (_isCardDragActive)
        {
            return;
        }

        CancelCardDrag();
        _handCards.DeselectAll();
        if (index >= 0 && index < _handCards.ItemCount)
        {
            _handCards.Select((int)index);
            UpdateActionHintForCurrentInteraction();
        }
    }

    private void OnHandCardsGuiInput(InputEvent @event)
    {
        _ = @event;
    }

    private bool BeginCardDrag(int handIndex)
    {
        if (handIndex < 0 || handIndex >= _handCards.ItemCount)
        {
            return false;
        }

        _handCards.DeselectAll();
        _handCards.Select(handIndex);
        _isCardDragActive = true;
        _draggedHandIndex = handIndex;
        _draggedTargetEnemyId = string.Empty;
        _selectedEnemyTargetId = string.Empty;
        _hasPendingInvalidTargetSelection = false;
        RefreshDragGhost(handIndex);
        _dragCardGhost.Visible = true;
        ApplyHoverPreviewForTest($"drag:{handIndex}");
        UpdateActionHintForCurrentInteraction();
        return true;
    }

    private void HoverEnemyTarget(string enemyId)
    {
        if (!_isCardDragActive)
        {
            return;
        }

        _draggedTargetEnemyId = string.IsNullOrWhiteSpace(enemyId) ? string.Empty : enemyId.Trim();
        ApplyTargetInspectionForTest(_draggedTargetEnemyId);
        if (!string.IsNullOrWhiteSpace(_draggedTargetEnemyId))
        {
            ApplyHoverPreviewForTest($"drag:{_draggedHandIndex}:{_draggedTargetEnemyId}");
        }
        UpdateActionHintForCurrentInteraction();
    }

    private bool ReleaseDraggedCard()
    {
        if (!_isCardDragActive || _draggedHandIndex < 0 || _draggedHandIndex >= _handCards.ItemCount)
        {
            return false;
        }

        if (!string.IsNullOrWhiteSpace(_draggedTargetEnemyId))
        {
            _ = TrySelectEnemyTarget(_draggedTargetEnemyId);
        }

        if (ResolveSelectedHandIndex() != _draggedHandIndex)
        {
            _handCards.DeselectAll();
            _handCards.Select(_draggedHandIndex);
        }

        var accepted = RequestPlaySelectedCard();
        if (accepted)
        {
            _selectedEnemyTargetId = string.Empty;
            ClearDragState(resetHint: false);
            UpdateActionHintForCurrentInteraction();
            return true;
        }

        if (!string.IsNullOrWhiteSpace(_draggedTargetEnemyId) && _hasPendingInvalidTargetSelection)
        {
            var cardName = _draggedHandIndex >= 0 && _draggedHandIndex < _handCards.ItemCount
                ? _handCards.GetItemText(_draggedHandIndex)
                : "play_card";
            AppendCommandFeedback(cardName, accepted: false, refusalReasonKey: "combat.feedback.refusal_reason.invalid_target");
        }

        UpdateActionHintForCurrentInteraction();
        return false;
    }

    private void CancelCardDrag()
    {
        if (!_isCardDragActive)
        {
            return;
        }

        ClearDragState(resetHint: true);
    }

    private void ClearDragState(bool resetHint)
    {
        _isCardDragActive = false;
        _draggedHandIndex = -1;
        _draggedTargetEnemyId = string.Empty;
        _hasPendingInvalidTargetSelection = false;
        _dragCardGhost.Visible = false;
        _dragCardGhostTitle.Text = string.Empty;
        _dragCardGhostCost.Text = string.Empty;
        _dragCardGhostType.Text = string.Empty;
        _dragCardGhostSummary.Text = string.Empty;
        CloseHoverPreviewForTest();
        HideTargetInspectionForTest();
        if (resetHint)
        {
            UpdateActionHintForCurrentInteraction();
        }
    }

    private int ResolveSelectedHandIndex()
    {
        if (_isCardDragActive && _draggedHandIndex >= 0 && _draggedHandIndex < _handCards.ItemCount)
        {
            return _draggedHandIndex;
        }

        var selectedItems = _handCards.GetSelectedItems();
        if (selectedItems.Length <= 0)
        {
            return -1;
        }

        var selectedIndex = selectedItems[0];
        return selectedIndex >= 0 && selectedIndex < _handCards.ItemCount ? selectedIndex : -1;
    }

    private void ProcessRuntimePointerState()
    {
        var pointerPosition = ResolveRuntimePointerPosition();
        var isLeftPressed = ResolveRuntimeLeftPressed();

        if (isLeftPressed && !_wasLeftMousePressed)
        {
            var handIndex = ResolveHandIndexAtPosition(pointerPosition);
            if (handIndex >= 0)
            {
                BeginCardDrag(handIndex);
            }
        }

        if (_isCardDragActive)
        {
            UpdateDragGhostPosition(pointerPosition);
            var hoveredEnemy = ResolveEnemyTargetIdAtPosition(pointerPosition);
            if (!string.Equals(hoveredEnemy, _draggedTargetEnemyId, StringComparison.Ordinal))
            {
                HoverEnemyTarget(hoveredEnemy);
            }
        }

        if (!isLeftPressed && _wasLeftMousePressed && _isCardDragActive)
        {
            var hoveredEnemy = ResolveEnemyTargetIdAtPosition(pointerPosition);
            if (!string.IsNullOrWhiteSpace(hoveredEnemy))
            {
                HoverEnemyTarget(hoveredEnemy);
                _ = ReleaseDraggedCard();
            }
            else
            {
                CancelCardDrag();
            }
        }

        _wasLeftMousePressed = isLeftPressed;
    }

    private Vector2 ResolveRuntimePointerPosition()
    {
        return _runtimePointerStateOverrideEnabled ? _runtimePointerPositionOverride : GetGlobalMousePosition();
    }

    private bool ResolveRuntimeLeftPressed()
    {
        return _runtimePointerStateOverrideEnabled
            ? _runtimePointerPressedOverride
            : Input.IsMouseButtonPressed(MouseButton.Left);
    }

    private void UpdateActionHintForCurrentInteraction()
    {
        if (_isCardDragActive)
        {
            if (!string.IsNullOrWhiteSpace(_draggedTargetEnemyId)
                && _enemyCombatById.TryGetValue(_draggedTargetEnemyId, out var hoveredState)
                && hoveredState.CurrentHp > 0)
            {
                _actionHintLabel.Text = ResolveUiText("combat.action.hint.drag_release");
                return;
            }

            if (!string.IsNullOrWhiteSpace(_draggedTargetEnemyId))
            {
                _actionHintLabel.Text = ResolveUiText("combat.action.hint.drag_invalid_target");
                return;
            }

            _actionHintLabel.Text = ResolveUiText("combat.action.hint.drag_active");
            return;
        }

        _actionHintLabel.Text = ResolveUiText("combat.action.hint");
    }

    private void RefreshEnemyTargetHighlight(string preferredId)
    {
        if (_isCardDragActive
            && !string.IsNullOrWhiteSpace(_draggedTargetEnemyId)
            && _enemyCombatById.TryGetValue(_draggedTargetEnemyId, out var hoveredState)
            && hoveredState.CurrentHp > 0)
        {
            _enemyPortraitFrame.SelfModulate = new Color(1.0f, 0.9f, 0.55f, 1.0f);
            _enemyTargetHighlight.Visible = true;
            return;
        }

        _enemyPortraitFrame.SelfModulate = Colors.White;
        _enemyTargetHighlight.Visible = false;
    }

    private void RefreshDragGhost(int handIndex)
    {
        if (handIndex < 0 || handIndex >= _handCards.ItemCount)
        {
            _dragCardGhostTitle.Text = string.Empty;
            _dragCardGhostCost.Text = string.Empty;
            _dragCardGhostType.Text = string.Empty;
            _dragCardGhostSummary.Text = string.Empty;
            return;
        }

        var cardName = _handCards.GetItemText(handIndex);
        if (TryResolveCardDefinition(cardName, out var definition))
        {
            _dragCardGhostTitle.Text = ResolveCardDisplayName(definition);
            _dragCardGhostCost.Text = definition.Cost.ToString(CultureInfo.InvariantCulture);
            _dragCardGhostType.Text = ResolveCardTypeBadgeText(definition);
            _dragCardGhostSummary.Text = ResolveCardEffectSummary(definition);
            return;
        }

        _dragCardGhostTitle.Text = cardName;
        _dragCardGhostCost.Text = string.Empty;
        _dragCardGhostType.Text = string.Empty;
        _dragCardGhostSummary.Text = string.Empty;
    }

    private void UpdateDragGhostPosition(Vector2 pointerPosition)
    {
        if (!_dragCardGhost.Visible)
        {
            return;
        }

        _dragCardGhost.Position = pointerPosition + new Vector2(18.0f, -24.0f);
    }

    private int ResolveHandIndexAtPosition(Vector2 position)
    {
        if (!_handCards.GetGlobalRect().HasPoint(position))
        {
            return -1;
        }

        var local = position - _handCards.GlobalPosition;
        return _handCards.GetItemAtPosition(local, true);
    }

    private string ResolveEnemyTargetIdAtPosition(Vector2 position)
    {
        foreach (var enemyId in GetAliveEnemyIds())
        {
            if (IsEnemyTargetHovered(enemyId, position))
            {
                return enemyId;
            }
        }

        return string.Empty;
    }

    private bool IsEnemyTargetHovered(string enemyId, Vector2 position)
    {
        if (string.IsNullOrWhiteSpace(enemyId))
        {
            return false;
        }

        if (_enemyIntentByEnemy.ContainsKey(enemyId))
        {
            foreach (var child in _enemyIntentList.GetChildren())
            {
                if (child is not Control row || !row.HasMeta("enemy_id"))
                {
                    continue;
                }

                var rowEnemyId = row.GetMeta("enemy_id").AsString();
                if (string.Equals(rowEnemyId, enemyId, StringComparison.Ordinal) && row.GetGlobalRect().HasPoint(position))
                {
                    return true;
                }
            }
        }

        if (string.Equals(_selectedEnemyTargetId, enemyId, StringComparison.Ordinal) || string.IsNullOrWhiteSpace(_selectedEnemyTargetId))
        {
            return _enemyStatusValue.GetParent<Control>().GetGlobalRect().HasPoint(position);
        }

        return false;
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

    private Texture2D ResolveEnemyPortraitTexture(string enemyId)
    {
        var portraitKey = string.IsNullOrWhiteSpace(enemyId) ? DefaultEnemyId : enemyId.Trim();
        foreach (var path in BuildEnemyPortraitTextureCandidates(portraitKey))
        {
            if (ResourceLoader.Exists(path) && ResourceLoader.Load(path) is Texture2D texture)
            {
                _lastResolvedEnemyPortraitPath = $"resource:{path}";
                return texture;
            }

            var rawTexture = TryLoadRawTexture(path);
            if (rawTexture is not null)
            {
                _lastResolvedEnemyPortraitPath = $"raw:{path}";
                return rawTexture;
            }
        }

        _lastResolvedEnemyPortraitPath = $"fallback:{portraitKey}";
        return EnsureEnemyPortraitFallbackTexture();
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

    private static Texture2D? TryLoadRawTexture(string resourcePath)
    {
        if (string.IsNullOrWhiteSpace(resourcePath) || !resourcePath.StartsWith("res://", StringComparison.Ordinal))
        {
            return null;
        }

        var absolutePath = ProjectSettings.GlobalizePath(resourcePath);
        if (!global::System.IO.File.Exists(absolutePath))
        {
            return null;
        }

        var image = new Image();
        var error = image.Load(absolutePath);
        if (error != Error.Ok)
        {
            return null;
        }

        return ImageTexture.CreateFromImage(image);
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

    private static IEnumerable<string> BuildEnemyPortraitTextureCandidates(string enemyId)
    {
        if (string.IsNullOrWhiteSpace(enemyId))
        {
            yield break;
        }

        if (string.Equals(enemyId, DefaultEnemyId, StringComparison.Ordinal))
        {
            yield return "res://Game.Godot/Assets/Textures/Combat/Enemies/enemy_fungal_knight_target.png";
        }
        yield return $"res://Game.Godot/Assets/Textures/Combat/Enemies/{enemyId}.png";
        yield return $"res://Game.Godot/Assets/Textures/Combat/Enemies/enemy_fungal_knight_target.png";
        yield return $"res://logs/aiart/t74-enemy-target-2026-05-13/processed/clean.png";
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

    private Texture2D EnsureEnemyPortraitFallbackTexture()
    {
        if (_enemyPortraitFallbackTexture is not null)
        {
            return _enemyPortraitFallbackTexture;
        }

        var image = Image.CreateEmpty(160, 160, false, Image.Format.Rgba8);
        image.Fill(new Color(0.24f, 0.28f, 0.22f, 1.0f));
        _enemyPortraitFallbackTexture = ImageTexture.CreateFromImage(image);
        return _enemyPortraitFallbackTexture;
    }

    private void RefreshRuntimeDebugPanel()
    {
        _debugScenePathLabel.Text = $"scene: {SceneFilePath}";
        var portraitState = _enemyPortrait.Texture is null ? "missing" : "ok";
        _debugPortraitStatusLabel.Text = $"portrait: {portraitState} | path: {_lastResolvedEnemyPortraitPath}";
        _debugDragStateLabel.Text = $"drag: active={_isCardDragActive} hand={_draggedHandIndex} target={_draggedTargetEnemyId}";
        var mouse = ResolveRuntimePointerPosition();
        var pointerSource = _runtimePointerStateOverrideEnabled ? "override" : "live";
        var hoveredHandIndex = ResolveHandIndexAtPosition(mouse);
        var hoveredEnemyId = ResolveEnemyTargetIdAtPosition(mouse);
        _debugMouseStateLabel.Text = $"mouse: {mouse.X:0.0}, {mouse.Y:0.0} left={ResolveRuntimeLeftPressed()} src={pointerSource} hand={hoveredHandIndex} enemy={hoveredEnemyId}";
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
        string? TurnState,
        List<ParticipantItemPayload>? Powers = null,
        List<ParticipantItemPayload>? Relics = null,
        List<ParticipantItemPayload>? Potions = null
    );

    private void PublishPowerRelicOutcomeMessage(string message)
    {
        if (string.IsNullOrWhiteSpace(message))
        {
            return;
        }

        _feedbackMessageLabel.Text = message;
        _feedbackHistoryList.AddItem(message);
        _lastPowerRelicOutcomeMessages.Add(message);
    }

    private sealed record ParticipantsContractPayload(
        List<ParticipantItemPayload>? Powers,
        List<ParticipantItemPayload>? Relics,
        List<ParticipantItemPayload>? Potions = null
    );

    private sealed record ParticipantItemPayload(
        string? Id,
        string? InspectText,
        int Priority = 10,
        int RegistrationOrder = 10,
        string? OutcomeMessage = null,
        bool VisibleOnSurface = true
    );

    private void ApplyPowerRelicParticipants(
        IReadOnlyList<ParticipantItemPayload>? powers,
        IReadOnlyList<ParticipantItemPayload>? relics,
        IReadOnlyList<ParticipantItemPayload>? potions)
    {
        _powerInspectById.Clear();
        _relicInspectById.Clear();
        _potionInspectById.Clear();
        _powerTriggerById.Clear();
        _relicTriggerById.Clear();
        _potionTriggerById.Clear();
        _powerOutcomeById.Clear();
        _relicOutcomeById.Clear();
        _potionOutcomeById.Clear();
        _potionVisibleOnSurfaceIds.Clear();
        _powerParticipantList.Clear();
        _relicParticipantList.Clear();
        _potionParticipantList.Clear();
        _potionRuntimeClosureExecutedForTest = false;

        if (powers is not null)
        {
            foreach (var power in powers)
            {
                var id = (power.Id ?? string.Empty).Trim();
                if (string.IsNullOrWhiteSpace(id))
                {
                    continue;
                }

                var inspectText = string.IsNullOrWhiteSpace(power.InspectText)
                    ? $"inspect {id}"
                    : power.InspectText.Trim();
                _powerInspectById[id] = inspectText;
                _powerTriggerById[id] = new TriggerOrderItemPayload(
                    SourceId: $"Power.{id}",
                    Priority: power.Priority,
                    RegistrationOrder: power.RegistrationOrder);
                _powerOutcomeById[id] = string.IsNullOrWhiteSpace(power.OutcomeMessage)
                    ? "triggered"
                    : power.OutcomeMessage.Trim();
                _powerParticipantList.AddItem($"{id}: {inspectText}");
            }
        }

        if (relics is not null)
        {
            foreach (var relic in relics)
            {
                var id = (relic.Id ?? string.Empty).Trim();
                if (string.IsNullOrWhiteSpace(id))
                {
                    continue;
                }

                var inspectText = string.IsNullOrWhiteSpace(relic.InspectText)
                    ? $"inspect {id}"
                    : relic.InspectText.Trim();
                _relicInspectById[id] = inspectText;
                _relicTriggerById[id] = new TriggerOrderItemPayload(
                    SourceId: $"Relic.{id}",
                    Priority: relic.Priority,
                    RegistrationOrder: relic.RegistrationOrder);
                _relicOutcomeById[id] = string.IsNullOrWhiteSpace(relic.OutcomeMessage)
                    ? "triggered"
                    : relic.OutcomeMessage.Trim();
                _relicParticipantList.AddItem($"{id}: {inspectText}");
            }
        }

        if (potions is not null)
        {
            foreach (var potion in potions)
            {
                var id = (potion.Id ?? string.Empty).Trim();
                if (string.IsNullOrWhiteSpace(id))
                {
                    continue;
                }

                var inspectText = string.IsNullOrWhiteSpace(potion.InspectText)
                    ? $"inspect {id}"
                    : potion.InspectText.Trim();
                _potionInspectById[id] = inspectText;
                _potionTriggerById[id] = new TriggerOrderItemPayload(
                    SourceId: $"Potion.{id}",
                    Priority: potion.Priority,
                    RegistrationOrder: potion.RegistrationOrder);
                _potionOutcomeById[id] = string.IsNullOrWhiteSpace(potion.OutcomeMessage)
                    ? "triggered"
                    : potion.OutcomeMessage.Trim();
                if (potion.VisibleOnSurface)
                {
                    _potionParticipantList.AddItem($"{id}: {inspectText}");
                    _potionVisibleOnSurfaceIds.Add(id);
                }
            }
        }

        _powerRelicPanel.Visible = _powerParticipantList.ItemCount > 0 || _relicParticipantList.ItemCount > 0 || _potionParticipantList.ItemCount > 0;
    }

    private sealed record TriggerOrderContractPayload(
        List<TriggerOrderItemPayload>? Triggers
    );

    private sealed record TriggerOrderItemPayload(
        string? SourceId,
        int Priority,
        int RegistrationOrder
    );

    private sealed record OutcomeContractPayload(
        List<OutcomeItemPayload>? Outcomes
    );

    private sealed record OutcomeItemPayload(
        string? SourceId,
        string? Message
    );

    private sealed record EnemyIntentContractPayload(
        List<EnemyIntentPreviewItemPayload>? EnemyIntents
    );

    private sealed record EnemyIntentFromAiContractPayload(
        string? CombatState,
        List<int>? RngStream,
        List<EnemyIntentFromAiEnemyPayload>? Enemies
    );

    private sealed record EnemyIntentFromAiEnemyPayload(
        string EnemyId,
        List<EnemyIntentFromAiBehaviorPayload>? Intents
    );

    private sealed record EnemyIntentFromAiBehaviorPayload(
        string IntentId,
        string IconId,
        string TextKey
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
