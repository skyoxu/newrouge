using System;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Game.Core.Contracts.Events;
using Xunit;

namespace Game.Core.Tests.Contracts;

public class EventContractsBatch3Tests
{
    [Fact]
    public void Card_and_combat_guard_events_have_explicit_payloads()
    {
        var cardUpgraded = new CardUpgradedEvent(
            RunId: "run-1",
            CardInstanceId: "card-inst-1",
            CardId: "warrior.slash",
            FromForm: CardForm.Base,
            ToForm: CardForm.U1A,
            Route: UpgradeRoute.A,
            UpgradedAt: DateTimeOffset.UtcNow
        );

        var cardUltimate = new CardUltimatePromotedEvent(
            RunId: cardUpgraded.RunId,
            CardInstanceId: cardUpgraded.CardInstanceId,
            CardId: cardUpgraded.CardId,
            FromForm: cardUpgraded.ToForm,
            ToForm: CardForm.Ultimate,
            PromotedAt: DateTimeOffset.UtcNow
        );

        var invalidPlay = new CombatCardInvalidPlayBlockedEvent(
            RunId: cardUpgraded.RunId,
            CombatId: "combat-1",
            ActorId: "player",
            CardInstanceId: cardUpgraded.CardInstanceId,
            ReasonCode: "energy_not_enough",
            BlockedAt: DateTimeOffset.UtcNow
        );

        var fixedDamage = new CombatFixedDamageResolvedEvent(
            RunId: cardUpgraded.RunId,
            CombatId: "combat-1",
            SourceId: "enemy-1",
            TargetId: "player",
            Amount: 3,
            TargetArmorAfter: 0,
            ResolvedAt: DateTimeOffset.UtcNow
        );

        var loopStop = new CombatLoopHardStoppedEvent(
            RunId: cardUpgraded.RunId,
            CombatId: "combat-1",
            PlayedCardsCount: 100,
            Threshold: 100,
            ReasonCode: "hard_stop",
            StoppedAt: DateTimeOffset.UtcNow
        );

        var turnStarted = new CombatTurnStartedEvent(
            RunId: cardUpgraded.RunId,
            CombatId: "combat-1",
            Turn: 2,
            ActorId: "player",
            Energy: 3,
            DrawCount: 4,
            StartedAt: DateTimeOffset.UtcNow
        );

        cardUltimate.ToForm.Should().Be(CardForm.Ultimate);
        invalidPlay.ReasonCode.Should().Be("energy_not_enough");
        fixedDamage.Amount.Should().Be(3);
        loopStop.Threshold.Should().Be(100);
        turnStarted.Turn.Should().Be(2);
    }

    [Fact]
    public void Run_map_shop_and_relic_events_have_clear_fields()
    {
        var actLoaded = new ActConfigLoadedEvent(
            RunId: "run-1",
            ActId: 1,
            ConfigVersion: "v1",
            LoadedAt: DateTimeOffset.UtcNow
        );

        var runDifficulty = new RunDifficultySelectedEvent(
            RunId: actLoaded.RunId,
            DifficultyId: 5,
            SelectedAt: DateTimeOffset.UtcNow
        );

        var runCharacter = new RunCharacterSelectedEvent(
            RunId: actLoaded.RunId,
            CharacterId: "warrior",
            SelectedAt: DateTimeOffset.UtcNow
        );

        var nodeSelected = new MapNodeSelectedEvent(
            RunId: actLoaded.RunId,
            ActId: 1,
            NodeId: "N-1-2",
            SelectedAt: DateTimeOffset.UtcNow
        );

        var nodeEntered = new MapNodeEnteredEvent(
            RunId: actLoaded.RunId,
            ActId: 1,
            NodeId: nodeSelected.NodeId,
            NodeType: "combat",
            EnteredAt: DateTimeOffset.UtcNow
        );

        var nodeLocked = new MapNodeLockedEvent(
            RunId: actLoaded.RunId,
            ActId: 1,
            NodeId: "N-1-1",
            ReasonCode: "path_committed",
            LockedAt: DateTimeOffset.UtcNow
        );

        var backtrackBlocked = new MapPathBacktrackBlockedEvent(
            RunId: actLoaded.RunId,
            FromNodeId: nodeEntered.NodeId,
            ToNodeId: nodeLocked.NodeId,
            ReasonCode: "one_way",
            BlockedAt: DateTimeOffset.UtcNow
        );

        var relicGranted = new RelicGrantedEvent(
            RunId: actLoaded.RunId,
            RelicId: "relic-1",
            SourceType: "reward",
            SourceId: nodeEntered.NodeId,
            GrantedAt: DateTimeOffset.UtcNow
        );

        var inventoryLocked = new ShopInventoryLockedEvent(
            RunId: actLoaded.RunId,
            ShopId: "shop-1",
            StableIds: new[] { "s1", "s2", "s3" },
            DisplayOrder: new[] { "s2", "s1", "s3" },
            LockedAt: DateTimeOffset.UtcNow
        );

        var shopCurseRemoved = new ShopCurseRemovedEvent(
            RunId: actLoaded.RunId,
            ShopId: inventoryLocked.ShopId,
            CardId: "curse-1",
            Price: 80,
            RemovedAt: DateTimeOffset.UtcNow
        );

        var runResumed = new RunResumedEvent(
            RunId: actLoaded.RunId,
            SavePointId: "node-pre-enter",
            ResumedAt: DateTimeOffset.UtcNow
        );

        nodeEntered.NodeType.Should().Be("combat");
        backtrackBlocked.ReasonCode.Should().Be("one_way");
        relicGranted.SourceType.Should().Be("reward");
        inventoryLocked.StableIds.Should().HaveCount(3);
        shopCurseRemoved.Price.Should().Be(80);
        runResumed.SavePointId.Should().Be("node-pre-enter");
    }

    [Fact]
    public void Status_health_score_and_audit_events_have_traceable_values()
    {
        var statusApplied = new StatusAppliedEvent(
            RunId: "run-1",
            CombatId: "combat-1",
            TargetId: "enemy-1",
            StatusId: "vulnerable",
            Stacks: 1,
            DurationTurns: 2,
            SourceId: "player",
            AppliedAt: DateTimeOffset.UtcNow
        );

        var difficultyModifier = new DifficultyModifierAppliedEvent(
            RunId: statusApplied.RunId,
            DifficultyId: 10,
            ModifierId: "overplay_tax",
            Value: 1,
            AppliedAt: DateTimeOffset.UtcNow
        );

        var health = new HealthUpdatedEvent(
            RunId: statusApplied.RunId,
            TargetId: "enemy-1",
            PreviousHealth: 40,
            CurrentHealth: 28,
            Delta: -12,
            UpdatedAt: DateTimeOffset.UtcNow
        );

        var score = new ScoreUpdatedEvent(
            RunId: statusApplied.RunId,
            PreviousScore: 100,
            CurrentScore: 124,
            Delta: 24,
            UpdatedAt: DateTimeOffset.UtcNow
        );

        var intent = new IntentSelectedEvent(
            RunId: statusApplied.RunId,
            CombatId: statusApplied.CombatId,
            ActorId: "enemy-1",
            IntentId: "intent.attack",
            SelectedAt: DateTimeOffset.UtcNow
        );

        var darkCost = new DarkCostAppliedEvent(
            RunId: statusApplied.RunId,
            SourceId: "event.dark_shrine",
            CostType: "hp_loss",
            Amount: 5,
            AppliedAt: DateTimeOffset.UtcNow
        );

        var curseAdded = new CurseAddedEvent(
            RunId: statusApplied.RunId,
            CardId: "curse-1",
            SourceType: "event",
            SourceId: "evt-dark",
            AddedAt: DateTimeOffset.UtcNow
        );

        var curseRemoved = new CurseRemovedEvent(
            RunId: statusApplied.RunId,
            CardId: curseAdded.CardId,
            SourceType: "rest",
            SourceId: "rest-1",
            RemovedAt: DateTimeOffset.UtcNow
        );

        var traceability = new TraceabilityCheckedEvent(
            RunId: statusApplied.RunId,
            Scope: "task-links",
            Status: "ok",
            CheckedAt: DateTimeOffset.UtcNow
        );

        var audit = new AuditLoggedEvent(
            RunId: statusApplied.RunId,
            Action: "write_autosave",
            Reason: "reward_opened",
            Target: "autosave-slot",
            Caller: "SaveService",
            LoggedAt: DateTimeOffset.UtcNow
        );

        difficultyModifier.DifficultyId.Should().Be(10);
        health.Delta.Should().Be(-12);
        score.CurrentScore.Should().BeGreaterThan(score.PreviousScore);
        intent.IntentId.Should().Be("intent.attack");
        darkCost.Amount.Should().Be(5);
        curseRemoved.CardId.Should().Be(curseAdded.CardId);
        traceability.Status.Should().Be("ok");
        audit.Action.Should().Be("write_autosave");
    }
}
