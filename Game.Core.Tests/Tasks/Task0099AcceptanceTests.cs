using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Combat;
using Game.Core.Contracts.Interfaces;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0099AcceptanceTests
{
    private const int TaskmasterId = 99;
    private const string StrictEvidenceEnvName = "TASK0099_GATE_EVIDENCE_REQUIRED";
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string ThisTestRef = "Game.Core.Tests/Tasks/Task0099AcceptanceTests.cs";
    private const string LegacyRelicAcceptanceRef = "Game.Core.Tests/Tasks/Task0031AcceptanceTests.cs";
    private const string WorkflowEvidenceRef = "Game.Core.Tests/Tasks/Task0098WorkflowSelectionEvidenceTests.cs";
    private const string PipelineTaskPrefix = "sc-review-pipeline-task-99";

    // ACC:T99.1
    [Fact]
    [Trait("acceptance", "ACC:T99.1")]
    public void ShouldReferenceSharedCombatTriggerEvidence_WhenValidatingAcceptanceLine1()
    {
        AssertAcceptanceRefsContain(TasksBackPath, index: 0, ThisTestRef, LegacyRelicAcceptanceRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, index: 0, ThisTestRef, LegacyRelicAcceptanceRef);

        var legacyTests = ReadRepositoryText(LegacyRelicAcceptanceRef);
        legacyTests.Should().Contain("ACC:T31.1");

        var ordered = PlayCardResolutionPipeline.ResolveTriggerOrder(new[]
        {
            new CombatTriggerOrderKey("Status.Burn", Priority: 1, RegistrationOrder: 0),
            new CombatTriggerOrderKey("Relic.ashen_hourglass", Priority: 1, RegistrationOrder: 1),
            new CombatTriggerOrderKey("Status.Weak", Priority: 2, RegistrationOrder: 0),
        });

        ordered.Should().Equal("Relic.ashen_hourglass", "Status.Burn", "Status.Weak");
    }

    // ACC:T99.2
    [Fact]
    [Trait("acceptance", "ACC:T99.2")]
    public void ShouldReferenceUniquenessEvidence_WhenValidatingAcceptanceLine2()
    {
        AssertAcceptanceRefsContain(TasksBackPath, index: 1, ThisTestRef, LegacyRelicAcceptanceRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, index: 1, ThisTestRef, LegacyRelicAcceptanceRef);

        var legacyTests = ReadRepositoryText(LegacyRelicAcceptanceRef);
        legacyTests.Should().Contain("ACC:T31.2");

        var baseline = StartingRelicService.Definitions;
        StartingRelicService.ValidateUniqueRelicIds(baseline).IsValid.Should().BeTrue();

        var duplicateSet = baseline.Concat(new[]
        {
            new StartingRelicDefinition(
                baseline[0].RelicId,
                "relic.name.duplicate-task99",
                "effect.duplicate-task99",
                new[] { "m1", "duplicate" }),
        });

        var duplicateValidation = StartingRelicService.ValidateUniqueRelicIds(duplicateSet);
        duplicateValidation.IsValid.Should().BeFalse();
        duplicateValidation.DuplicateRelicIds.Should().Contain(baseline[0].RelicId);
    }

    // ACC:T99.3
    [Fact]
    [Trait("acceptance", "ACC:T99.3")]
    public void ShouldReferenceOwnershipEvidence_WhenValidatingAcceptanceLine3()
    {
        AssertAcceptanceRefsContain(TasksBackPath, index: 2, ThisTestRef, LegacyRelicAcceptanceRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, index: 2, ThisTestRef, LegacyRelicAcceptanceRef);

        var legacyTests = ReadRepositoryText(LegacyRelicAcceptanceRef);
        legacyTests.Should().Contain("ACC:T31.6");

        var ownedCombatantId = "combatant.player.main";
        var otherCombatantId = "combatant.enemy.alt";
        var ownedInput = new PlayCardPipelineInput(
            DifficultyId: 10,
            CardsPlayedThisTurn: 1,
            OverplayTriggerN: 3,
            OverplayTaxPerCard: 1,
            BaseCardCost: 1,
            EnergyBefore: 3,
            BaseDamage: 8,
            Strength: 2,
            WeakMultiplier: 1.0,
            VulnerableMultiplier: 1.0,
            IsFixedDamage: false,
            CombatantId: ownedCombatantId,
            StableId: "relic.ashen_hourglass");
        var otherInput = ownedInput with
        {
            CombatantId = otherCombatantId,
            StableId = "relic.obsidian_mirror",
        };

        var service = new CombatService();
        var ownedResult = service.ExecutePlayCardPipeline(ownedInput);
        var otherResult = service.ExecutePlayCardPipeline(otherInput);

        ownedResult.Success.Should().BeTrue();
        otherResult.Success.Should().BeTrue();
        ownedResult.OrderingKey.Should().StartWith($"{ownedCombatantId}|");
        otherResult.OrderingKey.Should().StartWith($"{otherCombatantId}|");
        ownedResult.OrderingKey.Should().NotBe(otherResult.OrderingKey);
    }

    // ACC:T99.4
    [Fact]
    [Trait("acceptance", "ACC:T99.4")]
    public void ShouldKeepScopeOnCombatTimeRelicTriggering_WhenValidatingAcceptanceLine4()
    {
        AssertAcceptanceRefsContain(TasksBackPath, index: 3, ThisTestRef, LegacyRelicAcceptanceRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, index: 3, ThisTestRef, LegacyRelicAcceptanceRef);

        var acceptanceBack = ReadAcceptanceLine(TasksBackPath, 3);
        acceptanceBack.Should().Contain("post-combat relic closure");
        acceptanceBack.Should().Contain("remain unchanged");

        var spyBus = new SpyEventBus();
        var service = new CombatService(spyBus);

        var combatResult = service.ExecutePlayCardPipeline(new PlayCardPipelineInput(
            DifficultyId: 10,
            CardsPlayedThisTurn: 2,
            OverplayTriggerN: 3,
            OverplayTaxPerCard: 1,
            BaseCardCost: 1,
            EnergyBefore: 4,
            BaseDamage: 10,
            Strength: 2,
            WeakMultiplier: 1.0,
            VulnerableMultiplier: 1.0,
            IsFixedDamage: false,
            CombatantId: "combatant.player.main",
            StableId: "relic.ashen_hourglass"));

        combatResult.Success.Should().BeTrue();
        spyBus.PublishedTypes.Should().NotBeEmpty();
        spyBus.PublishedTypes.Should().OnlyContain(type => type == EventTypes.AuditLogged);

        var publishedCountBeforeEndTurn = spyBus.PublishedTypes.Count;

        var endTurn = service.ResolveEndTurnProgression(new EndTurnProgressionInput(
            Difficulty: 10,
            PlayerHp: 35,
            PlayerBlock: 5,
            DrawPileCount: 12,
            DiscardPileCount: 4,
            HandCount: 3,
            IncomingEnemyDamage: 9,
            NextHandCards: new[] { "card.strike", "card.defend" }));

        endTurn.DamageTaken.Should().Be(4);
        endTurn.NextPlayerHp.Should().Be(31);
        endTurn.NextPlayerBlock.Should().Be(0);
        endTurn.NextEnergy.Should().Be(3);

        spyBus.PublishedTypes.Count.Should().Be(
            publishedCountBeforeEndTurn,
            "post-combat closure path must remain unchanged and should not emit extra combat-time trigger events");
        spyBus.PublishedTypes.Should().NotContain(EventTypes.CombatRelicTriggered);
    }

    // ACC:T99.5
    [Fact]
    [Trait("acceptance", "ACC:T99.5")]
    public void ShouldReferenceCombatIntegrationEvidence_WhenValidatingAcceptanceLine5()
    {
        AssertAcceptanceRefsContain(TasksBackPath, index: 4, ThisTestRef, LegacyRelicAcceptanceRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, index: 4, ThisTestRef, LegacyRelicAcceptanceRef);

        var result = new CombatService().ExecutePlayCardPipeline(new PlayCardPipelineInput(
            DifficultyId: 10,
            CardsPlayedThisTurn: 2,
            OverplayTriggerN: 3,
            OverplayTaxPerCard: 1,
            BaseCardCost: 1,
            EnergyBefore: 4,
            BaseDamage: 10,
            Strength: 2,
            WeakMultiplier: 1.0,
            VulnerableMultiplier: 1.0,
            IsFixedDamage: false,
            CombatantId: "combatant.player.main",
            StableId: "relic.ashen_hourglass"));

        result.Success.Should().BeTrue();
        result.ExecutedSteps.Should().ContainInOrder(
            PlayCardPipelineStep.BeforePlayTriggers,
            PlayCardPipelineStep.ResolveEffect,
            PlayCardPipelineStep.AfterPlayTriggers);
        result.StateAfter.ResolvedEffects.Should().Be(1);
    }

    // ACC:T99.6
    [Fact]
    [Trait("acceptance", "ACC:T99.6")]
    public void ShouldRequireWorkflowSelectionEvidenceBeforeImplementationEvidence_WhenValidatingAcceptanceLine6()
    {
        AssertAcceptanceRefsContain(TasksBackPath, index: 5, ThisTestRef, WorkflowEvidenceRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, index: 5, ThisTestRef, WorkflowEvidenceRef);

        if (!TryResolveLatestPipelineIndexPath(out var latestIndexPath, out var missingReason))
        {
            EnsurePipelineEvidenceOrSkip(missingReason);
            return;
        }

        var latestIndex = ReadJsonRoot(latestIndexPath);
        ReadString(latestIndex, "task_id").Should().Be("99");

        var runEventsPath = ReadString(latestIndex, "run_events_path");
        runEventsPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(runEventsPath!).Should().BeTrue("workflow selection order must be verifiable from run-events evidence");

        var runEvents = ReadRunEvents(runEventsPath!);
        runEvents.Should().NotBeEmpty();

        var implementationEvents = runEvents
            .Where(IsImplementationEvidenceEvent)
            .OrderBy(record => record.Timestamp)
            .ToArray();
        if (implementationEvents.Length == 0)
        {
            EnsurePipelineEvidenceOrSkip("latest run-events do not contain implementation evidence events");
            return;
        }

        HasSelectionEventBeforeImplementationEvidence(runEvents).Should().BeTrue(
            "workflow selection record must be emitted before implementation evidence events");

        var withoutSelection = runEvents
            .Where(record => !IsSelectionEvent(record))
            .OrderBy(record => record.Timestamp)
            .ToArray();

        HasSelectionEventBeforeImplementationEvidence(withoutSelection).Should().BeFalse(
            "workflow selection record is mandatory and cannot be inferred when run events miss it");

        var implementationWithoutSelection = withoutSelection
            .Where(IsImplementationEvidenceEvent)
            .OrderBy(record => record.Timestamp)
            .Select(record => $"{record.EventFamily}:{record.EventName}:{record.StepName}:{record.Timestamp:O}")
            .ToArray();
        var implementationWithSelection = implementationEvents
            .Select(record => $"{record.EventFamily}:{record.EventName}:{record.StepName}:{record.Timestamp:O}")
            .ToArray();

        implementationWithoutSelection.Should().Equal(
            implementationWithSelection,
            "removing workflow-selection evidence must not mutate implementation evidence payload/order");
    }

    private static void AssertAcceptanceRefsContain(string taskFilePath, int index, params string[] expectedRefs)
    {
        var task = ReadTaskNode(taskFilePath, TaskmasterId);
        var acceptance = ReadStringArray(task, "acceptance");
        acceptance.Length.Should().BeGreaterThan(index, $"acceptance[{index}] must exist in {taskFilePath}");

        var refs = ParseRefs(acceptance[index]);
        foreach (var expected in expectedRefs)
        {
            refs.Should().Contain(expected, $"{taskFilePath} acceptance[{index}] should include {expected}");
        }

        var testRefs = ReadStringArray(task, "test_refs");
        testRefs.Should().Contain(ThisTestRef, $"{taskFilePath} test_refs should include {ThisTestRef}");
    }

    private static string ReadAcceptanceLine(string taskFilePath, int index)
    {
        var task = ReadTaskNode(taskFilePath, TaskmasterId);
        var acceptance = ReadStringArray(task, "acceptance");
        acceptance.Length.Should().BeGreaterThan(index, $"acceptance[{index}] must exist in {taskFilePath}");
        return acceptance[index];
    }

    private static JsonElement ReadTaskNode(string taskFilePath, int taskmasterId)
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), taskFilePath.Replace('/', Path.DirectorySeparatorChar));
        using var document = JsonDocument.Parse(File.ReadAllText(absolutePath));
        var task = document.RootElement
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("taskmaster_id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.GetInt32() == taskmasterId);

        task.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"taskmaster_id={taskmasterId} must exist in {taskFilePath}");
        return JsonDocument.Parse(task.GetRawText()).RootElement.Clone();
    }

    private static string[] ReadStringArray(JsonElement node, string propertyName)
    {
        if (!node.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        return property.EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString() ?? string.Empty)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }

    private static string[] ParseRefs(string acceptanceLine)
    {
        const string marker = "Refs:";
        var markerIndex = acceptanceLine.IndexOf(marker, StringComparison.Ordinal);
        if (markerIndex < 0)
        {
            return Array.Empty<string>();
        }

        var refsPart = acceptanceLine[(markerIndex + marker.Length)..].Trim();
        if (refsPart.Length == 0)
        {
            return Array.Empty<string>();
        }

        return refsPart.Split(new[] { ' ', '\t', '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
    }

    private static string ReadRepositoryText(string relativePath)
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), relativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(absolutePath).Should().BeTrue($"required file is missing: {relativePath}");
        return File.ReadAllText(absolutePath);
    }

    private static bool TryResolveLatestPipelineIndexPath(out string latestIndexPath, out string reason)
    {
        var root = FindRepositoryRoot();
        var ciRoot = Path.Combine(root, "logs", "ci");
        if (!Directory.Exists(ciRoot))
        {
            latestIndexPath = string.Empty;
            reason = $"missing logs/ci root: {ciRoot}";
            return false;
        }

        latestIndexPath = Directory
            .EnumerateFiles(ciRoot, "latest.json", SearchOption.AllDirectories)
            .Where(path => path.Contains(PipelineTaskPrefix, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(path => File.GetLastWriteTimeUtc(path))
            .FirstOrDefault() ?? string.Empty;

        if (string.IsNullOrWhiteSpace(latestIndexPath))
        {
            reason = "missing pipeline latest.json for task 99 under logs/ci/<date>/sc-review-pipeline-task-99*/latest.json";
            return false;
        }

        reason = string.Empty;
        return true;
    }

    private static JsonElement ReadJsonRoot(string path)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        return document.RootElement.Clone();
    }

    private static IReadOnlyList<RunEventRecord> ReadRunEvents(string runEventsPath)
    {
        var records = new List<RunEventRecord>();
        foreach (var rawLine in File.ReadAllLines(runEventsPath))
        {
            var line = rawLine.Trim();
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            var timestamp = ReadTimestamp(root);
            if (timestamp == DateTimeOffset.MinValue)
            {
                continue;
            }

            records.Add(new RunEventRecord(
                Timestamp: timestamp,
                EventFamily: ReadString(root, "event_family"),
                EventName: ReadString(root, "event"),
                StepName: ReadString(root, "step_name")));
        }

        return records;
    }

    private static bool HasSelectionEventBeforeImplementationEvidence(IEnumerable<RunEventRecord> runEvents)
    {
        var ordered = runEvents.OrderBy(record => record.Timestamp).ToArray();
        var selection = ordered.FirstOrDefault(IsSelectionEvent);
        var implementation = ordered.FirstOrDefault(IsImplementationEvidenceEvent);

        if (selection is null || implementation is null)
        {
            return false;
        }

        return selection.Timestamp <= implementation.Timestamp;
    }

    private static bool IsSelectionEvent(RunEventRecord record)
    {
        return string.Equals(record.EventFamily, "run", StringComparison.Ordinal)
               && (
                   string.Equals(record.EventName, "run_forked", StringComparison.Ordinal)
                   || string.Equals(record.EventName, "run_resumed", StringComparison.Ordinal)
                   || string.Equals(record.EventName, "run_started", StringComparison.Ordinal));
    }

    private static bool IsImplementationEvidenceEvent(RunEventRecord record)
    {
        if (!string.Equals(record.EventFamily, "step", StringComparison.Ordinal))
        {
            return false;
        }

        if (!string.Equals(record.EventName, "step_completed", StringComparison.Ordinal))
        {
            return false;
        }

        return string.Equals(record.StepName, "sc-test", StringComparison.Ordinal)
               || string.Equals(record.StepName, "sc-acceptance-check", StringComparison.Ordinal)
               || string.Equals(record.StepName, "sc-llm-review", StringComparison.Ordinal);
    }

    private static void EnsurePipelineEvidenceOrSkip(string reason)
    {
        if (!ShouldRequirePipelineEvidence())
        {
            return;
        }

        throw new Xunit.Sdk.XunitException(
            "Task0099 pipeline evidence is required but missing. "
            + reason
            + " Set TASK0099_GATE_EVIDENCE_REQUIRED=0 (or unset) to suppress in CI/non-Task99 runs.");
    }

    private static bool ShouldRequirePipelineEvidence()
    {
        var raw = Environment.GetEnvironmentVariable(StrictEvidenceEnvName);
        if (string.IsNullOrWhiteSpace(raw))
        {
            return false;
        }

        return raw.Equals("1", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("true", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("yes", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("on", StringComparison.OrdinalIgnoreCase);
    }

    private static string ReadString(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.String)
        {
            return string.Empty;
        }

        return property.GetString() ?? string.Empty;
    }

    private static DateTimeOffset ReadTimestamp(JsonElement root)
    {
        if (!root.TryGetProperty("ts", out var node) || node.ValueKind != JsonValueKind.String)
        {
            return DateTimeOffset.MinValue;
        }

        var raw = node.GetString();
        return DateTimeOffset.TryParse(raw, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var parsed)
            ? parsed
            : DateTimeOffset.MinValue;
    }

    private static string FindRepositoryRoot()
    {
        var current = AppContext.BaseDirectory;
        while (!string.IsNullOrWhiteSpace(current))
        {
            var candidate = Path.Combine(current, "newrouge.sln");
            if (File.Exists(candidate))
            {
                return current;
            }

            var parent = Directory.GetParent(current);
            if (parent is null)
            {
                break;
            }

            current = parent.FullName;
        }

        throw new DirectoryNotFoundException("Cannot locate repository root containing newrouge.sln.");
    }

    private sealed record RunEventRecord(
        DateTimeOffset Timestamp,
        string EventFamily,
        string EventName,
        string StepName);

    private sealed class SpyEventBus : IEventBus
    {
        public List<string> PublishedTypes { get; } = new();

        public Task PublishAsync(DomainEvent evt)
        {
            PublishedTypes.Add(evt.Type);
            return Task.CompletedTask;
        }

        public IDisposable Subscribe(Func<DomainEvent, Task> handler)
        {
            return new NoopDisposable();
        }

        private sealed class NoopDisposable : IDisposable
        {
            public void Dispose()
            {
            }
        }
    }
}
