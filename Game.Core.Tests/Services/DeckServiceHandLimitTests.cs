using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class DeckServiceHandLimitTests
{
    // ACC:T33.9
    [Fact]
    public void ShouldPreserveDrawAndDiscardOrder_WhenApplyingDrawThenDiscard()
    {
        var sut = CreateSut();
        var initialSnapshot = DeckSnapshot.Create(
            drawPile: new[] { "d-1", "d-2", "d-3" },
            hand: Array.Empty<string>(),
            discardPile: Array.Empty<string>());

        var afterDrawSnapshot = sut.Draw(initialSnapshot, 2);
        var finalSnapshot = sut.Discard(afterDrawSnapshot, new[] { "d-2" });

        finalSnapshot.Hand.Should().Equal("d-1");
        finalSnapshot.DiscardPile.Should().Equal("d-2");
        finalSnapshot.DrawPile.Should().Equal("d-3");
    }

    // ACC:T33.9
    [Fact]
    public void ShouldRetainFlaggedCardsOnly_WhenProcessingEndOfTurn()
    {
        var sut = CreateSut();
        var initialSnapshot = DeckSnapshot.Create(
            drawPile: Array.Empty<string>(),
            hand: new[] { "h-1", "h-2", "h-3" },
            discardPile: Array.Empty<string>(),
            retainedInstanceIds: new[] { "h-2" },
            handLimit: 10);

        var finalSnapshot = sut.EndOfTurn(initialSnapshot);

        finalSnapshot.Hand.Should().Equal("h-2");
        finalSnapshot.DiscardPile.Should().Equal("h-1", "h-3");
    }

    // ACC:T33.9
    [Fact]
    public void ShouldDiscardOverflowByInstanceId_WhenRetainedCardsExceedHandLimit()
    {
        var sut = CreateSut();
        var initialSnapshot = DeckSnapshot.Create(
            drawPile: Array.Empty<string>(),
            hand: new[] { "c-003", "c-001", "c-002" },
            discardPile: Array.Empty<string>(),
            retainedInstanceIds: new[] { "c-003", "c-001", "c-002" },
            handLimit: 2);

        var finalSnapshot = sut.EndOfTurn(initialSnapshot);

        finalSnapshot.Hand.Should().Equal("c-002", "c-003");
        finalSnapshot.DiscardPile.Should().Equal("c-001");
    }

    // ACC:T33.9
    [Fact]
    public void ShouldDiscardLowestInstanceIds_WhenDrawCausesHandOverflow()
    {
        var sut = CreateSut();
        var initialSnapshot = DeckSnapshot.Create(
            drawPile: new[] { "h-011", "h-012" },
            hand: new[] { "h-001", "h-002", "h-003", "h-004", "h-005", "h-006", "h-007", "h-008", "h-009", "h-010" },
            discardPile: Array.Empty<string>(),
            handLimit: 10);

        var finalSnapshot = sut.Draw(initialSnapshot, 2);

        finalSnapshot.Hand.Should().Equal("h-003", "h-004", "h-005", "h-006", "h-007", "h-008", "h-009", "h-010", "h-011", "h-012");
        finalSnapshot.DiscardPile.Should().Equal("h-001", "h-002");
        finalSnapshot.DrawPile.Should().BeEmpty();
    }

    // ACC:T33.9
    [Fact]
    public void ShouldKeepStateUnchanged_WhenDiscardingUnknownInstanceId()
    {
        var sut = CreateSut();
        var initialSnapshot = DeckSnapshot.Create(
            drawPile: new[] { "d-9" },
            hand: new[] { "h-1", "h-2" },
            discardPile: new[] { "x-1" });

        var finalSnapshot = sut.Discard(initialSnapshot, new[] { "missing-id" });

        finalSnapshot.Hand.Should().Equal("h-1", "h-2");
        finalSnapshot.DiscardPile.Should().Equal("x-1");
        finalSnapshot.DrawPile.Should().Equal("d-9");
    }

    private static IDeckOperationsPort CreateSut()
    {
        return new DeckOperationsPortAdapter(new DeckService());
    }

    private interface IDeckOperationsPort
    {
        DeckSnapshot Draw(DeckSnapshot snapshot, int count);

        DeckSnapshot Discard(DeckSnapshot snapshot, IReadOnlyList<string> cardInstanceIds);

        DeckSnapshot EndOfTurn(DeckSnapshot snapshot);
    }

    private sealed class DeckOperationsPortAdapter : IDeckOperationsPort
    {
        private readonly DeckService _service;

        public DeckOperationsPortAdapter(DeckService service)
        {
            _service = service;
        }

        public DeckSnapshot Draw(DeckSnapshot snapshot, int count)
        {
            var next = _service.Draw(ToState(snapshot), count);
            return FromState(next);
        }

        public DeckSnapshot Discard(DeckSnapshot snapshot, IReadOnlyList<string> cardInstanceIds)
        {
            var next = _service.Discard(ToState(snapshot), cardInstanceIds);
            return FromState(next);
        }

        public DeckSnapshot EndOfTurn(DeckSnapshot snapshot)
        {
            var next = _service.EndOfTurn(ToState(snapshot));
            return FromState(next);
        }

        private static DeckState ToState(DeckSnapshot snapshot)
        {
            return new DeckState(
                DrawPile: snapshot.DrawPile,
                Hand: snapshot.Hand,
                DiscardPile: snapshot.DiscardPile,
                ExhaustPile: Array.Empty<string>(),
                RetainedInstanceIds: snapshot.RetainedInstanceIds,
                HandLimit: snapshot.HandLimit);
        }

        private static DeckSnapshot FromState(DeckState state)
        {
            return DeckSnapshot.Create(
                drawPile: state.DrawPile,
                hand: state.Hand,
                discardPile: state.DiscardPile,
                retainedInstanceIds: state.RetainedInstanceIds,
                handLimit: state.HandLimit);
        }
    }

    private sealed record DeckSnapshot(
        IReadOnlyList<string> DrawPile,
        IReadOnlyList<string> Hand,
        IReadOnlyList<string> DiscardPile,
        IReadOnlySet<string> RetainedInstanceIds,
        int HandLimit)
    {
        public static DeckSnapshot Create(
            IEnumerable<string> drawPile,
            IEnumerable<string> hand,
            IEnumerable<string> discardPile,
            IEnumerable<string>? retainedInstanceIds = null,
            int handLimit = 10)
        {
            return new DeckSnapshot(
                DrawPile: drawPile.ToArray(),
                Hand: hand.ToArray(),
                DiscardPile: discardPile.ToArray(),
                RetainedInstanceIds: new HashSet<string>(retainedInstanceIds ?? Array.Empty<string>(), StringComparer.Ordinal),
                HandLimit: handLimit);
        }
    }
}
