using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class DeckServiceTests
{
    // ACC:T71.1
    // ACC:T33.4
    [Fact]
    public void ShouldAppendCardsInDrawOrder_WhenDrawingWithoutHandOverflow()
    {
        var sut = CreateSut();
        var initialSnapshot = DeckSnapshot.Create(
            drawPile: new[] { "d-1", "d-2", "d-3" },
            hand: new[] { "h-0" },
            discardPile: new[] { "x-1" });

        var drawnSnapshot = sut.Draw(initialSnapshot, 2);

        drawnSnapshot.Hand.Should().Equal("h-0", "d-1", "d-2");
        drawnSnapshot.DrawPile.Should().Equal("d-3");
        drawnSnapshot.DiscardPile.Should().Equal("x-1");
    }

    // ACC:T71.2
    // ACC:T33.5
    [Fact]
    public void ShouldMoveOnlySpecifiedInstance_WhenDiscardingKnownCard()
    {
        var sut = CreateSut();
        var initialSnapshot = DeckSnapshot.Create(
            drawPile: new[] { "d-9" },
            hand: new[] { "h-1", "h-2", "h-3" },
            discardPile: new[] { "x-1" });

        var discardedSnapshot = sut.Discard(initialSnapshot, new[] { "h-2" });

        discardedSnapshot.Hand.Should().Equal("h-1", "h-3");
        discardedSnapshot.DiscardPile.Should().Equal("x-1", "h-2");
        discardedSnapshot.DrawPile.Should().Equal("d-9");
    }

    // ACC:T71.4
    // ACC:T33.5
    [Fact]
    public void ShouldKeepStateUnchanged_WhenDiscardingUnknownCardInstance()
    {
        var sut = CreateSut();
        var initialSnapshot = DeckSnapshot.Create(
            drawPile: new[] { "d-9" },
            hand: new[] { "h-1", "h-2" },
            discardPile: new[] { "x-1" },
            exhaustPile: new[] { "e-1" },
            retainedInstanceIds: new[] { "h-2" },
            handLimit: 7);

        var discardedSnapshot = sut.Discard(initialSnapshot, new[] { "missing-id" });

        discardedSnapshot.DrawPile.Should().Equal(initialSnapshot.DrawPile);
        discardedSnapshot.Hand.Should().Equal(initialSnapshot.Hand);
        discardedSnapshot.DiscardPile.Should().Equal(initialSnapshot.DiscardPile);
        discardedSnapshot.ExhaustPile.Should().Equal(initialSnapshot.ExhaustPile);
        discardedSnapshot.RetainedInstanceIds.Should().BeEquivalentTo(initialSnapshot.RetainedInstanceIds);
        discardedSnapshot.HandLimit.Should().Be(initialSnapshot.HandLimit);
    }

    // ACC:T71.5
    // ACC:T33.6
    [Fact]
    public void ShouldNeverReturnExhaustedCard_WhenExhaustingThenCyclingDeck()
    {
        var sut = CreateSut();
        var initialSnapshot = DeckSnapshot.Create(
            drawPile: new[] { "d-1", "d-2" },
            hand: new[] { "h-1" },
            discardPile: new[] { "x-1" },
            exhaustPile: new[] { "e-1" });

        var afterExhaustSnapshot = sut.Exhaust(initialSnapshot, "h-1");
        var cycledSnapshot = sut.Draw(sut.Shuffle(afterExhaustSnapshot), 5);

        afterExhaustSnapshot.ExhaustPile.Should().Contain("h-1");
        cycledSnapshot.Hand.Should().NotContain("h-1");
        cycledSnapshot.DrawPile.Should().NotContain("h-1");
        cycledSnapshot.DiscardPile.Should().NotContain("h-1");
    }

    // ACC:T33.7
    [Fact]
    public void ShouldRetainMarkedCardsOnly_WhenEndingTurn()
    {
        var sut = CreateSut();
        var initialSnapshot = DeckSnapshot.Create(
            drawPile: Array.Empty<string>(),
            hand: new[] { "h-1", "h-2", "h-3" },
            discardPile: new[] { "x-1" },
            retainedInstanceIds: new[] { "h-2" },
            handLimit: 10);

        var finalSnapshot = sut.EndOfTurn(initialSnapshot);

        finalSnapshot.Hand.Should().Equal("h-2");
        finalSnapshot.DiscardPile.Should().Equal("x-1", "h-1", "h-3");
    }

    // ACC:T33.8
    [Fact]
    public void ShouldPreserveCardMembershipAndOtherZones_WhenShufflingDrawPile()
    {
        var sut = CreateSut();
        var initialSnapshot = DeckSnapshot.Create(
            drawPile: new[] { "d-1", "d-2", "d-3", "d-4" },
            hand: new[] { "h-1" },
            discardPile: new[] { "x-1", "x-2" },
            exhaustPile: new[] { "e-1" });

        var shuffledSnapshot = sut.Shuffle(initialSnapshot);

        shuffledSnapshot.DrawPile.Should().HaveCount(initialSnapshot.DrawPile.Count);
        shuffledSnapshot.DrawPile.Should().BeEquivalentTo(initialSnapshot.DrawPile);
        shuffledSnapshot.Hand.Should().Equal(initialSnapshot.Hand);
        shuffledSnapshot.DiscardPile.Should().Equal(initialSnapshot.DiscardPile);
        shuffledSnapshot.ExhaustPile.Should().Equal(initialSnapshot.ExhaustPile);
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

    private static IDeckOperationsPort CreateSut()
    {
        return new DeckOperationsPortAdapter(new DeckService());
    }

    private interface IDeckOperationsPort
    {
        DeckSnapshot Draw(DeckSnapshot snapshot, int count);

        DeckSnapshot Discard(DeckSnapshot snapshot, IReadOnlyList<string> cardInstanceIds);

        DeckSnapshot Exhaust(DeckSnapshot snapshot, string cardInstanceId);

        DeckSnapshot EndOfTurn(DeckSnapshot snapshot);

        DeckSnapshot Shuffle(DeckSnapshot snapshot);
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

        public DeckSnapshot Exhaust(DeckSnapshot snapshot, string cardInstanceId)
        {
            var next = _service.Exhaust(ToState(snapshot), cardInstanceId);
            return FromState(next);
        }

        public DeckSnapshot EndOfTurn(DeckSnapshot snapshot)
        {
            var next = _service.EndOfTurn(ToState(snapshot));
            return FromState(next);
        }

        public DeckSnapshot Shuffle(DeckSnapshot snapshot)
        {
            var next = _service.Shuffle(ToState(snapshot));
            return FromState(next);
        }

        private static DeckState ToState(DeckSnapshot snapshot)
        {
            return new DeckState(
                DrawPile: snapshot.DrawPile,
                Hand: snapshot.Hand,
                DiscardPile: snapshot.DiscardPile,
                ExhaustPile: snapshot.ExhaustPile,
                RetainedInstanceIds: snapshot.RetainedInstanceIds,
                HandLimit: snapshot.HandLimit);
        }

        private static DeckSnapshot FromState(DeckState state)
        {
            return DeckSnapshot.Create(
                drawPile: state.DrawPile,
                hand: state.Hand,
                discardPile: state.DiscardPile,
                exhaustPile: state.ExhaustPile,
                retainedInstanceIds: state.RetainedInstanceIds,
                handLimit: state.HandLimit);
        }
    }

    private sealed record DeckSnapshot(
        IReadOnlyList<string> DrawPile,
        IReadOnlyList<string> Hand,
        IReadOnlyList<string> DiscardPile,
        IReadOnlyList<string> ExhaustPile,
        IReadOnlySet<string> RetainedInstanceIds,
        int HandLimit)
    {
        public static DeckSnapshot Create(
            IEnumerable<string> drawPile,
            IEnumerable<string> hand,
            IEnumerable<string> discardPile,
            IEnumerable<string>? exhaustPile = null,
            IEnumerable<string>? retainedInstanceIds = null,
            int handLimit = 10)
        {
            return new DeckSnapshot(
                DrawPile: drawPile.ToArray(),
                Hand: hand.ToArray(),
                DiscardPile: discardPile.ToArray(),
                ExhaustPile: (exhaustPile ?? Array.Empty<string>()).ToArray(),
                RetainedInstanceIds: new HashSet<string>(retainedInstanceIds ?? Array.Empty<string>(), StringComparer.Ordinal),
                HandLimit: handLimit);
        }
    }
}
