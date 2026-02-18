using System;
using System.Collections.Generic;
using FluentAssertions;
using Game.Core.Contracts.Events;
using Game.Core.Contracts.Run;
using Xunit;

namespace Game.Core.Tests.Contracts;

public class EventContractsM1Tests
{
    [Fact]
    public void ShouldCombatEventsHaveExpectedPayloadShape_WhenExecuted()
    {
        var started = new CombatStartedEvent(
            RunId: "run-1",
            CombatId: "combat-1",
            Turn: 1,
            StartedAt: DateTimeOffset.UtcNow
        );

        var played = new CombatCardPlayedEvent(
            RunId: started.RunId,
            CombatId: started.CombatId,
            ActorId: "player",
            TargetId: "enemy-1",
            CardInstanceId: "card-inst-1",
            EnergyCost: 1,
            Sequence: 3,
            PlayedAt: DateTimeOffset.UtcNow
        );

        var resolved = new CombatDamageResolvedEvent(
            RunId: started.RunId,
            CombatId: started.CombatId,
            SourceId: "player",
            TargetId: "enemy-1",
            BaseDamage: 12,
            FinalDamage: 15,
            IsFixedDamage: false,
            TargetArmorAfter: 0,
            ResolvedAt: DateTimeOffset.UtcNow
        );

        var ended = new CombatEndedEvent(
            RunId: started.RunId,
            CombatId: started.CombatId,
            PlayerWon: true,
            Turns: 4,
            EndedAt: DateTimeOffset.UtcNow
        );

        started.Turn.Should().Be(1);
        played.Sequence.Should().Be(3);
        resolved.FinalDamage.Should().BeGreaterThanOrEqualTo(0);
        ended.PlayerWon.Should().BeTrue();
    }

    [Fact]
    public void ShouldRewardAndEventNodeEventsAreDeterministicPayloads_WhenExecuted()
    {
        var presented = new RewardOfferPresentedEvent(
            RunId: "run-1",
            OfferContextId: "reward-floor-3",
            CandidateIds: new List<string> { "c1", "c2", "c3" },
            DisplayOrder: new List<string> { "c2", "c1", "c3" },
            PresentedAt: DateTimeOffset.UtcNow
        );

        var selected = new RewardOfferSelectedEvent(
            RunId: presented.RunId,
            OfferContextId: presented.OfferContextId,
            SelectedId: "c2",
            SelectedIndex: 0,
            SelectedAt: DateTimeOffset.UtcNow
        );

        var skipped = new RewardOfferSkippedEvent(
            RunId: presented.RunId,
            OfferContextId: presented.OfferContextId,
            SkippedAt: DateTimeOffset.UtcNow
        );

        var entered = new EventEnteredEvent(
            RunId: "run-1",
            EventId: "evt-dark-shrine",
            NodeId: "N-1-4",
            OptionIds: new List<string> { "opt-a", "opt-b" },
            EnteredAt: DateTimeOffset.UtcNow
        );

        var committed = new EventChoiceCommittedEvent(
            RunId: entered.RunId,
            EventId: entered.EventId,
            OptionId: "opt-a",
            ChoiceResultId: "res-1",
            CommittedAt: DateTimeOffset.UtcNow
        );

        var rest = new RestOptionSelectedEvent(
            RunId: "run-1",
            NodeId: "N-1-5",
            OptionId: "upgrade",
            TargetCardInstanceId: "card-inst-2",
            SelectedAt: DateTimeOffset.UtcNow
        );

        var shop = new ShopItemPurchasedEvent(
            RunId: "run-1",
            ShopId: "shop-1",
            ItemId: "relic-1",
            ItemType: "relic",
            Price: 120,
            PurchasedAt: DateTimeOffset.UtcNow
        );

        presented.CandidateIds.Should().HaveCount(3);
        selected.SelectedId.Should().Be("c2");
        skipped.OfferContextId.Should().Be(presented.OfferContextId);
        committed.OptionId.Should().Be("opt-a");
        rest.OptionId.Should().Be("upgrade");
        shop.Price.Should().Be(120);
    }

    [Fact]
    public void ShouldRunTransitionEventTracksCommandDrivenStateChanges_WhenExecuted()
    {
        var evt = new RunStateTransitionedEvent(
            RunId: "run-1",
            FromState: RunState.NodePreEnter,
            ToState: RunState.Combat,
            Reason: "node_type_combat",
            TransitionedAt: DateTimeOffset.UtcNow
        );

        evt.FromState.Should().Be(RunState.NodePreEnter);
        evt.ToState.Should().Be(RunState.Combat);
        evt.Reason.Should().Be("node_type_combat");
    }
}
