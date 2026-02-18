using System;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Events;
using Game.Core.Contracts.Guild;
using Xunit;

namespace Game.Core.Tests.Contracts;

public class DomainEventContractTests
{
    [Fact]
    public void ShouldDomainEventUsesDataJsonAndDateTimeOffset_WhenExecuted()
    {
        var now = DateTimeOffset.UtcNow;
        var evt = new DomainEvent(
            Type: EventTypes.RunStarted,
            Source: nameof(DomainEventContractTests),
            DataJson: "{\"runId\":\"r1\"}",
            Timestamp: now,
            Id: "evt-1"
        );

        evt.Type.Should().Be(EventTypes.RunStarted);
        evt.DataJson.Should().Be("{\"runId\":\"r1\"}");
        evt.Timestamp.Should().Be(now);
        evt.SpecVersion.Should().Be("1.0");
        evt.DataContentType.Should().Be("application/json");
    }

    [Theory]
    [InlineData(RunStartedEvent.EventType, "core.run.started")]
    [InlineData(RewardOfferLockedEvent.EventType, "core.reward.offer.locked")]
    [InlineData(AutosaveWrittenEvent.EventType, "core.autosave.written")]
    [InlineData(RunContinueBlockedEvent.EventType, "core.run.continue.blocked")]
    [InlineData(RunStateTransitionedEvent.EventType, "core.run.state.transitioned")]
    [InlineData(CombatStartedEvent.EventType, "core.combat.started")]
    [InlineData(CombatCardPlayedEvent.EventType, "core.combat.card.played")]
    [InlineData(CombatDamageResolvedEvent.EventType, "core.combat.damage.resolved")]
    [InlineData(CombatEndedEvent.EventType, "core.combat.ended")]
    [InlineData(RewardOfferPresentedEvent.EventType, "core.reward.offer.presented")]
    [InlineData(RewardOfferSelectedEvent.EventType, "core.reward.offer.selected")]
    [InlineData(RewardOfferSkippedEvent.EventType, "core.reward.offer.skipped")]
    [InlineData(EventEnteredEvent.EventType, "core.event.entered")]
    [InlineData(EventChoiceCommittedEvent.EventType, "core.event.choice.committed")]
    [InlineData(RestOptionSelectedEvent.EventType, "core.rest.option.selected")]
    [InlineData(ShopItemPurchasedEvent.EventType, "core.shop.item.purchased")]
    [InlineData(DeckInitializedEvent.EventType, "core.deck.initialized")]
    [InlineData(DeckDrawnEvent.EventType, "core.deck.drawn")]
    [InlineData(DeckDiscardedEvent.EventType, "core.deck.discarded")]
    [InlineData(DeckRetainedEvent.EventType, "core.deck.retained")]
    [InlineData(DeckExhaustedEvent.EventType, "core.deck.exhausted")]
    [InlineData(DeckShuffledEvent.EventType, "core.deck.shuffled")]
    [InlineData(StatusAppliedEvent.EventType, "core.status.applied")]
    [InlineData(StatusStackedEvent.EventType, "core.status.stacked")]
    [InlineData(StatusExpiredEvent.EventType, "core.status.expired")]
    [InlineData(StatusDispelledEvent.EventType, "core.status.dispelled")]
    [InlineData(SaveWriteSucceededEvent.EventType, "core.save.write.succeeded")]
    [InlineData(SaveWriteFailedEvent.EventType, "core.save.write.failed")]
    [InlineData(SaveLoadedEvent.EventType, "core.save.loaded")]
    [InlineData(SaveMigrationFailedEvent.EventType, "core.save.migration.failed")]
    [InlineData(RngStreamAdvancedEvent.EventType, "core.rng.stream.advanced")]
    [InlineData(RngStreamRestoredEvent.EventType, "core.rng.stream.restored")]
    [InlineData(ActConfigLoadedEvent.EventType, "core.act.config.loaded")]
    [InlineData(AuditLoggedEvent.EventType, "core.audit.logged")]
    [InlineData(CardUltimatePromotedEvent.EventType, "core.card.ultimate.promoted")]
    [InlineData(CardUpgradedEvent.EventType, "core.card.upgraded")]
    [InlineData(CombatCardInvalidPlayBlockedEvent.EventType, "core.combat.card.invalid_play_blocked")]
    [InlineData(CombatFixedDamageResolvedEvent.EventType, "core.combat.fixed_damage.resolved")]
    [InlineData(CombatLoopHardStoppedEvent.EventType, "core.combat.loop.hard_stopped")]
    [InlineData(CombatTurnStartedEvent.EventType, "core.combat.turn.started")]
    [InlineData(CurseAddedEvent.EventType, "core.curse.added")]
    [InlineData(CurseRemovedEvent.EventType, "core.curse.removed")]
    [InlineData(DarkCostAppliedEvent.EventType, "core.darkcost.applied")]
    [InlineData(DifficultyModifierAppliedEvent.EventType, "core.difficulty.modifier.applied")]
    [InlineData(HealthUpdatedEvent.EventType, "core.health.updated")]
    [InlineData(IntentSelectedEvent.EventType, "core.intent.selected")]
    [InlineData(MapNodeEnteredEvent.EventType, "core.map.node.entered")]
    [InlineData(MapNodeLockedEvent.EventType, "core.map.node.locked")]
    [InlineData(MapNodeSelectedEvent.EventType, "core.map.node.selected")]
    [InlineData(MapPathBacktrackBlockedEvent.EventType, "core.map.path.backtrack.blocked")]
    [InlineData(RelicGrantedEvent.EventType, "core.relic.granted")]
    [InlineData(RunCharacterSelectedEvent.EventType, "core.run.character.selected")]
    [InlineData(RunDifficultySelectedEvent.EventType, "core.run.difficulty.selected")]
    [InlineData(RunResumedEvent.EventType, "core.run.resumed")]
    [InlineData(ScoreUpdatedEvent.EventType, "core.score.updated")]
    [InlineData(ShopCurseRemovedEvent.EventType, "core.shop.curse.removed")]
    [InlineData(ShopInventoryLockedEvent.EventType, "core.shop.inventory.locked")]
    [InlineData(TraceabilityCheckedEvent.EventType, "core.traceability.checked")]
    [InlineData(GuildMemberJoined.EventType, "core.guild.member.joined")]
    public void EventType_constants_match_expected_values(string actual, string expected)
    {
        actual.Should().Be(expected);
        actual.Should().StartWith("core.");
    }
}
