using System.Collections.Generic;
using System.Text.Json;
using Godot;
using Game.Core.Contracts.Combat;

namespace Game.Godot.Scripts.UI;

public partial class CombatScene : Control
{
    [Signal]
    public delegate void TurnActionRequestedEventHandler(string actionName);

    private ItemList _handCards = default!;
    private Label _energyValue = default!;
    private Label _drawPileValue = default!;
    private Label _discardPileValue = default!;
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

    public override void _Ready()
    {
        _handCards = GetNode<ItemList>("HUD/HandCards");
        _energyValue = GetNode<Label>("HUD/EnergyValue");
        _drawPileValue = GetNode<Label>("HUD/DrawPileValue");
        _discardPileValue = GetNode<Label>("HUD/DiscardPileValue");
        _startTurnButton = GetNode<Button>("HUD/TurnControls/StartTurnButton");
        _endTurnButton = GetNode<Button>("HUD/TurnControls/EndTurnButton");
        _turnTitleLabel = GetNode<Label>("HUD/TurnTitleLabel");

        _startTurnButton.Pressed += OnStartTurnPressed;
        _endTurnButton.Pressed += OnEndTurnPressed;
        _startTurnButton.Text = Tr("combat.turn.start");
        _endTurnButton.Text = Tr("combat.turn.end");
        _turnTitleLabel.Text = Tr("combat.turn.title");
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

        if (payload is null || payload.HandCards is null || payload.Energy < 0 || payload.DrawPileCount < 0 || payload.DiscardPileCount < 0)
        {
            return false;
        }

        ApplyCoreSnapshot(new CombatHudSnapshot(payload.HandCards, payload.Energy, payload.DrawPileCount, payload.DiscardPileCount));
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
            { "energy", _energyValue.Text },
            { "draw", _drawPileValue.Text },
            { "discard", _discardPileValue.Text },
        };
    }

    public bool RequestTurnAction(string actionName)
    {
        if (actionName != "start_turn" && actionName != "end_turn")
        {
            return false;
        }

        _dispatchedCommands.Add(actionName);
        EmitSignal(SignalName.TurnActionRequested, actionName);
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
        return Tr(localizationKey);
    }

    public string GetTurnTitleTextForTest()
    {
        return _turnTitleLabel.Text;
    }

    public string GetEndTurnButtonTextForTest()
    {
        return _endTurnButton.Text;
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

        _energyValue.Text = snapshot.Energy.ToString();
        _drawPileValue.Text = snapshot.DrawPileCount.ToString();
        _discardPileValue.Text = snapshot.DiscardPileCount.ToString();
    }

    private sealed record CombatHudSnapshotPayload(
        List<string>? HandCards,
        int Energy,
        int DrawPileCount,
        int DiscardPileCount
    );
}
