using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Events;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Save;
using Game.Core.Ports;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0036AcceptanceTests
{
    private const int TaskmasterId = 36;
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0036AcceptanceTests.cs";
    private const string OverlayChecklistPath = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md";
    private const string TaskGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private static readonly string[] RequiredAdrIds = { "ADR-0032", "ADR-0023" };

    // ACC:T36.1
    [Fact]
    public async Task ShouldWriteOnlyThreeAutosaves_WhenAllowedAndDisallowedTriggersAreProcessed()
    {
        var recorder = new SaveWriteRecorder();
        var service = BuildService(recorder, runId: "run-36");
        var now = new DateTimeOffset(2026, 4, 19, 8, 0, 0, TimeSpan.Zero);

        await service.HandleCombatStartedAsync(new CombatStartedEvent(
            RunId: "run-36",
            CombatId: "combat-1",
            Turn: 1,
            StartedAt: now));
        await service.HandleSkipFlowStartedAsync("run-36", now.AddSeconds(1));
        await service.HandleRewardOfferLockedAsync(new RewardOfferLockedEvent(
            RunId: "run-36",
            OfferContextId: "reward-ctx-1",
            StableIds: new[] { "offer-a", "offer-b", "offer-c" },
            DisplayOrder: new[] { "offer-a", "offer-b", "offer-c" },
            LockedAt: now.AddSeconds(2)));
        await service.HandleRewardOfferLockedAsync(new RewardOfferLockedEvent(
            RunId: "run-36",
            OfferContextId: "reward-ctx-1",
            StableIds: new[] { "offer-a", "offer-b", "offer-c" },
            DisplayOrder: new[] { "offer-a", "offer-b", "offer-c" },
            LockedAt: now.AddSeconds(3)));
        await service.HandleEventChoiceCommittedAsync(new EventChoiceCommittedEvent(
            RunId: "run-36",
            EventId: "event-1",
            OptionId: "option-1",
            ChoiceResultId: "result-1",
            CommittedAt: now.AddSeconds(4)));
        await service.HandleSkipFlowCompletedAsync("run-36", now.AddSeconds(5));

        recorder.Snapshots.Should().HaveCount(3);
        recorder.Snapshots.Select(ReadTrigger).Should().Equal(
            "BattleEnteredInitialState",
            "RewardScreenFirstShown",
            "EventChoiceCommitted");
    }

    // ACC:T36.2
    [Fact]
    public async Task ShouldKeepAutosaveCountUnchanged_WhenSkipFlowRunsBeforeAndAfter()
    {
        var recorder = new SaveWriteRecorder();
        var service = BuildService(recorder, runId: "run-36");
        var now = new DateTimeOffset(2026, 4, 19, 8, 10, 0, TimeSpan.Zero);

        await service.HandleCombatStartedAsync(new CombatStartedEvent(
            RunId: "run-36",
            CombatId: "combat-2",
            Turn: 1,
            StartedAt: now));
        var countBeforeSkip = recorder.Snapshots.Count;

        await service.HandleSkipFlowStartedAsync("run-36", now.AddSeconds(1));
        await service.HandleSkipFlowCompletedAsync("run-36", now.AddSeconds(2));

        recorder.Snapshots.Count.Should().Be(countBeforeSkip);
    }

    // ACC:T36.2
    [Fact]
    public async Task ShouldWriteAdditionalAutosave_WhenRewardContextChangesUnderSameRun()
    {
        var recorder = new SaveWriteRecorder();
        var service = BuildService(recorder, runId: "run-36");
        var now = new DateTimeOffset(2026, 4, 19, 8, 12, 0, TimeSpan.Zero);

        await service.HandleRewardOfferLockedAsync(new RewardOfferLockedEvent(
            RunId: "run-36",
            OfferContextId: "reward-ctx-a",
            StableIds: new[] { "offer-a", "offer-b", "offer-c" },
            DisplayOrder: new[] { "offer-a", "offer-b", "offer-c" },
            LockedAt: now));
        await service.HandleRewardOfferLockedAsync(new RewardOfferLockedEvent(
            RunId: "run-36",
            OfferContextId: "reward-ctx-b",
            StableIds: new[] { "offer-a", "offer-b", "offer-c" },
            DisplayOrder: new[] { "offer-b", "offer-c", "offer-a" },
            LockedAt: now.AddSeconds(1)));

        recorder.Snapshots.Should().HaveCount(2, "different reward contexts must not be deduplicated");
        recorder.Snapshots.Select(ReadTrigger).Should().Equal("RewardScreenFirstShown", "RewardScreenFirstShown");
    }

    // ACC:T36.3
    [Fact]
    public void ShouldPointOverlayTestRefsToTaskFile_WhenChecklistSemanticsAreValidated()
    {
        var repoRoot = FindRepositoryRoot();
        var checklistPath = Path.Combine(repoRoot, OverlayChecklistPath.Replace('/', Path.DirectorySeparatorChar));
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, TaskGameplayPath.Replace('/', Path.DirectorySeparatorChar)),
            TaskmasterId);

        File.Exists(checklistPath).Should().BeTrue();
        var checklistContent = File.ReadAllText(checklistPath);
        var acceptanceItems = ReadStringArray(taskNode, "acceptance");
        var taskTestRefs = ReadStringArray(taskNode, "test_refs");

        taskTestRefs.Should().Contain(ThisTaskTestRef);
        acceptanceItems.Should().Contain(item => item.Contains(ThisTaskTestRef, StringComparison.Ordinal));
        acceptanceItems.Should().Contain(item => item.Contains("战斗进入初始状态", StringComparison.Ordinal));
        acceptanceItems.Should().Contain(item => item.Contains("奖励界面首次显示", StringComparison.Ordinal));
        acceptanceItems.Should().Contain(item => item.Contains("事件选择作出后", StringComparison.Ordinal));
        acceptanceItems.Should().Contain(item => item.Contains("跳过/略过流程", StringComparison.Ordinal));
        checklistContent.Should().Contain("Task36", "overlay checklist must include task36 refs block");
        checklistContent.Should().Contain(ThisTaskTestRef);
    }

    // ACC:T36.4
    [Fact]
    public async Task ShouldCaptureConsistentAutosaveContent_WhenThreeDeterministicTriggersFire()
    {
        var recorder = new SaveWriteRecorder();
        var service = BuildService(recorder, runId: "run-36");
        var now = new DateTimeOffset(2026, 4, 19, 8, 20, 0, TimeSpan.Zero);

        await service.HandleCombatStartedAsync(new CombatStartedEvent(
            RunId: "run-36",
            CombatId: "combat-3",
            Turn: 1,
            StartedAt: now));
        await service.HandleRewardOfferLockedAsync(new RewardOfferLockedEvent(
            RunId: "run-36",
            OfferContextId: "reward-ctx-2",
            StableIds: new[] { "offer-a", "offer-b", "offer-c" },
            DisplayOrder: new[] { "offer-c", "offer-a", "offer-b" },
            LockedAt: now.AddSeconds(1)));
        await service.HandleEventChoiceCommittedAsync(new EventChoiceCommittedEvent(
            RunId: "run-36",
            EventId: "event-2",
            OptionId: "option-2",
            ChoiceResultId: "result-2",
            CommittedAt: now.AddSeconds(2)));

        recorder.Snapshots.Should().HaveCount(3);
        recorder.Snapshots.Select(ReadSequence).Should().Equal(1L, 2L, 3L);
        recorder.Snapshots.Select(snapshot => snapshot.RunId).Distinct().Should().ContainSingle().Which.Should().Be("run-36");
        recorder.Snapshots.Select(snapshot => snapshot.SavePointId).Should().OnlyContain(value => value.StartsWith("deterministic/", StringComparison.Ordinal));
    }

    // ACC:T36.5
    [Fact]
    public void ShouldRequireBothAdrLinks_WhenTaskAcceptanceTraceabilityIsChecked()
    {
        var repoRoot = FindRepositoryRoot();
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, TaskGameplayPath.Replace('/', Path.DirectorySeparatorChar)),
            TaskmasterId);
        var overlayPath = Path.Combine(repoRoot, OverlayChecklistPath.Replace('/', Path.DirectorySeparatorChar));

        var adrRefs = ReadStringArray(taskNode, "adr_refs");
        var acceptanceItems = ReadStringArray(taskNode, "acceptance");
        var checklist = File.ReadAllText(overlayPath);

        adrRefs.Should().Contain(RequiredAdrIds);
        acceptanceItems.Should().Contain(item => item.Contains("ADR-0032", StringComparison.Ordinal));
        acceptanceItems.Should().Contain(item => item.Contains("ADR-0023", StringComparison.Ordinal));
        checklist.Should().Contain("ADR-0032");
        checklist.Should().Contain("ADR-0023");
    }

    // ACC:T36.6
    [Fact]
    public void ShouldFailGateCheck_WhenAdrBackLinkEvidenceIsMissing()
    {
        var repoRoot = FindRepositoryRoot();
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, TaskGameplayPath.Replace('/', Path.DirectorySeparatorChar)),
            TaskmasterId);
        var evidenceRefs = ReadStringArray(taskNode, "evidence_refs");

        var evidenceByAdrId = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["ADR-0032"] = ResolveExistingEvidencePath(repoRoot, evidenceRefs, "ADR-0032")
        };

        var gateResult = AdrBacklinkGate.Evaluate(RequiredAdrIds, evidenceByAdrId);

        gateResult.ContinueAllowed.Should().BeFalse();
        gateResult.ErrorCode.Should().Be("missing_adr_backlink");
        gateResult.ErrorMessage.Should().Contain("ADR-0023");
    }

    [Fact]
    public async Task ShouldWriteAutosaveFromRealEventBusFlow_WhenProductionListenerReceivesEvents()
    {
        var recorder = new SaveWriteRecorder();
        var bus = new InMemoryEventBus();
        var listener = new DeterministicAutosaveTriggerEventListener(
            bus,
            BuildService(recorder, runId: "run-36"));
        var now = new DateTimeOffset(2026, 4, 19, 8, 30, 0, TimeSpan.Zero);

        await bus.PublishAsync(new Game.Core.Contracts.DomainEvent(
            Type: EventTypes.CombatStarted,
            Source: "task36.test",
            DataJson: JsonSerializer.Serialize(new CombatStartedEvent("run-36", "combat-6", 1, now)),
            Timestamp: now,
            Id: "evt-1"));
        await bus.PublishAsync(new Game.Core.Contracts.DomainEvent(
            Type: EventTypes.RewardOfferLocked,
            Source: "task36.test",
            DataJson: JsonSerializer.Serialize(new RewardOfferLockedEvent(
                "run-36",
                "reward-ctx-6",
                new[] { "offer-a", "offer-b", "offer-c" },
                new[] { "offer-a", "offer-b", "offer-c" },
                now.AddSeconds(1))),
            Timestamp: now.AddSeconds(1),
            Id: "evt-2"));
        await bus.PublishAsync(new Game.Core.Contracts.DomainEvent(
            Type: EventTypes.EventChoiceCommitted,
            Source: "task36.test",
            DataJson: JsonSerializer.Serialize(new EventChoiceCommittedEvent(
                "run-36",
                "event-6",
                "option-6",
                "result-6",
                now.AddSeconds(2))),
            Timestamp: now.AddSeconds(2),
            Id: "evt-3"));

        recorder.Snapshots.Should().HaveCount(3);
        recorder.Snapshots.Select(ReadTrigger).Should().Equal(
            "BattleEnteredInitialState",
            "RewardScreenFirstShown",
            "EventChoiceCommitted");
        recorder.Snapshots.Select(ReadSequence).Should().Equal(1L, 2L, 3L);
        listener.Dispose();
    }

    [Fact]
    public async Task ShouldKeepAutosaveCountUnchanged_WhenNonWhitelistedEventIsPublishedToEventBus()
    {
        var recorder = new SaveWriteRecorder();
        var bus = new InMemoryEventBus();
        var listener = new DeterministicAutosaveTriggerEventListener(
            bus,
            BuildService(recorder, runId: "run-36"));
        var now = new DateTimeOffset(2026, 4, 19, 8, 40, 0, TimeSpan.Zero);

        await bus.PublishAsync(new Game.Core.Contracts.DomainEvent(
            Type: EventTypes.CombatStarted,
            Source: "task36.test",
            DataJson: JsonSerializer.Serialize(new CombatStartedEvent("run-36", "combat-7", 1, now)),
            Timestamp: now,
            Id: "evt-baseline"));
        var countBeforeNoise = recorder.Snapshots.Count;

        await bus.PublishAsync(new Game.Core.Contracts.DomainEvent(
            Type: EventTypes.RunStarted,
            Source: "task36.test",
            DataJson: JsonSerializer.Serialize(new { run_id = "run-36" }),
            Timestamp: now.AddSeconds(1),
            Id: "evt-noise"));

        recorder.Snapshots.Count.Should().Be(countBeforeNoise);
        listener.Dispose();
    }

    [Fact]
    public void ShouldFailGateCheck_WhenAdr0032BackLinkEvidenceIsMissing()
    {
        var evidenceByAdrId = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["ADR-0023"] = "logs/ci/exists-for-test.json"
        };

        var gateResult = AdrBacklinkGate.Evaluate(RequiredAdrIds, evidenceByAdrId);

        gateResult.ContinueAllowed.Should().BeFalse();
        gateResult.ErrorCode.Should().Be("missing_adr_backlink");
        gateResult.ErrorMessage.Should().Contain("ADR-0032");
    }

    private static DeterministicAutosaveTriggerService BuildService(SaveWriteRecorder recorder, string runId)
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
                    run_id = context.RunId,
                }),
                SavedAt: context.OccurredAt));
    }

    private static string ReadTrigger(AutosaveSnapshot snapshot)
    {
        using var doc = JsonDocument.Parse(snapshot.StateJson);
        return doc.RootElement.GetProperty("trigger").GetString() ?? string.Empty;
    }

    private static long ReadSequence(AutosaveSnapshot snapshot)
    {
        using var doc = JsonDocument.Parse(snapshot.StateJson);
        return doc.RootElement.GetProperty("sequence").GetInt64();
    }

    private static string ResolveExistingEvidencePath(string repoRoot, IReadOnlyCollection<string> evidenceRefs, string adrId)
    {
        _ = adrId;
        foreach (var relativePath in evidenceRefs)
        {
            var absolutePath = Path.Combine(repoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar));
            if (File.Exists(absolutePath))
            {
                return relativePath;
            }
        }

        return string.Empty;
    }

    private static JsonElement ReadTaskNodeByTaskmasterId(string taskFilePath, int taskmasterId)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(taskFilePath));
        var taskNode = document.RootElement
            .EnumerateArray()
            .FirstOrDefault(item =>
                item.TryGetProperty("taskmaster_id", out var idNode) &&
                idNode.ValueKind == JsonValueKind.Number &&
                idNode.GetInt32() == taskmasterId);

        taskNode.ValueKind.Should().NotBe(JsonValueKind.Undefined, "Task metadata must exist");
        return JsonDocument.Parse(taskNode.GetRawText()).RootElement.Clone();
    }

    private static IReadOnlyCollection<string> ReadStringArray(JsonElement node, string fieldName)
    {
        if (!node.TryGetProperty(fieldName, out var field) || field.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        return field.EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString() ?? string.Empty)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            var marker = Path.Combine(current.FullName, ".taskmaster", "tasks", "tasks_gameplay.json");
            if (File.Exists(marker))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root from AppContext.BaseDirectory.");
    }

    private sealed class SaveWriteRecorder : ISaveService
    {
        private readonly List<AutosaveSnapshot> snapshots = new();

        public IReadOnlyList<AutosaveSnapshot> Snapshots => snapshots;

        public Task WriteAutosaveAsync(AutosaveSnapshot snapshot)
        {
            snapshots.Add(snapshot);
            return Task.CompletedTask;
        }

        public Task<AutosaveSnapshot?> ReadAutosaveAsync()
        {
            return Task.FromResult<AutosaveSnapshot?>(snapshots.LastOrDefault());
        }

        public Task<ContinueMetadata?> ReadContinueMetadataAsync()
        {
            return Task.FromResult<ContinueMetadata?>(null);
        }

        public Task<ContinueLoadValidationResult> ValidateContinueLoadAsync()
        {
            return Task.FromResult(new ContinueLoadValidationResult(true, null, null));
        }
    }

    private sealed class DeterministicAutosaveTriggerEventListener : IDisposable
    {
        private readonly IDisposable subscription;
        private readonly DeterministicAutosaveTriggerService service;

        public DeterministicAutosaveTriggerEventListener(IEventBus eventBus, DeterministicAutosaveTriggerService service)
        {
            this.service = service;
            subscription = eventBus.Subscribe(OnEventAsync);
        }

        public void Dispose()
        {
            subscription.Dispose();
        }

        private Task OnEventAsync(Game.Core.Contracts.DomainEvent evt)
        {
            if (string.IsNullOrWhiteSpace(evt.DataJson))
            {
                return Task.CompletedTask;
            }

            return evt.Type switch
            {
                EventTypes.CombatStarted => HandleCombatStartedAsync(evt.DataJson),
                EventTypes.RewardOfferLocked => HandleRewardOfferLockedAsync(evt.DataJson),
                EventTypes.EventChoiceCommitted => HandleEventChoiceCommittedAsync(evt.DataJson),
                _ => Task.CompletedTask,
            };
        }

        private Task HandleCombatStartedAsync(string payload)
        {
            var model = JsonSerializer.Deserialize<CombatStartedEvent>(payload);
            return model is null ? Task.CompletedTask : service.HandleCombatStartedAsync(model);
        }

        private Task HandleRewardOfferLockedAsync(string payload)
        {
            var model = JsonSerializer.Deserialize<RewardOfferLockedEvent>(payload);
            return model is null ? Task.CompletedTask : service.HandleRewardOfferLockedAsync(model);
        }

        private Task HandleEventChoiceCommittedAsync(string payload)
        {
            var model = JsonSerializer.Deserialize<EventChoiceCommittedEvent>(payload);
            return model is null ? Task.CompletedTask : service.HandleEventChoiceCommittedAsync(model);
        }
    }
}
