using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Reflection;
using Godot;
using Game.Core.Contracts.Config;
using Game.Core.Contracts.Combat;
using Game.Core.Contracts.Status;
using Game.Core.Services;

namespace Game.Godot.Scripts.UI;

public partial class CombatScene : Control
{
    private static readonly string[] LiveRelicDefinitionCandidatePaths =
    {
        "res://Game.Core/Data/m1-relic-definitions.json",
        "res://../Game.Core/Data/m1-relic-definitions.json",
    };

    private static IReadOnlyDictionary<string, RelicEffectDefinition>? _liveRelicCatalogCache;

    [Signal]
    public delegate void TurnActionRequestedEventHandler(string actionName);

    private ItemList _handCards = default!;
    private Label _difficultyValue = default!;
    private Label _playerHpValue = default!;
    private Label _energyValue = default!;
    private Label _drawPileValue = default!;
    private Label _discardPileValue = default!;
    private PanelContainer _drawPileBadge = default!;
    private PanelContainer _discardPileBadge = default!;
    private PanelContainer _exhaustPileBadge = default!;
    private Label _turnStateValue = default!;
    private Label _feedbackMessageLabel = default!;
    private ItemList _feedbackHistoryList = default!;
    private Label _enemyIntentTitleLabel = default!;
    private VBoxContainer _enemyIntentList = default!;
    private Label _enemyRosterTitleLabel = default!;
    private HBoxContainer _enemyRosterContainer = default!;
    private VBoxContainer _powerRelicPanel = default!;
    private Label _powerRelicTitleLabel = default!;
    private ItemList _powerParticipantList = default!;
    private ItemList _relicParticipantList = default!;
    private ItemList _potionParticipantList = default!;
    private HBoxContainer _cardButtonRow = default!;
    private Control _handFanLayer = default!;
    private Label _enemyStatusTitleLabel = default!;
    private HBoxContainer _enemyBattleStage = default!;
    private PanelContainer _playerBattleStagePanel = default!;
    private PanelContainer _playerTargetHighlight = default!;
    private TextureRect _playerPortrait = default!;
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
    private Label _debugCombatRuntimeLabel = default!;
    private Control _combatFxLayer = default!;
    private AudioStreamPlayer _combatSfxPlayer = default!;
    private PanelContainer _dragCardGhost = default!;
    private Control _dragCardGhostBody = default!;
    private TextureRect _dragCardGhostFace = default!;
    private Label _dragCardGhostTitle = default!;
    private Label _dragCardGhostCost = default!;
    private Label _dragCardGhostType = default!;
    private Label _dragCardGhostSummary = default!;
    private Line2D _dragArrow = default!;
    private Button _masterDeckButton = default!;
    private Button _mapButton = default!;
    private Control _pileViewerOverlay = default!;
    private Button _pileViewerBackButton = default!;
    private Label _pileViewerTitle = default!;
    private GridContainer _pileViewerGrid = default!;
    private Control _mapOverlay = default!;
    private Button _mapOverlayBackButton = default!;
    private Label _mapOverlayTitle = default!;
    private Control _mapOverlayContent = default!;
    private Control? _mapOverlayScene;
    private TextureRect _enemyPortraitInStatusPanel = default!;

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
    private readonly List<CombatFloatFxState> _activeCombatFloatFx = new();
    private readonly Dictionary<string, int> _hitFlashTokensByTarget = new(StringComparer.Ordinal);
    private readonly Dictionary<string, AudioStreamWav> _sfxToneCache = new(StringComparer.Ordinal);
    private string _lastHoverPreviewText = string.Empty;
    private bool _targetInspectionVisibleForTest;
    private bool _isCardDragActive;
    private int _draggedHandIndex = -1;
    private string _draggedTargetEnemyId = string.Empty;
    private bool _wasLeftMousePressed;
    private bool _runtimePointerStateOverrideEnabled;
    private Vector2 _runtimePointerPositionOverride = Vector2.Zero;
    private bool _runtimePointerPressedOverride;
    private bool _reducedMotionForTest;
    private bool _simulateMissingSfxForTest;
    private int _pendingDamageFloatValue;
    private string _pendingDamageTargetEnemyId = string.Empty;
    private int _pendingBlockFloatValue;
    private int _pendingEnemyActionDamage;
    private string _pendingHitTargetId = string.Empty;
    private string _lastResolvedSfxHook = string.Empty;
    private int _resolvedSfxPlaybackCount;
    private int _lastPlayCardOverplayTax;
    private bool _lastPlayCardPipelineSuccess;
    private const string DefaultEnemyId = "enemy_m1_slime";
    private const string DefaultEnemySupportId = "enemy_m1_slime_b";
    private readonly Dictionary<string, EnemyCombatState> _enemyCombatById = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Dictionary<string, int>> _enemyStatusStacksByEnemy = new(StringComparer.Ordinal);
    private readonly Dictionary<string, StatusInstance> _playerStatuses = new(StringComparer.Ordinal);
    private readonly Dictionary<string, CardDefinitionRuntime> _cardDefinitionsByLookup = new(StringComparer.Ordinal);
    private string _selectedEnemyTargetId = string.Empty;
    private bool _hasPendingInvalidTargetSelection;
    private readonly Dictionary<string, EnemyIntentState> _enemyIntentByEnemy = new(StringComparer.Ordinal);
    private bool _enemyIntentPreviewManuallyAppliedForTest;
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
    private readonly HashSet<string> _appliedCombatStartRelicIds = new(StringComparer.Ordinal);
    private bool _sceneLocalEffectStackUsedForTest;
    private static readonly Dictionary<string, Dictionary<string, string>> FeedbackTextMapsByLocale = new(StringComparer.OrdinalIgnoreCase);
    private bool _cardDefinitionAutoLoadEnabledForTest = true;
    private bool _enemyIntentDefinitionAutoLoadEnabledForTest = true;
    private bool _uiSignalsBound;
    private static readonly string[] CardDefinitionCandidatePaths =
    {
        "res://Game.Core/Data/m1-card-definitions.json",
        "res://../Game.Core/Data/m1-card-definitions.json",
    };
    private static readonly string[] StartingDeckCandidatePaths =
    {
        "res://Game.Core/Data/m1-warrior-starting-deck.json",
        "res://../Game.Core/Data/m1-warrior-starting-deck.json",
    };
    private static readonly string[] EnemyIntentDefinitionCandidatePaths =
    {
        "res://Game.Core/Data/m1-enemy-intent-definitions.json",
        "res://../Game.Core/Data/m1-enemy-intent-definitions.json",
    };
    private static readonly string[] ActConfigCandidatePaths =
    {
        "res://Game.Core/Data/act1-config.json",
        "res://../Game.Core/Data/act1-config.json",
    };
    private Texture2D? _enemyIntentFallbackTexture;
    private Texture2D? _enemyPortraitFallbackTexture;
    private readonly Dictionary<string, Texture2D> _cardFaceTextureCache = new(StringComparer.Ordinal);
    private bool _defeatResolvedForCurrentHpDrop;
    private int _hpChangedEmissionCount;
    private int _defeatEligibleTransitionCount;
    private int _defeatResolveCount;
    private int _unifiedHpUpdateEntryCount;
    private int _cardsPlayedThisTurn;
    private float _targetHighlightPulsePhase;
    private readonly CombatService _combatService = new();
    private string _lastResolvedEnemyPortraitPath = "unresolved";
    private bool _bootstrappedEnemyRuntimeActive;
    private bool _manualEnemyRuntimeOverrideUsedForTest;
    private readonly List<Control> _handFanCards = new();
    private readonly List<Vector2> _handFanBasePositions = new();
    private readonly List<float> _handFanBaseRotations = new();
    private int _hoveredHandFanIndex = -1;
    private Texture2D? _playerPortraitTexture;
    private Vector2 _dragCardGhostFaceDefaultMinimumSize;
    private float _dragGhostVisualScaleForTest = 1.0f;
    private const string DefaultPlayerPortraitId = "player_fungal_knight";
    private const int DefaultDrawCountPerTurn = 5;
    private const int DefaultHandLimit = 10;
    private const int PileViewerOverlayZIndex = 1000;
    private const int DragOverlayZIndex = 2000;
    private const int CombatFxLayerZIndex = 2500;
    private const string PlayerHitTargetId = "player";
    private readonly DeckService _deckService = new();
    private readonly StatusService _statusService = new();
    private DeckState? _deckState;
    private int _runtimeDeckInstanceCounter;
    private string _pileViewerSource = "master";
    private const int MapOverlayZIndex = 1001;
    private static readonly PackedScene? MapOverlayScenePacked = LoadMapOverlayScenePacked();

    public override void _Ready()
    {
        _handCards = GetNode<ItemList>("HUD/HandCards");
        _difficultyValue = GetNode<Label>("HUD/DifficultyValue");
        _playerHpValue = GetNode<Label>("HUD/PlayerHpValue");
        _energyValue = GetNode<Label>("HUD/EnergyValue");
        _drawPileValue = GetNode<Label>("HUD/DrawPileValue");
        _discardPileValue = GetNode<Label>("HUD/DiscardPileValue");
        _drawPileBadge = GetNode<PanelContainer>("HUD/DrawPileBadge");
        _discardPileBadge = GetNode<PanelContainer>("HUD/DiscardPileBadge");
        _exhaustPileBadge = GetNode<PanelContainer>("HUD/ExhaustPileBadge");
        _turnStateValue = GetNode<Label>("HUD/TurnStateValue");
        _masterDeckButton = GetNode<Button>("HUD/MasterDeckButton");
        _mapButton = GetNode<Button>("HUD/MapButton");
        _feedbackMessageLabel = GetNode<Label>("HUD/FeedbackMessageLabel");
        _feedbackHistoryList = GetNode<ItemList>("HUD/FeedbackHistoryList");
        _enemyRosterTitleLabel = GetNode<Label>("HUD/EnemyRosterPanel/EnemyRosterTitle");
        _enemyRosterContainer = GetNode<HBoxContainer>("HUD/EnemyRosterPanel/EnemyRosterContainer");
        _enemyIntentTitleLabel = GetNode<Label>("HUD/EnemyIntentPanel/EnemyIntentTitle");
        _enemyIntentList = GetNode<VBoxContainer>("HUD/EnemyIntentPanel/EnemyIntentList");
        _powerRelicPanel = GetNode<VBoxContainer>("HUD/PowerRelicPanel");
        _powerRelicTitleLabel = GetNode<Label>("HUD/PowerRelicPanel/PowerRelicTitle");
        _powerParticipantList = GetNode<ItemList>("HUD/PowerRelicPanel/PowerParticipantList");
        _relicParticipantList = GetNode<ItemList>("HUD/PowerRelicPanel/RelicParticipantList");
        _potionParticipantList = GetNode<ItemList>("HUD/PowerRelicPanel/PotionParticipantList");
        _cardButtonRow = GetNode<HBoxContainer>("HUD/CardButtonRow");
        _handFanLayer = GetNode<Control>("HUD/HandFanLayer");
        _enemyStatusTitleLabel = GetNode<Label>("HUD/EnemyStatusPanel/EnemyStatusTitle");
        _enemyBattleStage = GetNode<HBoxContainer>("HUD/EnemyBattleStagePanel/EnemyBattleStageMargin/EnemyBattleStage");
        _playerBattleStagePanel = GetNode<PanelContainer>("HUD/PlayerBattleStagePanel");
        _playerTargetHighlight = GetNode<PanelContainer>("HUD/PlayerBattleStagePanel/PlayerTargetHighlight");
        _playerPortrait = GetNode<TextureRect>("HUD/PlayerBattleStagePanel/PlayerBattleStageMargin/PlayerBattleStage/PlayerPortraitFrame/PlayerPortrait");
        _enemyPortraitFrame = GetNode<PanelContainer>("HUD/EnemyStatusPanel/EnemyPortraitFrame");
        _enemyTargetHighlight = GetNode<ColorRect>("HUD/EnemyStatusPanel/EnemyTargetHighlight");
        _enemyPortrait = GetNode<TextureRect>("HUD/EnemyStatusPanel/EnemyPortraitFrame/EnemyPortrait");
        _enemyPortraitInStatusPanel = _enemyPortrait;
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
        _debugCombatRuntimeLabel = GetNode<Label>("HUD/DebugPanel/DebugMargin/DebugVBox/DebugCombatRuntime");
        _combatFxLayer = GetNode<Control>("HUD/CombatFxLayer");
        _combatSfxPlayer = GetNode<AudioStreamPlayer>("HUD/CombatSfxPlayer");
        _dragArrow = GetNode<Line2D>("HUD/DragArrow");
        _dragCardGhost = GetNode<PanelContainer>("HUD/DragCardGhost");
        _dragCardGhostBody = GetNode<Control>("HUD/DragCardGhost/GhostMargin/GhostBody");
        _dragCardGhostFace = GetNode<TextureRect>("HUD/DragCardGhost/GhostMargin/GhostBody/GhostFace");
        _dragCardGhostFaceDefaultMinimumSize = _dragCardGhostFace.CustomMinimumSize;
        _dragCardGhostTitle = GetNode<Label>("HUD/DragCardGhost/GhostMargin/GhostBody/GhostHeader/GhostHeaderRow/GhostTitle");
        _dragCardGhostCost = GetNode<Label>("HUD/DragCardGhost/GhostMargin/GhostBody/GhostHeader/GhostHeaderRow/GhostCostBadge/GhostCost");
        _dragCardGhostType = GetNode<Label>("HUD/DragCardGhost/GhostMargin/GhostBody/GhostMetaRow/GhostTypeBadge/GhostType");
        _dragCardGhostSummary = GetNode<Label>("HUD/DragCardGhost/GhostMargin/GhostBody/GhostSummary");
        _pileViewerOverlay = GetNode<Control>("HUD/PileViewerOverlay");
        _pileViewerBackButton = GetNode<Button>("HUD/PileViewerOverlay/PileViewerShell/BackColumn/BackButton");
        _pileViewerTitle = GetNode<Label>("HUD/PileViewerOverlay/PileViewerShell/ContentColumn/PileViewerTitle");
        _pileViewerGrid = GetNode<GridContainer>("HUD/PileViewerOverlay/PileViewerShell/ContentColumn/PileViewerScroll/PileViewerGrid");
        _mapOverlay = GetNode<Control>("HUD/MapOverlay");
        _mapOverlayBackButton = GetNode<Button>("HUD/MapOverlay/MapOverlayShell/BackColumn/BackButton");
        _mapOverlayTitle = GetNode<Label>("HUD/MapOverlay/MapOverlayShell/ContentColumn/MapOverlayTitle");
        _mapOverlayContent = GetNode<Control>("HUD/MapOverlay/MapOverlayShell/ContentColumn/MapOverlayScroll/MapOverlayContent");

        BindUiSignalsOnce();
        _startTurnButton.Visible = false;
        _startTurnButton.Text = ResolveUiText("combat.turn.start");
        _playSelectedCardButton.Text = ResolveUiText("combat.action.play_selected");
        _playSelectedCardButton.Visible = false;
        _endTurnButton.Text = ResolveUiText("combat.turn.end");
        _turnTitleLabel.Text = ResolveUiText("combat.turn.title");
        _actionHintLabel.Text = ResolveUiText("combat.action.hint");
        _handTitleLabel.Text = ResolveUiText("combat.hand.title");
        _pileViewerOverlay.ZIndex = PileViewerOverlayZIndex;
        _mapOverlay.ZIndex = MapOverlayZIndex;
        _combatFxLayer.ZIndex = CombatFxLayerZIndex;
        _dragCardGhost.ZIndex = DragOverlayZIndex;
        _dragArrow.ZIndex = DragOverlayZIndex + 1;
        _enemyRosterTitleLabel.Text = ResolveUiText("combat.enemy.title");
        _enemyStatusTitleLabel.Text = ResolveUiText("combat.enemy.title");
        _enemyIntentTitleLabel.Text = ResolveUiText("combat.intent.title");
        _feedbackMessageLabel.Text = string.Empty;
        _powerRelicTitleLabel.Text = "Power/Relic/Potion Participants";
        _powerRelicPanel.Visible = false;
        _playerPortrait.Texture = ResolvePlayerPortraitTexture();
        _masterDeckButton.Text = "Deck 0";
        _mapButton.Text = "Map";
        ApplyDefaultM1CombatSnapshotIfEmpty();
        ApplyDefaultM1EnemyStateIfEmpty();
        ApplyDefaultM1EnemyIntentIfEmpty();
        EnsureCardDefinitionsLoaded();
        EnsureDefaultHandSelection();
        RefreshRuntimeDebugPanel();
    }

    public override void _ExitTree()
    {
        _uiSignalsBound = false;
        if (_startTurnButton is not null)
        {
            _startTurnButton.Pressed -= OnStartTurnPressed;
        }

        if (_drawPileBadge is not null)
        {
            _drawPileBadge.GuiInput -= OnDrawPileBadgeGuiInput;
        }

        if (_discardPileBadge is not null)
        {
            _discardPileBadge.GuiInput -= OnDiscardPileBadgeGuiInput;
        }

        if (_exhaustPileBadge is not null)
        {
            _exhaustPileBadge.GuiInput -= OnExhaustPileBadgeGuiInput;
        }

        if (_playSelectedCardButton is not null)
        {
            _playSelectedCardButton.Pressed -= OnPlaySelectedCardPressed;
        }

        if (_endTurnButton is not null)
        {
            _endTurnButton.Pressed -= OnEndTurnPressed;
        }

        if (_masterDeckButton is not null)
        {
            _masterDeckButton.Pressed -= OnMasterDeckPressed;
        }

        if (_mapButton is not null)
        {
            _mapButton.Pressed -= OnMapButtonPressed;
        }

        if (_pileViewerBackButton is not null)
        {
            _pileViewerBackButton.Pressed -= OnPileViewerBackPressed;
        }

        if (_mapOverlayBackButton is not null)
        {
            _mapOverlayBackButton.Pressed -= OnMapOverlayBackPressed;
        }

        if (_handCards is not null)
        {
            _handCards.ItemClicked -= OnHandCardClicked;
            _handCards.GuiInput -= OnHandCardsGuiInput;
        }
    }

    private void BindUiSignalsOnce()
    {
        if (_uiSignalsBound)
        {
            return;
        }

        _uiSignalsBound = true;
        _startTurnButton.Pressed += OnStartTurnPressed;
        _playSelectedCardButton.Pressed += OnPlaySelectedCardPressed;
        _endTurnButton.Pressed += OnEndTurnPressed;
        _masterDeckButton.Pressed += OnMasterDeckPressed;
        _mapButton.Pressed += OnMapButtonPressed;
        _pileViewerBackButton.Pressed += OnPileViewerBackPressed;
        _mapOverlayBackButton.Pressed += OnMapOverlayBackPressed;
        _drawPileBadge.GuiInput += OnDrawPileBadgeGuiInput;
        _discardPileBadge.GuiInput += OnDiscardPileBadgeGuiInput;
        _exhaustPileBadge.GuiInput += OnExhaustPileBadgeGuiInput;
        _handCards.ItemClicked += OnHandCardClicked;
        _handCards.GuiInput += OnHandCardsGuiInput;
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
        var configuredRelics = BuildConfiguredLiveRelicParticipants(payload.RelicIds);
        var mergedRelics = MergeRelicParticipants(payload.Relics, configuredRelics);
        if (payload.Powers is not null || mergedRelics is not null || payload.Potions is not null)
        {
            ApplyPowerRelicParticipants(payload.Powers, mergedRelics, payload.Potions);
        }
        ApplyConfiguredCombatStartRelicEffects(payload.RelicIds);
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
            hand.Add(GetHandCardIdAt(index));
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
            handCards.Add(GetHandCardIdAt(index));
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
        var acceptedCountBefore = _acceptedCommandFeedbackCount;
        var selectedStateBefore = _latestCommandOutcomeState;
        AppendCommandFeedback(commandName, accepted);
        _acceptedCommandFeedbackCount = acceptedCountBefore + (accepted ? 1 : 0);
        _latestCommandOutcomeState = selectedStateBefore;
    }

    public void ApplyHoverPreviewForTest(string previewId)
    {
        var selectedIndex = _isCardDragActive ? _draggedHandIndex : ResolveSelectedHandIndex();
        if (selectedIndex < 0 || selectedIndex >= _handCards.ItemCount)
        {
            _lastHoverPreviewText = string.Empty;
            return;
        }
        var cardName = GetHandCardIdAt(selectedIndex);
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
        var hadPreview = !string.IsNullOrWhiteSpace(_lastHoverPreviewText);
        _lastHoverPreviewText = string.Empty;
        if (hadPreview)
        {
            PublishPresentationCue("card_preview_closed");
        }
    }

    public void ApplyTargetInspectionForTest(string targetId)
    {
        var normalized = string.IsNullOrWhiteSpace(targetId) ? string.Empty : targetId.Trim();
        if (!string.IsNullOrEmpty(normalized)
            && (_enemyIntentByEnemy.ContainsKey(normalized) || _enemyCombatById.ContainsKey(normalized)))
        {
            _targetInspectionVisibleForTest = true;
            PublishPresentationCue("intent_detail_opened");
        }
        if (_isCardDragActive)
        {
            _draggedTargetEnemyId = normalized;
            _ = TrySelectEnemyTarget(normalized);
            UpdateActionHintForCurrentInteraction();
        }
        if (TryInspectParticipant(targetId))
        {
            _targetInspectionVisibleForTest = true;
        }
    }

    public void HideTargetInspectionForTest()
    {
        if (_targetInspectionVisibleForTest)
        {
            PublishPresentationCue("intent_detail_hidden");
            _targetInspectionVisibleForTest = false;
        }
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

    public int GetVisibleHandFanCardCountForTest()
    {
        return _handFanCards.Count;
    }

    public int GetHoveredHandFanCardIndexForTest()
    {
        return _hoveredHandFanIndex;
    }

    public float GetHandFanCardScaleForTest(int handIndex)
    {
        if (handIndex < 0 || handIndex >= _handFanCards.Count)
        {
            return 0.0f;
        }

        return _handFanCards[handIndex].Scale.X;
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

    public bool IsPlayerTargetHighlightActiveForTest()
    {
        return _playerTargetHighlight.Visible;
    }

    public string GetDragGhostTextForTest()
    {
        return _dragCardGhostTitle.Text;
    }

    public float GetHandFanCardRotationForTest(int handIndex)
    {
        if (handIndex < 0 || handIndex >= _handFanCards.Count)
        {
            return 0.0f;
        }

        return _handFanCards[handIndex].RotationDegrees;
    }

    public float GetDragGhostVisualScaleForTest()
    {
        return _dragGhostVisualScaleForTest;
    }

    public bool IsDraggedEnemySourceCardEmphasisActiveForTest()
    {
        return _isCardDragActive
            && CurrentDraggedCardTargetsEnemy()
            && _draggedHandIndex >= 0
            && _hoveredHandFanIndex == _draggedHandIndex;
    }

    public bool SetExhaustPileCountForTest(int count)
    {
        _exhaustPileCount = Math.Max(0, count);
        if (_deckState is not null)
        {
            var exhaustPile = BuildRuntimeExhaustPile(_exhaustPileCount, _deckState.DrawPile.Count + _deckState.Hand.Count + _deckState.DiscardPile.Count);
            _deckState = _deckState with
            {
                ExhaustPile = exhaustPile,
            };
        }

        RefreshMasterDeckButton();
        return true;
    }

    public bool OpenPileViewerForTest(string pileSource)
    {
        return ShowPileViewer(pileSource);
    }

    public void ClosePileViewerForTest()
    {
        HidePileViewer();
    }

    public int GetPileViewerVisibleCardCountForTest()
    {
        if (_pileViewerSource == "draw")
        {
            return _deckState?.DrawPile.Count ?? (TryParseIntLabel(_drawPileValue, out var drawCount) ? drawCount : 0);
        }

        if (_pileViewerSource == "discard")
        {
            return _deckState?.DiscardPile.Count ?? (TryParseIntLabel(_discardPileValue, out var discardCount) ? discardCount : 0);
        }

        if (_pileViewerSource == "exhaust")
        {
            return _exhaustPileCount;
        }

        return (_deckState?.Hand.Count ?? _handCards.ItemCount)
            + (_deckState?.DrawPile.Count ?? (TryParseIntLabel(_drawPileValue, out var masterDrawCount) ? masterDrawCount : 0))
            + (_deckState?.DiscardPile.Count ?? (TryParseIntLabel(_discardPileValue, out var masterDiscardCount) ? masterDiscardCount : 0));
    }

    public string GetRuntimeDebugSceneTextForTest()
    {
        return _debugScenePathLabel.Text;
    }

    public string GetRuntimeDebugPortraitTextForTest()
    {
        return _debugPortraitStatusLabel.Text;
    }

    public bool IsPileViewerVisibleForTest()
    {
        return _pileViewerOverlay.Visible;
    }

    public string GetEnemyPortraitPathForTest(string enemyId)
    {
        _ = ResolveEnemyPortraitTexture(enemyId);
        return _lastResolvedEnemyPortraitPath;
    }

    public string GetMasterDeckButtonTextForTest()
    {
        return _masterDeckButton.Text;
    }

    public bool IsMapOverlayVisibleForTest()
    {
        return _mapOverlay.Visible;
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

    public void ProcessInputEventForTest(InputEvent @event)
    {
        _Input(@event);
    }

    public Vector2 GetHandCardPointerForTest(int handIndex)
    {
        if (handIndex < 0 || handIndex >= _handCards.ItemCount)
        {
            return Vector2.Zero;
        }

        if (handIndex < _handFanCards.Count)
        {
            return _handFanCards[handIndex].GetGlobalRect().GetCenter();
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

    public Vector2 GetPlayerTargetPointerForTest()
    {
        if (_playerTargetHighlight.Visible)
        {
            return _playerTargetHighlight.GetGlobalRect().GetCenter();
        }

        if (_playerBattleStagePanel.GetNodeOrNull<Control>("PlayerBattleStageMargin/PlayerBattleStage/PlayerPortraitFrame") is { } portraitFrame)
        {
            return portraitFrame.GetGlobalRect().GetCenter();
        }

        return _playerBattleStagePanel.GetGlobalRect().GetCenter();
    }

    public Vector2 GetEnemyTargetPointerForTest(string enemyId)
    {
        if (string.IsNullOrWhiteSpace(enemyId))
        {
            return Vector2.Zero;
        }

        var normalizedEnemyId = enemyId.Trim();
        var battleStageUnit = FindEnemyBattleStageUnit(normalizedEnemyId);
        if (battleStageUnit is not null)
        {
            if (battleStageUnit.GetNodeOrNull<Control>("EnemyPortraitFrame") is { } portraitFrame)
            {
                return portraitFrame.GetGlobalRect().GetCenter();
            }

            return battleStageUnit.GetGlobalRect().GetCenter();
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

    public global::Godot.Collections.Array<string> GetVisibleCombatFloatTextsForTest()
    {
        var texts = new global::Godot.Collections.Array<string>();
        foreach (var fx in _activeCombatFloatFx.ToArray())
        {
            if (!GodotObject.IsInstanceValid(fx.Label) || !fx.Label.Visible)
            {
                continue;
            }

            texts.Add(fx.Descriptor);
        }

        return texts;
    }

    public bool IsHitFlashActiveForTest(string targetId)
    {
        if (string.IsNullOrWhiteSpace(targetId))
        {
            return false;
        }

        return _hitFlashTokensByTarget.ContainsKey(targetId.Trim());
    }

    public int GetResolvedSfxPlaybackCountForTest()
    {
        return _resolvedSfxPlaybackCount;
    }

    public string GetLastResolvedSfxHookForTest()
    {
        return _lastResolvedSfxHook;
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

    public bool ApplyConfiguredCombatRelicsForTest(global::Godot.Collections.Array relicIds)
    {
        var normalizedRelicIds = new List<string>();
        foreach (var relicId in relicIds)
        {
            var normalized = relicId.ToString().Trim();
            if (!string.IsNullOrWhiteSpace(normalized))
            {
                normalizedRelicIds.Add(normalized);
            }
        }

        var configuredRelics = BuildConfiguredLiveRelicParticipants(normalizedRelicIds);
        if (configuredRelics is null || configuredRelics.Count <= 0)
        {
            return false;
        }

        ApplyPowerRelicParticipants(null, configuredRelics, null);
        ApplyConfiguredCombatStartRelicEffects(normalizedRelicIds);
        return true;
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

        var selectedCardName = GetHandCardIdAt(selectedIndex);
        var accepted = TryPlayCard(selectedCardName, selectedIndex);
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
            handCards.Add(GetHandCardIdAt(index));
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
            _pendingDamageFloatValue = result.Damage;
            _pendingDamageTargetEnemyId = targetEnemyId;
            _pendingHitTargetId = string.IsNullOrWhiteSpace(targetEnemyId) ? DefaultEnemyId : targetEnemyId.Trim();
            PublishPresentationCue("damage_number");
            PublishPresentationCue("hit_feedback");
            PublishSfxHook("hit");
        }
        if (result.Block > 0)
        {
            _pendingBlockFloatValue = result.Block;
            PublishPresentationCue("block_gain_number");
            PublishSfxHook("block");
        }
        var updatedDeckState = _deckState;
        if (updatedDeckState is not null && selectedIndex >= 0 && selectedIndex < updatedDeckState.Hand.Count)
        {
            var playedInstanceId = updatedDeckState.Hand[selectedIndex];
            updatedDeckState = result.MovedToExhaust
                ? _deckService.Exhaust(updatedDeckState, playedInstanceId)
                : _deckService.Discard(updatedDeckState, new[] { playedInstanceId });
            _deckState = updatedDeckState;
            handCards = updatedDeckState.Hand
                .Select(ResolveRuntimeCardLabel)
                .ToList();
        }
        else
        {
            handCards.RemoveAt(selectedIndex);
        }

        var remainingEnergy = pipelineResult.StateAfter.Energy;
        _cardsPlayedThisTurn = pipelineResult.StateAfter.CardsPlayedThisTurn;
        if (result.MovedToExhaust)
        {
            _exhaustPileCount += 1;
        }

        var nextDrawPile = updatedDeckState?.DrawPile.Count ?? drawPile;
        var nextDiscardPile = updatedDeckState?.DiscardPile.Count ?? (result.MovedToExhaust ? discardPile : discardPile + 1);
        ApplyCoreSnapshot(new CombatHudSnapshot(
            handCards,
            remainingEnergy,
            nextDrawPile,
            nextDiscardPile,
            difficulty,
            playerHp,
            _turnStateValue.Text));
        ClearDragState(resetHint: false);
        UpdateActionHintForCurrentInteraction();
        var acceptedDetail = BuildAcceptedCardDetail(result, remainingEnergy, definition.Cost);
        var participantOutcomeDetail = BuildLastPowerRelicOutcomeDetail();
        var combinedDetail = string.IsNullOrWhiteSpace(participantOutcomeDetail)
            ? acceptedDetail
            : $"{acceptedDetail} {participantOutcomeDetail}";
        AppendCommandFeedback(normalizedCard, accepted: true, detail: combinedDetail);
        TryAutoCompleteVictoryRoute();
        return true;
    }

    private void ResolvePowerRelicRuntimeForCardPlay()
    {
        _lastPowerRelicOutcomeMessages.Clear();
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

    private void ApplyConfiguredCombatStartRelicEffects(IReadOnlyList<string>? relicIds)
    {
        if (relicIds is null || relicIds.Count <= 0)
        {
            return;
        }

        var pendingRelicIds = relicIds
            .Where(relicId => !_appliedCombatStartRelicIds.Contains(relicId))
            .Distinct(StringComparer.Ordinal)
            .ToArray();
        if (pendingRelicIds.Length <= 0)
        {
            return;
        }

        var catalog = LoadLiveRelicCatalog();
        if (catalog.Count <= 0 || !TryParseIntLabel(_energyValue, out var currentEnergy))
        {
            return;
        }

        var resolution = RelicEffectRuntimeService.ResolveCombatStartEffects(currentEnergy, pendingRelicIds, catalog);
        if (resolution.AdjustedEnergy == currentEnergy)
        {
            return;
        }

        _energyValue.Text = resolution.AdjustedEnergy.ToString(CultureInfo.InvariantCulture);

        foreach (var effect in resolution.Effects)
        {
            if (!_appliedCombatStartRelicIds.Add(effect.RelicId))
            {
                continue;
            }

            if (!catalog.TryGetValue(effect.RelicId, out var definition))
            {
                continue;
            }

            var participantId = ToParticipantId(definition.RelicId);
            var attribution = ResolveFeedbackTemplate(definition.AttributionKey);
            var outcome = ResolveFeedbackTemplate(definition.OutcomeTextKey);
            PublishPowerRelicOutcomeMessage($"Relic.{participantId}: {attribution} - {outcome}");
        }
    }

    private List<ParticipantItemPayload>? BuildConfiguredLiveRelicParticipants(IReadOnlyList<string>? relicIds)
    {
        if (relicIds is null || relicIds.Count <= 0)
        {
            return null;
        }

        var catalog = LoadLiveRelicCatalog();
        if (catalog.Count <= 0)
        {
            return null;
        }

        var participants = new List<ParticipantItemPayload>();
        foreach (var relicId in relicIds)
        {
            if (!catalog.TryGetValue(relicId, out var definition)
                || !string.Equals(definition.ExecutionBoundary, "t99.shared.combat", StringComparison.Ordinal)
                || !string.Equals(definition.TriggerPath, "core.combat.relic.triggered", StringComparison.Ordinal))
            {
                continue;
            }

            var attribution = ResolveFeedbackTemplate(definition.AttributionKey);
            var outcome = ResolveFeedbackTemplate(definition.OutcomeTextKey);
            participants.Add(new ParticipantItemPayload(
                ToParticipantId(definition.RelicId),
                $"{attribution}: {outcome}",
                Priority: 10,
                RegistrationOrder: 10,
                OutcomeMessage: outcome,
                VisibleOnSurface: true));
        }

        return participants.Count > 0 ? participants : null;
    }

    private static List<ParticipantItemPayload>? MergeRelicParticipants(
        IReadOnlyList<ParticipantItemPayload>? explicitRelics,
        IReadOnlyList<ParticipantItemPayload>? configuredRelics)
    {
        if (explicitRelics is null || explicitRelics.Count <= 0)
        {
            return configuredRelics is null ? null : new List<ParticipantItemPayload>(configuredRelics);
        }

        if (configuredRelics is null || configuredRelics.Count <= 0)
        {
            return new List<ParticipantItemPayload>(explicitRelics);
        }

        var merged = new List<ParticipantItemPayload>(explicitRelics);
        var seenIds = new HashSet<string>(
            explicitRelics
                .Select(item => item.Id?.Trim())
                .Where(item => !string.IsNullOrWhiteSpace(item))!,
            StringComparer.Ordinal);

        foreach (var item in configuredRelics)
        {
            var normalizedId = item.Id?.Trim();
            if (string.IsNullOrWhiteSpace(normalizedId) || seenIds.Add(normalizedId))
            {
                merged.Add(item);
            }
        }

        return merged;
    }

    private static string ToParticipantId(string relicId)
    {
        return relicId.StartsWith("relic.", StringComparison.Ordinal)
            ? relicId["relic.".Length..]
            : relicId;
    }

    private static IReadOnlyDictionary<string, RelicEffectDefinition> LoadLiveRelicCatalog()
    {
        if (_liveRelicCatalogCache is not null)
        {
            return _liveRelicCatalogCache;
        }

        foreach (var path in LiveRelicDefinitionCandidatePaths)
        {
            var absolutePath = ProjectSettings.GlobalizePath(path);
            if (!global::System.IO.File.Exists(absolutePath))
            {
                continue;
            }

            var payload = global::System.IO.File.ReadAllText(absolutePath);
            if (string.IsNullOrWhiteSpace(payload))
            {
                continue;
            }

            _liveRelicCatalogCache = RelicEffectCatalogService.Parse(payload);
            return _liveRelicCatalogCache;
        }

        var repoRoot = global::System.IO.Path.GetFullPath(
            global::System.IO.Path.Combine(ProjectSettings.GlobalizePath("res://"), ".."));
        var repoRelativeCatalogPath = global::System.IO.Path.Combine(
            repoRoot,
            "Game.Core",
            "Data",
            "m1-relic-definitions.json");
        if (global::System.IO.File.Exists(repoRelativeCatalogPath))
        {
            var payload = global::System.IO.File.ReadAllText(repoRelativeCatalogPath);
            if (!string.IsNullOrWhiteSpace(payload))
            {
                _liveRelicCatalogCache = RelicEffectCatalogService.Parse(payload);
                return _liveRelicCatalogCache;
            }
        }

        _liveRelicCatalogCache = new Dictionary<string, RelicEffectDefinition>(StringComparer.Ordinal);
        return _liveRelicCatalogCache;
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

    public string GetEnemyNameForTest()
    {
        return _enemyNameValue.Text;
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

    public int GetEnemyHpForTest(string enemyId)
    {
        if (string.IsNullOrWhiteSpace(enemyId) || !_enemyCombatById.TryGetValue(enemyId.Trim(), out var state))
        {
            return -1;
        }

        return state.CurrentHp;
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
        if (!enabled)
        {
            _enemyIntentPreviewManuallyAppliedForTest = false;
            _enemyIntentByEnemy.Clear();
            foreach (var child in _enemyIntentList.GetChildren())
            {
                child.QueueFree();
            }

            _enemyIntentList.Visible = false;
        }
        else
        {
            _enemyIntentPreviewManuallyAppliedForTest = false;
        }
    }

    public string GetPlayerStatusSummaryForTest()
    {
        if (_playerStatuses.Count <= 0)
        {
            return string.Empty;
        }

        var parts = new List<string>();
        foreach (var status in _playerStatuses.Values)
        {
            var visibleAmount = ResolveVisiblePlayerStatusValue(status);
            if (visibleAmount <= 0)
            {
                continue;
            }

            parts.Add($"{status.StatusId}:{visibleAmount}");
        }

        if (parts.Count <= 0)
        {
            return string.Empty;
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

        if (_bootstrappedEnemyRuntimeActive && !_manualEnemyRuntimeOverrideUsedForTest)
        {
            _enemyCombatById.Clear();
            _enemyStatusStacksByEnemy.Clear();
            _enemyIntentByEnemy.Clear();
            _selectedEnemyTargetId = string.Empty;
            _bootstrappedEnemyRuntimeActive = false;
            _manualEnemyRuntimeOverrideUsedForTest = true;
        }

        var hasEnemy = _enemyCombatById.TryGetValue(enemyId, out var existingState);
        var state = hasEnemy && existingState is not null
            ? existingState
            : new EnemyCombatState(
                enemyId,
                ResolveEnemyDisplayName(enemyId),
                maxHp,
                0,
                ResolveUiText("combat.enemy.status.none"),
                maxHp,
                ResolveEnemyNameKey(enemyId));

        var clampedHp = Math.Min(maxHp, currentHp);
        _enemyCombatById[enemyId] = state with { CurrentHp = clampedHp, MaxHp = maxHp };
        if (clampedHp <= 0)
        {
            RemoveEnemyFromActiveSets(enemyId);
        }
        else if (!_enemyIntentByEnemy.ContainsKey(enemyId))
        {
            EnsureFallbackEnemyIntentForTest(enemyId);
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
        _playSelectedCardButton.Visible = false;
        _endTurnButton.Text = ResolveUiText("combat.turn.end");
        _turnTitleLabel.Text = ResolveUiText("combat.turn.title");
        _actionHintLabel.Text = ResolveUiText("combat.action.hint");
        _handTitleLabel.Text = ResolveUiText("combat.hand.title");
        _enemyRosterTitleLabel.Text = ResolveUiText("combat.enemy.title");
        _enemyStatusTitleLabel.Text = ResolveUiText("combat.enemy.title");
        _enemyIntentTitleLabel.Text = ResolveUiText("combat.intent.title");
        var handCards = new List<string>();
        for (var index = 0; index < _handCards.ItemCount; index++)
        {
            handCards.Add(GetHandCardIdAt(index));
        }

        RebuildCardButtons(handCards);
        RefreshDefaultM1EnemyStateLocale();
        RefreshEnemyIntentRows();
        RefreshMasterDeckButton();
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
        _enemyIntentPreviewManuallyAppliedForTest = true;
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

    public global::Godot.Collections.Array<string> GetEnemyIntentIdsForTest()
    {
        var ids = new global::Godot.Collections.Array<string>();
        foreach (var enemyId in _enemyIntentByEnemy.Keys.OrderBy(static item => item, StringComparer.Ordinal))
        {
            ids.Add(enemyId);
        }

        return ids;
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
            AddHandCardItem(card);
        }

        _difficultyValue.Text = snapshot.Difficulty.ToString();
        _playerHpValue.Text = snapshot.PlayerHp.ToString();
        _energyValue.Text = snapshot.Energy.ToString();
        _drawPileValue.Text = snapshot.DrawPileCount.ToString();
        _discardPileValue.Text = snapshot.DiscardPileCount.ToString();
        _turnStateValue.Text = string.IsNullOrWhiteSpace(snapshot.TurnState)
            ? _turnTitleLabel.Text
            : snapshot.TurnState;
        SyncRuntimeDeckState(snapshot.HandCards, snapshot.DrawPileCount, snapshot.DiscardPileCount);
        RefreshMasterDeckButton();
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
            handCards.Add(GetHandCardIdAt(index));
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
        var nextDeckState = ResolveNextDeckStateAfterEndTurn(handCards);
        var nextHandCards = nextDeckState.Hand
            .Select(ResolveRuntimeCardLabel)
            .ToList();
        _deckState = nextDeckState;
        var progression = _combatService.ResolveEndTurnProgression(
            new EndTurnProgressionInput(
                Difficulty: difficulty,
                PlayerHp: playerHp,
                PlayerBlock: _playerBlock,
                DrawPileCount: nextDeckState.DrawPile.Count,
                DiscardPileCount: nextDeckState.DiscardPile.Count,
                HandCount: 0,
                IncomingEnemyDamage: incomingDamage,
                NextHandCards: nextHandCards));

        _playerBlock = progression.NextPlayerBlock;
        _cardsPlayedThisTurn = 0;
        _turnIndex += 1;
        var statusTransitionDetail = ResolveEndTurnStatusTransitions();
        ApplyCoreSnapshot(new CombatHudSnapshot(
            progression.NextHandCards,
            progression.NextEnergy,
            nextDeckState.DrawPile.Count,
            nextDeckState.DiscardPile.Count,
            difficulty,
            progression.NextPlayerHp,
            "PlayerTurn"));
        ApplyDefaultM1EnemyIntentIfEmpty();
        _pendingEnemyActionDamage = progression.DamageTaken;
        _pendingHitTargetId = PlayerHitTargetId;
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
        var totalDamage = 0;
        foreach (var enemyId in GetAliveEnemyIds())
        {
            if (!_enemyIntentByEnemy.TryGetValue(enemyId, out var intentState))
            {
                continue;
            }

            totalDamage += TryParseDamageFromIntentDescription(intentState.Description);
        }

        return Math.Max(0, totalDamage);
    }

    private static int TryParseDamageFromIntentDescription(string? description)
    {
        var digits = new List<char>();
        foreach (var ch in description ?? string.Empty)
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
        _feedbackHistoryList.AddItem(finalMessage);
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
        DispatchPresentationCueRuntime(normalized);
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
        PlayRuntimeSfx(normalized);
    }

    private void DispatchPresentationCueRuntime(string cue)
    {
        switch (cue)
        {
            case "damage_number":
                if (_pendingDamageFloatValue > 0)
                {
                    ShowCombatFloat(
                        text: $"-{_pendingDamageFloatValue}",
                        descriptor: $"damage:-{_pendingDamageFloatValue}",
                        globalAnchor: ResolveEnemyCombatFxAnchor(_pendingDamageTargetEnemyId),
                        color: new Color(1.0f, 0.42f, 0.34f, 1.0f));
                }

                _pendingDamageFloatValue = 0;
                _pendingDamageTargetEnemyId = string.Empty;
                break;
            case "block_gain_number":
                if (_pendingBlockFloatValue > 0)
                {
                    ShowCombatFloat(
                        text: $"+{_pendingBlockFloatValue} Block",
                        descriptor: $"block:+{_pendingBlockFloatValue}",
                        globalAnchor: ResolvePlayerCombatFxAnchor(),
                        color: new Color(0.47f, 0.86f, 1.0f, 1.0f));
                }

                _pendingBlockFloatValue = 0;
                break;
            case "hit_feedback":
                if (!string.IsNullOrWhiteSpace(_pendingHitTargetId))
                {
                    BeginHitFlash(_pendingHitTargetId);
                }

                _pendingHitTargetId = string.Empty;
                break;
            case "enemy_action_feedback":
                if (_pendingEnemyActionDamage > 0)
                {
                    ShowCombatFloat(
                        text: $"-{_pendingEnemyActionDamage}",
                        descriptor: $"enemy_damage:-{_pendingEnemyActionDamage}",
                        globalAnchor: ResolvePlayerCombatFxAnchor(),
                        color: new Color(1.0f, 0.56f, 0.42f, 1.0f));
                }

                if (!string.IsNullOrWhiteSpace(_pendingHitTargetId))
                {
                    BeginHitFlash(_pendingHitTargetId);
                }

                _pendingEnemyActionDamage = 0;
                _pendingHitTargetId = string.Empty;
                break;
        }
    }

    private void ShowCombatFloat(string text, string descriptor, Vector2 globalAnchor, Color color)
    {
        if (_combatFxLayer is null || !GodotObject.IsInstanceValid(_combatFxLayer))
        {
            return;
        }

        var label = new Label
        {
            Text = text,
            Visible = true,
            MouseFilter = MouseFilterEnum.Ignore,
            HorizontalAlignment = HorizontalAlignment.Center,
        };
        label.AddThemeColorOverride("font_color", color);
        label.AddThemeColorOverride("font_outline_color", new Color(0.05f, 0.06f, 0.08f, 0.92f));
        label.AddThemeConstantOverride("outline_size", 8);
        label.AddThemeFontSizeOverride("font_size", _reducedMotionForTest ? 26 : 32);
        _combatFxLayer.AddChild(label);
        label.ResetSize();
        label.Size = label.GetMinimumSize();
        label.PivotOffset = label.Size / 2.0f;

        var localAnchor = globalAnchor - _combatFxLayer.GlobalPosition;
        var startPosition = localAnchor - label.Size / 2.0f;
        label.Position = startPosition;
        label.Scale = _reducedMotionForTest ? new Vector2(1.0f, 1.0f) : new Vector2(0.92f, 0.92f);
        label.Modulate = new Color(1.0f, 1.0f, 1.0f, 1.0f);

        var fxState = new CombatFloatFxState(label, descriptor);
        _activeCombatFloatFx.Add(fxState);

        var travelDistance = _reducedMotionForTest ? 18.0f : 42.0f;
        var duration = _reducedMotionForTest ? 0.18f : 0.48f;
        var tween = CreateTween();
        tween.SetParallel(true);
        tween.TweenProperty(label, "position", startPosition + new Vector2(0.0f, -travelDistance), duration)
            .SetTrans(Tween.TransitionType.Cubic)
            .SetEase(Tween.EaseType.Out);
        tween.TweenProperty(label, "scale", _reducedMotionForTest ? new Vector2(1.04f, 1.04f) : Vector2.One, duration * 0.45f)
            .SetTrans(Tween.TransitionType.Back)
            .SetEase(Tween.EaseType.Out);
        tween.TweenProperty(label, "modulate:a", 0.0f, duration)
            .SetDelay(_reducedMotionForTest ? 0.02f : 0.08f)
            .SetTrans(Tween.TransitionType.Cubic)
            .SetEase(Tween.EaseType.In);
        tween.Finished += () => RemoveCombatFloatFx(fxState);
    }

    private void RemoveCombatFloatFx(CombatFloatFxState fxState)
    {
        _activeCombatFloatFx.Remove(fxState);
        if (GodotObject.IsInstanceValid(fxState.Label))
        {
            fxState.Label.QueueFree();
        }
    }

    private void BeginHitFlash(string targetId)
    {
        if (string.IsNullOrWhiteSpace(targetId))
        {
            return;
        }

        var normalizedTargetId = targetId.Trim();
        var flashToken = _hitFlashTokensByTarget.TryGetValue(normalizedTargetId, out var currentToken)
            ? currentToken + 1
            : 1;
        _hitFlashTokensByTarget[normalizedTargetId] = flashToken;
        ApplyHitFlashVisual(normalizedTargetId, active: true);

        var tween = CreateTween();
        tween.TweenInterval(_reducedMotionForTest ? 0.08f : 0.16f);
        tween.Finished += () =>
        {
            if (_hitFlashTokensByTarget.TryGetValue(normalizedTargetId, out var activeToken) && activeToken == flashToken)
            {
                _hitFlashTokensByTarget.Remove(normalizedTargetId);
                ApplyHitFlashVisual(normalizedTargetId, active: false);
            }
        };
    }

    private void ApplyHitFlashVisual(string targetId, bool active)
    {
        var tint = active
            ? new Color(1.0f, 0.72f, 0.72f, 1.0f)
            : Colors.White;
        if (string.Equals(targetId, PlayerHitTargetId, StringComparison.Ordinal))
        {
            _playerPortrait.SelfModulate = tint;
            return;
        }

        _enemyPortrait.SelfModulate = tint;
        if (FindEnemyBattleStageUnit(targetId)?.GetNodeOrNull<TextureRect>("EnemyPortraitFrame/EnemyPortrait") is { } portrait)
        {
            portrait.SelfModulate = tint;
        }
    }

    private Vector2 ResolveEnemyCombatFxAnchor(string enemyId)
    {
        var normalizedEnemyId = string.IsNullOrWhiteSpace(enemyId) ? DefaultEnemyId : enemyId.Trim();
        if (FindEnemyBattleStageUnit(normalizedEnemyId)?.GetNodeOrNull<Control>("EnemyPortraitFrame") is { } portraitFrame)
        {
            var rect = portraitFrame.GetGlobalRect();
            return new Vector2(rect.GetCenter().X, rect.Position.Y + rect.Size.Y * 0.28f);
        }

        var fallbackRect = _enemyPortraitFrame.GetGlobalRect();
        return new Vector2(fallbackRect.GetCenter().X, fallbackRect.Position.Y + fallbackRect.Size.Y * 0.30f);
    }

    private Vector2 ResolvePlayerCombatFxAnchor()
    {
        if (_playerBattleStagePanel.GetNodeOrNull<Control>("PlayerBattleStageMargin/PlayerBattleStage/PlayerPortraitFrame") is { } portraitFrame)
        {
            var rect = portraitFrame.GetGlobalRect();
            return new Vector2(rect.GetCenter().X, rect.Position.Y + rect.Size.Y * 0.24f);
        }

        var fallbackRect = _playerBattleStagePanel.GetGlobalRect();
        return new Vector2(fallbackRect.GetCenter().X, fallbackRect.Position.Y + fallbackRect.Size.Y * 0.24f);
    }

    private void PlayRuntimeSfx(string hook)
    {
        if (_combatSfxPlayer is null || !GodotObject.IsInstanceValid(_combatSfxPlayer))
        {
            return;
        }

        var toneProfile = ResolveSfxToneProfile(hook);
        if (!_sfxToneCache.TryGetValue(hook, out var stream))
        {
            stream = CreateSfxTone(toneProfile.FrequencyHz, toneProfile.DurationSeconds);
            _sfxToneCache[hook] = stream;
        }

        _combatSfxPlayer.Stop();
        _combatSfxPlayer.Stream = stream;
        _combatSfxPlayer.VolumeDb = Mathf.LinearToDb(toneProfile.VolumeLinear);
        _combatSfxPlayer.Play();
        _lastResolvedSfxHook = hook;
        _resolvedSfxPlaybackCount += 1;
    }

    private static SfxToneProfile ResolveSfxToneProfile(string hook)
    {
        return hook switch
        {
            "card_play" => new SfxToneProfile(520.0f, 0.08f, 0.38f),
            "hit" => new SfxToneProfile(180.0f, 0.14f, 0.64f),
            "block" => new SfxToneProfile(760.0f, 0.10f, 0.36f),
            "enemy_action" => new SfxToneProfile(146.0f, 0.18f, 0.70f),
            "invalid_action" => new SfxToneProfile(240.0f, 0.12f, 0.30f),
            _ => new SfxToneProfile(400.0f, 0.10f, 0.32f),
        };
    }

    private static AudioStreamWav CreateSfxTone(float frequencyHz, float durationSeconds)
    {
        const int sampleRate = 22050;
        var frameCount = Math.Max(1, (int)MathF.Ceiling(sampleRate * Math.Max(0.02f, durationSeconds)));
        var pcmData = new byte[frameCount * 2];
        for (var index = 0; index < frameCount; index++)
        {
            var normalizedTime = (float)index / sampleRate;
            var envelope = MathF.Min(1.0f, index / 300.0f) * (1.0f - normalizedTime / Math.Max(durationSeconds, 0.02f));
            var sampleValue = MathF.Sin(normalizedTime * frequencyHz * Mathf.Tau) * envelope * 0.72f;
            var pcmSample = (short)Mathf.Clamp(sampleValue * short.MaxValue, short.MinValue, short.MaxValue);
            pcmData[index * 2] = (byte)(pcmSample & 0xff);
            pcmData[index * 2 + 1] = (byte)((pcmSample >> 8) & 0xff);
        }

        return new AudioStreamWav
        {
            Format = AudioStreamWav.FormatEnum.Format16Bits,
            MixRate = sampleRate,
            Stereo = false,
            Data = pcmData,
        };
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
            enemyState = new EnemyCombatState(
                resolvedEnemyId,
                ResolveEnemyDisplayName(resolvedEnemyId),
                32,
                0,
                ResolveUiText("combat.enemy.status.none"),
                32,
                ResolveEnemyNameKey(resolvedEnemyId));
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

    private string BuildLastPowerRelicOutcomeDetail()
    {
        if (_lastPowerRelicOutcomeMessages.Count <= 0)
        {
            return string.Empty;
        }

        return string.Join(" | ", _lastPowerRelicOutcomeMessages);
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
        var rageStacks = _statusService.GetRageStacks(_playerStatuses);
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
            StableId: $"turn-{_turnIndex}",
            RageStacks: rageStacks);
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

        var type = cardNode.TryGetProperty("type", out var typeNode) && typeNode.ValueKind == JsonValueKind.String
            ? typeNode.GetString()?.Trim() ?? "unknown"
            : "unknown";
        var target = ResolveCardTargetByType(type, cardNode.TryGetProperty("target", out var targetNode) && targetNode.ValueKind == JsonValueKind.String
            ? targetNode.GetString()?.Trim() ?? string.Empty
            : string.Empty);
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

    private static string ResolveCardTargetByType(string type, string explicitTarget)
    {
        var normalizedType = (type ?? string.Empty).Trim().ToLowerInvariant();
        var normalizedExplicitTarget = (explicitTarget ?? string.Empty).Trim().ToLowerInvariant();
        if (normalizedExplicitTarget == "all_enemies")
        {
            return normalizedExplicitTarget;
        }

        if (normalizedType == "attack")
        {
            return "enemy";
        }

        if (normalizedType == "skill" || normalizedType == "power")
        {
            return "self";
        }

        return normalizedExplicitTarget.Length > 0 ? normalizedExplicitTarget : "enemy";
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
        var normalizedStatusId = (statusId ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(normalizedStatusId) || stacks <= 0)
        {
            return;
        }

        _statusService.ApplyToTarget(_playerStatuses, BuildPlayerStatusInstance(normalizedStatusId, stacks));
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

        var playerStatusIds = _playerStatuses.Keys.ToArray();
        var previousVisibleValues = new Dictionary<string, int>(StringComparer.Ordinal);
        foreach (var statusId in playerStatusIds)
        {
            if (!_playerStatuses.TryGetValue(statusId, out var currentStatus))
            {
                continue;
            }

            previousVisibleValues[statusId] = ResolveVisiblePlayerStatusValue(currentStatus);
        }

        _statusService.ProcessTurnPhase(_playerStatuses, ExpiresTiming.OwnerEndOfTurnCleanup);

        foreach (var statusId in playerStatusIds)
        {
            previousVisibleValues.TryGetValue(statusId, out var previousVisible);
            if (_playerStatuses.TryGetValue(statusId, out var nextStatus))
            {
                var nextVisible = ResolveVisiblePlayerStatusValue(nextStatus);
                if (previousVisible > 0 && nextVisible > 0 && nextVisible != previousVisible)
                {
                    details.Add($"decayed {statusId} to {nextVisible} on self");
                }

                continue;
            }

            if (previousVisible > 0)
            {
                details.Add($"expired {statusId} on self");
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

    private StatusInstance BuildPlayerStatusInstance(string statusId, int stacks)
    {
        var normalizedStatusId = statusId.Trim();
        var decaysAtEndTurn = ShouldDecayStatusAtEndTurn(normalizedStatusId);
        var statusType = ResolvePlayerStatusType(normalizedStatusId);
        var visibleStacks = Math.Max(0, stacks);
        var durationTurns = decaysAtEndTurn ? visibleStacks : 0;

        return new StatusInstance(
            StableId: $"player.{normalizedStatusId}",
            StatusId: normalizedStatusId,
            StatusType: statusType,
            Stacks: visibleStacks,
            DurationTurns: durationTurns,
            SourceId: "combat_scene",
            ExpiresTiming: decaysAtEndTurn ? ExpiresTiming.OwnerEndOfTurnCleanup : ExpiresTiming.Never,
            Strength: 0);
    }

    private static StatusType ResolvePlayerStatusType(string statusId)
    {
        if (string.IsNullOrWhiteSpace(statusId))
        {
            return StatusType.Buff;
        }

        if (string.Equals(statusId, "status.weak", StringComparison.OrdinalIgnoreCase)
            || string.Equals(statusId, "status.vulnerable", StringComparison.OrdinalIgnoreCase)
            || string.Equals(statusId, "status.poison", StringComparison.OrdinalIgnoreCase)
            || statusId.EndsWith("_down", StringComparison.OrdinalIgnoreCase))
        {
            return StatusType.Debuff;
        }

        return StatusType.Buff;
    }

    private static int ResolveVisiblePlayerStatusValue(StatusInstance status)
    {
        if (status.ExpiresTiming == ExpiresTiming.OwnerEndOfTurnCleanup)
        {
            return Math.Max(0, status.DurationTurns);
        }

        return Math.Max(0, status.Stacks);
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
        RefreshEnemyRosterCards(aliveEnemies);
        RefreshEnemyBattleStageUnits(aliveEnemies);
        if (aliveEnemies.Count <= 0)
        {
            _enemyPortrait.Texture = null;
            _lastResolvedEnemyPortraitPath = "fallback:empty";
            _enemyPortraitFrame.Visible = false;
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

        _enemyPortrait.Texture = null;
        _enemyPortrait.Visible = false;
        _enemyPortraitFrame.Visible = false;
        _enemyNameValue.Text = preferredState.Name;
        _enemyHpValue.Text = $"{preferredState.CurrentHp}/{preferredState.MaxHp}";
        _enemyBlockValue.Text = preferredState.Block.ToString(CultureInfo.InvariantCulture);
        _enemyStatusValue.Text = preferredState.Status;
        RefreshEnemyTargetHighlight(preferredId);
    }

    private void RefreshEnemyBattleStageUnits(IReadOnlyList<string> aliveEnemies)
    {
        foreach (var child in _enemyBattleStage.GetChildren())
        {
            _enemyBattleStage.RemoveChild(child);
            child.QueueFree();
        }

        _enemyBattleStage.Visible = aliveEnemies.Count > 0;
        foreach (var enemyId in aliveEnemies)
        {
            if (!_enemyCombatById.TryGetValue(enemyId, out var state))
            {
                continue;
            }

            _enemyBattleStage.AddChild(CreateEnemyBattleStageUnit(state));
        }
    }

    private Control CreateEnemyBattleStageUnit(EnemyCombatState state)
    {
        var unit = new VBoxContainer
        {
            Name = $"EnemyStage_{state.EnemyId}",
            CustomMinimumSize = new Vector2(176.0f, 248.0f),
            SizeFlagsVertical = SizeFlags.ShrinkCenter,
            MouseFilter = MouseFilterEnum.Stop,
        };
        unit.SetMeta("enemy_id", state.EnemyId);

        var portraitFrame = new PanelContainer
        {
            Name = "EnemyPortraitFrame",
            CustomMinimumSize = new Vector2(176.0f, 176.0f),
            MouseFilter = MouseFilterEnum.Ignore,
        };
        portraitFrame.AddThemeStyleboxOverride("panel", _enemyPortraitFrame.GetThemeStylebox("panel"));

        var portrait = new TextureRect
        {
            Name = "EnemyPortrait",
            CustomMinimumSize = new Vector2(176.0f, 176.0f),
            ExpandMode = TextureRect.ExpandModeEnum.FitWidthProportional,
            StretchMode = TextureRect.StretchModeEnum.KeepAspectCentered,
            Texture = ResolveEnemyPortraitTexture(state.EnemyId),
            MouseFilter = MouseFilterEnum.Ignore,
        };
        portraitFrame.AddChild(portrait);

        var name = new Label
        {
            Name = "EnemyName",
            Text = state.Name,
            HorizontalAlignment = HorizontalAlignment.Center,
            AutowrapMode = TextServer.AutowrapMode.WordSmart,
            MouseFilter = MouseFilterEnum.Ignore,
        };
        var hp = new Label
        {
            Name = "EnemyHp",
            Text = $"{state.CurrentHp}/{state.MaxHp}",
            HorizontalAlignment = HorizontalAlignment.Center,
            MouseFilter = MouseFilterEnum.Ignore,
        };

        unit.AddChild(portraitFrame);
        unit.AddChild(name);
        unit.AddChild(hp);
        ApplyEnemyPortraitFrameHighlight(portraitFrame, isHovered: false, isSelected: false);
        return unit;
    }

    private Control? FindEnemyBattleStageUnit(string enemyId)
    {
        if (string.IsNullOrWhiteSpace(enemyId))
        {
            return null;
        }

        foreach (var child in _enemyBattleStage.GetChildren())
        {
            if (child is not Control unit || !unit.HasMeta("enemy_id"))
            {
                continue;
            }

            if (string.Equals(unit.GetMeta("enemy_id").AsString(), enemyId, StringComparison.Ordinal))
            {
                return unit;
            }
        }

        return null;
    }

    private void RefreshEnemyRosterCards(IReadOnlyList<string> aliveEnemies)
    {
        foreach (var child in _enemyRosterContainer.GetChildren())
        {
            _enemyRosterContainer.RemoveChild(child);
            child.QueueFree();
        }

        _enemyRosterContainer.Visible = aliveEnemies.Count > 0;
        foreach (var enemyId in aliveEnemies)
        {
            if (!_enemyCombatById.TryGetValue(enemyId, out var state))
            {
                continue;
            }

            _enemyRosterContainer.AddChild(CreateEnemyRosterCard(state));
        }
    }

    private Control CreateEnemyRosterCard(EnemyCombatState state)
    {
        var card = new VBoxContainer
        {
            Name = $"EnemyRoster_{state.EnemyId}",
            CustomMinimumSize = new Vector2(168.0f, 96.0f),
            MouseFilter = MouseFilterEnum.Ignore,
        };
        card.SetMeta("enemy_id", state.EnemyId);

        var enemyName = new Label
        {
            Name = "EnemyName",
            Text = state.Name,
            HorizontalAlignment = HorizontalAlignment.Center,
            AutowrapMode = TextServer.AutowrapMode.WordSmart,
            MouseFilter = MouseFilterEnum.Ignore,
        };
        var enemyHp = new Label
        {
            Name = "EnemyHp",
            Text = $"{state.CurrentHp}/{state.MaxHp}",
            HorizontalAlignment = HorizontalAlignment.Center,
            MouseFilter = MouseFilterEnum.Ignore,
        };
        var enemyBlock = new Label
        {
            Name = "EnemyBlock",
            Text = $"Block {state.Block.ToString(CultureInfo.InvariantCulture)}",
            HorizontalAlignment = HorizontalAlignment.Center,
            MouseFilter = MouseFilterEnum.Ignore,
        };
        var enemyStatus = new Label
        {
            Name = "EnemyStatus",
            Text = state.Status,
            HorizontalAlignment = HorizontalAlignment.Center,
            AutowrapMode = TextServer.AutowrapMode.WordSmart,
            MouseFilter = MouseFilterEnum.Ignore,
        };

        card.AddChild(enemyName);
        card.AddChild(enemyHp);
        card.AddChild(enemyBlock);
        card.AddChild(enemyStatus);
        return card;
    }

    private Control? FindEnemyRosterCard(string enemyId)
    {
        if (string.IsNullOrWhiteSpace(enemyId))
        {
            return null;
        }

        foreach (var child in _enemyRosterContainer.GetChildren())
        {
            if (child is not Control card || !card.HasMeta("enemy_id"))
            {
                continue;
            }

            if (string.Equals(card.GetMeta("enemy_id").AsString(), enemyId, StringComparison.Ordinal))
            {
                return card;
            }
        }

        return null;
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
            "combat.action.hint" => isZh ? "拖拽或选择一张手牌来使用；右键或 Esc 取消当前选牌；没有合适操作时点击“结束回合”。" : "Drag or select a card to play it. Right-click or Esc cancels. Click End Turn when you are done.",
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
        if (!_enemyIntentPreviewManuallyAppliedForTest)
        {
            _enemyIntentByEnemy.Clear();
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
        }

        RefreshEnemyIntentRows();
    }

    private void ApplyDefaultM1CombatSnapshotIfEmpty()
    {
        if (_handCards.ItemCount > 0)
        {
            return;
        }

        var starterDeck = TryLoadRunDeckCardIdsFromMain();
        if (starterDeck.Count <= 0)
        {
            starterDeck = TryLoadStartingDeckCardIdsFromData();
        }
        if (starterDeck.Count <= 0)
        {
            return;
        }

        var openingHand = starterDeck
            .Take(DefaultDrawCountPerTurn)
            .ToList();
        var drawPile = starterDeck
            .Skip(DefaultDrawCountPerTurn)
            .ToList();

        _runtimeDeckInstanceCounter = 0;
        _deckState = new DeckState(
            DrawPile: drawPile.Select(CreateRuntimeCardInstanceId).ToList(),
            Hand: openingHand.Select(CreateRuntimeCardInstanceId).ToList(),
            DiscardPile: Array.Empty<string>(),
            ExhaustPile: Array.Empty<string>(),
            RetainedInstanceIds: new HashSet<string>(StringComparer.Ordinal),
            HandLimit: DefaultHandLimit);

        ApplyCoreSnapshot(new CombatHudSnapshot(
            openingHand,
            3,
            drawPile.Count,
            0,
            1,
            80,
            "PlayerTurn"));
    }

    private List<string> TryLoadRunDeckCardIdsFromMain()
    {
        var main = GetTree()?.Root?.GetNodeOrNull<Node>("/root/Main");
        if (main is null || !main.HasMethod("GetRunDeckCardIdsForTest"))
        {
            return new List<string>();
        }

        var variant = main.Call("GetRunDeckCardIdsForTest");
        var array = variant.As<global::Godot.Collections.Array>();
        if (array.Count <= 0)
        {
            return new List<string>();
        }

        var cards = new List<string>(array.Count);
        foreach (var item in array)
        {
            var cardId = item.ToString().Trim();
            if (!string.IsNullOrWhiteSpace(cardId))
            {
                cards.Add(cardId);
            }
        }

        return cards;
    }

    private void ApplyDefaultM1EnemyStateIfEmpty()
    {
        if (_enemyCombatById.Count > 0)
        {
            return;
        }

        if (TryApplyDefaultEncounterEnemyStateFromActConfig())
        {
            return;
        }

        _enemyCombatById[DefaultEnemyId] = new EnemyCombatState(
            DefaultEnemyId,
            ResolveUiText("enemy.act1.slime_scout.name"),
            32,
            0,
            ResolveUiText("combat.enemy.status.none"),
            32,
            "enemy.act1.slime_scout.name");
        _enemyCombatById[DefaultEnemySupportId] = new EnemyCombatState(
            DefaultEnemySupportId,
            ResolveUiText("enemy.act1.slime_scout.name"),
            24,
            0,
            ResolveUiText("combat.enemy.status.none"),
            24,
            "enemy.act1.slime_scout.name");
        _selectedEnemyTargetId = DefaultEnemyId;
        _bootstrappedEnemyRuntimeActive = true;
        RefreshPrimaryEnemyPanel();
    }

    private bool TryApplyDefaultEncounterEnemyStateFromActConfig()
    {
        var loadedConfig = TryLoadActConfigFromCandidates();
        if (loadedConfig is null)
        {
            return false;
        }

        var (config, sourcePath) = loadedConfig.Value;
        if (!TryResolveActiveEncounterId(config, out var encounterId) || string.IsNullOrWhiteSpace(encounterId))
        {
            return false;
        }

        var definitionsPath = TryResolveEnemyDefinitionsPath(config, sourcePath);
        if (string.IsNullOrWhiteSpace(definitionsPath))
        {
            return false;
        }

        var definitions = TryLoadEnemyDefinitions(definitionsPath!);
        if (definitions is null || definitions.Count <= 0)
        {
            return false;
        }

        var roster = TryResolveEncounterRoster(config, encounterId!);
        if (roster is null || roster.Count <= 0)
        {
            return false;
        }

        foreach (var rosterEntry in roster)
        {
            if (!definitions.TryGetValue(rosterEntry.EnemyId, out var definition))
            {
                return false;
            }

            _enemyCombatById[rosterEntry.RuntimeId] = new EnemyCombatState(
                rosterEntry.RuntimeId,
                ResolveUiText(definition.NameKey),
                definition.Hp,
                0,
                ResolveUiText("combat.enemy.status.none"),
                definition.Hp,
                definition.NameKey);
        }

        _selectedEnemyTargetId = roster[0].RuntimeId;
        _bootstrappedEnemyRuntimeActive = true;
        RefreshPrimaryEnemyPanel();
        return true;
    }

    private static (ActConfig Config, string SourcePath)? TryLoadActConfigFromCandidates()
    {
        var loader = new ActConfigLoader();
        foreach (var path in ActConfigCandidatePaths)
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

            var result = loader.LoadFromJson(file.GetAsText(), path);
            if (result.IsSuccess && result.Config is not null)
            {
                return (result.Config, path);
            }
        }

        return null;
    }

    private bool TryResolveActiveEncounterId(ActConfig config, out string? encounterId)
    {
        encounterId = null;
        if (config.NodeGraph.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        var selectedNodeId = ResolveSelectedMapNodeIdFromMain();
        if (string.IsNullOrWhiteSpace(selectedNodeId))
        {
            return TryResolveStartEncounterId(config, out encounterId);
        }
        if (!config.NodeGraph.TryGetProperty("nodes", out var nodesNode) || nodesNode.ValueKind != JsonValueKind.Array)
        {
            return false;
        }
        foreach (var node in nodesNode.EnumerateArray())
        {
            if (node.ValueKind != JsonValueKind.Object)
            {
                continue;
            }

            if (!node.TryGetProperty("id", out var idNode) || idNode.ValueKind != JsonValueKind.String)
            {
                continue;
            }

            if (!string.Equals(idNode.GetString()?.Trim(), selectedNodeId, StringComparison.Ordinal))
            {
                continue;
            }

            if (!node.TryGetProperty("encounter_id", out var encounterIdNode) || encounterIdNode.ValueKind != JsonValueKind.String)
            {
                return false;
            }

            encounterId = encounterIdNode.GetString()?.Trim();
            return !string.IsNullOrWhiteSpace(encounterId);
        }

        return false;
    }

    private static string? TryResolveEnemyDefinitionsPath(ActConfig config, string actConfigPath)
    {
        if (config.Encounters.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        if (!config.Encounters.TryGetProperty("enemy_definitions_file", out var pathNode) || pathNode.ValueKind != JsonValueKind.String)
        {
            return null;
        }

        var relativePath = pathNode.GetString()?.Trim();
        if (string.IsNullOrWhiteSpace(relativePath))
        {
            return null;
        }

        if (relativePath.StartsWith("res://", StringComparison.Ordinal))
        {
            return FileAccess.FileExists(relativePath) ? relativePath : null;
        }

        var normalizedRelative = relativePath.Replace('\\', '/').TrimStart('/');
        var candidates = new List<string>
        {
            $"res://{normalizedRelative}",
            $"res://../{normalizedRelative}",
        };
        var parentPrefix = string.Concat("res://", "..", "/");
        if (actConfigPath.StartsWith(parentPrefix, StringComparison.Ordinal))
        {
            candidates.Insert(0, string.Concat(parentPrefix, normalizedRelative));
        }

        foreach (var candidate in candidates.Distinct(StringComparer.Ordinal))
        {
            if (FileAccess.FileExists(candidate))
            {
                return candidate;
            }
        }

        return null;
    }

    private static List<EncounterRosterEntry>? TryResolveEncounterRoster(ActConfig config, string encounterId)
    {
        if (config.Encounters.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        if (!config.Encounters.TryGetProperty("encounter_rosters", out var rostersNode) || rostersNode.ValueKind != JsonValueKind.Object)
        {
            return new List<EncounterRosterEntry>
            {
                new(encounterId, encounterId),
            };
        }

        if (!rostersNode.TryGetProperty(encounterId, out var rosterNode) || rosterNode.ValueKind != JsonValueKind.Array)
        {
            return null;
        }

        var roster = new List<EncounterRosterEntry>();
        foreach (var itemNode in rosterNode.EnumerateArray())
        {
            if (!TryBuildEncounterRosterEntry(itemNode, out var entry))
            {
                return null;
            }

            roster.Add(entry);
        }

        return roster;
    }

    private static bool TryBuildEncounterRosterEntry(JsonElement itemNode, out EncounterRosterEntry entry)
    {
        entry = default!;
        if (itemNode.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        if (!itemNode.TryGetProperty("runtime_id", out var runtimeIdNode) || runtimeIdNode.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        if (!itemNode.TryGetProperty("enemy_id", out var enemyIdNode) || enemyIdNode.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        var runtimeId = runtimeIdNode.GetString()?.Trim() ?? string.Empty;
        var enemyId = enemyIdNode.GetString()?.Trim() ?? string.Empty;
        if (runtimeId.Length <= 0 || enemyId.Length <= 0)
        {
            return false;
        }

        entry = new EncounterRosterEntry(runtimeId, enemyId);
        return true;
    }

    private static Dictionary<string, EncounterEnemyDefinition>? TryLoadEnemyDefinitions(string path)
    {
        if (!FileAccess.FileExists(path))
        {
            return null;
        }

        using var file = FileAccess.Open(path, FileAccess.ModeFlags.Read);
        if (file is null)
        {
            return null;
        }

        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(file.GetAsText(), SafeJsonDocumentOptions);
        }
        catch (JsonException)
        {
            return null;
        }

        using (document)
        {
            if (!document.RootElement.TryGetProperty("enemy_definitions", out var definitionsNode) || definitionsNode.ValueKind != JsonValueKind.Array)
            {
                return null;
            }

            var definitions = new Dictionary<string, EncounterEnemyDefinition>(StringComparer.Ordinal);
            foreach (var definitionNode in definitionsNode.EnumerateArray())
            {
                if (!TryBuildEncounterEnemyDefinition(definitionNode, out var definition))
                {
                    continue;
                }

                definitions[definition.Id] = definition;
            }

            return definitions;
        }
    }

    private static bool TryBuildEncounterEnemyDefinition(JsonElement definitionNode, out EncounterEnemyDefinition definition)
    {
        definition = default!;
        if (definitionNode.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        if (!definitionNode.TryGetProperty("id", out var idNode) || idNode.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        if (!definitionNode.TryGetProperty("name_key", out var nameKeyNode) || nameKeyNode.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        if (!definitionNode.TryGetProperty("stats", out var statsNode) || statsNode.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        if (!statsNode.TryGetProperty("hp", out var hpNode) || hpNode.ValueKind != JsonValueKind.Number)
        {
            return false;
        }

        var id = idNode.GetString()?.Trim() ?? string.Empty;
        var nameKey = nameKeyNode.GetString()?.Trim() ?? string.Empty;
        var hp = Math.Max(1, hpNode.GetInt32());
        if (id.Length <= 0 || nameKey.Length <= 0)
        {
            return false;
        }

        definition = new EncounterEnemyDefinition(id, nameKey, hp);
        return true;
    }

    private Dictionary<string, List<string>> BuildRuntimeEnemyIntentMappings()
    {
        var mappings = new Dictionary<string, List<string>>(StringComparer.Ordinal);
        foreach (var (runtimeId, state) in _enemyCombatById)
        {
            AddRuntimeEnemyIntentMapping(mappings, runtimeId, runtimeId);
            AddRuntimeEnemyIntentMapping(mappings, runtimeId, state.NameKey);
        }

        var loadedConfig = TryLoadActConfigFromCandidates();
        if (loadedConfig is null)
        {
            return mappings;
        }

        var (config, sourcePath) = loadedConfig.Value;
        if (!TryResolveActiveEncounterId(config, out var encounterId) || string.IsNullOrWhiteSpace(encounterId))
        {
            return mappings;
        }

        var roster = TryResolveEncounterRoster(config, encounterId!);
        if (roster is null || roster.Count <= 0)
        {
            return mappings;
        }

        var definitionsPath = TryResolveEnemyDefinitionsPath(config, sourcePath);
        if (string.IsNullOrWhiteSpace(definitionsPath))
        {
            return mappings;
        }

        var definitions = TryLoadEnemyDefinitions(definitionsPath!);
        if (definitions is null || definitions.Count <= 0)
        {
            return mappings;
        }

        foreach (var entry in roster)
        {
            AddRuntimeEnemyIntentMapping(mappings, entry.RuntimeId, entry.RuntimeId);
            AddRuntimeEnemyIntentMapping(mappings, entry.RuntimeId, entry.EnemyId);
            if (definitions.TryGetValue(entry.EnemyId, out var definition))
            {
                AddRuntimeEnemyIntentMapping(mappings, entry.RuntimeId, definition.NameKey);
            }
        }

        return mappings;
    }

    private static void AddRuntimeEnemyIntentMapping(Dictionary<string, List<string>> mappings, string runtimeId, string mappingKey)
    {
        if (string.IsNullOrWhiteSpace(runtimeId) || string.IsNullOrWhiteSpace(mappingKey))
        {
            return;
        }

        var normalizedKey = mappingKey.Trim();
        if (!mappings.TryGetValue(normalizedKey, out var runtimeIds))
        {
            runtimeIds = new List<string>();
            mappings[normalizedKey] = runtimeIds;
        }

        if (!runtimeIds.Contains(runtimeId, StringComparer.Ordinal))
        {
            runtimeIds.Add(runtimeId);
        }
    }

    private bool TryResolveRuntimeEnemyIntentTargets(
        string enemyKey,
        IReadOnlyDictionary<string, List<string>> rosterMappings,
        out IReadOnlyList<string> runtimeEnemyIds)
    {
        runtimeEnemyIds = Array.Empty<string>();
        var normalizedKey = enemyKey.Trim();
        if (normalizedKey.Length <= 0)
        {
            return false;
        }

        if (rosterMappings.TryGetValue(normalizedKey, out var mappedRuntimeIds) && mappedRuntimeIds.Count > 0)
        {
            runtimeEnemyIds = mappedRuntimeIds;
            return true;
        }

        if (_enemyCombatById.ContainsKey(normalizedKey))
        {
            runtimeEnemyIds = new[] { normalizedKey };
            return true;
        }

        return false;
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
                Name = ResolveUiText(state.NameKey),
                Status = RebuildEnemyStatusSummaryForLocale(enemyId),
            };
        }

        RefreshPrimaryEnemyPanel();
    }

    private void ApplyDefaultM1EnemyIntentIfEmpty()
    {
        if (_enemyIntentPreviewManuallyAppliedForTest)
        {
            RefreshEnemyIntentRows();
            return;
        }

        if (_enemyIntentByEnemy.Count <= 0)
        {
            var generated = TryGenerateEnemyIntentPreviewFromDataDefinitions();
            if (!generated)
            {
                _enemyIntentByEnemy.Clear();
            }
        }

        EnsureFallbackEnemyIntentsForAliveEnemies();
    }

    private void EnsureFallbackEnemyIntentForTest(string enemyId)
    {
        if (_enemyIntentPreviewManuallyAppliedForTest)
        {
            return;
        }

        if (string.IsNullOrWhiteSpace(enemyId))
        {
            return;
        }

        var normalizedEnemyId = enemyId.Trim();
        if (!_enemyCombatById.ContainsKey(normalizedEnemyId))
        {
            return;
        }

        _enemyIntentByEnemy[normalizedEnemyId] = new EnemyIntentState(
            EnemyId: normalizedEnemyId,
            IconId: "icon_sword",
            TextKey: "combat.intent.attack_6",
            Description: ResolveUiText("combat.intent.attack_6"),
            Turn: _enemyIntentTurnIndex);
        RefreshEnemyIntentRows();
    }

    private void EnsureFallbackEnemyIntentsForAliveEnemies()
    {
        if (_enemyIntentPreviewManuallyAppliedForTest)
        {
            return;
        }

        var changed = false;
        foreach (var enemyId in GetAliveEnemyIds())
        {
            if (_enemyIntentByEnemy.ContainsKey(enemyId))
            {
                continue;
            }

            _enemyIntentByEnemy[enemyId] = new EnemyIntentState(
                EnemyId: enemyId,
                IconId: "icon_sword",
                TextKey: "combat.intent.attack_6",
                Description: ResolveUiText("combat.intent.attack_6"),
                Turn: _enemyIntentTurnIndex);
            changed = true;
        }

        if (changed)
        {
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
        var rosterMappings = BuildRuntimeEnemyIntentMappings();

        foreach (var enemy in payload.Enemies)
        {
            if (string.IsNullOrWhiteSpace(enemy.EnemyId) || enemy.Intents is null || enemy.Intents.Count <= 0)
            {
                return false;
            }

            if (!TryResolveRuntimeEnemyIntentTargets(enemy.EnemyId, rosterMappings, out var runtimeEnemyIds))
            {
                continue;
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

            foreach (var runtimeEnemyId in runtimeEnemyIds)
            {
                previews.Add(new EnemyIntentPreviewItemPayload(
                    runtimeEnemyId,
                    selectedIntent.IconId ?? string.Empty,
                    selectedIntent.TextKey ?? string.Empty));
            }
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

        RebuildVisibleHandFan(handCards);
    }

    private void RebuildVisibleHandFan(IReadOnlyList<string> handCards)
    {
        foreach (var child in _handFanLayer.GetChildren())
        {
            _handFanLayer.RemoveChild(child);
            child.QueueFree();
        }

        _handFanCards.Clear();
        _handFanBasePositions.Clear();
        _handFanBaseRotations.Clear();
        _hoveredHandFanIndex = -1;
        _handFanLayer.Visible = handCards.Count > 0;
        if (handCards.Count <= 0)
        {
            return;
        }

        const float cardWidth = 184.0f;
        const float cardHeight = 262.0f;
        const float spacing = 116.0f;
        const float fanArc = 10.0f;
        const float baseY = 6.0f;
        var totalWidth = (handCards.Count - 1) * spacing;
        var centerX = _handFanLayer.Size.X / 2.0f;

        for (var index = 0; index < handCards.Count; index++)
        {
            var visual = CreateHandFanCard(handCards[index], index, cardWidth, cardHeight);
            var normalized = handCards.Count == 1 ? 0.0f : (index / (float)(handCards.Count - 1) * 2.0f - 1.0f);
            var x = centerX - cardWidth / 2.0f + (index * spacing) - totalWidth / 2.0f;
            var y = baseY + MathF.Abs(normalized) * 12.0f;
            var rotation = normalized * fanArc;
            visual.Position = new Vector2(x, y);
            visual.RotationDegrees = rotation;
            visual.SetMeta("hand_index", index);
            visual.PivotOffset = new Vector2(cardWidth / 2.0f, cardHeight * 0.78f);
            _handFanLayer.AddChild(visual);
            _handFanCards.Add(visual);
            _handFanBasePositions.Add(new Vector2(x, y));
            _handFanBaseRotations.Add(rotation);
        }

        RefreshHandFanVisualState();
    }

    private void RefreshMasterDeckButton()
    {
        if (_masterDeckButton is null)
        {
            return;
        }

        var drawCount = _deckState?.DrawPile.Count ?? (TryParseIntLabel(_drawPileValue, out var parsedDraw) ? parsedDraw : 0);
        var discardCount = _deckState?.DiscardPile.Count ?? (TryParseIntLabel(_discardPileValue, out var parsedDiscard) ? parsedDiscard : 0);
        var handCount = _deckState?.Hand.Count ?? _handCards.ItemCount;
        var total = drawCount + discardCount + handCount;
        _masterDeckButton.Text = $"Deck {total}";
    }

    private bool ShowPileViewer(string pileSource)
    {
        _pileViewerSource = NormalizePileSource(pileSource);
        _pileViewerOverlay.Visible = true;
        _pileViewerOverlay.SetAnchorsPreset(LayoutPreset.FullRect);
        _pileViewerOverlay.Size = GetViewportRect().Size;
        _pileViewerOverlay.MouseFilter = MouseFilterEnum.Stop;
        _pileViewerOverlay.FocusMode = FocusModeEnum.All;
        _pileViewerOverlay.GrabFocus();
        _pileViewerTitle.Text = ResolvePileViewerTitle(_pileViewerSource);
        RebuildPileViewerGrid();
        return true;
    }

    private void HidePileViewer()
    {
        _pileViewerOverlay.Visible = false;
        _pileViewerOverlay.ReleaseFocus();
    }

    private void ShowMapOverlay()
    {
        EnsureMapOverlayScene();
        RefreshMapOverlay();
        _mapOverlay.Visible = true;
        _mapOverlay.GrabFocus();
    }

    private void HideMapOverlay()
    {
        _mapOverlay.Visible = false;
        _mapOverlay.ReleaseFocus();
    }

    private void RefreshMapOverlay()
    {
        _mapOverlayTitle.Text = "Map";
        if (_mapOverlayBackButton is not null)
        {
            _mapOverlayBackButton.Text = "Back";
        }

        if (_mapOverlayScene is null)
        {
            return;
        }

        if (_mapOverlayScene.HasMethod("RefreshVisibleTextForTest"))
        {
            _mapOverlayScene.Call("RefreshVisibleTextForTest");
        }
    }

    private void EnsureMapOverlayScene()
    {
        if (_mapOverlayScene is not null && GodotObject.IsInstanceValid(_mapOverlayScene))
        {
            return;
        }

        if (MapOverlayScenePacked is null)
        {
            return;
        }

        if (MapOverlayScenePacked.Instantiate() is not Control mapScene)
        {
            return;
        }

        mapScene.Name = "MapOverlayScene";
        mapScene.MouseFilter = MouseFilterEnum.Ignore;
        mapScene.SetAnchorsPreset(LayoutPreset.FullRect);
        _mapOverlayContent.AddChild(mapScene);
        _mapOverlayScene = mapScene;
        DisableMapOverlayActionButtons(mapScene);
    }

    private static PackedScene? LoadMapOverlayScenePacked()
    {
        return ResourceLoader.Load<PackedScene>("res://Game.Godot/Scenes/Map/Map.tscn");
    }

    private static void DisableMapOverlayActionButtons(Control mapScene)
    {
        var actionRow = mapScene.GetNodeOrNull<Control>("ActionRow");
        if (actionRow is not null)
        {
            actionRow.Visible = false;
        }

        foreach (var nodePath in new[] { "btn_combat", "btn_event", "btn_shop", "btn_rest" })
        {
            if (mapScene.GetNodeOrNull<Button>($"ActionRow/{nodePath}") is { } button)
            {
                button.Disabled = true;
            }
        }

        if (mapScene.GetType().GetMethod("RefreshVisibleTextForTest", BindingFlags.Instance | BindingFlags.Public) is not null)
        {
            mapScene.Call("RefreshVisibleTextForTest");
        }
    }

    private void RebuildPileViewerGrid()
    {
        foreach (var child in _pileViewerGrid.GetChildren())
        {
            _pileViewerGrid.RemoveChild(child);
            child.QueueFree();
        }

        foreach (var cardName in ResolvePileViewerCards())
        {
            _pileViewerGrid.AddChild(CreatePileViewerCard(cardName));
        }
        RefreshMasterDeckButton();
    }

    private IReadOnlyList<string> ResolvePileViewerCards()
    {
        if (_pileViewerSource == "draw")
        {
            return _deckState?.DrawPile.Select(ResolveRuntimeCardLabel).ToList() ?? new List<string>();
        }

        if (_pileViewerSource == "discard")
        {
            return _deckState?.DiscardPile.Select(ResolveRuntimeCardLabel).ToList() ?? new List<string>();
        }

        if (_pileViewerSource == "exhaust")
        {
            if (_deckState is not null && _deckState.ExhaustPile.Count > 0)
            {
                return _deckState.ExhaustPile.Select(ResolveRuntimeCardLabel).ToList();
            }

            return BuildRuntimeExhaustPile(_exhaustPileCount, 0);
        }

        if (_pileViewerSource == "master")
        {
            var cards = new List<string>();
            if (_deckState is not null)
            {
                cards.AddRange(_deckState.Hand.Select(ResolveRuntimeCardLabel));
                cards.AddRange(_deckState.DrawPile.Select(ResolveRuntimeCardLabel));
                cards.AddRange(_deckState.DiscardPile.Select(ResolveRuntimeCardLabel));
            }
            return cards;
        }

        return new List<string>();
    }

    private static List<string> BuildRuntimeExhaustPile(int count, int baseIndex)
    {
        var exhaustPile = new List<string>(Math.Max(0, count));
        for (var index = 0; index < count; index++)
        {
            exhaustPile.Add(DefaultDeckCardNameForIndex(baseIndex + index));
        }

        return exhaustPile;
    }

    private static string NormalizePileSource(string pileSource)
    {
        return pileSource.Trim().ToLowerInvariant() switch
        {
            "draw" => "draw",
            "discard" => "discard",
            "exhaust" => "exhaust",
            _ => "master",
        };
    }

    private static string ResolvePileViewerTitle(string pileSource)
    {
        return pileSource switch
        {
            "draw" => "Draw Pile",
            "discard" => "Discard Pile",
            "exhaust" => "Exhaust Pile",
            _ => "Master Deck",
        };
    }

    private Control CreatePileViewerCard(string cardName)
    {
        var card = new VBoxContainer
        {
            CustomMinimumSize = new Vector2(160.0f, 230.0f),
            SizeFlagsHorizontal = SizeFlags.ShrinkBegin,
            MouseFilter = MouseFilterEnum.Ignore,
        };

        var face = new TextureRect
        {
            Texture = ResolveCardFaceTextureForCardId(cardName),
            ExpandMode = TextureRect.ExpandModeEnum.FitWidthProportional,
            StretchMode = TextureRect.StretchModeEnum.KeepAspectCentered,
            CustomMinimumSize = new Vector2(160.0f, 190.0f),
            MouseFilter = MouseFilterEnum.Ignore,
            SelfModulate = Colors.White,
        };
        card.AddChild(face);

        var title = new Label
        {
            Text = ResolvePileViewerCardTitle(cardName),
            HorizontalAlignment = HorizontalAlignment.Left,
            MouseFilter = MouseFilterEnum.Ignore,
        };
        card.AddChild(title);
        return card;
    }

    private void OnMasterDeckPressed()
    {
        HideMapOverlay();
        ShowPileViewer("master");
    }

    private void OnMapButtonPressed()
    {
        HidePileViewer();
        ShowMapOverlay();
    }

    private void OnPileViewerBackPressed()
    {
        HidePileViewer();
    }

    private void OnMapOverlayBackPressed()
    {
        HideMapOverlay();
    }

    private void OnDrawPileBadgeGuiInput(InputEvent @event)
    {
        if (@event is InputEventMouseButton mouseButton && mouseButton.Pressed && mouseButton.ButtonIndex == MouseButton.Left)
        {
            HideMapOverlay();
            ShowPileViewer("draw");
        }
    }

    private void OnDiscardPileBadgeGuiInput(InputEvent @event)
    {
        if (@event is InputEventMouseButton mouseButton && mouseButton.Pressed && mouseButton.ButtonIndex == MouseButton.Left)
        {
            HideMapOverlay();
            ShowPileViewer("discard");
        }
    }

    private void OnExhaustPileBadgeGuiInput(InputEvent @event)
    {
        if (@event is InputEventMouseButton mouseButton && mouseButton.Pressed && mouseButton.ButtonIndex == MouseButton.Left)
        {
            HideMapOverlay();
            ShowPileViewer("exhaust");
        }
    }

    private Control CreateHandFanCard(string cardName, int handIndex, float cardWidth, float cardHeight)
    {
        var card = new Control
        {
            Name = $"HandFanCard_{handIndex}",
            CustomMinimumSize = new Vector2(cardWidth, cardHeight),
            Size = new Vector2(cardWidth, cardHeight),
            MouseFilter = MouseFilterEnum.Ignore,
        };

        var face = new TextureRect
        {
            Name = "CardFace",
            Texture = ResolveCardFaceTextureForCardId(cardName),
            ExpandMode = TextureRect.ExpandModeEnum.FitWidthProportional,
            StretchMode = TextureRect.StretchModeEnum.KeepAspectCentered,
            CustomMinimumSize = new Vector2(cardWidth, cardHeight),
            Size = new Vector2(cardWidth, cardHeight),
            MouseFilter = MouseFilterEnum.Ignore,
        };
        card.AddChild(face);

        var title = new Label
        {
            Name = "CardTitle",
            Position = new Vector2(28.0f, 20.0f),
            Size = new Vector2(cardWidth - 56.0f, 28.0f),
            HorizontalAlignment = HorizontalAlignment.Center,
            Text = ResolveHandFanCardTitle(cardName),
            MouseFilter = MouseFilterEnum.Ignore,
        };
        card.AddChild(title);

        var cost = new Label
        {
            Name = "CardCost",
            Position = new Vector2(24.0f, 20.0f),
            Size = new Vector2(40.0f, 40.0f),
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
            Text = ResolveHandFanCardCost(cardName),
            MouseFilter = MouseFilterEnum.Ignore,
        };
        card.AddChild(cost);

        var summary = new Label
        {
            Name = "CardSummary",
            Position = new Vector2(26.0f, cardHeight - 86.0f),
            Size = new Vector2(cardWidth - 52.0f, 60.0f),
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
            AutowrapMode = TextServer.AutowrapMode.WordSmart,
            Text = ResolveHandFanCardSummary(cardName),
            MouseFilter = MouseFilterEnum.Ignore,
        };
        card.AddChild(summary);

        return card;
    }

    private string BuildCardButtonText(string cardName)
    {
        if (!TryResolveCardDefinition(cardName, out var definition))
        {
            return ResolveHandCardListDisplayText(cardName);
        }

        var displayName = ResolveCardDisplayName(definition);
        var typeText = string.IsNullOrWhiteSpace(definition.Type) ? "unknown" : definition.Type;
        var effectSummary = ResolveCardEffectSummary(definition);
        return $"{displayName}\nCost {definition.Cost} | {typeText}\n{effectSummary}";
    }

    private string ResolvePileViewerCardTitle(string cardName)
    {
        if (!TryResolveCardDefinition(cardName, out var definition))
        {
            return ResolveHandCardListDisplayText(cardName);
        }

        return ResolveCardDisplayName(definition);
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

    private string ResolveHandFanCardTitle(string cardName)
    {
        return TryResolveCardDefinition(cardName, out var definition)
            ? ResolveCardDisplayName(definition)
            : ResolveHandCardListDisplayText(cardName);
    }

    private string ResolveHandFanCardCost(string cardName)
    {
        return TryResolveCardDefinition(cardName, out var definition)
            ? definition.Cost.ToString(CultureInfo.InvariantCulture)
            : string.Empty;
    }

    private string ResolveHandFanCardSummary(string cardName)
    {
        return TryResolveCardDefinition(cardName, out var definition)
            ? ResolveCardEffectSummary(definition)
            : string.Empty;
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
        if (@event is InputEventAction overlayActionEvent
            && overlayActionEvent.Pressed
            && string.Equals(overlayActionEvent.Action.ToString(), "ui_cancel", StringComparison.Ordinal))
        {
            if (_mapOverlay.Visible)
            {
                HideMapOverlay();
                AcceptEvent();
                return;
            }

            if (_pileViewerOverlay.Visible)
            {
                HidePileViewer();
                AcceptEvent();
                return;
            }
        }

        if (@event.IsActionPressed("ui_cancel"))
        {
            if (_mapOverlay.Visible)
            {
                HideMapOverlay();
                AcceptEvent();
                return;
            }

            if (_pileViewerOverlay.Visible)
            {
                HidePileViewer();
                AcceptEvent();
                return;
            }
        }

        if (@event is InputEventAction actionEvent
            && actionEvent.Pressed
            && string.Equals(actionEvent.Action.ToString(), "ui_cancel", StringComparison.Ordinal))
        {
            if (CancelSelectedCardInteraction())
            {
                AcceptEvent();
            }

            return;
        }

        if (@event.IsActionPressed("ui_cancel"))
        {
            if (CancelSelectedCardInteraction())
            {
                AcceptEvent();
            }

            return;
        }

        if (@event is InputEventMouseButton mouseButton
            && mouseButton.Pressed
            && mouseButton.ButtonIndex == MouseButton.Right
            && CancelSelectedCardInteraction())
        {
            AcceptEvent();
        }
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
        }
        else
        {
            _targetHighlightPulsePhase += (float)delta * 5.0f;
            var pulse = 0.78f + (MathF.Sin(_targetHighlightPulsePhase) * 0.12f + 0.12f);
            _enemyTargetHighlight.Modulate = new Color(1.0f, 1.0f, 1.0f, pulse);
        }

        if (_playerTargetHighlight.Visible)
        {
            var pulse = 0.76f + (MathF.Sin(_targetHighlightPulsePhase) * 0.10f + 0.10f);
            _playerTargetHighlight.Modulate = new Color(1.0f, 1.0f, 1.0f, pulse);
        }
        else
        {
            _playerTargetHighlight.Modulate = Colors.White;
        }
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
        if (CurrentDraggedCardTargetsEnemy())
        {
            _hoveredHandFanIndex = handIndex;
        }
        RefreshDragGhost(handIndex);
        RefreshDragPresentationForCurrentCard(handIndex);
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
        if (CurrentDraggedCardTargetsEnemy() && _draggedHandIndex >= 0)
        {
            _hoveredHandFanIndex = _draggedHandIndex;
        }
        ApplyTargetInspectionForTest(_draggedTargetEnemyId);
        RefreshDragPresentationForCurrentCard(_draggedHandIndex);
        if (!string.IsNullOrWhiteSpace(_draggedTargetEnemyId))
        {
            ApplyHoverPreviewForTest($"drag:{_draggedHandIndex}:{_draggedTargetEnemyId}");
        }
        RefreshEnemyTargetHighlight(_selectedEnemyTargetId);
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
                ? GetHandCardIdAt(_draggedHandIndex)
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
        _dragArrow.Visible = false;
        _dragArrow.ClearPoints();
        _dragCardGhostTitle.Text = string.Empty;
        _dragCardGhostCost.Text = string.Empty;
        _dragCardGhostType.Text = string.Empty;
        _dragCardGhostSummary.Text = string.Empty;
        _dragCardGhostFace.Texture = null;
        _dragCardGhost.Scale = Vector2.One;
        _dragCardGhost.Set("scale", Vector2.One);
        _dragCardGhostBody.Scale = Vector2.One;
        _dragCardGhostBody.Set("scale", Vector2.One);
        _dragCardGhostFace.CustomMinimumSize = _dragCardGhostFaceDefaultMinimumSize;
        _dragGhostVisualScaleForTest = 1.0f;
        _dragCardGhost.RotationDegrees = 0.0f;
        _playerTargetHighlight.Visible = false;
        _playerBattleStagePanel.SelfModulate = Colors.White;
        CloseHoverPreviewForTest();
        HideTargetInspectionForTest();
        RefreshHandFanVisualState();
        if (resetHint)
        {
            UpdateActionHintForCurrentInteraction();
        }
    }

    private bool CancelSelectedCardInteraction()
    {
        var hadInteraction = _isCardDragActive
            || ResolveSelectedHandIndex() >= 0
            || !string.IsNullOrWhiteSpace(_selectedEnemyTargetId);
        if (!hadInteraction)
        {
            return false;
        }

        if (_isCardDragActive)
        {
            ClearDragState(resetHint: false);
        }

        ForceClearHiddenHandSelection();
        _selectedEnemyTargetId = string.Empty;
        _draggedTargetEnemyId = string.Empty;
        _hasPendingInvalidTargetSelection = false;
        CloseHoverPreviewForTest();
        HideTargetInspectionForTest();
        RefreshEnemyTargetHighlight(string.Empty);
        UpdateActionHintForCurrentInteraction();
        return true;
    }

    private void ForceClearHiddenHandSelection()
    {
        _handCards.DeselectAll();
        _handCards.Call("deselect_all");
        for (var index = 0; index < _handCards.ItemCount; index++)
        {
            _handCards.Deselect(index);
            _handCards.Call("deselect", index);
        }

        if (_handCards.GetSelectedItems().Length <= 0)
        {
            return;
        }

        var cards = new List<string>(_handCards.ItemCount);
        for (var index = 0; index < _handCards.ItemCount; index++)
        {
            cards.Add(GetHandCardIdAt(index));
        }

        _handCards.Clear();
        foreach (var cardName in cards)
        {
            AddHandCardItem(cardName);
        }

        _handCards.DeselectAll();
        _handCards.Call("deselect_all");
        for (var index = 0; index < _handCards.ItemCount; index++)
        {
            _handCards.Deselect(index);
            _handCards.Call("deselect", index);
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
        if (_pileViewerOverlay.Visible)
        {
            _wasLeftMousePressed = ResolveRuntimeLeftPressed();
            RefreshRuntimeDebugPanel();
            return;
        }

        var pointerPosition = ResolveRuntimePointerPosition();
        var isLeftPressed = ResolveRuntimeLeftPressed();
        UpdateHoveredHandFan(pointerPosition);

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
            if (CurrentDraggedCardTargetsEnemy())
            {
                var hoveredEnemy = ResolveEnemyTargetIdAtPosition(pointerPosition);
                if (!string.Equals(hoveredEnemy, _draggedTargetEnemyId, StringComparison.Ordinal))
                {
                    HoverEnemyTarget(hoveredEnemy);
                }
            }
            else
            {
                _draggedTargetEnemyId = string.Empty;
                RefreshDragPresentationForCurrentCard(_draggedHandIndex);
            }

            UpdateDragGhostPosition(pointerPosition);
        }

        if (!isLeftPressed && _wasLeftMousePressed && _isCardDragActive)
        {
            if (CurrentDraggedCardTargetsEnemy())
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
            else
            {
                _ = ReleaseDraggedCard();
            }
        }

        RefreshEnemyTargetHighlight(_selectedEnemyTargetId);
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
        var selfTargetActive = _isCardDragActive && CurrentDraggedCardTargetsSelf();
        foreach (var child in _enemyBattleStage.GetChildren())
        {
            if (child is not Control unit || !unit.HasMeta("enemy_id"))
            {
                continue;
            }

            var unitEnemyId = unit.GetMeta("enemy_id").AsString();
            var isHoveredUnit = _isCardDragActive
                && !string.IsNullOrWhiteSpace(_draggedTargetEnemyId)
                && string.Equals(unitEnemyId, _draggedTargetEnemyId, StringComparison.Ordinal)
                && _enemyCombatById.TryGetValue(unitEnemyId, out var hoveredUnitState)
                && hoveredUnitState.CurrentHp > 0;
            var isSelectedUnit = !_isCardDragActive
                && !string.IsNullOrWhiteSpace(preferredId)
                && string.Equals(unitEnemyId, preferredId, StringComparison.Ordinal);
            unit.SelfModulate = Colors.White;
            if (unit.GetNodeOrNull<PanelContainer>("EnemyPortraitFrame") is { } portraitFrame)
            {
                ApplyEnemyPortraitFrameHighlight(portraitFrame, isHoveredUnit, isSelectedUnit);
            }
        }

        foreach (var child in _enemyRosterContainer.GetChildren())
        {
            if (child is not Control card || !card.HasMeta("enemy_id"))
            {
                continue;
            }

            var cardEnemyId = card.GetMeta("enemy_id").AsString();
            var isHoveredCard = _isCardDragActive
                && !string.IsNullOrWhiteSpace(_draggedTargetEnemyId)
                && string.Equals(cardEnemyId, _draggedTargetEnemyId, StringComparison.Ordinal)
                && _enemyCombatById.TryGetValue(cardEnemyId, out var hoveredCardState)
                && hoveredCardState.CurrentHp > 0;
            var isSelectedCard = !_isCardDragActive
                && !string.IsNullOrWhiteSpace(preferredId)
                && string.Equals(cardEnemyId, preferredId, StringComparison.Ordinal);
            card.SelfModulate = isHoveredCard
                ? new Color(1.0f, 0.96f, 0.84f, 1.0f)
                : (isSelectedCard ? new Color(0.97f, 0.98f, 0.92f, 1.0f) : Colors.White);
        }

        _playerTargetHighlight.Visible = selfTargetActive;
        _playerBattleStagePanel.SelfModulate = selfTargetActive
            ? new Color(1.0f, 0.94f, 0.72f, 1.0f)
            : Colors.White;

        if (_isCardDragActive
            && !string.IsNullOrWhiteSpace(_draggedTargetEnemyId)
            && _enemyCombatById.TryGetValue(_draggedTargetEnemyId, out var hoveredState)
            && hoveredState.CurrentHp > 0)
        {
            _enemyPortraitFrame.SelfModulate = Colors.White;
            ApplyEnemyPortraitFrameHighlight(_enemyPortraitFrame, isHovered: true, isSelected: false);
            _enemyTargetHighlight.Visible = true;
            return;
        }

        _enemyPortraitFrame.SelfModulate = Colors.White;
        ApplyEnemyPortraitFrameHighlight(_enemyPortraitFrame, isHovered: false, isSelected: false);
        _enemyTargetHighlight.Visible = false;
    }

    private static void ApplyEnemyPortraitFrameHighlight(PanelContainer portraitFrame, bool isHovered, bool isSelected)
    {
        if (portraitFrame.GetThemeStylebox("panel") is not StyleBoxFlat existingStyle)
        {
            return;
        }

        var style = existingStyle.Duplicate() as StyleBoxFlat;
        if (style is null)
        {
            return;
        }

        style.BgColor = new Color(style.BgColor, 0.0f);
        if (isHovered)
        {
            style.BorderWidthLeft = 4;
            style.BorderWidthTop = 4;
            style.BorderWidthRight = 4;
            style.BorderWidthBottom = 4;
            style.BorderColor = new Color(1.0f, 0.9f, 0.45f, 0.96f);
            style.ShadowColor = new Color(1.0f, 0.85f, 0.26f, 0.24f);
            style.ShadowSize = 14;
        }
        else if (isSelected)
        {
            style.BorderWidthLeft = 2;
            style.BorderWidthTop = 2;
            style.BorderWidthRight = 2;
            style.BorderWidthBottom = 2;
            style.BorderColor = new Color(0.88f, 0.94f, 0.78f, 0.88f);
            style.ShadowColor = new Color(0.78f, 0.88f, 0.66f, 0.16f);
            style.ShadowSize = 8;
        }
        else
        {
            style.BorderWidthLeft = 0;
            style.BorderWidthTop = 0;
            style.BorderWidthRight = 0;
            style.BorderWidthBottom = 0;
            style.BorderColor = new Color(0.0f, 0.0f, 0.0f, 0.0f);
            style.ShadowColor = new Color(0.0f, 0.0f, 0.0f, 0.0f);
            style.ShadowSize = 0;
        }

        portraitFrame.AddThemeStyleboxOverride("panel", style);
    }

    private void RefreshDragGhost(int handIndex)
    {
        if (handIndex < 0 || handIndex >= _handCards.ItemCount)
        {
            _dragCardGhostFace.Texture = null;
            _dragCardGhostTitle.Text = string.Empty;
            _dragCardGhostCost.Text = string.Empty;
            _dragCardGhostType.Text = string.Empty;
            _dragCardGhostSummary.Text = string.Empty;
            return;
        }

        var cardName = GetHandCardIdAt(handIndex);
        _dragCardGhostFace.Texture = ResolveCardFaceTextureForCardId(cardName);
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

    private void RefreshDragPresentationForCurrentCard(int handIndex)
    {
        var targetsEnemy = CardTargetsEnemy(handIndex);
        _dragCardGhost.Visible = !targetsEnemy;
        _dragArrow.Visible = targetsEnemy;
        var ghostScale = targetsEnemy ? Vector2.One : new Vector2(1.3f, 1.3f);
        _dragGhostVisualScaleForTest = ghostScale.X;
        _dragCardGhost.Scale = Vector2.One;
        _dragCardGhost.Set("scale", Vector2.One);
        _dragCardGhostBody.Scale = Vector2.One;
        _dragCardGhostBody.Set("scale", Vector2.One);
        _dragCardGhostFace.CustomMinimumSize = targetsEnemy
            ? _dragCardGhostFaceDefaultMinimumSize
            : _dragCardGhostFaceDefaultMinimumSize * ghostScale;
        _dragCardGhost.RotationDegrees = 0.0f;
        _dragCardGhost.QueueSort();
        _dragCardGhost.ResetSize();
        if (!targetsEnemy)
        {
            _dragArrow.ClearPoints();
        }

        RefreshHandFanVisualState();
    }

    private void UpdateDragGhostPosition(Vector2 pointerPosition)
    {
        if (_dragCardGhost.Visible)
        {
            var ghostSize = ResolveVisibleDragGhostSize();
            _dragCardGhost.GlobalPosition = pointerPosition - (ghostSize * 0.5f);
        }

        if (!_dragArrow.Visible)
        {
            return;
        }

        _dragArrow.ClearPoints();
        var from = GetHandCardPointerForTest(Math.Clamp(_draggedHandIndex, 0, Math.Max(0, _handCards.ItemCount - 1)));
        var to = pointerPosition;
        var mid = from.Lerp(to, 0.55f) + new Vector2(0.0f, -48.0f);
        _dragArrow.AddPoint(from);
        _dragArrow.AddPoint(mid);
        _dragArrow.AddPoint(to);
    }

    private Vector2 ResolveVisibleDragGhostSize()
    {
        var minimumSize = _dragCardGhost.GetCombinedMinimumSize();
        if (minimumSize.X > 0.0f && minimumSize.Y > 0.0f)
        {
            _dragCardGhost.Size = minimumSize;
            return minimumSize;
        }

        var currentSize = _dragCardGhost.Size;
        if (currentSize.X > 0.0f && currentSize.Y > 0.0f)
        {
            return currentSize;
        }

        return _dragCardGhostFace.CustomMinimumSize;
    }

    private int ResolveHandIndexAtPosition(Vector2 position)
    {
        for (var index = _handFanCards.Count - 1; index >= 0; index--)
        {
            var card = _handFanCards[index];
            if (card.GetGlobalRect().HasPoint(position))
            {
                return index;
            }
        }

        if (!_handCards.Visible || !_handCards.GetGlobalRect().HasPoint(position))
        {
            return -1;
        }

        var local = position - _handCards.GlobalPosition;
        return _handCards.GetItemAtPosition(local, true);
    }

    private void UpdateHoveredHandFan(Vector2 pointerPosition)
    {
        if (_isCardDragActive && CurrentDraggedCardTargetsEnemy() && _draggedHandIndex >= 0)
        {
            if (_hoveredHandFanIndex != _draggedHandIndex)
            {
                _hoveredHandFanIndex = _draggedHandIndex;
                RefreshHandFanVisualState();
            }

            return;
        }

        var hovered = -1;
        for (var index = _handFanCards.Count - 1; index >= 0; index--)
        {
            if (_handFanCards[index].GetGlobalRect().HasPoint(pointerPosition))
            {
                hovered = index;
                break;
            }
        }

        if (_hoveredHandFanIndex == hovered)
        {
            return;
        }

        _hoveredHandFanIndex = hovered;
        RefreshHandFanVisualState();
    }

    private void RefreshHandFanVisualState()
    {
        for (var index = 0; index < _handFanCards.Count; index++)
        {
            var card = _handFanCards[index];
            var basePosition = index < _handFanBasePositions.Count ? _handFanBasePositions[index] : card.Position;
            var baseRotation = index < _handFanBaseRotations.Count ? _handFanBaseRotations[index] : card.RotationDegrees;
            var scale = Vector2.One;
            var zIndex = index;
            var offset = Vector2.Zero;
            var isDraggedEnemyCard = _isCardDragActive
                && CurrentDraggedCardTargetsEnemy()
                && index == _draggedHandIndex;

            if (isDraggedEnemyCard || index == _hoveredHandFanIndex)
            {
                scale = new Vector2(1.16f, 1.16f);
                offset = new Vector2(0.0f, -56.0f);
                zIndex = 200;
            }
            else if (_hoveredHandFanIndex >= 0 && Math.Abs(index - _hoveredHandFanIndex) == 1)
            {
                offset = new Vector2(index < _hoveredHandFanIndex ? -24.0f : 24.0f, -12.0f);
                zIndex = 120;
            }

            card.Scale = scale;
            card.Set("scale", scale);
            card.ZIndex = zIndex;
            card.Position = basePosition + offset;
            card.RotationDegrees = baseRotation;
        }
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

        var battleStageUnit = FindEnemyBattleStageUnit(enemyId);
        if (battleStageUnit?.GetNodeOrNull<Control>("EnemyPortraitFrame") is { } portraitFrame
            && portraitFrame.GetGlobalRect().HasPoint(position))
        {
            return true;
        }

        return false;
    }

    private static bool TryResolveStartEncounterId(ActConfig config, out string? encounterId)
    {
        encounterId = null;
        if (config.NodeGraph.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        if (!config.NodeGraph.TryGetProperty("start_node_id", out var startNodeIdNode) || startNodeIdNode.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        var startNodeId = startNodeIdNode.GetString()?.Trim();
        if (string.IsNullOrWhiteSpace(startNodeId))
        {
            return false;
        }

        if (!config.NodeGraph.TryGetProperty("nodes", out var nodesNode) || nodesNode.ValueKind != JsonValueKind.Array)
        {
            return false;
        }

        foreach (var node in nodesNode.EnumerateArray())
        {
            if (node.ValueKind != JsonValueKind.Object)
            {
                continue;
            }

            if (!node.TryGetProperty("id", out var idNode) || idNode.ValueKind != JsonValueKind.String)
            {
                continue;
            }

            if (!string.Equals(idNode.GetString()?.Trim(), startNodeId, StringComparison.Ordinal))
            {
                continue;
            }

            if (!node.TryGetProperty("encounter_id", out var encounterIdNode) || encounterIdNode.ValueKind != JsonValueKind.String)
            {
                return false;
            }

            encounterId = encounterIdNode.GetString()?.Trim();
            return !string.IsNullOrWhiteSpace(encounterId);
        }

        return false;
    }

    private string? ResolveSelectedMapNodeIdFromMain()
    {
        var main = GetNodeOrNull<Node>("/root/Main");
        if (main is null || !main.HasMethod("GetMapRouteLastSelectedNodeIdForTest"))
        {
            return null;
        }

        var selected = main.Call("GetMapRouteLastSelectedNodeIdForTest");
        if (selected.VariantType != Variant.Type.String)
        {
            return null;
        }

        var nodeId = selected.AsString().Trim();
        return string.IsNullOrWhiteSpace(nodeId) ? null : nodeId;
    }

    private bool CurrentDraggedCardTargetsEnemy()
    {
        return CardTargetsEnemy(_draggedHandIndex);
    }

    private bool CurrentDraggedCardTargetsSelf()
    {
        return CardTargetsSelf(_draggedHandIndex);
    }

    private bool CardTargetsEnemy(int handIndex)
    {
        return ResolveDraggedCardTarget(handIndex) == "enemy";
    }

    private bool CardTargetsSelf(int handIndex)
    {
        return ResolveDraggedCardTarget(handIndex) == "self";
    }

    private string ResolveDraggedCardTarget(int handIndex)
    {
        if (handIndex < 0 || handIndex >= _handCards.ItemCount)
        {
            return string.Empty;
        }

        var cardName = GetHandCardIdAt(handIndex);
        if (TryResolveCardDefinition(cardName, out var definition))
        {
            return definition.Target.Trim().ToLowerInvariant();
        }

        return "enemy";
    }

    private void SyncRuntimeDeckState(IReadOnlyList<string> visibleHandCards, int drawPileCount, int discardPileCount)
    {
        if (_deckState is not null
            && _deckState.DrawPile.Count == drawPileCount
            && _deckState.DiscardPile.Count == discardPileCount
            && _deckState.Hand.Count == visibleHandCards.Count
            && _deckState.Hand.Select(ResolveRuntimeCardLabel).SequenceEqual(visibleHandCards))
        {
            return;
        }

        var hand = visibleHandCards
            .Select(CreateRuntimeCardInstanceId)
            .ToList();
        var drawPile = new List<string>(Math.Max(0, drawPileCount));
        for (var index = 0; index < drawPileCount; index++)
        {
            drawPile.Add(CreateRuntimeCardInstanceId(DefaultDeckCardNameForIndex(index)));
        }

        var discardPile = new List<string>(Math.Max(0, discardPileCount));
        for (var index = 0; index < discardPileCount; index++)
        {
            discardPile.Add(CreateRuntimeCardInstanceId(DefaultDeckCardNameForIndex(index + drawPileCount)));
        }

        _deckState = new DeckState(
            DrawPile: drawPile,
            Hand: hand,
            DiscardPile: discardPile,
            ExhaustPile: Array.Empty<string>(),
            RetainedInstanceIds: new HashSet<string>(StringComparer.Ordinal),
            HandLimit: DefaultHandLimit);
    }

    private DeckState ResolveNextDeckStateAfterEndTurn(IReadOnlyList<string> visibleHandCards)
    {
        if (_deckState is null)
        {
            SyncRuntimeDeckState(
                visibleHandCards,
                TryParseIntLabel(_drawPileValue, out var drawPile) ? drawPile : 0,
                TryParseIntLabel(_discardPileValue, out var discardPile) ? discardPile : 0);
        }

        var currentState = _deckState!;
        var endState = _deckService.EndOfTurn(currentState);
        return _deckService.Draw(endState, DefaultDrawCountPerTurn);
    }

    private string ResolveRuntimeCardLabel(string instanceId)
    {
        if (string.IsNullOrWhiteSpace(instanceId))
        {
            return string.Empty;
        }

        var separator = instanceId.IndexOf('#', StringComparison.Ordinal);
        return separator > 0 ? instanceId[..separator] : instanceId;
    }

    private void AddHandCardItem(string cardId)
    {
        var normalizedCardId = string.IsNullOrWhiteSpace(cardId) ? string.Empty : cardId.Trim();
        var displayText = ResolveHandCardListDisplayText(normalizedCardId);
        _handCards.AddItem(displayText);
        _handCards.SetItemMetadata(_handCards.ItemCount - 1, normalizedCardId);
    }

    private string GetHandCardIdAt(int index)
    {
        if (index < 0 || index >= _handCards.ItemCount)
        {
            return string.Empty;
        }

        var metadata = _handCards.GetItemMetadata(index);
        if (metadata.VariantType == Variant.Type.String)
        {
            var canonical = metadata.AsString().Trim();
            if (!string.IsNullOrWhiteSpace(canonical))
            {
                return canonical;
            }
        }

        return _handCards.GetItemText(index);
    }

    private string ResolveHandCardListDisplayText(string cardId)
    {
        if (string.IsNullOrWhiteSpace(cardId))
        {
            return string.Empty;
        }

        if (TryResolveCardDefinition(cardId, out var definition))
        {
            return ResolveCardDisplayName(definition);
        }

        var fallbackKey = $"{cardId.Trim()}.name";
        var localized = ResolveFeedbackTemplate(fallbackKey);
        if (!string.Equals(localized, fallbackKey, StringComparison.Ordinal))
        {
            return localized;
        }

        var lastDot = cardId.LastIndexOf('.');
        return lastDot >= 0 && lastDot < cardId.Length - 1
            ? cardId[(lastDot + 1)..]
            : cardId.Trim();
    }

    private string CreateRuntimeCardInstanceId(string cardName)
    {
        var normalized = string.IsNullOrWhiteSpace(cardName) ? "Card" : cardName.Trim();
        _runtimeDeckInstanceCounter += 1;
        return $"{normalized}#{_runtimeDeckInstanceCounter}";
    }

    private static string DefaultDeckCardNameForIndex(int index)
    {
        var starterDeck = TryLoadStartingDeckCardIdsFromData();
        if (starterDeck.Count <= 0)
        {
            return index % 2 == 0 ? "Strike" : "Defend";
        }

        var normalizedIndex = Math.Abs(index) % starterDeck.Count;
        return starterDeck[normalizedIndex];
    }

    private static List<string> TryLoadStartingDeckCardIdsFromData()
    {
        foreach (var path in StartingDeckCandidatePaths)
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
                if (!document.RootElement.TryGetProperty("cards", out var cardsNode) || cardsNode.ValueKind != JsonValueKind.Array)
                {
                    continue;
                }

                var starterDeck = new List<string>();
                foreach (var cardNode in cardsNode.EnumerateArray())
                {
                    if (!cardNode.TryGetProperty("card_id", out var cardIdNode) || cardIdNode.ValueKind != JsonValueKind.String)
                    {
                        continue;
                    }

                    var cardId = cardIdNode.GetString()?.Trim() ?? string.Empty;
                    if (string.IsNullOrWhiteSpace(cardId))
                    {
                        continue;
                    }

                    var count = cardNode.TryGetProperty("count", out var countNode) && countNode.ValueKind == JsonValueKind.Number
                        ? Math.Max(0, countNode.GetInt32())
                        : 1;
                    for (var i = 0; i < count; i++)
                    {
                        starterDeck.Add(cardId);
                    }
                }

                if (starterDeck.Count > 0)
                {
                    return starterDeck;
                }
            }
        }

        return new List<string>();
    }

    private string ResolveEnemyDisplayName(string runtimeOrDefinitionId)
    {
        return ResolveUiText(ResolveEnemyNameKey(runtimeOrDefinitionId));
    }

    private string ResolveEnemyNameKey(string runtimeOrDefinitionId)
    {
        var normalized = runtimeOrDefinitionId?.Trim() ?? string.Empty;
        if (normalized.Length <= 0)
        {
            return "enemy.act1.slime_scout.name";
        }

        if (TryResolveEnemyDefinitionByRuntimeOrDefinitionId(normalized, out var definition))
        {
            return definition.NameKey;
        }

        return "enemy.act1.slime_scout.name";
    }

    private bool TryResolveEnemyDefinitionByRuntimeOrDefinitionId(string runtimeOrDefinitionId, out EncounterEnemyDefinition definition)
    {
        definition = default!;
        var loadedConfig = TryLoadActConfigFromCandidates();
        if (loadedConfig is null)
        {
            return false;
        }

        var (config, sourcePath) = loadedConfig.Value;
        var definitionsPath = TryResolveEnemyDefinitionsPath(config, sourcePath);
        if (string.IsNullOrWhiteSpace(definitionsPath))
        {
            return false;
        }

        var definitions = TryLoadEnemyDefinitions(definitionsPath!);
        if (definitions is null || definitions.Count <= 0)
        {
            return false;
        }

        if (definitions.TryGetValue(runtimeOrDefinitionId, out var directDefinition) && directDefinition is not null)
        {
            definition = directDefinition;
            return true;
        }

        if (TryResolveActiveEncounterId(config, out var encounterId) && !string.IsNullOrWhiteSpace(encounterId))
        {
            var roster = TryResolveEncounterRoster(config, encounterId!);
            if (roster is not null)
            {
                foreach (var entry in roster)
                {
                    if (!string.Equals(entry.RuntimeId, runtimeOrDefinitionId, StringComparison.Ordinal))
                    {
                        continue;
                    }

                    if (definitions.TryGetValue(entry.EnemyId, out var mappedDefinition) && mappedDefinition is not null)
                    {
                        definition = mappedDefinition;
                        return true;
                    }

                    return false;
                }
            }
        }

        return false;
    }

    private string RebuildEnemyStatusSummaryForLocale(string enemyId)
    {
        if (!_enemyStatusStacksByEnemy.TryGetValue(enemyId, out var statusMap) || statusMap.Count <= 0)
        {
            return ResolveUiText("combat.enemy.status.none");
        }

        return BuildStatusSummary(statusMap);
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

    private Texture2D ResolvePlayerPortraitTexture()
    {
        if (_playerPortraitTexture is not null)
        {
            return _playerPortraitTexture;
        }

        foreach (var path in BuildPlayerPortraitTextureCandidates(DefaultPlayerPortraitId))
        {
            if (ResourceLoader.Exists(path) && ResourceLoader.Load(path) is Texture2D texture)
            {
                _playerPortraitTexture = texture;
                return texture;
            }

            var rawTexture = TryLoadRawTexture(path);
            if (rawTexture is not null)
            {
                _playerPortraitTexture = rawTexture;
                return rawTexture;
            }
        }

        _playerPortraitTexture = EnsureEnemyPortraitFallbackTexture();
        return _playerPortraitTexture;
    }

    private Texture2D ResolveCardFaceTexture()
    {
        return ResolveCardFaceTextureForCardId(string.Empty);
    }

    private Texture2D ResolveCardFaceTextureForCardId(string cardId)
    {
        var key = string.IsNullOrWhiteSpace(cardId) ? "__default__" : NormalizeCardLookupKey(cardId);
        if (_cardFaceTextureCache.TryGetValue(key, out var cachedTexture))
        {
            return cachedTexture;
        }

        foreach (var path in BuildCardFaceTextureCandidates(cardId))
        {
            if (ResourceLoader.Exists(path) && ResourceLoader.Load(path) is Texture2D texture)
            {
                _cardFaceTextureCache[key] = texture;
                return texture;
            }

            var rawTexture = TryLoadRawTexture(path);
            if (rawTexture is not null)
            {
                _cardFaceTextureCache[key] = rawTexture;
                return rawTexture;
            }
        }

        var fallback = EnsureEnemyPortraitFallbackTexture();
        _cardFaceTextureCache[key] = fallback;
        return fallback;
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
        if (string.Equals(enemyId, DefaultEnemySupportId, StringComparison.Ordinal))
        {
            yield return "res://Game.Godot/Assets/Textures/Combat/Enemies/enemy_m1_slime_b.png";
        }
        if (string.Equals(enemyId, "act1-slime-scout-b", StringComparison.Ordinal))
        {
            yield return "res://Game.Godot/Assets/Textures/Combat/Enemies/enemy_m1_slime_b.png";
        }
        yield return $"res://Game.Godot/Assets/Textures/Combat/Enemies/{enemyId}.png";
        yield return $"res://Game.Godot/Assets/Textures/Combat/Enemies/enemy_fungal_knight_target.png";
        yield return $"res://logs/aiart/t74-enemy-target-2026-05-13/processed/clean.png";
    }

    private static IEnumerable<string> BuildPlayerPortraitTextureCandidates(string portraitId)
    {
        if (string.IsNullOrWhiteSpace(portraitId))
        {
            yield break;
        }

        yield return $"res://Game.Godot/Assets/Textures/Combat/Player/{portraitId}.png";
        yield return $"res://logs/aiart/combat-player-2026-05-17/player_fungal_knight_raw.png";
    }

    private static IEnumerable<string> BuildCardFaceTextureCandidates(string cardId)
    {
        if (!string.IsNullOrWhiteSpace(cardId))
        {
            var normalized = cardId.Trim();
            yield return $"res://Game.Godot/Assets/Textures/Cards/{normalized}.png";
            yield return $"res://Game.Godot/Assets/Textures/Cards/{normalized}_raw.png";
            yield return $"res://Game.Godot/Assets/Textures/Cards/card_reward_{normalized[(normalized.LastIndexOf('.') + 1)..]}.png";
        }
        yield return "res://Game.Godot/Assets/Textures/Cards/card_spore_slash.png";
        yield return "res://logs/aiart/combat-card-2026-05-17/slay_card_face_raw.png";
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
        var portraitState = _enemyBattleStage.GetChildCount() > 0 ? "ok" : "missing";
        _debugPortraitStatusLabel.Text = $"portrait: {portraitState} | path: {_lastResolvedEnemyPortraitPath}";
        _debugDragStateLabel.Text = $"drag: active={_isCardDragActive} hand={_draggedHandIndex} target={_draggedTargetEnemyId}";
        var mouse = ResolveRuntimePointerPosition();
        var pointerSource = _runtimePointerStateOverrideEnabled ? "override" : "live";
        var hoveredHandIndex = ResolveHandIndexAtPosition(mouse);
        var hoveredEnemyId = ResolveEnemyTargetIdAtPosition(mouse);
        _debugMouseStateLabel.Text = $"mouse: {mouse.X:0.0}, {mouse.Y:0.0} left={ResolveRuntimeLeftPressed()} src={pointerSource} hand={hoveredHandIndex} enemy={hoveredEnemyId}";
        var aliveIds = string.Join(",", GetAliveEnemyIds());
        var liveHandCount = _deckState?.Hand.Count ?? _handCards.ItemCount;
        var liveDrawCount = _deckState?.DrawPile.Count ?? (TryParseIntLabel(_drawPileValue, out var parsedDraw) ? parsedDraw : -1);
        var liveDiscardCount = _deckState?.DiscardPile.Count ?? (TryParseIntLabel(_discardPileValue, out var parsedDiscard) ? parsedDiscard : -1);
        _debugCombatRuntimeLabel.Text =
            $"runtime: alive=[{aliveIds}] stage={_enemyBattleStage.GetChildCount()} intents={_enemyIntentByEnemy.Count} incoming={TryResolveIncomingEnemyDamageFromIntent()} selected={_selectedEnemyTargetId} hand={liveHandCount} draw={liveDrawCount} discard={liveDiscardCount} exhaust={_exhaustPileCount} pileViewer={_pileViewerOverlay.Visible}";
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
        List<string>? RelicIds = null,
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
        int MaxHp = 32,
        string NameKey = "enemy.act1.slime_scout.name"
    );

    private sealed record EncounterEnemyDefinition(
        string Id,
        string NameKey,
        int Hp
    );

    private sealed record EncounterRosterEntry(
        string RuntimeId,
        string EnemyId
    );

    private sealed record CombatFloatFxState(
        Label Label,
        string Descriptor
    );

    private sealed record SfxToneProfile(
        float FrequencyHz,
        float DurationSeconds,
        float VolumeLinear
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
