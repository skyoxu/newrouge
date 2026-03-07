using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Save;
using Game.Core.Ports;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

[Collection("SaveServiceEnvironmentSerial")]
[Trait("task", "T12")]
[Trait("adr", "ADR-0032")]
[Trait("adr", "ADR-0023")]
public sealed class SaveServicePathValidationTests
{
    private const string SaveRelativePathEnvVar = "NEWROUGE_SAVE_TEST_RELATIVE_PATH";
    private static readonly DateTimeOffset FixedSavedAt = new(2026, 3, 6, 12, 0, 0, TimeSpan.Zero);

    // ACC:T12.10
    // ACC:T12.14
    // ACC:T12.22
    // ACC:T12.24
    [Theory]
    [InlineData("user://saves/slot-01.json", "saves/slot-01.json")]
    [InlineData("user://profiles/main\\continue.save", "profiles/main/continue.save")]
    public async Task ShouldPersistAutosaveUnderNormalizedUserRelativePath_WhenPathIsValid(string configuredPath, string expectedRelativePath)
    {
        using var sandbox = SaveServiceSandbox.Create();
        using var _ = SaveServiceEnvironment.Override(SaveRelativePathEnvVar, configuredPath);
        var service = sandbox.CreateService();
        var snapshot = CreateSnapshot();

        await service.WriteAutosaveAsync(snapshot);

        sandbox.GetPersistedRelativePaths().Should().ContainSingle(expectedRelativePath);

        using var document = JsonDocument.Parse(File.ReadAllText(sandbox.GetAbsolutePath(expectedRelativePath)));
        document.RootElement.GetProperty("save_point_id").GetString().Should().Be(snapshot.SavePointId);
        document.RootElement.GetProperty("schema_version").GetString().Should().Be(snapshot.SchemaVersion);
    }

    // ACC:T12.11
    // ACC:T12.15
    // ACC:T12.23
    // ACC:T12.24
    [Theory]
    [InlineData("C:/temp/slot-01.json", "path_outside_user_scope", "C:/temp/slot-01.json")]
    [InlineData("//server/share/slot-01.json", "path_outside_user_scope", "//server/share/slot-01.json")]
    [InlineData("/tmp/slot-01.json", "path_outside_user_scope", "/tmp/slot-01.json")]
    [InlineData("user://saves/../slot-01.json", "path_contains_traversal", "saves/../slot-01.json")]
    [InlineData("user://profiles/../../config.json", "path_contains_traversal", "profiles/../../config.json")]
    public void ShouldRejectAbsoluteAndTraversalLikePathsWithStructuredEvidence_WhenPathEscapesUserScope(
        string configuredPath,
        string expectedReason,
        string expectedNormalizedPath)
    {
        using var sandbox = SaveServiceSandbox.Create();
        using var _ = SaveServiceEnvironment.Override(SaveRelativePathEnvVar, configuredPath);

        var exception = FluentActions.Invoking(() => sandbox.CreateService())
            .Should().Throw<InvalidOperationException>()
            .Which;

        exception.Data["reason"].Should().Be(expectedReason);
        exception.Data["input_path"].Should().Be(configuredPath);
        exception.Data["normalized_path"].Should().Be(expectedNormalizedPath);
        exception.Data["write_intent"].Should().Be("none");
        exception.Data["caller"].Should().Be(nameof(SaveService));
        sandbox.GetPersistedRelativePaths().Should().BeEmpty();
    }

    // ACC:T12.12
    // ACC:T12.15
    [Theory]
    [InlineData("user://saves/slot-01.tmp", ".tmp")]
    [InlineData("user://saves/slot-01.exe", ".exe")]
    [InlineData("user://profiles/main/settings.cfg", ".cfg")]
    [InlineData("user://profiles/main/slot-01", "")]
    public void ShouldRejectUnsupportedExtensionsWithStructuredEvidence_WhenConfiguredPathIsInvalid(string configuredPath, string expectedExtension)
    {
        using var sandbox = SaveServiceSandbox.Create();
        using var _ = SaveServiceEnvironment.Override(SaveRelativePathEnvVar, configuredPath);

        var exception = FluentActions.Invoking(() => sandbox.CreateService())
            .Should().Throw<InvalidOperationException>()
            .Which;

        exception.Data["reason"].Should().Be("extension_not_allowed");
        exception.Data["input_path"].Should().Be(configuredPath);
        exception.Data["write_intent"].Should().Be("none");
        if (string.IsNullOrEmpty(expectedExtension))
        {
            exception.Data.Contains("extension").Should().BeFalse();
        }
        else
        {
            exception.Data["extension"].Should().Be(expectedExtension);
        }

        sandbox.GetPersistedRelativePaths().Should().BeEmpty();
    }

    private static AutosaveSnapshot CreateSnapshot()
    {
        var stateJson = JsonSerializer.Serialize(new
        {
            hp = 60,
            floor = 2,
            offer_locks = new[] { "offer-alpha", "offer-beta" },
        });

        return new AutosaveSnapshot(
            RunId: "run-path-validation-1",
            SavePointId: "reward_open",
            SchemaVersion: "3",
            StateJson: stateJson,
            SavedAt: FixedSavedAt);
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
            var rootPath = Path.Combine(Path.GetTempPath(), "newrouge-save-path-validation-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(rootPath);
            return new SaveServiceSandbox(rootPath);
        }

        public ISaveService CreateService()
        {
            return new SaveService(new NoOpDataStore(), new DirectoryInfo(RootPath));
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
