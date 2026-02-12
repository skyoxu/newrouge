using System;
using System.Collections.Generic;
using FluentAssertions;
using Game.Core.Contracts.Events;
using Xunit;

namespace Game.Core.Tests.Contracts;

public class DeckStatusSaveEventContractsTests
{
    [Fact]
    public void Deck_events_should_keep_strongly_typed_payloads()
    {
        var init = new DeckInitializedEvent(
            RunId: "run-1",
            CombatId: "combat-1",
            DrawPileCount: 12,
            DiscardPileCount: 0,
            ExhaustPileCount: 0,
            InitializedAt: DateTimeOffset.UtcNow
        );

        var draw = new DeckDrawnEvent(
            RunId: init.RunId,
            CombatId: init.CombatId,
            ActorId: "player",
            DrawnCardInstanceIds: new List<string> { "c1", "c2", "c3", "c4" },
            DrawCount: 4,
            DrawPileCountAfter: 8,
            DrawnAt: DateTimeOffset.UtcNow
        );

        var discard = new DeckDiscardedEvent(
            RunId: init.RunId,
            CombatId: init.CombatId,
            ActorId: "player",
            CardInstanceIds: new List<string> { "c2", "c3" },
            DiscardPileCountAfter: 2,
            DiscardedAt: DateTimeOffset.UtcNow
        );

        var retain = new DeckRetainedEvent(
            RunId: init.RunId,
            CombatId: init.CombatId,
            ActorId: "player",
            CardInstanceIds: new List<string> { "c1" },
            RetainedAt: DateTimeOffset.UtcNow
        );

        var exhaust = new DeckExhaustedEvent(
            RunId: init.RunId,
            CombatId: init.CombatId,
            ActorId: "player",
            CardInstanceId: "c4",
            ExhaustPileCountAfter: 1,
            ExhaustedAt: DateTimeOffset.UtcNow
        );

        var shuffle = new DeckShuffledEvent(
            RunId: init.RunId,
            CombatId: init.CombatId,
            DrawPileCountBefore: 0,
            DiscardPileCountBefore: 5,
            DrawPileCountAfter: 5,
            DiscardPileCountAfter: 0,
            ShuffledAt: DateTimeOffset.UtcNow
        );

        draw.DrawnCardInstanceIds.Should().HaveCount(4);
        discard.CardInstanceIds.Should().Contain("c2");
        retain.CardInstanceIds.Should().ContainSingle();
        exhaust.ExhaustPileCountAfter.Should().Be(1);
        shuffle.DrawPileCountAfter.Should().Be(5);
    }

    [Fact]
    public void Status_events_should_encode_apply_stack_expire_dispel_paths()
    {
        var applied = new StatusAppliedEvent(
            RunId: "run-1",
            CombatId: "combat-1",
            TargetId: "enemy-1",
            StatusId: "weak",
            Stacks: 1,
            DurationTurns: 2,
            SourceId: "player",
            AppliedAt: DateTimeOffset.UtcNow
        );

        var stacked = new StatusStackedEvent(
            RunId: applied.RunId,
            CombatId: applied.CombatId,
            TargetId: applied.TargetId,
            StatusId: applied.StatusId,
            PreviousStacks: 1,
            CurrentStacks: 2,
            StackedAt: DateTimeOffset.UtcNow
        );

        var expired = new StatusExpiredEvent(
            RunId: applied.RunId,
            CombatId: applied.CombatId,
            TargetId: applied.TargetId,
            StatusId: applied.StatusId,
            ExpiredAt: DateTimeOffset.UtcNow
        );

        var dispelled = new StatusDispelledEvent(
            RunId: applied.RunId,
            CombatId: applied.CombatId,
            TargetId: applied.TargetId,
            StatusId: "vulnerable",
            Reason: "cleanse",
            DispelledAt: DateTimeOffset.UtcNow
        );

        stacked.CurrentStacks.Should().Be(2);
        expired.StatusId.Should().Be("weak");
        dispelled.Reason.Should().Be("cleanse");
    }

    [Fact]
    public void Save_and_rng_events_should_preserve_resume_traceability()
    {
        var writeOk = new SaveWriteSucceededEvent(
            RunId: "run-1",
            SavePointId: "reward-floor-3",
            SchemaVersion: "1.0.0",
            IntegrityHash: "HASH-1",
            WrittenAt: DateTimeOffset.UtcNow
        );

        var writeFail = new SaveWriteFailedEvent(
            RunId: writeOk.RunId,
            SavePointId: writeOk.SavePointId,
            ReasonCode: "io_error",
            Message: "disk full",
            FailedAt: DateTimeOffset.UtcNow
        );

        var loaded = new SaveLoadedEvent(
            RunId: writeOk.RunId,
            SavePointId: writeOk.SavePointId,
            SchemaVersion: writeOk.SchemaVersion,
            LoadedAt: DateTimeOffset.UtcNow
        );

        var migrationFail = new SaveMigrationFailedEvent(
            RunId: writeOk.RunId,
            FromSchema: "0.9.0",
            ToSchema: "1.0.0",
            ReasonCode: "missing_field",
            FailedAt: DateTimeOffset.UtcNow
        );

        var advanced = new RngStreamAdvancedEvent(
            RunId: writeOk.RunId,
            StreamName: "reward",
            PositionBefore: 99,
            PositionAfter: 100,
            AdvancedAt: DateTimeOffset.UtcNow
        );

        var restored = new RngStreamRestoredEvent(
            RunId: writeOk.RunId,
            StreamName: "reward",
            PositionAfter: 99,
            SnapshotHash: "SNAP-1",
            RestoredAt: DateTimeOffset.UtcNow
        );

        writeFail.ReasonCode.Should().Be("io_error");
        loaded.SchemaVersion.Should().Be("1.0.0");
        migrationFail.FromSchema.Should().Be("0.9.0");
        advanced.PositionAfter.Should().BeGreaterThan(advanced.PositionBefore);
        restored.StreamName.Should().Be("reward");
    }
}
