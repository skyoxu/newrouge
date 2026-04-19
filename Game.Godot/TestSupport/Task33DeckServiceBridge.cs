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

    public global::Godot.Collections.Dictionary CreateState(
        global::Godot.Collections.Array drawIds,
        global::Godot.Collections.Array handIds,
        global::Godot.Collections.Array discardIds,
        global::Godot.Collections.Array exhaustIds,
        global::Godot.Collections.Array retainIds)
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

    public global::Godot.Collections.Dictionary Draw(global::Godot.Collections.Dictionary state, int count)
    {
        var next = _service.Draw(FromState(state), count);
        return ToState(next);
    }

    public global::Godot.Collections.Dictionary DiscardByIds(
        global::Godot.Collections.Dictionary state,
        global::Godot.Collections.Array cardIds)
    {
        var next = _service.Discard(FromState(state), ToStringList(cardIds));
        return ToState(next);
    }

    public global::Godot.Collections.Dictionary ExhaustByIds(
        global::Godot.Collections.Dictionary state,
        global::Godot.Collections.Array cardIds)
    {
        var snapshot = FromState(state);
        foreach (var cardId in ToStringList(cardIds))
        {
            snapshot = _service.Exhaust(snapshot, cardId);
        }

        return ToState(snapshot);
    }

    public global::Godot.Collections.Dictionary EndOfTurn(global::Godot.Collections.Dictionary state)
    {
        var next = _service.EndOfTurn(FromState(state));
        return ToState(next);
    }

    private static DeckState FromState(global::Godot.Collections.Dictionary state)
    {
        return new DeckState(
            DrawPile: ToStringList((global::Godot.Collections.Array)state["draw_pile"]),
            Hand: ToStringList((global::Godot.Collections.Array)state["hand"]),
            DiscardPile: ToStringList((global::Godot.Collections.Array)state["discard_pile"]),
            ExhaustPile: ToStringList((global::Godot.Collections.Array)state["exhaust_pile"]),
            RetainedInstanceIds: new HashSet<string>(
                ToStringList((global::Godot.Collections.Array)state["retain_ids"]),
                StringComparer.Ordinal),
            HandLimit: state.ContainsKey("hand_limit") ? (int)state["hand_limit"] : DefaultHandLimit);
    }

    private static global::Godot.Collections.Dictionary ToState(DeckState state)
    {
        return new global::Godot.Collections.Dictionary
        {
            { "draw_pile", ToVariantArray(state.DrawPile) },
            { "hand", ToVariantArray(state.Hand) },
            { "discard_pile", ToVariantArray(state.DiscardPile) },
            { "exhaust_pile", ToVariantArray(state.ExhaustPile) },
            { "retain_ids", ToVariantArray(state.RetainedInstanceIds) },
            { "hand_limit", state.HandLimit },
        };
    }

    private static List<string> ToStringList(global::Godot.Collections.Array values)
    {
        var list = new List<string>(values.Count);
        foreach (var value in values)
        {
            list.Add(value.ToString());
        }

        return list;
    }

    private static global::Godot.Collections.Array ToVariantArray(IEnumerable<string> ids)
    {
        var array = new global::Godot.Collections.Array();
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
