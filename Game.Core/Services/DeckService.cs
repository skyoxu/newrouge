using System;
using System.Collections.Generic;
using System.Linq;

namespace Game.Core.Services;

public sealed class DeckService
{
    public DeckState Draw(DeckState snapshot, int count)
    {
        if (count <= 0)
        {
            return snapshot;
        }

        var drawPile = snapshot.DrawPile.ToList();
        var hand = snapshot.Hand.ToList();
        var discardPile = snapshot.DiscardPile.ToList();

        for (var i = 0; i < count; i++)
        {
            if (drawPile.Count == 0)
            {
                if (discardPile.Count == 0)
                {
                    break;
                }

                drawPile = BuildShuffledDrawPile(discardPile);
                discardPile.Clear();
            }

            hand.Add(drawPile[0]);
            drawPile.RemoveAt(0);
        }

        var boundedAfterDraw = ApplyHandLimit(hand, discardPile, snapshot.HandLimit);
        hand = boundedAfterDraw.Hand;
        discardPile = boundedAfterDraw.DiscardPile;

        return snapshot with
        {
            DrawPile = drawPile,
            Hand = hand,
            DiscardPile = discardPile,
        };
    }

    public DeckState Discard(DeckState snapshot, IReadOnlyList<string> cardInstanceIds)
    {
        if (cardInstanceIds.Count == 0)
        {
            return snapshot;
        }

        var hand = snapshot.Hand.ToList();
        var discardPile = snapshot.DiscardPile.ToList();

        foreach (var cardInstanceId in cardInstanceIds)
        {
            var index = hand.FindIndex(card => string.Equals(card, cardInstanceId, StringComparison.Ordinal));
            if (index < 0)
            {
                continue;
            }

            discardPile.Add(hand[index]);
            hand.RemoveAt(index);
        }

        return snapshot with
        {
            Hand = hand,
            DiscardPile = discardPile,
        };
    }

    public DeckState Exhaust(DeckState snapshot, string cardInstanceId)
    {
        if (string.IsNullOrWhiteSpace(cardInstanceId))
        {
            return snapshot;
        }

        var hand = snapshot.Hand.ToList();
        var exhaustPile = snapshot.ExhaustPile.ToList();
        var index = hand.FindIndex(card => string.Equals(card, cardInstanceId, StringComparison.Ordinal));
        if (index < 0)
        {
            return snapshot;
        }

        exhaustPile.Add(hand[index]);
        hand.RemoveAt(index);

        return snapshot with
        {
            Hand = hand,
            ExhaustPile = exhaustPile,
        };
    }

    public DeckState EndOfTurn(DeckState snapshot)
    {
        var retained = new List<string>();
        var discardPile = snapshot.DiscardPile.ToList();

        foreach (var card in snapshot.Hand)
        {
            if (snapshot.RetainedInstanceIds.Contains(card))
            {
                retained.Add(card);
            }
            else
            {
                discardPile.Add(card);
            }
        }

        var boundedAfterRetain = ApplyHandLimit(retained, discardPile, snapshot.HandLimit);
        return snapshot with
        {
            Hand = boundedAfterRetain.Hand,
            DiscardPile = boundedAfterRetain.DiscardPile,
        };
    }

    public DeckState Shuffle(DeckState snapshot)
    {
        return snapshot with
        {
            DrawPile = BuildShuffledDrawPile(snapshot.DrawPile),
        };
    }

    private static List<string> BuildShuffledDrawPile(IEnumerable<string> cards)
    {
        return cards
            .OrderBy(BuildInstanceSortKey)
            .ToList();
    }

    private static (List<string> Hand, List<string> DiscardPile) ApplyHandLimit(
        IReadOnlyList<string> hand,
        List<string> discardPile,
        int handLimit)
    {
        if (hand.Count <= handLimit)
        {
            return (hand.ToList(), discardPile);
        }

        var orderedHand = hand
            .OrderBy(BuildInstanceSortKey)
            .ToList();
        while (orderedHand.Count > handLimit)
        {
            discardPile.Add(orderedHand[0]);
            orderedHand.RemoveAt(0);
        }

        return (orderedHand, discardPile);
    }

    private static (int PrefixOrder, long NumericSuffix, string Lexical) BuildInstanceSortKey(string cardInstanceId)
    {
        if (TryParseTrailingNumber(cardInstanceId, out var number))
        {
            return (0, number, cardInstanceId);
        }

        return (1, 0L, cardInstanceId);
    }

    private static bool TryParseTrailingNumber(string input, out long value)
    {
        value = 0L;
        if (string.IsNullOrWhiteSpace(input))
        {
            return false;
        }

        var end = input.Length - 1;
        while (end >= 0 && char.IsDigit(input[end]))
        {
            end--;
        }

        var start = end + 1;
        if (start >= input.Length)
        {
            return false;
        }

        return long.TryParse(input[start..], out value);
    }
}

public sealed record DeckState(
    IReadOnlyList<string> DrawPile,
    IReadOnlyList<string> Hand,
    IReadOnlyList<string> DiscardPile,
    IReadOnlyList<string> ExhaustPile,
    IReadOnlySet<string> RetainedInstanceIds,
    int HandLimit);
