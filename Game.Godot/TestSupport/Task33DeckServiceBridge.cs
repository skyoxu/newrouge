using System;
using System.Collections.Generic;
using System.Linq;
using Game.Core.Services;
using Godot;

namespace Game.Godot.TestSupport;

public partial class Task33DeckServiceBridge : Node
{
    private const int DefaultHandLimit = 10;
    private readonly DeckService _service = new();

    public Godot.Collections.Dictionary CreateState(
        Godot.Collections.Array drawIds,
        Godot.Collections.Array handIds,
        Godot.Collections.Array discardIds,
        Godot.Collections.Array exhaustIds,
        Godot.Collections.Array retainIds)
    {
        var state = new DeckState(
            DrawPile: ToStringList(drawIds),
            Hand: ToStringList(handIds),
            DiscardPile: ToStringList(discardIds),
            ExhaustPile: ToStringList(exhaustIds),
            RetainedInstanceIds: new HashSet<string>(ToStringList(retainIds), StringComparer.Ordinal),
            HandLimit: DefaultHandLimit);
        return ToState(state);
    }

    public Godot.Collections.Dictionary Draw(Godot.Collections.Dictionary state, int count)
    {
        var next = _service.Draw(FromState(state), count);
        return ToState(next);
    }

    public Godot.Collections.Dictionary DiscardByIds(Godot.Collections.Dictionary state, Godot.Collections.Array cardIds)
    {
        var next = _service.Discard(FromState(state), ToStringList(cardIds));
        return ToState(next);
    }

    public Godot.Collections.Dictionary ExhaustByIds(Godot.Collections.Dictionary state, Godot.Collections.Array cardIds)
    {
        var snapshot = FromState(state);
        foreach (var cardId in ToStringList(cardIds))
        {
            snapshot = _service.Exhaust(snapshot, cardId);
        }

        return ToState(snapshot);
    }

    public Godot.Collections.Dictionary EndOfTurn(Godot.Collections.Dictionary state)
    {
        var next = _service.EndOfTurn(FromState(state));
        return ToState(next);
    }

    private static DeckState FromState(Godot.Collections.Dictionary state)
    {
        return new DeckState(
            DrawPile: ToStringList((Godot.Collections.Array)state["draw_pile"]),
            Hand: ToStringList((Godot.Collections.Array)state["hand"]),
            DiscardPile: ToStringList((Godot.Collections.Array)state["discard_pile"]),
            ExhaustPile: ToStringList((Godot.Collections.Array)state["exhaust_pile"]),
            RetainedInstanceIds: new HashSet<string>(ToStringList((Godot.Collections.Array)state["retain_ids"]), StringComparer.Ordinal),
            HandLimit: state.ContainsKey("hand_limit") ? (int)state["hand_limit"] : DefaultHandLimit);
    }

    private static Godot.Collections.Dictionary ToState(DeckState state)
    {
        return new Godot.Collections.Dictionary
        {
            { "draw_pile", ToVariantArray(state.DrawPile) },
            { "hand", ToVariantArray(state.Hand) },
            { "discard_pile", ToVariantArray(state.DiscardPile) },
            { "exhaust_pile", ToVariantArray(state.ExhaustPile) },
            { "retain_ids", ToVariantArray(state.RetainedInstanceIds) },
            { "hand_limit", state.HandLimit },
        };
    }

    private static List<string> ToStringList(Godot.Collections.Array values)
    {
        var list = new List<string>(values.Count);
        foreach (var value in values)
        {
            list.Add(value.ToString());
        }

        return list;
    }

    private static Godot.Collections.Array ToVariantArray(IEnumerable<string> ids)
    {
        var array = new Godot.Collections.Array();
        foreach (var id in ids)
        {
            if (int.TryParse(id, out var numeric))
            {
                array.Add(numeric);
            }
            else
            {
                array.Add(id);
            }
        }

        return array;
    }
}
