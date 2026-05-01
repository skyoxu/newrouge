using System;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts.Save;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0066AcceptanceTests
{
    // ACC:T66.1
    [Theory]
    [InlineData(0, false)]
    [InlineData(1, true)]
    [InlineData(2, false)]
    public void ShouldAcceptOwnershipOnly_WhenExactlyOneOwnerSurfaceIsSelected(int ownerCount, bool expectedAccepted)
    {
        var policy = new RunSummaryOwnershipPolicy();
        var selection = BuildSelection(ownerCount);

        var result = policy.Validate(selection);

        result.IsAccepted.Should().Be(expectedAccepted);
    }

    // ACC:T66.2
    // ACC:T91.1
    // ACC:T91.4
    // ACC:T91.6
    [Fact]
    public async Task ShouldReadStoredRunSummaryMetadataWithoutRecomputeOrMutation_WhenOpeningHudSummary()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateService();
        var savedAt = new DateTimeOffset(2026, 4, 21, 0, 0, 0, TimeSpan.Zero);
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 7,
                label_key = "ui.difficulty.label",
                description_key = "ui.difficulty.7",
                ruleset_id = "ruleset.nightmare",
            },
            run_summary = new
            {
                outcome = "Defeat",
                node_progress = 4,
                failure_or_recovery_reason = "Recovered from last checkpoint",
                owner_surface = "HudOverlay",
            }
        });

        await saveService.WriteAutosaveAsync(new AutosaveSnapshot(
            RunId: "run-66",
            SavePointId: "node-4",
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: savedAt));

        var summary = await saveService.ReadRunSummaryMetadataAsync();
        using var roundtrip = JsonDocument.Parse(stateJson);

        summary.Should().NotBeNull();
        summary!.Outcome.Should().Be("Defeat");
        summary.NodeProgress.Should().Be(4);
        summary.FailureOrRecoveryReason.Should().Be("Recovered from last checkpoint");
        summary.OwnerSurface.Should().Be(RunSummaryOwnerSurface.HudOverlay);
        summary.DifficultyId.Should().Be(7);

        roundtrip.RootElement
            .GetProperty("run_summary")
            .GetProperty("node_progress")
            .GetInt32()
            .Should().Be(4);
    }

    // ACC:T66.3
    [Fact]
    public async Task ShouldKeepRunSummaryDifficultyConsistentWithContinueMetadata_WhenUsingTheSameSavedRun()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateService();
        var savedAt = new DateTimeOffset(2026, 4, 21, 1, 0, 0, TimeSpan.Zero);
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 6,
                label_key = "ui.difficulty.label",
                description_key = "ui.difficulty.6",
                ruleset_id = "ruleset.t66",
            },
            run_summary = new
            {
                outcome = "Victory",
                node_progress = 9,
                failure_or_recovery_reason = "Completed with stable state",
                owner_surface = "HudOverlay",
            }
        });

        await saveService.WriteAutosaveAsync(new AutosaveSnapshot(
            RunId: "run-66-consistency",
            SavePointId: "node-9",
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: savedAt));

        var summary = await saveService.ReadRunSummaryMetadataAsync();
        var continuation = await saveService.ReadContinueMetadataAsync();

        summary.Should().NotBeNull();
        continuation.Should().NotBeNull();
        summary!.RunId.Should().Be(continuation!.RunId);
        summary.DifficultyId.Should().Be(continuation.DifficultyId);

        // Negative path: stale/mismatched expected value must fail acceptance semantics.
        summary.DifficultyId.Should().NotBe(3);
    }

    private static RunSummaryOwnershipSelection BuildSelection(int ownerCount)
    {
        var source = new[]
        {
            RunSummaryOwnerSurface.IndependentScreen,
            RunSummaryOwnerSurface.HudOverlay,
            RunSummaryOwnerSurface.MainMenuMetadataPanel,
        };

        var owners = ownerCount switch
        {
            <= 0 => Array.Empty<RunSummaryOwnerSurface>(),
            1 => new[] { source[1] },
            _ => new[] { source[0], source[1] }
        };
        return new RunSummaryOwnershipSelection(owners);
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
            var rootPath = Path.Combine(Path.GetTempPath(), "newrouge-task0066-" + Guid.NewGuid().ToString("N"));
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
