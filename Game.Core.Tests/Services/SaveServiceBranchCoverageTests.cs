using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
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

namespace Game.Core.Tests.Services;

public sealed class SaveServiceBranchCoverageTests
{
    private static readonly DateTimeOffset FixedSavedAt = new(2026, 5, 1, 12, 30, 0, TimeSpan.Zero);

    [Fact]
    public async Task ShouldReturnRunSummaryDefault_WhenRunSummaryShapeIsInvalid()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var snapshot = CreateSnapshot(
            runId: "run-default-summary",
            stateJson: JsonSerializer.Serialize(new
            {
                difficulty = new
                {
                    difficulty_id = 3,
                    label_key = "difficulty.label.hard",
                    description_key = "difficulty.description.hard",
                    ruleset_id = "ruleset.hard",
                },
            }));
        await service.WriteAutosaveAsync(snapshot);

        var summary = await service.ReadRunSummaryMetadataAsync();

        summary.Should().NotBeNull();
        summary!.Outcome.Should().Be("Unknown");
        summary.NodeProgress.Should().Be(0);
        summary.FailureOrRecoveryReason.Should().Be("No stored run summary reason.");
        summary.OwnerSurface.Should().Be(RunSummaryOwnerSurface.HudOverlay);
    }

    [Fact]
    public async Task ShouldResolveOwnerSurfaceFromString_AndFallbackWhenInvalid()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();

        var validState = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 3,
                label_key = "difficulty.label.hard",
                description_key = "difficulty.description.hard",
                ruleset_id = "ruleset.hard",
            },
            run_summary = new
            {
                outcome = "Victory",
                node_progress = 8,
                failure_or_recovery_reason = "none",
                owner_surface = "MainMenuMetadataPanel",
            },
        });
        await service.WriteAutosaveAsync(CreateSnapshot("run-owner-valid", validState));
        var valid = await service.ReadRunSummaryMetadataAsync();
        valid!.OwnerSurface.Should().Be(RunSummaryOwnerSurface.MainMenuMetadataPanel);

        var invalidState = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 3,
                label_key = "difficulty.label.hard",
                description_key = "difficulty.description.hard",
                ruleset_id = "ruleset.hard",
            },
            run_summary = new
            {
                outcome = "Retreat",
                node_progress = 5,
                failure_or_recovery_reason = "manual",
                owner_surface = "NotARealSurface",
            },
        });
        await service.WriteAutosaveAsync(CreateSnapshot("run-owner-invalid", invalidState));
        var invalid = await service.ReadRunSummaryMetadataAsync();
        invalid!.OwnerSurface.Should().Be(RunSummaryOwnerSurface.HudOverlay);
    }

    [Fact]
    public async Task ShouldReturnRunSummaryDefault_WhenNodeProgressNegative()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var negativeNodeProgressState = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 3,
                label_key = "difficulty.label.hard",
                description_key = "difficulty.description.hard",
                ruleset_id = "ruleset.hard",
            },
            run_summary = new
            {
                outcome = "Defeat",
                node_progress = -1,
                failure_or_recovery_reason = "invalid-progress",
                owner_surface = (int)RunSummaryOwnerSurface.IndependentScreen,
            },
        });
        await service.WriteAutosaveAsync(CreateSnapshot("run-negative-progress", negativeNodeProgressState));

        var summary = await service.ReadRunSummaryMetadataAsync();

        summary.Should().NotBeNull();
        summary!.Outcome.Should().Be("Unknown");
        summary.NodeProgress.Should().Be(0);
        summary.FailureOrRecoveryReason.Should().Be("No stored run summary reason.");
        summary.OwnerSurface.Should().Be(RunSummaryOwnerSurface.HudOverlay);
    }

    [Fact]
    public async Task ShouldReturnDefaultContinueValidation_WhenEnvelopeHasMalformedStateJson()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var malformedState = "{\"difficulty\":";
        var envelope = BuildEnvelopeJson(
            runId: "run-malformed",
            savePointId: "node-branch",
            schemaVersion: "1.0.0",
            stateJson: malformedState,
            savedAt: FixedSavedAt,
            integrityHash: ComputeHash(malformedState));
        Directory.CreateDirectory(Path.GetDirectoryName(sandbox.SaveFilePath)!);
        File.WriteAllText(sandbox.SaveFilePath, envelope, new UTF8Encoding(false));

        var validation = await sandbox.CreateService().ValidateContinueLoadAsync();

        validation.ContinueAllowed.Should().BeFalse();
        validation.ErrorCode.Should().Be("invalid_metadata");
    }

    [Fact]
    public async Task ShouldUseDataStoreBranchAndSurfaceSaveFailedReason_WhenSaveThrows()
    {
        var dataStore = new ThrowingDataStore();
        var service = new SaveService(dataStore, new DirectoryInfo(Path.GetTempPath()), eventBus: null, logger: null);
        ForceDataStoreBranch(service);
        var snapshot = CreateSnapshot(
            runId: "run-fail",
            stateJson: JsonSerializer.Serialize(new
            {
                difficulty = new
                {
                    difficulty_id = 3,
                    label_key = "difficulty.label.hard",
                    description_key = "difficulty.description.hard",
                    ruleset_id = "ruleset.hard",
                },
                run_summary = new
                {
                    outcome = "Victory",
                    node_progress = 7,
                    failure_or_recovery_reason = "none",
                    owner_surface = (int)RunSummaryOwnerSurface.IndependentScreen,
                },
            }));

        var exception = await Record.ExceptionAsync(() => service.WriteAutosaveAsync(snapshot));

        exception.Should().BeOfType<InvalidOperationException>();
        var invalid = (InvalidOperationException)exception!;
        invalid.Data["reason"].Should().Be("save_failed");
        invalid.Data["action"].Should().Be("save_store");
        invalid.Data["target"].Should().Be("user://saves/autosave.json");
        invalid.Data["run_id"].Should().Be("run-fail");
    }

    [Fact]
    public async Task ShouldSwallowEventPublishErrorsAndLogWarning_WhenEventBusThrows()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var logger = new RecordingLogger();
        var service = sandbox.CreateService(eventBus: new ThrowingEventBus(), logger: logger);
        var snapshot = CreateSnapshot(
            runId: "run-publish",
            stateJson: JsonSerializer.Serialize(new
            {
                difficulty = new
                {
                    difficulty_id = 3,
                    label_key = "difficulty.label.hard",
                    description_key = "difficulty.description.hard",
                    ruleset_id = "ruleset.hard",
                },
                run_summary = new
                {
                    outcome = "Victory",
                    node_progress = 7,
                    failure_or_recovery_reason = "none",
                    owner_surface = (int)RunSummaryOwnerSurface.IndependentScreen,
                },
            }));

        await service.WriteAutosaveAsync(snapshot);

        logger.Warnings.Should().ContainSingle();
        logger.Warnings[0].Should().Contain("Save event publish failed");
    }

    [Fact]
    public void ShouldCoverPrivateParsingBranches_WhenInvokingHelpersViaReflection()
    {
        var getFullPathOrNull = typeof(SaveService).GetMethod("GetFullPathOrNull", BindingFlags.NonPublic | BindingFlags.Static);
        getFullPathOrNull.Should().NotBeNull();
        getFullPathOrNull!.Invoke(null, new object?[] { null }).Should().BeNull();
        getFullPathOrNull.Invoke(null, new object?[] { "." }).Should().BeOfType<string>();

        using var numberDoc = JsonDocument.Parse("""{"difficulty_id":3}""");
        using var stringDoc = JsonDocument.Parse("""{"difficulty_id":"4"}""");
        using var invalidDoc = JsonDocument.Parse("""{"difficulty_id":"not-int"}""");
        using var missingDoc = JsonDocument.Parse("""{"other":1}""");

        var tryReadIntValue = typeof(SaveService).GetMethod("TryReadIntValue", BindingFlags.NonPublic | BindingFlags.Static);
        tryReadIntValue.Should().NotBeNull();

        var intArgs = new object?[] { numberDoc.RootElement, "difficulty_id", 0 };
        ((bool)tryReadIntValue!.Invoke(null, intArgs)!).Should().BeTrue();
        intArgs[2].Should().Be(3);

        var stringArgs = new object?[] { stringDoc.RootElement, "difficulty_id", 0 };
        ((bool)tryReadIntValue.Invoke(null, stringArgs)!).Should().BeTrue();
        stringArgs[2].Should().Be(4);

        var invalidArgs = new object?[] { invalidDoc.RootElement, "difficulty_id", 0 };
        ((bool)tryReadIntValue.Invoke(null, invalidArgs)!).Should().BeFalse();

        var missingArgs = new object?[] { missingDoc.RootElement, "difficulty_id", 0 };
        ((bool)tryReadIntValue.Invoke(null, missingArgs)!).Should().BeFalse();

        using var ownerNumericDoc = JsonDocument.Parse("""{"owner_surface":2}""");
        using var ownerStringDoc = JsonDocument.Parse("""{"owner_surface":"HudOverlay"}""");
        using var ownerInvalidDoc = JsonDocument.Parse("""{"owner_surface":"NotReal"}""");
        using var ownerMissingDoc = JsonDocument.Parse("""{}""");
        var tryReadOwnerSurface = typeof(SaveService).GetMethod("TryReadOwnerSurface", BindingFlags.NonPublic | BindingFlags.Static);
        tryReadOwnerSurface.Should().NotBeNull();

        var ownerNumericArgs = new object?[] { ownerNumericDoc.RootElement, RunSummaryOwnerSurface.HudOverlay };
        ((bool)tryReadOwnerSurface!.Invoke(null, ownerNumericArgs)!).Should().BeTrue();
        ownerNumericArgs[1].Should().Be(RunSummaryOwnerSurface.MainMenuMetadataPanel);

        var ownerStringArgs = new object?[] { ownerStringDoc.RootElement, RunSummaryOwnerSurface.HudOverlay };
        ((bool)tryReadOwnerSurface.Invoke(null, ownerStringArgs)!).Should().BeTrue();
        ownerStringArgs[1].Should().Be(RunSummaryOwnerSurface.HudOverlay);

        var ownerInvalidArgs = new object?[] { ownerInvalidDoc.RootElement, RunSummaryOwnerSurface.HudOverlay };
        ((bool)tryReadOwnerSurface.Invoke(null, ownerInvalidArgs)!).Should().BeFalse();

        var ownerMissingArgs = new object?[] { ownerMissingDoc.RootElement, RunSummaryOwnerSurface.HudOverlay };
        ((bool)tryReadOwnerSurface.Invoke(null, ownerMissingArgs)!).Should().BeFalse();

        var tryReadCompleteDifficultySnapshot = typeof(SaveService).GetMethod("TryReadCompleteDifficultySnapshot", BindingFlags.NonPublic | BindingFlags.Static);
        tryReadCompleteDifficultySnapshot.Should().NotBeNull();
        var outType = tryReadCompleteDifficultySnapshot!.GetParameters()[1].ParameterType.GetElementType();
        outType.Should().NotBeNull();
        var whitespaceArgs = new object?[] { "   ", null };
        ((bool)tryReadCompleteDifficultySnapshot.Invoke(null, whitespaceArgs)!).Should().BeFalse();
        var malformedArgs = new object?[] { "{", null };
        ((bool)tryReadCompleteDifficultySnapshot.Invoke(null, malformedArgs)!).Should().BeFalse();
    }

    private static AutosaveSnapshot CreateSnapshot(string runId, string stateJson)
    {
        return new AutosaveSnapshot(
            RunId: runId,
            SavePointId: "node-branch",
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: FixedSavedAt);
    }

    private static string BuildEnvelopeJson(
        string runId,
        string savePointId,
        string schemaVersion,
        string stateJson,
        DateTimeOffset savedAt,
        string integrityHash)
    {
        return JsonSerializer.Serialize(new
        {
            run_id = runId,
            save_point_id = savePointId,
            schema_version = schemaVersion,
            saved_at = savedAt,
            state_json = stateJson,
            offer_locks = Array.Empty<string>(),
            integrity_hash = integrityHash,
        });
    }

    private static string ComputeHash(string content)
    {
        var bytes = Encoding.UTF8.GetBytes(content);
        return Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    }

    private static void ForceDataStoreBranch(SaveService service)
    {
        var field = typeof(SaveService).GetField("_physicalUserRoot", BindingFlags.Instance | BindingFlags.NonPublic);
        field.Should().NotBeNull();
        field!.SetValue(service, null);
    }

    private sealed class SaveServiceSandbox : IDisposable
    {
        private const string SaveRelativePath = "saves/autosave.json";

        private SaveServiceSandbox(string rootPath)
        {
            RootPath = rootPath;
        }

        public string RootPath { get; }

        public string SaveFilePath => Path.Combine(RootPath, SaveRelativePath.Replace('/', Path.DirectorySeparatorChar));

        public static SaveServiceSandbox Create()
        {
            var rootPath = Path.Combine(Path.GetTempPath(), "newrouge-save-branch-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(rootPath);
            return new SaveServiceSandbox(rootPath);
        }

        public SaveService CreateService(IEventBus? eventBus = null, ILogger? logger = null)
        {
            return new SaveService(new InMemoryDataStore(), new DirectoryInfo(RootPath), eventBus: eventBus, logger: logger);
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

    private sealed class InMemoryDataStore : IDataStore
    {
        public Task SaveAsync(string key, string json) => Task.CompletedTask;
        public Task<string?> LoadAsync(string key) => Task.FromResult<string?>(null);
        public Task DeleteAsync(string key) => Task.CompletedTask;
    }

    private sealed class ThrowingDataStore : IDataStore
    {
        public Task SaveAsync(string key, string json)
        {
            throw new IOException("disk full");
        }

        public Task<string?> LoadAsync(string key)
        {
            return Task.FromResult<string?>(null);
        }

        public Task DeleteAsync(string key)
        {
            return Task.CompletedTask;
        }
    }

    private sealed class ThrowingEventBus : IEventBus
    {
        public Task PublishAsync(DomainEvent evt)
        {
            throw new InvalidOperationException("publish failed");
        }

        public IDisposable Subscribe(Func<DomainEvent, Task> handler) => NoopDisposable.Instance;
    }

    private sealed class RecordingLogger : ILogger
    {
        public List<string> Warnings { get; } = new();

        public void Info(string message)
        {
        }

        public void Warn(string message)
        {
            Warnings.Add(message);
        }

        public void Error(string message)
        {
        }

        public void Error(string message, Exception ex)
        {
        }
    }

    private sealed class NoopDisposable : IDisposable
    {
        public static NoopDisposable Instance { get; } = new();
        public void Dispose()
        {
        }
    }
}
