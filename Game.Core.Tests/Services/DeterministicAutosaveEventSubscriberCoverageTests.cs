using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Events;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Save;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class DeterministicAutosaveEventSubscriberCoverageTests
{
    [Fact]
    public async Task ShouldIgnoreUnknownEventAndWhitespacePayload_WhenSubscriberReceivesUnsupportedInput()
    {
        var recorder = new SaveWriteRecorder();
        var bus = new InMemoryEventBus();
        using var subscriber = new DeterministicAutosaveEventSubscriber(bus, BuildTriggerService(recorder));

        await bus.PublishAsync(new DomainEvent(
            Type: "unknown.event",
            Source: "tests",
            DataJson: "{}",
            Timestamp: DateTimeOffset.UtcNow,
            Id: "evt-unknown"));
        await bus.PublishAsync(new DomainEvent(
            Type: EventTypes.CombatStarted,
            Source: "tests",
            DataJson: "   ",
            Timestamp: DateTimeOffset.UtcNow,
            Id: "evt-empty"));

        recorder.Snapshots.Should().BeEmpty();
    }

    [Fact]
    public async Task ShouldUseFallbackPropertyNamesAndDropInvalidArrayMembers_WhenHandlingRewardOfferLocked()
    {
        var recorder = new SaveWriteRecorder();
        var bus = new InMemoryEventBus();
        using var subscriber = new DeterministicAutosaveEventSubscriber(bus, BuildTriggerService(recorder));
        var ts = new DateTimeOffset(2026, 5, 1, 21, 30, 0, TimeSpan.Zero);

        var payload = JsonSerializer.Serialize(new
        {
            RunId = "run-coverage",
            OfferContextId = "ctx-01",
            StableIds = new object?[] { "a", "", null, "b", 123 },
            DisplayOrder = new object?[] { "b", "a", " ", null, 42 }
        });
        await bus.PublishAsync(new DomainEvent(
            Type: EventTypes.RewardOfferLocked,
            Source: "tests",
            DataJson: payload,
            Timestamp: ts,
            Id: "evt-reward-fallback"));

        recorder.Snapshots.Should().ContainSingle();
        using var doc = JsonDocument.Parse(recorder.Snapshots[0].StateJson);
        var root = doc.RootElement;
        root.GetProperty("trigger").GetString().Should().Be("RewardScreenFirstShown");
        root.GetProperty("source_id").GetString().Should().Be("ctx-01");
        recorder.Snapshots[0].SavePointId.Should().Contain("RewardScreenFirstShown");
    }

    [Fact]
    public async Task ShouldDefaultTurnAndSkipInvalidCombatStartedPayload_WhenHandlingCombatStarted()
    {
        var recorder = new SaveWriteRecorder();
        var bus = new InMemoryEventBus();
        using var subscriber = new DeterministicAutosaveEventSubscriber(bus, BuildTriggerService(recorder));
        var ts = new DateTimeOffset(2026, 5, 1, 21, 35, 0, TimeSpan.Zero);

        var validFallbackPayload = JsonSerializer.Serialize(new
        {
            RunId = "run-combat",
            CombatId = "combat-01",
            Turn = "invalid-number"
        });
        await bus.PublishAsync(new DomainEvent(
            Type: EventTypes.CombatStarted,
            Source: "tests",
            DataJson: validFallbackPayload,
            Timestamp: ts,
            Id: "evt-combat-valid-fallback"));

        var invalidPayloadMissingCombatId = JsonSerializer.Serialize(new
        {
            run_id = "run-combat",
            turn = 3
        });
        await bus.PublishAsync(new DomainEvent(
            Type: EventTypes.CombatStarted,
            Source: "tests",
            DataJson: invalidPayloadMissingCombatId,
            Timestamp: ts.AddSeconds(1),
            Id: "evt-combat-invalid"));

        recorder.Snapshots.Should().ContainSingle();
        using var doc = JsonDocument.Parse(recorder.Snapshots[0].StateJson);
        var root = doc.RootElement;
        root.GetProperty("trigger").GetString().Should().Be("BattleEnteredInitialState");
        root.GetProperty("source_id").GetString().Should().Be("combat-01");
        recorder.Snapshots[0].SavePointId.Should().Contain("BattleEnteredInitialState");
    }

    [Fact]
    public async Task ShouldSkipEventChoiceWhenRequiredFieldsAreMissing_AndAcceptWhenAllPresent()
    {
        var recorder = new SaveWriteRecorder();
        var bus = new InMemoryEventBus();
        using var subscriber = new DeterministicAutosaveEventSubscriber(bus, BuildTriggerService(recorder));
        var ts = new DateTimeOffset(2026, 5, 1, 21, 40, 0, TimeSpan.Zero);

        var missingRequiredPayload = JsonSerializer.Serialize(new
        {
            run_id = "run-choice",
            event_id = "event-01",
            option_id = "opt-01"
        });
        await bus.PublishAsync(new DomainEvent(
            Type: EventTypes.EventChoiceCommitted,
            Source: "tests",
            DataJson: missingRequiredPayload,
            Timestamp: ts,
            Id: "evt-choice-missing"));

        var validPayload = JsonSerializer.Serialize(new
        {
            RunId = "run-choice",
            EventId = "event-01",
            OptionId = "opt-01",
            ChoiceResultId = "result-01"
        });
        await bus.PublishAsync(new DomainEvent(
            Type: EventTypes.EventChoiceCommitted,
            Source: "tests",
            DataJson: validPayload,
            Timestamp: ts.AddSeconds(1),
            Id: "evt-choice-valid"));

        recorder.Snapshots.Should().ContainSingle();
        using var doc = JsonDocument.Parse(recorder.Snapshots[0].StateJson);
        var root = doc.RootElement;
        root.GetProperty("trigger").GetString().Should().Be("EventChoiceCommitted");
        root.GetProperty("source_id").GetString().Should().Be("event-01");
        recorder.Snapshots[0].SavePointId.Should().Contain("EventChoiceCommitted");
    }

    private static DeterministicAutosaveTriggerService BuildTriggerService(SaveWriteRecorder recorder)
    {
        return new DeterministicAutosaveTriggerService(
            recorder,
            context => new AutosaveSnapshot(
                RunId: context.RunId,
                SavePointId: $"deterministic/{context.Trigger}/{context.Sequence}",
                SchemaVersion: "v1",
                StateJson: JsonSerializer.Serialize(new
                {
                    trigger = context.Trigger,
                    source_id = context.SourceId,
                    sequence = context.Sequence,
                }),
                SavedAt: context.OccurredAt));
    }

    private sealed class SaveWriteRecorder : ISaveService
    {
        public List<AutosaveSnapshot> Snapshots { get; } = new();

        public Task WriteAutosaveAsync(AutosaveSnapshot snapshot)
        {
            Snapshots.Add(snapshot);
            return Task.CompletedTask;
        }

        public Task<AutosaveSnapshot?> ReadAutosaveAsync() => Task.FromResult<AutosaveSnapshot?>(Snapshots.LastOrDefault());

        public Task<ContinueMetadata?> ReadContinueMetadataAsync() => Task.FromResult<ContinueMetadata?>(null);

        public Task<RunSummaryMetadata?> ReadRunSummaryMetadataAsync() => Task.FromResult<RunSummaryMetadata?>(null);

        public Task<ContinueLoadValidationResult> ValidateContinueLoadAsync()
            => Task.FromResult(new ContinueLoadValidationResult(true, null, null));
    }

    private sealed class InMemoryEventBus : IEventBus
    {
        private readonly List<Func<DomainEvent, Task>> handlers = new();

        public IDisposable Subscribe(Func<DomainEvent, Task> handler)
        {
            handlers.Add(handler);
            return new Subscription(handlers, handler);
        }

        public async Task PublishAsync(DomainEvent evt)
        {
            foreach (var handler in handlers.ToArray())
            {
                await handler(evt);
            }
        }

        private sealed class Subscription(List<Func<DomainEvent, Task>> handlers, Func<DomainEvent, Task> handler) : IDisposable
        {
            public void Dispose()
            {
                handlers.Remove(handler);
            }
        }
    }
}
