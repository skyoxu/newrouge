using System;
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

// Traceability: ADR-0032, ADR-0023.
[Collection("SaveServiceEnvironmentSerial")]
[Trait("task", "T12")]
[Trait("adr", "ADR-0032")]
[Trait("adr", "ADR-0023")]
public sealed class Task0012AcceptanceTests
{
    private const string SaveRelativePathEnvVar = "NEWROUGE_SAVE_TEST_RELATIVE_PATH";
    private const string DefaultRelativePath = "saves/autosave.json";

    // ACC:T12.1
    [Fact]
    public async Task ShouldPreserveSerializedSavePayload_WhenAtomicReplaceCommitsLatestWrite()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var previous = CreateSnapshot(savePointId: "save-point-11", schemaVersion: "schema-11");
        var next = CreateSnapshot(savePointId: "save-point-12", schemaVersion: "schema-12");

        await service.WriteAutosaveAsync(previous);
        await service.WriteAutosaveAsync(next);
        var restored = await service.ReadAutosaveAsync();

        restored.Should().NotBeNull();
        restored!.RunId.Should().Be(next.RunId);
        restored.SavePointId.Should().Be(next.SavePointId);
        restored.SchemaVersion.Should().Be(next.SchemaVersion);
        restored.StateJson.Should().Be(next.StateJson);

        var committedContent = sandbox.ReadPersisted(DefaultRelativePath);
        committedContent.Should().Contain("\"schema_version\":\"schema-12\"");
        committedContent.Should().Contain("\"save_point_id\":\"save-point-12\"");
        committedContent.Should().Contain("\"offer_locks\"");
        sandbox.GetPersistedRelativePaths().Should().Equal(DefaultRelativePath);
        sandbox.Exists(DefaultRelativePath + ".tmp").Should().BeFalse();

        SaveWriteSucceededEvent.EventType.Should().Be(EventTypes.SaveWriteSucceeded);
        SaveLoadedEvent.EventType.Should().Be(EventTypes.SaveLoaded);
    }

    // ACC:T12.2
    [Theory]
    [InlineData("C:/temp/slot-01.json", "path_outside_user_scope")]
    [InlineData("/tmp/slot-01.json", "path_outside_user_scope")]
    [InlineData("../slot-01.json", "path_contains_traversal")]
    [InlineData("user://saves/../slot-01.json", "path_contains_traversal")]
    [InlineData("user://profiles/../../config.json", "path_contains_traversal")]
    public void ShouldRejectInvalidWriteTargets_WhenPathIsNotAUserRelativeSavePath(string candidatePath, string expectedReason)
    {
        using var sandbox = SaveServiceSandbox.Create();
        using var _ = SaveServiceEnvironment.Override(SaveRelativePathEnvVar, candidatePath);

        var exception = FluentActions.Invoking(() => sandbox.CreateService())
            .Should().Throw<InvalidOperationException>()
            .Which;

        exception.Data["reason"].Should().Be(expectedReason);
        exception.Data["input_path"].Should().Be(candidatePath);
        exception.Data["write_intent"].Should().Be("none");
        sandbox.GetPersistedRelativePaths().Should().BeEmpty();
    }

    // ACC:T12.3
    [Fact]
    public async Task ShouldPreserveLastCommittedContentAndEmitEvidence_WhenAtomicReplaceFails()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var previous = CreateSnapshot(savePointId: "save-point-previous", schemaVersion: "schema-11");
        await service.WriteAutosaveAsync(previous);
        var baselineContent = sandbox.ReadPersisted(DefaultRelativePath);
        var targetFilePath = sandbox.GetAbsolutePath(DefaultRelativePath);

        var next = CreateSnapshot(savePointId: "save-point-next", schemaVersion: "schema-12");
        Exception? error;
        using (new FileStream(targetFilePath, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            error = await Record.ExceptionAsync(() => service.WriteAutosaveAsync(next));
        }

        error.Should().NotBeNull();
        error.Should().BeOfType<InvalidOperationException>();
        error!.Message.Should().Contain("reason_code=atomic_replace_failed");
        error.Data["action"].Should().Be("replace_target");
        error.Data["reason"].Should().Be("atomic_replace_failed");
        error.Data["target"].Should().Be("user://saves/autosave.json");
        error.Data["temp_path"].Should().NotBeNull();
        error.Data["caller"].Should().Be(nameof(SaveService));
        error.Data["run_id"].Should().Be(next.RunId);
        error.Data["schema_version"].Should().Be(next.SchemaVersion);
        error.Data["save_point_id"].Should().Be(next.SavePointId);
        error.InnerException.Should().NotBeNull();
        (error.InnerException is IOException || error.InnerException is UnauthorizedAccessException).Should().BeTrue();

        (await sandbox.CreateService().ReadAutosaveAsync()).Should().BeEquivalentTo(previous);
        sandbox.ReadPersisted(DefaultRelativePath).Should().Be(baselineContent);
        sandbox.Exists(DefaultRelativePath + ".tmp").Should().BeFalse();
        SaveWriteFailedEvent.EventType.Should().Be(EventTypes.SaveWriteFailed);
    }

    private static AutosaveSnapshot CreateSnapshot(string savePointId, string schemaVersion)
    {
        var stateJson = JsonSerializer.Serialize(new
        {
            turn = 1,
            offer_locks = new[] { "offer-alpha", "offer-beta" },
        });

        return new AutosaveSnapshot(
            RunId: "run-001",
            SavePointId: savePointId,
            SchemaVersion: schemaVersion,
            StateJson: stateJson,
            SavedAt: new DateTimeOffset(2026, 3, 6, 8, 0, 0, TimeSpan.Zero));
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
            var rootPath = Path.Combine(Path.GetTempPath(), "newrouge-task0012-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(rootPath);
            return new SaveServiceSandbox(rootPath);
        }

        public ISaveService CreateService()
        {
            return new SaveService(new NoOpDataStore(), new DirectoryInfo(RootPath));
        }

        public string ReadPersisted(string relativePath)
        {
            return File.ReadAllText(GetAbsolutePath(relativePath));
        }

        public bool Exists(string relativePath)
        {
            return File.Exists(GetAbsolutePath(relativePath));
        }

        public string GetAbsolutePath(string relativePath)
        {
            return Path.Combine(RootPath, relativePath.Replace('/', Path.DirectorySeparatorChar));
        }

        public string[] GetPersistedRelativePaths()
        {
            if (!Directory.Exists(RootPath))
            {
                return Array.Empty<string>();
            }

            return Directory.EnumerateFiles(RootPath, "*", SearchOption.AllDirectories)
                .Select(path => Path.GetRelativePath(RootPath, path).Replace("\\", "/"))
                .OrderBy(path => path, StringComparer.Ordinal)
                .ToArray();
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

    private sealed class SaveServiceEnvironment : IDisposable
    {
        private readonly string _variableName;
        private readonly string? _originalValue;

        private SaveServiceEnvironment(string variableName, string value)
        {
            _variableName = variableName;
            _originalValue = Environment.GetEnvironmentVariable(variableName);
            Environment.SetEnvironmentVariable(variableName, value);
        }

        public static SaveServiceEnvironment Override(string variableName, string value)
        {
            return new SaveServiceEnvironment(variableName, value);
        }

        public void Dispose()
        {
            Environment.SetEnvironmentVariable(_variableName, _originalValue);
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
