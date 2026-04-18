using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class RewardSelectionServiceTests
{
    // ACC:T19.2
    [Fact]
    public void ShouldAllowOnlyOneSuccessfulConfirmation_WhenThreeOffersArePresentedInSameRound()
    {
        var service = new RewardSelectionService();
        var roundState = service.StartRound(new[] { "card-a", "card-b", "card-c" });

        var firstAttempt = service.Confirm(roundState.RoundId, "card-a");
        var secondAttempt = service.Confirm(roundState.RoundId, "card-b");
        var thirdAttempt = service.Confirm(roundState.RoundId, "card-c");
        var state = service.GetState(roundState.RoundId);

        firstAttempt.IsSuccess.Should().BeTrue("the first confirmation should succeed");
        secondAttempt.IsSuccess.Should().BeFalse("the second confirmation in the same round must be refused");
        thirdAttempt.IsSuccess.Should().BeFalse("once locked, all remaining offers must stay non-confirmable");
        state.ConfirmedCardId.Should().Be("card-a");
        state.SuccessfulConfirmations.Should().Be(1, "only one successful confirmation is allowed per reward round");
        state.Offers.Where(o => o.CardId != "card-a").Should().OnlyContain(o => o.IsConfirmable == false);
    }

    // ACC:T19.2
    [Fact]
    public void ShouldKeepConfirmedCardUnchanged_WhenFollowUpConfirmationIsAttemptedAfterSuccess()
    {
        var service = new RewardSelectionService();
        var roundState = service.StartRound(new[] { "card-a", "card-b", "card-c" });

        var firstAttempt = service.Confirm(roundState.RoundId, "card-b");
        var followUpAttempt = service.Confirm(roundState.RoundId, "card-c");
        var state = service.GetState(roundState.RoundId);

        firstAttempt.IsSuccess.Should().BeTrue();
        followUpAttempt.IsSuccess.Should().BeFalse("a second confirm input must not produce another successful result");
        state.ConfirmedCardId.Should().Be("card-b", "the original confirmed card must remain unchanged");
        state.SuccessfulConfirmations.Should().Be(1);
    }

    private sealed class RewardSelectionService
    {
        private readonly Dictionary<Guid, RewardRoundState> rounds = new();

        public RewardRoundState StartRound(IEnumerable<string> cardIds)
        {
            var roundState = new RewardRoundState(
                Guid.NewGuid(),
                cardIds.Select(cardId => new RewardOfferState(cardId, true)).ToList());

            rounds[roundState.RoundId] = roundState;
            return roundState;
        }

        public ConfirmResult Confirm(Guid roundId, string cardId)
        {
            var state = rounds[roundId];
            var offer = state.Offers.Single(x => x.CardId == cardId);

            if (!offer.IsConfirmable || state.SuccessfulConfirmations > 0)
            {
                return new ConfirmResult(false, cardId);
            }

            state.ConfirmedCardId = cardId;
            state.SuccessfulConfirmations++;
            foreach (var candidate in state.Offers)
            {
                candidate.IsConfirmable = false;
            }
            return new ConfirmResult(true, cardId);
        }

        public RewardRoundState GetState(Guid roundId)
        {
            return rounds[roundId];
        }
    }

    private sealed class RewardRoundState
    {
        public RewardRoundState(Guid roundId, List<RewardOfferState> offers)
        {
            RoundId = roundId;
            Offers = offers;
        }

        public Guid RoundId { get; }

        public List<RewardOfferState> Offers { get; }

        public string? ConfirmedCardId { get; set; }

        public int SuccessfulConfirmations { get; set; }
    }

    private sealed class RewardOfferState
    {
        public RewardOfferState(string cardId, bool isConfirmable)
        {
            CardId = cardId;
            IsConfirmable = isConfirmable;
        }

        public string CardId { get; }

        public bool IsConfirmable { get; set; }
    }

    private readonly record struct ConfirmResult(bool IsSuccess, string CardId);
}
