using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts.Save;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0130AcceptanceTests
{
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string CandidatesPath = "docs/gdd/ui-gdd-flow.candidates.json";
    private const string ThisTestRef = "Game.Core.Tests/Tasks/Task0130AcceptanceTests.cs";

    // ACC:T130.1
    [Fact]
    [Trait("acceptance", "ACC:T130.1")]
    public async Task ShouldExposeStoredSummaryFields_WhenValidatingAccT130Line1()
    {
        AssertAcceptanceRefs(0);

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var savedAt = new DateTimeOffset(2026, 5, 12, 0, 0, 0, TimeSpan.Zero);
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 6,
                label_key = "ui.difficulty.label",
                description_key = "ui.difficulty.6",
                ruleset_id = "ruleset.t130"
            },
            run_summary = new
            {
                outcome = "Victory",
                node_progress = 12,
                failure_or_recovery_reason = "Settlement persisted",
                owner_surface = "HudOverlay"
            }
        });

        await service.WriteAutosaveAsync(new AutosaveSnapshot(
            RunId: "run-t130-acc1",
            SavePointId: "node-12",
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: savedAt));

        var summary = await service.ReadRunSummaryMetadataAsync();
        summary.Should().NotBeNull();
        summary!.Outcome.Should().Be("Victory");
        summary.NodeProgress.Should().Be(12);
        summary.FailureOrRecoveryReason.Should().Be("Settlement persisted");
    }

    // ACC:T130.2
    [Fact]
    [Trait("acceptance", "ACC:T130.2")]
    public void ShouldRequireAllStandaloneSurfaces_WhenValidatingAccT130Line2()
    {
        AssertAcceptanceRefs(1);

        var candidate = LoadSettlementCandidate();
        var surfaces = GetStringArray(candidate, "suggested_standalone_surfaces");
        var gameplayTask = LoadTaskNode(TasksGameplayPath, 130);
        var gameplayRefs = GetStringArray(gameplayTask, "test_refs");
        var hudScene = LoadTextFromRepoRoot("Game.Godot/Scenes/UI/HUD.tscn");

        surfaces.Should().Contain(new[] { "RunSummaryPanel", "SettlementMetadataPanel", "ResumeEvidencePanel" });
        surfaces.Distinct(StringComparer.Ordinal).Count().Should().Be(3);
        gameplayRefs.Should().Contain("Tests.Godot/tests/UI/test_run_summary_surface.gd");
        hudScene.Should().Contain("[node name=\"RunSummaryPanel\"");
        hudScene.Should().Contain("[node name=\"SummaryOutcomeLabel\"");
        hudScene.Should().Contain("[node name=\"SummaryNodeProgressLabel\"");
        hudScene.Should().Contain("[node name=\"SummaryReasonLabel\"");
        hudScene.Should().Contain("[node name=\"SettlementMetadataPanel\"");
        hudScene.Should().Contain("[node name=\"RewardMetadataLabel\"");
        hudScene.Should().Contain("[node name=\"RelicMetadataLabel\"");
        hudScene.Should().Contain("[node name=\"ResumeEvidencePanel\"");
        hudScene.Should().Contain("[node name=\"ResumeEvidenceLabel\"");
    }

    // ACC:T130.3
    [Fact]
    [Trait("acceptance", "ACC:T130.3")]
    public async Task ShouldRenderStoredRunDataWithoutPlaceholderFallback_WhenValidatingAccT130Line3()
    {
        AssertAcceptanceRefs(2);

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var savedAt = new DateTimeOffset(2026, 5, 12, 0, 10, 0, TimeSpan.Zero);
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 7,
                label_key = "ui.difficulty.label",
                description_key = "ui.difficulty.7",
                ruleset_id = "ruleset.t130"
            },
            run_summary = new
            {
                outcome = "Defeat",
                node_progress = 8,
                failure_or_recovery_reason = "Final strike",
                owner_surface = "MainMenuMetadataPanel"
            }
        });

        await service.WriteAutosaveAsync(new AutosaveSnapshot(
            RunId: "run-t130-acc3",
            SavePointId: "node-8",
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: savedAt));

        var summary = await service.ReadRunSummaryMetadataAsync();
        summary.Should().NotBeNull();
        summary!.Outcome.Should().Be("Defeat");
        summary.NodeProgress.Should().Be(8);
        summary.FailureOrRecoveryReason.Should().Be("Final strike");
        summary.OwnerSurface.Should().Be(RunSummaryOwnerSurface.MainMenuMetadataPanel);
        summary.HasRewardMetadataEvidence.Should().BeFalse();
        summary.HasRelicMetadataEvidence.Should().BeFalse();
        summary.HasResumeEvidence.Should().BeFalse();

        summary.Outcome.Should().NotBe("Unknown");
        summary.FailureOrRecoveryReason.Should().NotBe("No stored run summary reason.");
    }

    // ACC:T130.3
    [Fact]
    [Trait("acceptance", "ACC:T130.3")]
    public async Task ShouldExposeSettlementEvidenceFlagsFromStoredRunData_WhenValidatingAccT130Line3()
    {
        AssertAcceptanceRefs(2);

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var savedAt = new DateTimeOffset(2026, 5, 12, 0, 11, 0, TimeSpan.Zero);
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 7,
                label_key = "ui.difficulty.label",
                description_key = "ui.difficulty.7",
                ruleset_id = "ruleset.t130"
            },
            run_summary = new
            {
                outcome = "Victory",
                node_progress = 9,
                failure_or_recovery_reason = "Settlement with evidence",
                owner_surface = "HudOverlay"
            },
            deferred_metadata_probe = new
            {
                reward_metadata = new { offer_ids = new[] { "r1" } },
                relic_metadata = new { equipped = new[] { "Relic-A" } },
                resume_metadata = new { checkpoint = "node-9" }
            }
        });

        await service.WriteAutosaveAsync(new AutosaveSnapshot(
            RunId: "run-t130-acc3-evidence",
            SavePointId: "node-9",
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: savedAt));

        var summary = await service.ReadRunSummaryMetadataAsync();
        summary.Should().NotBeNull();
        summary!.HasRewardMetadataEvidence.Should().BeTrue();
        summary.HasRelicMetadataEvidence.Should().BeTrue();
        summary.HasResumeEvidence.Should().BeTrue();
    }

    // ACC:T130.4
    [Fact]
    [Trait("acceptance", "ACC:T130.4")]
    public async Task ShouldReturnNoSummaryWithoutStoredRunData_WhenValidatingAccT130Line4()
    {
        AssertAcceptanceRefs(3);

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();

        var summary = await service.ReadRunSummaryMetadataAsync();
        summary.Should().BeNull();
    }

    // ACC:T130.5
    [Fact]
    [Trait("acceptance", "ACC:T130.5")]
    public async Task ShouldExposeMissingFieldsAsDefaultSummaryState_WhenValidatingAccT130Line5()
    {
        AssertAcceptanceRefs(4);
        var gameplayTask = LoadTaskNode(TasksGameplayPath, 130);
        var gameplayRefs = GetStringArray(gameplayTask, "test_refs");

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var savedAt = new DateTimeOffset(2026, 5, 12, 0, 20, 0, TimeSpan.Zero);
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 5,
                label_key = "ui.difficulty.label",
                description_key = "ui.difficulty.5",
                ruleset_id = "ruleset.t130"
            },
            run_summary = new
            {
                outcome = "Victory",
                node_progress = 3
            }
        });

        await service.WriteAutosaveAsync(new AutosaveSnapshot(
            RunId: "run-t130-acc5",
            SavePointId: "node-3",
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: savedAt));

        var summary = await service.ReadRunSummaryMetadataAsync();
        summary.Should().NotBeNull();
        summary!.Outcome.Should().Be("Unknown");
        summary.NodeProgress.Should().Be(0);
        summary.FailureOrRecoveryReason.Should().Be("No stored run summary reason.");
        summary.OwnerSurface.Should().Be(RunSummaryOwnerSurface.HudOverlay);
        gameplayRefs.Should().Contain("Tests.Godot/tests/UI/test_run_summary_surface.gd");
        summary.HasRewardMetadataEvidence.Should().BeFalse();
        summary.HasRelicMetadataEvidence.Should().BeFalse();
        summary.HasResumeEvidence.Should().BeFalse();
    }

    // ACC:T130.5
    [Fact]
    [Trait("acceptance", "ACC:T130.5")]
    public async Task ShouldExposeOnlyRewardEvidence_WhenOnlyRewardMetadataExists()
    {
        AssertAcceptanceRefs(4);

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 5,
                label_key = "ui.difficulty.label",
                description_key = "ui.difficulty.5",
                ruleset_id = "ruleset.t130"
            },
            run_summary = new
            {
                outcome = "Victory",
                node_progress = 6,
                failure_or_recovery_reason = "Reward-only evidence",
                owner_surface = "HudOverlay"
            },
            deferred_metadata_probe = new
            {
                reward_metadata = new { offer_ids = new[] { "r1" } }
            }
        });

        await service.WriteAutosaveAsync(new AutosaveSnapshot(
            RunId: "run-t130-acc5-reward-only",
            SavePointId: "node-6",
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: DateTimeOffset.UtcNow));

        var summary = await service.ReadRunSummaryMetadataAsync();
        summary.Should().NotBeNull();
        summary!.HasRewardMetadataEvidence.Should().BeTrue();
        summary.HasRelicMetadataEvidence.Should().BeFalse();
        summary.HasResumeEvidence.Should().BeFalse();
    }

    // ACC:T130.5
    [Fact]
    [Trait("acceptance", "ACC:T130.5")]
    public async Task ShouldExposeOnlyRelicEvidence_WhenOnlyRelicMetadataExists()
    {
        AssertAcceptanceRefs(4);

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 5,
                label_key = "ui.difficulty.label",
                description_key = "ui.difficulty.5",
                ruleset_id = "ruleset.t130"
            },
            run_summary = new
            {
                outcome = "Victory",
                node_progress = 6,
                failure_or_recovery_reason = "Relic-only evidence",
                owner_surface = "HudOverlay"
            },
            deferred_metadata_probe = new
            {
                relic_metadata = new { equipped = new[] { "Relic-A" } }
            }
        });

        await service.WriteAutosaveAsync(new AutosaveSnapshot(
            RunId: "run-t130-acc5-relic-only",
            SavePointId: "node-6",
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: DateTimeOffset.UtcNow));

        var summary = await service.ReadRunSummaryMetadataAsync();
        summary.Should().NotBeNull();
        summary!.HasRewardMetadataEvidence.Should().BeFalse();
        summary.HasRelicMetadataEvidence.Should().BeTrue();
        summary.HasResumeEvidence.Should().BeFalse();
    }

    // ACC:T130.5
    [Fact]
    [Trait("acceptance", "ACC:T130.5")]
    public async Task ShouldExposeOnlyResumeEvidence_WhenOnlyResumeMetadataExists()
    {
        AssertAcceptanceRefs(4);

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 5,
                label_key = "ui.difficulty.label",
                description_key = "ui.difficulty.5",
                ruleset_id = "ruleset.t130"
            },
            run_summary = new
            {
                outcome = "Victory",
                node_progress = 6,
                failure_or_recovery_reason = "Resume-only evidence",
                owner_surface = "HudOverlay"
            },
            deferred_metadata_probe = new
            {
                resume_metadata = new { checkpoint = "node-6" }
            }
        });

        await service.WriteAutosaveAsync(new AutosaveSnapshot(
            RunId: "run-t130-acc5-resume-only",
            SavePointId: "node-6",
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: DateTimeOffset.UtcNow));

        var summary = await service.ReadRunSummaryMetadataAsync();
        summary.Should().NotBeNull();
        summary!.HasRewardMetadataEvidence.Should().BeFalse();
        summary.HasRelicMetadataEvidence.Should().BeFalse();
        summary.HasResumeEvidence.Should().BeTrue();
    }

    // ACC:T130.6
    [Fact]
    [Trait("acceptance", "ACC:T130.6")]
    public async Task ShouldKeepRunSummaryDeterministicAcrossRepeatedReads_WhenValidatingAccT130Line6()
    {
        AssertAcceptanceRefs(5);

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var savedAt = new DateTimeOffset(2026, 5, 12, 0, 30, 0, TimeSpan.Zero);
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 4,
                label_key = "ui.difficulty.label",
                description_key = "ui.difficulty.4",
                ruleset_id = "ruleset.t130"
            },
            run_summary = new
            {
                outcome = "Victory",
                node_progress = 5,
                failure_or_recovery_reason = "Stable replay",
                owner_surface = "HudOverlay"
            }
        });

        await service.WriteAutosaveAsync(new AutosaveSnapshot(
            RunId: "run-t130-acc6",
            SavePointId: "node-5",
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: savedAt));

        var first = await service.ReadRunSummaryMetadataAsync();
        var second = await service.ReadRunSummaryMetadataAsync();

        second.Should().BeEquivalentTo(first);
    }

    // ACC:T130.7
    [Fact]
    [Trait("acceptance", "ACC:T130.7")]
    public async Task ShouldMapScopeCoverageToExpectedTaskIds_WhenValidatingAccT130Line7()
    {
        AssertAcceptanceRefs(6);

        var scopeTaskIds = LoadSettlementCandidate()
            .GetProperty("scope_task_ids")
            .EnumerateArray()
            .Select(e => e.GetInt32())
            .ToArray();

        scopeTaskIds.Should().Equal(new[] { 91, 107, 109, 113 });

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 9,
                label_key = "ui.difficulty.label",
                description_key = "ui.difficulty.9",
                ruleset_id = "ruleset.t130"
            },
            run_summary = new
            {
                outcome = "Victory",
                node_progress = 12,
                failure_or_recovery_reason = "Scope traceability context",
                owner_surface = "HudOverlay"
            },
            deferred_metadata_probe = new
            {
                reward_metadata = new { offer_ids = new[] { "r1" } },
                relic_metadata = new { equipped = new[] { "Relic-A" } },
                resume_metadata = new { checkpoint = "node-12" }
            }
        });

        await service.WriteAutosaveAsync(new AutosaveSnapshot(
            RunId: "run-t130-acc7-scope-context",
            SavePointId: "node-12",
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: DateTimeOffset.UtcNow));

        var summary = await service.ReadRunSummaryMetadataAsync();
        summary.Should().NotBeNull();
        summary!.Outcome.Should().Be("Victory");
        summary.HasRewardMetadataEvidence.Should().BeTrue();
        summary.HasRelicMetadataEvidence.Should().BeTrue();
        summary.HasResumeEvidence.Should().BeTrue();
    }

    // ACC:T130.8
    [Fact]
    [Trait("acceptance", "ACC:T130.8")]
    public async Task ShouldNotMutateRunProgressionOrSettlementOwnership_WhenInspectingSummarySurfaces()
    {
        AssertAcceptanceRefs(7);

        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var savedAt = new DateTimeOffset(2026, 5, 12, 0, 40, 0, TimeSpan.Zero);
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 8,
                label_key = "ui.difficulty.label",
                description_key = "ui.difficulty.8",
                ruleset_id = "ruleset.t130"
            },
            run_summary = new
            {
                outcome = "Victory",
                node_progress = 14,
                failure_or_recovery_reason = "No gameplay side effects",
                owner_surface = "HudOverlay"
            },
            deferred_metadata_probe = new
            {
                reward_metadata = new { offer_ids = new[] { "r1" } },
                relic_metadata = new { equipped = new[] { "Relic-A" } },
                resume_metadata = new { checkpoint = "node-14" }
            }
        });

        await service.WriteAutosaveAsync(new AutosaveSnapshot(
            RunId: "run-t130-acc8",
            SavePointId: "node-14",
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: savedAt));

        var first = await service.ReadRunSummaryMetadataAsync();
        var second = await service.ReadRunSummaryMetadataAsync();

        first.Should().NotBeNull();
        second.Should().NotBeNull();
        second.Should().BeEquivalentTo(first);
        second!.NodeProgress.Should().Be(14);
        second.OwnerSurface.Should().Be(RunSummaryOwnerSurface.HudOverlay);
        second.HasRewardMetadataEvidence.Should().BeTrue();
        second.HasRelicMetadataEvidence.Should().BeTrue();
        second.HasResumeEvidence.Should().BeTrue();
    }

    private static void AssertAcceptanceRefs(int acceptanceIndex)
    {
        AssertAcceptanceRefsContain(TasksBackPath, 130, acceptanceIndex, ThisTestRef);
        AssertAcceptanceRefsContain(TasksGameplayPath, 130, acceptanceIndex, ThisTestRef);
    }

    private static void AssertAcceptanceRefsContain(string taskFilePath, int taskmasterId, int acceptanceIndex, string expectedRef)
    {
        var task = LoadTaskNode(taskFilePath, taskmasterId);
        var acceptance = task.GetProperty("acceptance");
        var line = acceptance[acceptanceIndex].GetString() ?? string.Empty;
        line.Should().Contain(expectedRef);
    }

    private static JsonElement LoadTaskNode(string taskFilePath, int taskmasterId)
    {
        var root = LoadJsonFromRepoRoot(taskFilePath);
        foreach (var task in root.EnumerateArray())
        {
            if (TryReadTaskmasterIdForTask(task, out var parsedId) && parsedId == taskmasterId)
            {
                return task;
            }
        }

        throw new Xunit.Sdk.XunitException($"Task {taskmasterId} not found in {taskFilePath}.");
    }

    private static JsonElement LoadSettlementCandidate()
    {
        var root = LoadJsonFromRepoRoot(CandidatesPath);
        foreach (var candidate in root.GetProperty("candidates").EnumerateArray())
        {
            var bucket = candidate.GetProperty("bucket").GetString() ?? string.Empty;
            if (string.Equals(bucket, "settlement", StringComparison.Ordinal))
            {
                return candidate;
            }
        }

        throw new Xunit.Sdk.XunitException("settlement candidate not found.");
    }

    private static string[] GetStringArray(JsonElement parent, string propertyName)
    {
        if (!parent.TryGetProperty(propertyName, out var value) || value.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        return value.EnumerateArray().Select(e => e.GetString() ?? string.Empty).Where(s => !string.IsNullOrWhiteSpace(s)).ToArray();
    }

    private static bool TryReadTaskmasterIdForTask(JsonElement task, out int taskmasterId)
    {
        taskmasterId = 0;
        if (!task.TryGetProperty("taskmaster_id", out var idElement))
        {
            return false;
        }

        if (idElement.ValueKind == JsonValueKind.Number)
        {
            return idElement.TryGetInt32(out taskmasterId);
        }

        if (idElement.ValueKind == JsonValueKind.String)
        {
            return int.TryParse(idElement.GetString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out taskmasterId);
        }

        return false;
    }

    private static JsonElement LoadJsonFromRepoRoot(string repoRelativePath)
    {
        var path = ResolveFromRepoRoot(repoRelativePath);
        File.Exists(path).Should().BeTrue($"expected file: {path}");
        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        return doc.RootElement.Clone();
    }

    private static string LoadTextFromRepoRoot(string repoRelativePath)
    {
        var path = ResolveFromRepoRoot(repoRelativePath);
        File.Exists(path).Should().BeTrue($"expected file: {path}");
        return File.ReadAllText(path);
    }

    private static string ResolveFromRepoRoot(string repoRelativePath)
    {
        var current = new DirectoryInfo(Directory.GetCurrentDirectory());
        while (current is not null)
        {
            var candidate = Path.Combine(current.FullName, repoRelativePath.Replace('/', Path.DirectorySeparatorChar));
            if (File.Exists(candidate))
            {
                return candidate;
            }

            current = current.Parent;
        }

        return repoRelativePath;
    }


    private sealed class SaveServiceSandbox : IDisposable
    {
        private SaveServiceSandbox(string rootPath)
        {
            RootPath = rootPath;
        }

        public string RootPath { get; }

        public static SaveServiceSandbox Create()
        {
            var rootPath = Path.Combine(Path.GetTempPath(), "newrouge-task0130-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(rootPath);
            return new SaveServiceSandbox(rootPath);
        }

        public SaveService CreateService()
        {
            return new SaveService(new NoOpDataStore(), new DirectoryInfo(RootPath));
        }

        public void Dispose()
        {
            try
            {
                if (Directory.Exists(RootPath))
                {
                    Directory.Delete(RootPath, true);
                }
            }
            catch
            {
            }
        }
    }

    private sealed class NoOpDataStore : Game.Core.Ports.IDataStore
    {
        public System.Threading.Tasks.Task SaveAsync(string key, string json)
        {
            throw new InvalidOperationException("Physical save path was expected instead of IDataStore.SaveAsync.");
        }

        public System.Threading.Tasks.Task<string?> LoadAsync(string key)
        {
            throw new InvalidOperationException("Physical save path was expected instead of IDataStore.LoadAsync.");
        }

        public System.Threading.Tasks.Task DeleteAsync(string key)
        {
            throw new InvalidOperationException("Physical save path was expected instead of IDataStore.DeleteAsync.");
        }
    }
}




