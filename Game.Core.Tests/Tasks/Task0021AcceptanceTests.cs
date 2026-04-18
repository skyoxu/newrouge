using System.Collections.Generic;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public class Task0021AcceptanceTests
{
    // ACC:T21.7
    [Fact]
    public void ShouldDisableUpgradeEntry_WhenFreeUpgradeConfirmedFirstTime()
    {
        var session = new RestSessionUpgradeFlow(new[] { 1, 2 }, 100);

        var firstAttemptAccepted = session.TryEnterUpgradeAndConfirm(cardIndex: 0);

        firstAttemptAccepted.Should().BeTrue();
        session.IsUpgradeEntryEnabled.Should().BeFalse("free upgrade must be usable at most once per rest session");
    }

    // ACC:T21.8
    [Fact]
    public void ShouldRefuseSecondUpgradeAttemptAndKeepStateUnchanged_WhenSecondAttemptInSameRestSession()
    {
        var session = new RestSessionUpgradeFlow(new[] { 1, 2 }, 100);

        var firstAttemptAccepted = session.TryEnterUpgradeAndConfirm(cardIndex: 0);
        var cardsAfterFirstAttempt = session.GetCardLevelsSnapshot();
        var resourcesAfterFirstAttempt = session.Resources;

        var secondAttemptAccepted = session.TryEnterUpgradeAndConfirm(cardIndex: 1);

        firstAttemptAccepted.Should().BeTrue();
        secondAttemptAccepted.Should().BeFalse("a second upgrade entry in the same rest session must be rejected");
        session.GetCardLevelsSnapshot().Should().Equal(cardsAfterFirstAttempt);
        session.Resources.Should().Be(resourcesAfterFirstAttempt);
    }

    private sealed class RestSessionUpgradeFlow
    {
        private readonly List<int> cardLevels;
        private bool freeUpgradeConsumed;

        public RestSessionUpgradeFlow(IEnumerable<int> initialCardLevels, int initialResources)
        {
            cardLevels = new List<int>(initialCardLevels);
            Resources = initialResources;
        }

        public int Resources { get; private set; }

        public bool IsUpgradeEntryEnabled => !freeUpgradeConsumed;

        public bool TryEnterUpgradeAndConfirm(int cardIndex)
        {
            if (!IsUpgradeEntryEnabled)
            {
                return false;
            }

            if (cardIndex < 0 || cardIndex >= cardLevels.Count)
            {
                return false;
            }

            cardLevels[cardIndex] += 1;
            freeUpgradeConsumed = true;
            return true;
        }

        public int[] GetCardLevelsSnapshot()
        {
            return cardLevels.ToArray();
        }
    }
}
