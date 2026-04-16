using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Save;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0050AcceptanceTests
{
    private const int TaskmasterId = 50;
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0050AcceptanceTests.cs";
    private const string FeatureSlicePath = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Feature-Slice-M1-Warrior.md";
    private const string TestingPath = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Testing-M1.md";

    // ACC:T50.1
    [Fact]
    public void ShouldRouteMigrationOutcomeBySchemaVersion_WhenContinueGateEvaluatesAutosave()
    {
        var migrationService = new VersionAwareMigrationService(new Dictionary<string, SaveMigrationResult>(StringComparer.Ordinal)
        {
            ["1.0.0"] = SaveMigrationResult.Success(),
            ["2.0.0"] = SaveMigrationResult.Failure("Unsupported schema_version: 2.0.0."),
        });
        var service = new ContinueGateService(migrationService);

        var successDecision = service.Evaluate(CreateSnapshot(schemaVersion: "1.0.0", savePointId: "node-ready"));
        var failureDecision = service.Evaluate(CreateSnapshot(schemaVersion: "2.0.0", savePointId: "node-ready"));

        successDecision.ContinueAvailable.Should().BeTrue();
        successDecision.EnterGameAllowed.Should().BeTrue();
        successDecision.ErrorMessage.Should().BeNull();
        successDecision.StateAdvanced.Should().BeTrue();

        failureDecision.ContinueAvailable.Should().BeFalse();
        failureDecision.EnterGameAllowed.Should().BeFalse();
        failureDecision.ErrorMessage.Should().Contain("schema_version");
        failureDecision.StateAdvanced.Should().BeFalse();

        migrationService.ObservedSchemaVersions.Should().ContainInOrder("1.0.0", "2.0.0");
    }

    // ACC:T50.2
    [Fact]
    public void ShouldBlockContinueAndKeepStateUnchanged_WhenMigrationFails()
    {
        var service = new ContinueGateService(
            new VersionAwareMigrationService(new Dictionary<string, SaveMigrationResult>(StringComparer.Ordinal)
            {
                ["1.0.0"] = SaveMigrationResult.Failure("Migration failed for schema_version mismatch."),
            }));

        var decision = service.Evaluate(CreateSnapshot(schemaVersion: "1.0.0", savePointId: "node-failed"));

        decision.ContinueAvailable.Should().BeFalse();
        decision.EnterGameAllowed.Should().BeFalse();
        decision.ErrorMessage.Should().NotBeNullOrWhiteSpace();
        decision.StateAdvanced.Should().BeFalse();
    }

    // ACC:T50.3
    [Fact]
    public void ShouldResolveTaskTestRefsAndOverlayChecklistPaths_WhenAcceptanceEvidenceIsValidated()
    {
        var repoRoot = ResolveRepoRoot();
        var backTask = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_back.json"),
            TaskmasterId);
        var gameplayTask = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_gameplay.json"),
            TaskmasterId);

        foreach (var taskNode in new[] { backTask, gameplayTask })
        {
            var testRefs = ReadStringArray(taskNode, "test_refs");
            testRefs.Should().Contain(ThisTaskTestRef);
            foreach (var testRef in testRefs)
            {
                File.Exists(ResolveRepoPath(repoRoot, testRef)).Should().BeTrue(
                    "task test_ref must resolve to a concrete file: {0}",
                    testRef);
            }

            var overlayRefs = ReadStringArray(taskNode, "overlay_refs");
            overlayRefs.Should().NotBeEmpty("task overlay_refs should include at least one concrete overlay path");
            foreach (var overlayRef in overlayRefs)
            {
                File.Exists(ResolveRepoPath(repoRoot, overlayRef)).Should().BeTrue(
                    "overlay ref should resolve to a concrete file: {0}",
                    overlayRef);
            }
        }

        var mergedOverlayRefs = ReadStringArray(backTask, "overlay_refs")
            .Concat(ReadStringArray(gameplayTask, "overlay_refs"))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        mergedOverlayRefs.Any(path => path.EndsWith("ACCEPTANCE_CHECKLIST.md", StringComparison.OrdinalIgnoreCase))
            .Should()
            .BeTrue("Task 50 acceptance evidence should include a checklist backlink in at least one task view");
    }

    // ACC:T50.4
    [Fact]
    public void ShouldKeepContinueInaccessibleUntilMigrationSucceeds_WhenPreviousMigrationFailed()
    {
        var migrationService = new MutableMigrationService(SaveMigrationResult.Failure("Migration failed."));
        var service = new ContinueGateService(migrationService);
        var snapshot = CreateSnapshot(schemaVersion: "1.0.0", savePointId: "node-retry");

        var firstDecision = service.Evaluate(snapshot);
        firstDecision.ContinueAvailable.Should().BeFalse();
        firstDecision.EnterGameAllowed.Should().BeFalse();
        firstDecision.ErrorMessage.Should().NotBeNullOrWhiteSpace();

        migrationService.NextResult = SaveMigrationResult.Success();
        var secondDecision = service.Evaluate(snapshot);

        secondDecision.ContinueAvailable.Should().BeTrue();
        secondDecision.EnterGameAllowed.Should().BeTrue();
        secondDecision.ErrorMessage.Should().BeNull();
        secondDecision.StateAdvanced.Should().BeTrue();
    }

    // ACC:T50.5
    [Fact]
    public void ShouldContainAdr0032AndAdr0023AcrossTaskViews_WhenAdrTraceabilityIsEvaluated()
    {
        var repoRoot = ResolveRepoRoot();
        var backTask = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_back.json"),
            TaskmasterId);
        var gameplayTask = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_gameplay.json"),
            TaskmasterId);

        ReadStringArray(backTask, "adr_refs").Should().Contain(new[] { "ADR-0032", "ADR-0023" });
        ReadStringArray(gameplayTask, "adr_refs").Should().Contain(new[] { "ADR-0032", "ADR-0023" });
    }

    // ACC:T50.6
    [Fact]
    public void ShouldKeepOverlayEvidenceAlignedWithAdrAndTestBacklinks_WhenTraceabilityIsAudited()
    {
        var repoRoot = ResolveRepoRoot();
        var backTask = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_back.json"),
            TaskmasterId);
        var gameplayTask = ReadTaskNodeByTaskmasterId(
            Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_gameplay.json"),
            TaskmasterId);
        var checklistRelativePath = ReadStringArray(backTask, "overlay_refs")
            .Concat(ReadStringArray(gameplayTask, "overlay_refs"))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .First(path => path.EndsWith("ACCEPTANCE_CHECKLIST.md", StringComparison.OrdinalIgnoreCase));

        var checklistContent = File.ReadAllText(ResolveRepoPath(repoRoot, checklistRelativePath));
        var featureSliceContent = File.ReadAllText(ResolveRepoPath(repoRoot, FeatureSlicePath));
        var testingContent = File.ReadAllText(ResolveRepoPath(repoRoot, TestingPath));

        checklistContent.Should().Contain("ADR-0032");
        checklistContent.Should().Contain("ADR-0023");
        featureSliceContent.Should().Contain("ADR-0032");
        featureSliceContent.Should().Contain("ADR-0023");
        testingContent.Should().Contain(ThisTaskTestRef);
    }

    private static AutosaveSnapshot CreateSnapshot(string schemaVersion, string savePointId)
    {
        var stateJson = JsonSerializer.Serialize(new
        {
            hp = 35,
            offer_locks = new[] { "offer-50-a", "offer-50-b" },
            difficulty = new
            {
                difficulty_id = 3,
                label_key = "difficulty.label.normal",
                description_key = "difficulty.description.normal",
                ruleset_id = "ruleset.m1",
            },
        });

        return new AutosaveSnapshot(
            RunId: "run-50",
            SavePointId: savePointId,
            SchemaVersion: schemaVersion,
            StateJson: stateJson,
            SavedAt: new DateTimeOffset(2026, 4, 16, 13, 0, 0, TimeSpan.Zero));
    }

    private sealed class VersionAwareMigrationService : ISaveMigrationService
    {
        private readonly IReadOnlyDictionary<string, SaveMigrationResult> schemaResults;

        public VersionAwareMigrationService(IReadOnlyDictionary<string, SaveMigrationResult> schemaResults)
        {
            this.schemaResults = schemaResults;
        }

        public IList<string> ObservedSchemaVersions { get; } = new List<string>();

        public SaveMigrationResult AssessSchema(string schemaVersion)
        {
            ObservedSchemaVersions.Add(schemaVersion);
            if (schemaResults.TryGetValue(schemaVersion, out var result))
            {
                return result;
            }

            return SaveMigrationResult.Failure($"Unsupported schema_version: {schemaVersion}.");
        }
    }

    private sealed class MutableMigrationService : ISaveMigrationService
    {
        public MutableMigrationService(SaveMigrationResult initialResult)
        {
            NextResult = initialResult;
        }

        public SaveMigrationResult NextResult { get; set; }

        public SaveMigrationResult AssessSchema(string schemaVersion)
        {
            return NextResult;
        }
    }

    private static JsonElement ReadTaskNodeByTaskmasterId(string taskFilePath, int taskmasterId)
    {
        File.Exists(taskFilePath).Should().BeTrue("task metadata file must exist: {0}", taskFilePath);

        using var document = JsonDocument.Parse(File.ReadAllText(taskFilePath));
        var matched = document.RootElement
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("taskmaster_id", out var taskmasterNode)
                && taskmasterNode.ValueKind == JsonValueKind.Number
                && taskmasterNode.GetInt32() == taskmasterId);

        matched.ValueKind.Should().NotBe(
            JsonValueKind.Undefined,
            "taskmaster_id={0} should exist in {1}",
            taskmasterId,
            taskFilePath);
        return matched.Clone();
    }

    private static string[] ReadStringArray(JsonElement taskNode, string propertyName)
    {
        taskNode.TryGetProperty(propertyName, out var property).Should().BeTrue(
            "property {0} should exist in task metadata",
            propertyName);
        property.ValueKind.Should().Be(JsonValueKind.Array);

        return property
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(value => value!)
            .ToArray();
    }

    private static string ResolveRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, ".taskmaster")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root from AppContext.BaseDirectory.");
    }

    private static string ResolveRepoPath(string repoRoot, string relativePath)
    {
        return Path.Combine(repoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar));
    }
}
