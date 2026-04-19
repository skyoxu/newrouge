using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts.Config;
using Game.Core.Contracts.Run;
using Game.Core.Contracts.Save;
using Game.Core.Ports;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Contracts;

[Trait("task", "T12")]
[Trait("adr", "ADR-0032")]
[Trait("adr", "ADR-0023")]
public sealed class RunAndSaveContractsTests
{
    private static string RepoRoot => FindRepoRoot();

    private static string FindRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            var taskmasterDir = Path.Combine(current.FullName, ".taskmaster");
            if (Directory.Exists(taskmasterDir))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Cannot locate repository root from test execution directory.");
    }

    // ACC:T8.26
    [Fact]
    public void ShouldKeepRunTransitionStateAndCorrelationId_WhenComposingCommandDrivenContracts()
    {
        var command = new RunCommand(
            CommandId: "cmd-1",
            CommandType: "enter_node",
            Issuer: "player",
            PayloadJson: "{\"nodeId\":\"N-2\"}",
            IssuedAt: DateTimeOffset.UtcNow
        );

        var transition = new RunTransition(
            FromState: RunState.NodePreEnter,
            ToState: RunState.Combat,
            Reason: "node_type_combat",
            CorrelationId: command.CommandId,
            TransitionedAt: DateTimeOffset.UtcNow
        );

        transition.FromState.Should().Be(RunState.NodePreEnter);
        transition.ToState.Should().Be(RunState.Combat);
        transition.CorrelationId.Should().Be("cmd-1");
    }

    [Fact]
    public void ShouldKeepAutosaveAndContinueMetadataAlignedToSingleRun_WhenComposingContinueContracts()
    {
        var autosave = new AutosaveSnapshot(
            RunId: "run-1",
            SavePointId: "reward-opened-floor-2",
            SchemaVersion: "1.0.0",
            StateJson: "{\"hp\":60}",
            SavedAt: DateTimeOffset.UtcNow
        );

        var metadata = new ContinueMetadata(
            RunId: autosave.RunId,
            DifficultyId: 7,
            LabelKey: "difficulty.label.hard",
            DescriptionKey: "difficulty.description.hard",
            RulesetId: "ruleset.hard",
            Act: 1,
            NodeId: "N-2",
            IntegrityHash: "ABC123",
            UpdatedAt: DateTimeOffset.UtcNow
        );

        var difficulty = new DifficultyConfig(
            DifficultyId: 7,
            LabelKey: "difficulty.label.hard",
            DescriptionKey: "difficulty.description.hard",
            RulesetId: "ruleset.hard"
        );

        metadata.RunId.Should().Be(autosave.RunId);
        metadata.DifficultyId.Should().Be(difficulty.DifficultyId);
        metadata.LabelKey.Should().Be(difficulty.LabelKey);
        metadata.DescriptionKey.Should().Be(difficulty.DescriptionKey);
        metadata.RulesetId.Should().Be(difficulty.RulesetId);
    }

    // ACC:T51.8
    [Fact]
    public void ShouldExposeTask51AdrMappingEntry_WhenInspectingBackTaskMetadata()
    {
        var taskPath = Path.Combine(RepoRoot, ".taskmaster", "tasks", "tasks_back.json");
        File.Exists(taskPath).Should().BeTrue();

        using var doc = JsonDocument.Parse(File.ReadAllText(taskPath));
        var task51 = doc.RootElement
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("taskmaster_id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.GetInt32() == 51);

        task51.ValueKind.Should().Be(JsonValueKind.Object);

        var adrRefs = task51.GetProperty("adr_refs")
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
        adrRefs.Should().BeEquivalentTo(new[] { "ADR-0032", "ADR-0025" });

        var acceptanceItems = task51.GetProperty("acceptance")
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
        acceptanceItems.Should().NotBeEmpty();

        var refsPaths = acceptanceItems
            .OfType<string>()
            .SelectMany(ExtractRefPaths)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        refsPaths.Should().Contain("Game.Core.Tests/Tasks/Task0051AcceptanceTests.cs");
        refsPaths.Should().Contain("Tests.Godot/tests/Adapters/Db/test_savegame_persistence_cross_restart.gd");
    }

    // ACC:T12.16
    // ACC:T12.17
    // ACC:T12.18
    [Fact]
    public async Task ShouldPreserveStableSavePayloadShapeAndRoundTrip_WhenSerializingTask12Contracts()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var expectedOfferLocks = new[] { "offer-alpha", "offer-beta" };
        var snapshot = CreateSnapshot(expectedOfferLocks);

        await service.WriteAutosaveAsync(snapshot);
        var restored = await service.ReadAutosaveAsync();

        restored.Should().NotBeNull();
        restored!.SchemaVersion.Should().Be(snapshot.SchemaVersion);
        restored.SavePointId.Should().Be(snapshot.SavePointId);

        using var payloadDocument = JsonDocument.Parse(File.ReadAllText(sandbox.GetAbsolutePath("saves/autosave.json")));
        var payloadRoot = payloadDocument.RootElement;
        payloadRoot.TryGetProperty("schema_version", out var schemaVersionElement).Should().BeTrue();
        payloadRoot.TryGetProperty("save_point_id", out var savePointIdElement).Should().BeTrue();
        payloadRoot.TryGetProperty("offer_locks", out var offerLocksElement).Should().BeTrue();

        schemaVersionElement.ValueKind.Should().Be(JsonValueKind.String);
        savePointIdElement.ValueKind.Should().Be(JsonValueKind.String);
        offerLocksElement.ValueKind.Should().Be(JsonValueKind.Array);
        schemaVersionElement.GetString().Should().Be(snapshot.SchemaVersion);
        savePointIdElement.GetString().Should().Be(snapshot.SavePointId);
        offerLocksElement.EnumerateArray().Select(item => item.GetString()).Should().Equal(expectedOfferLocks);

        using var restoredState = JsonDocument.Parse(restored.StateJson);
        restoredState.RootElement.GetProperty("offer_locks")
            .EnumerateArray()
            .Select(item => item.GetString())
            .Should().Equal(expectedOfferLocks);
    }

    private static string[] ExtractRefPaths(string acceptanceItem)
    {
        if (string.IsNullOrWhiteSpace(acceptanceItem))
        {
            return Array.Empty<string>();
        }

        var markerIndex = acceptanceItem.IndexOf("Refs:", StringComparison.OrdinalIgnoreCase);
        if (markerIndex < 0)
        {
            return Array.Empty<string>();
        }

        var refsSegment = acceptanceItem[(markerIndex + "Refs:".Length)..];
        return Regex.Matches(refsSegment, @"[A-Za-z0-9._/\-]+\.(cs|gd)")
            .Select(match => match.Value)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static AutosaveSnapshot CreateSnapshot(string[] offerLocks)
    {
        var stateJson = JsonSerializer.Serialize(new
        {
            hp = 60,
            offer_locks = offerLocks,
        });

        return new AutosaveSnapshot(
            RunId: "run-contracts-1",
            SavePointId: "reward_open",
            SchemaVersion: "3",
            StateJson: stateJson,
            SavedAt: new DateTimeOffset(2026, 3, 6, 12, 0, 0, TimeSpan.Zero));
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
            var rootPath = Path.Combine(Path.GetTempPath(), "newrouge-contracts-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(rootPath);
            return new SaveServiceSandbox(rootPath);
        }

        public SaveService CreateService()
        {
            return new SaveService(new NoOpDataStore(), new DirectoryInfo(RootPath));
        }

        public string GetAbsolutePath(string relativePath)
        {
            return Path.Combine(RootPath, relativePath.Replace('/', Path.DirectorySeparatorChar));
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

    private sealed class NoOpDataStore : IDataStore
    {
        public Task SaveAsync(string key, string json)
        {
            throw new InvalidOperationException("Physical save path was expected instead of IDataStore.SaveAsync.");
        }

        public Task<string?> LoadAsync(string key)
        {
            throw new InvalidOperationException("Physical save path was expected instead of IDataStore.LoadAsync.");
        }

        public Task DeleteAsync(string key)
        {
            throw new InvalidOperationException("Physical save path was expected instead of IDataStore.DeleteAsync.");
        }
    }
}
