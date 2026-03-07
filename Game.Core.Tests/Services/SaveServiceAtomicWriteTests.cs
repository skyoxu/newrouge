using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Save;
using Game.Core.Ports;
using Xunit;

namespace Game.Core.Tests.Services;

// ADR refs: ADR-0032, ADR-0007.
[Collection("SaveServiceEnvironmentSerial")]
public sealed class SaveServiceAtomicWriteTests
{
    private static readonly object ActivationGate = new();
    private static readonly DateTimeOffset FixedSavedAt = new(2026, 1, 29, 12, 0, 0, TimeSpan.Zero);
    private static readonly string[] RequiredEvidenceKeys = { "ts", "action", "reason", "target", "caller", "run_id", "schema_version" };
    private const string SaveRootEnvVar = "NEWROUGE_SAVE_TEST_USER_ROOT";
    private const string SaveRelativePathEnvVar = "NEWROUGE_SAVE_TEST_RELATIVE_PATH";
    private const string SaveRelativePath = "saves/autosave.json";

    // ACC:T12.7
    // ACC:T12.9
    // ACC:T12.20
    // ACC:T12.21
    // ACC:T12.26
    [Fact]
    public async Task ShouldNotLeavePartialFileAndKeepPreviousSaveReadable_WhenReplaceFailsUnderExclusiveLock()
    {
        using var sandbox = SaveSandbox.Create();
        var previous = CreateSnapshot("run-previous", "reward_open", "1", "offer-a", "offer-b");
        var baseline = await WriteBaselineAsync(sandbox, previous);

        var next = CreateSnapshot("run-next", "event_enter", "1", "offer-c", "offer-d");
        Exception? error;
        using (new FileStream(baseline.TargetFilePath, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            error = await Record.ExceptionAsync(() => CreateService(sandbox).WriteAutosaveAsync(next));
        }

        error.Should().NotBeNull();
        (await CreateService(sandbox).ReadAutosaveAsync()).Should().BeEquivalentTo(previous);
        DiscoverTargetSaveFilePath(sandbox.RootPath, previous).Should().Be(baseline.TargetFilePath);
        File.ReadAllBytes(baseline.TargetFilePath).Should().Equal(baseline.BaselineBytes);
        AssertValidJson(baseline.TargetFilePath);
        GetNonLogFiles(sandbox.RootPath).Should().Equal(baseline.BaselineFiles);
    }

    // ACC:T12.8
    // ACC:T12.19
    [Fact]
    public async Task ShouldReplaceTargetWithLatestCompleteSnapshotAndCleanTransientFiles_WhenCommitSucceeds()
    {
        using var sandbox = SaveSandbox.Create();
        var previous = CreateSnapshot("run-previous", "combat_start", "1", "offer-a", "offer-b");
        var baseline = await WriteBaselineAsync(sandbox, previous);

        var next = CreateSnapshot("run-next", "shop_enter", "1", "offer-c", "offer-d");
        await FluentActions.Awaiting(() => CreateService(sandbox).WriteAutosaveAsync(next)).Should().NotThrowAsync();

        (await CreateService(sandbox).ReadAutosaveAsync()).Should().BeEquivalentTo(next);
        DiscoverTargetSaveFilePath(sandbox.RootPath, next).Should().Be(baseline.TargetFilePath);

        var currentBytes = File.ReadAllBytes(baseline.TargetFilePath);
        currentBytes.SequenceEqual(baseline.BaselineBytes).Should().BeFalse();

        var currentText = File.ReadAllText(baseline.TargetFilePath);
        currentText.Should().Contain(next.RunId);
        currentText.Should().Contain(next.SavePointId);
        currentText.Should().Contain("offer-c");
        currentText.Should().NotContain(previous.RunId);

        AssertValidJson(baseline.TargetFilePath);
        GetNonLogFiles(sandbox.RootPath).Should().Equal(baseline.BaselineFiles);
    }

    // ACC:T12.9
    // ACC:T12.25
    // ACC:T12.26
    // ACC:T12.27
    [Fact]
    public async Task ShouldPropagateContextErrorWithEvidenceFieldsAndPreservePreviousSave_WhenWriteFails()
    {
        using var sandbox = SaveSandbox.Create();
        var previous = CreateSnapshot("run-previous", "reward_open", "1", "offer-a", "offer-b");
        var baseline = await WriteBaselineAsync(sandbox, previous);

        var next = CreateSnapshot("run-next", "event_choice_committed", "2", "offer-x", "offer-y");
        Exception? error;
        using (new FileStream(baseline.TargetFilePath, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            error = await Record.ExceptionAsync(() => CreateService(sandbox).WriteAutosaveAsync(next));
        }

        error.Should().NotBeNull();
        error!.Message.Should().Contain(next.RunId);
        error.Message.Should().Contain(next.SavePointId);

        foreach (var key in RequiredEvidenceKeys)
        {
            error.Data.Contains(key).Should().BeTrue();
            error.Data[key]?.ToString().Should().NotBeNullOrWhiteSpace();
        }

        error.Data["run_id"]?.ToString().Should().Be(next.RunId);
        error.Data["schema_version"]?.ToString().Should().Be(next.SchemaVersion);
        (await CreateService(sandbox).ReadAutosaveAsync()).Should().BeEquivalentTo(previous);
        File.ReadAllBytes(baseline.TargetFilePath).Should().Equal(baseline.BaselineBytes);
        GetNonLogFiles(sandbox.RootPath).Should().Equal(baseline.BaselineFiles);
    }

    // ACC:T12.7
    // ACC:T12.25
    // ACC:T12.26
    // ACC:T12.27
    [Fact]
    public async Task ShouldPropagateContextErrorAndKeepPreviousSaveReadable_WhenTempWriteFailsBeforeReplace()
    {
        using var sandbox = SaveSandbox.Create();
        var previous = CreateSnapshot("run-previous", "reward_open", "1", "offer-a", "offer-b");
        var baseline = await WriteBaselineAsync(sandbox, previous);
        var blockedTempPath = baseline.TargetFilePath + ".tmp";
        Directory.CreateDirectory(blockedTempPath);

        var next = CreateSnapshot("run-next", "event_choice_committed", "2", "offer-x", "offer-y");
        var error = await Record.ExceptionAsync(() => CreateService(sandbox).WriteAutosaveAsync(next));

        error.Should().NotBeNull();
        error!.Message.Should().Contain(next.RunId);
        error.Message.Should().Contain(next.SavePointId);
        error.Message.Should().Contain("reason_code=temp_write_failed");
        error.Data["action"]?.ToString().Should().Be("write_temp");
        error.Data["reason"]?.ToString().Should().Be("temp_write_failed");
        error.Data["target"]?.ToString().Should().Be("user://saves/autosave.json");
        error.Data["temp_path"]?.ToString().Should().Be(blockedTempPath);
        error.Data["run_id"]?.ToString().Should().Be(next.RunId);
        error.Data["schema_version"]?.ToString().Should().Be(next.SchemaVersion);
        error.Data["save_point_id"]?.ToString().Should().Be(next.SavePointId);
        error.InnerException.Should().NotBeNull();
        (error.InnerException is UnauthorizedAccessException || error.InnerException is IOException).Should().BeTrue();
        (await CreateService(sandbox).ReadAutosaveAsync()).Should().BeEquivalentTo(previous);
        File.ReadAllBytes(baseline.TargetFilePath).Should().Equal(baseline.BaselineBytes);
        GetNonLogFiles(sandbox.RootPath).Should().Equal(baseline.BaselineFiles);
    }

    private static async Task<(string[] BaselineFiles, string TargetFilePath, byte[] BaselineBytes)> WriteBaselineAsync(SaveSandbox sandbox, AutosaveSnapshot snapshot)
    {
        await FluentActions.Awaiting(() => CreateService(sandbox).WriteAutosaveAsync(snapshot)).Should().NotThrowAsync();
        (await CreateService(sandbox).ReadAutosaveAsync()).Should().BeEquivalentTo(snapshot);

        var baselineFiles = GetNonLogFiles(sandbox.RootPath);
        var targetFilePath = DiscoverTargetSaveFilePath(sandbox.RootPath, snapshot);
        var baselineBytes = File.ReadAllBytes(targetFilePath);
        AssertValidJson(targetFilePath);
        return (baselineFiles, targetFilePath, baselineBytes);
    }

    private static AutosaveSnapshot CreateSnapshot(string runId, string savePointId, string schemaVersion, params string[] offerLocks)
    {
        var payload = JsonSerializer.Serialize(new
        {
            schema_version = schemaVersion,
            save_point_id = savePointId,
            offer_locks = offerLocks,
            resources = new { gold = 123, hp = 47 }
        });

        return new AutosaveSnapshot(runId, savePointId, schemaVersion, payload, FixedSavedAt);
    }

    private static ISaveService CreateService(SaveSandbox sandbox)
    {
        lock (ActivationGate)
        {
            Environment.SetEnvironmentVariable(SaveRootEnvVar, sandbox.RootPath);
            Environment.SetEnvironmentVariable(SaveRelativePathEnvVar, SaveRelativePath);

            var candidates = typeof(ISaveService).Assembly
                .GetTypes()
                .Where(type => typeof(ISaveService).IsAssignableFrom(type))
                .Where(type => !type.IsInterface && !type.IsAbstract)
                .OrderBy(type => type.Name.Equals("SaveService", StringComparison.Ordinal) ? 0 : 1)
                .ThenBy(type => type.FullName, StringComparer.Ordinal)
                .ToArray();

            if (candidates.Length == 0)
            {
                throw new InvalidOperationException("No concrete ISaveService implementation was found in Game.Core.");
            }

            foreach (var candidate in candidates)
            {
                foreach (var constructor in candidate.GetConstructors().OrderByDescending(ctor => ctor.GetParameters().Length))
                {
                    if (!TryCreateArguments(constructor.GetParameters(), sandbox, out var arguments))
                    {
                        continue;
                    }

                    if (constructor.Invoke(arguments) is ISaveService service)
                    {
                        return service;
                    }
                }
            }

            throw new InvalidOperationException("No ISaveService constructor matched the supported test dependencies.");
        }
    }

    private static bool TryCreateArguments(ParameterInfo[] parameters, SaveSandbox sandbox, out object?[] arguments)
    {
        arguments = new object?[parameters.Length];
        for (var index = 0; index < parameters.Length; index++)
        {
            var parameterType = parameters[index].ParameterType;
            if (parameterType == typeof(string))
            {
                arguments[index] = sandbox.RootPath;
                continue;
            }

            if (parameterType == typeof(DirectoryInfo))
            {
                arguments[index] = new DirectoryInfo(sandbox.RootPath);
                continue;
            }

            if (parameterType == typeof(IDataStore))
            {
                arguments[index] = new SandboxDataStore(sandbox.RootPath);
                continue;
            }

            if (parameterType == typeof(IEventBus))
            {
                arguments[index] = new NullEventBus();
                continue;
            }

            if (parameterType == typeof(ITime))
            {
                arguments[index] = new FixedTime();
                continue;
            }

            if (parameterType == typeof(ILogger))
            {
                arguments[index] = new NullLogger();
                continue;
            }

            if (parameterType == typeof(JsonSerializerOptions))
            {
                arguments[index] = new JsonSerializerOptions(JsonSerializerDefaults.Web);
                continue;
            }

            return false;
        }

        return true;
    }

    private static string DiscoverTargetSaveFilePath(string rootPath, AutosaveSnapshot snapshot)
    {
        var candidates = Directory.EnumerateFiles(rootPath, "*", SearchOption.AllDirectories)
            .Where(path => IsNonLogFile(rootPath, path))
            .Where(path => ContainsSnapshotIdentity(path, snapshot))
            .OrderBy(path => path.Length)
            .ToArray();

        candidates.Should().ContainSingle();
        return candidates[0];
    }

    private static bool ContainsSnapshotIdentity(string filePath, AutosaveSnapshot snapshot)
    {
        var content = TryReadAllText(filePath);
        if (string.IsNullOrWhiteSpace(content))
        {
            return false;
        }

        if (!content.Contains(snapshot.RunId, StringComparison.Ordinal) ||
            !content.Contains(snapshot.SavePointId, StringComparison.Ordinal))
        {
            return false;
        }

        using var document = JsonDocument.Parse(snapshot.StateJson);
        var offerLocks = document.RootElement.GetProperty("offer_locks").EnumerateArray()
            .Select(item => item.GetString())
            .Where(item => item is not null)
            .Cast<string>();

        return offerLocks.All(lockId => content.Contains(lockId, StringComparison.Ordinal));
    }

    private static string? TryReadAllText(string filePath)
    {
        try
        {
            return File.ReadAllText(filePath);
        }
        catch
        {
            return null;
        }
    }

    private static void AssertValidJson(string filePath)
    {
        var act = () => JsonDocument.Parse(File.ReadAllText(filePath));
        act.Should().NotThrow();
    }

    private static string[] GetNonLogFiles(string rootPath)
    {
        if (!Directory.Exists(rootPath))
        {
            return Array.Empty<string>();
        }

        return Directory.EnumerateFiles(rootPath, "*", SearchOption.AllDirectories)
            .Where(path => IsNonLogFile(rootPath, path))
            .Select(path => Path.GetRelativePath(rootPath, path).Replace('\\', '/'))
            .OrderBy(path => path, StringComparer.Ordinal)
            .ToArray();
    }

    private static bool IsNonLogFile(string rootPath, string absolutePath)
    {
        var relativePath = Path.GetRelativePath(rootPath, absolutePath).Replace('\\', '/');
        return !relativePath.StartsWith("logs/", StringComparison.OrdinalIgnoreCase);
    }

    private sealed class SaveSandbox : IDisposable
    {
        private SaveSandbox(string rootPath) => RootPath = rootPath;
        public string RootPath { get; }

        public static SaveSandbox Create()
        {
            var rootPath = Path.Combine(Path.GetTempPath(), "newrouge-save-atomic-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(rootPath);
            return new SaveSandbox(rootPath);
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

    private sealed class SandboxDataStore : IDataStore
    {
        private readonly string _rootPath;
        public SandboxDataStore(string rootPath) => _rootPath = rootPath;

        public Task SaveAsync(string key, string json)
        {
            var filePath = ResolveFilePath(key);
            var directoryPath = Path.GetDirectoryName(filePath);
            if (!string.IsNullOrWhiteSpace(directoryPath))
            {
                Directory.CreateDirectory(directoryPath);
            }

            File.WriteAllText(filePath, json);
            return Task.CompletedTask;
        }

        public Task<string?> LoadAsync(string key)
        {
            var filePath = ResolveFilePath(key);
            return Task.FromResult(File.Exists(filePath) ? File.ReadAllText(filePath) : null);
        }

        public Task DeleteAsync(string key)
        {
            var filePath = ResolveFilePath(key);
            if (File.Exists(filePath))
            {
                File.Delete(filePath);
            }

            return Task.CompletedTask;
        }

        private string ResolveFilePath(string key)
        {
            var normalized = key.Replace("user://", string.Empty, StringComparison.OrdinalIgnoreCase)
                .Replace('\\', '/')
                .Trim('/');

            if (string.IsNullOrWhiteSpace(normalized))
            {
                normalized = "autosave";
            }

            var segments = normalized.Split('/', StringSplitOptions.RemoveEmptyEntries)
                .Select(SanitizeSegment)
                .ToArray();

            var relativePath = Path.Combine(segments);
            if (!Path.HasExtension(relativePath))
            {
                relativePath += ".json";
            }

            return Path.Combine(_rootPath, relativePath);
        }

        private static string SanitizeSegment(string value)
        {
            var invalidCharacters = Path.GetInvalidFileNameChars();
            return new string(value.Select(ch => invalidCharacters.Contains(ch) ? '_' : ch).ToArray());
        }
    }

    private sealed class NullEventBus : IEventBus
    {
        public Task PublishAsync(DomainEvent evt) => Task.CompletedTask;
        public IDisposable Subscribe(Func<DomainEvent, Task> handler) => NoopDisposable.Instance;
    }

    private sealed class FixedTime : ITime
    {
        public double DeltaSeconds => 0d;
    }

    private sealed class NullLogger : ILogger
    {
        public void Info(string message) { }
        public void Warn(string message) { }
        public void Error(string message) { }
        public void Error(string message, Exception ex) { }
    }

    private sealed class NoopDisposable : IDisposable
    {
        public static NoopDisposable Instance { get; } = new();
        public void Dispose() { }
    }
}
