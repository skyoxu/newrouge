using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts.Interfaces;
using Game.Core.Ports;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

[Trait("task", "T12")]
[Trait("adr", "ADR-0032")]
[Trait("adr", "ADR-0023")]
public sealed class SaveServiceVersionGuardTests
{
    private const string DefaultRelativePath = "saves/autosave.json";
    private static readonly DateTimeOffset FixedSavedAt = new(2026, 3, 6, 12, 0, 0, TimeSpan.Zero);
    private static readonly string[] ForbiddenMigrationTokens =
    {
        "Migrate",
        "Upgrade",
        "ConvertLegacy",
        "AutoConvert",
        "AutoUpgrade",
    };

    // ACC:T12.5
    [Fact]
    public async Task ShouldKeepLegacySchemaBytesUntouched_WhenReadingLegacyEnvelope()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var legacyEnvelope = CreateEnvelopeJson(
            runId: "run-legacy",
            savePointId: "reward_open",
            schemaVersion: "legacy-v0",
            offerLocks: new[] { "offer-legacy-a", "offer-legacy-b" });
        sandbox.Seed(DefaultRelativePath, legacyEnvelope);

        var result = await sandbox.CreateService().ReadAutosaveAsync();

        result.Should().NotBeNull();
        result!.SchemaVersion.Should().Be("legacy-v0");
        result.SavePointId.Should().Be("reward_open");
        File.ReadAllText(sandbox.GetAbsolutePath(DefaultRelativePath)).Should().Be(legacyEnvelope);
        sandbox.GetPersistedRelativePaths().Should().Equal(DefaultRelativePath);
    }

    // ACC:T12.5
    [Fact]
    public async Task ShouldReturnNullWithoutWriteBack_WhenReadingIncompatibleEnvelope()
    {
        using var sandbox = SaveServiceSandbox.Create();
        const string incompatibleEnvelope = "{\"run_id\":\"run-bad\"";
        sandbox.Seed(DefaultRelativePath, incompatibleEnvelope);

        var result = await sandbox.CreateService().ReadAutosaveAsync();

        result.Should().BeNull();
        File.ReadAllText(sandbox.GetAbsolutePath(DefaultRelativePath)).Should().Be(incompatibleEnvelope);
        sandbox.GetPersistedRelativePaths().Should().Equal(DefaultRelativePath);
    }

    [Fact]
    public void ShouldNotExposeAutomaticMigrationEntryPoints_WhenInspectingSaveRelatedPublicApis()
    {
        var forbiddenPublicMethods = GetSaveRelatedPublicTypes()
            .SelectMany(type => type
                .GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                .Where(method => !method.IsSpecialName)
                .Select(method => $"{type.FullName}.{method.Name}"))
            .Where(signature => ForbiddenMigrationTokens.Any(token => signature.Contains(token, StringComparison.OrdinalIgnoreCase)))
            .OrderBy(signature => signature)
            .ToArray();

        forbiddenPublicMethods.Should().BeEmpty(
            "legacy or incompatible save data must be rejected instead of auto-migrated or auto-upgraded");
    }

    private static string CreateEnvelopeJson(string runId, string savePointId, string schemaVersion, string[] offerLocks)
    {
        return JsonSerializer.Serialize(new
        {
            run_id = runId,
            save_point_id = savePointId,
            schema_version = schemaVersion,
            saved_at = FixedSavedAt,
            state_json = JsonSerializer.Serialize(new { hp = 40, offer_locks = offerLocks }),
            offer_locks = offerLocks,
            integrity_hash = "legacy-hash"
        });
    }

    private static IEnumerable<Type> GetSaveRelatedPublicTypes()
    {
        return GetCandidateAssemblies()
            .SelectMany(GetLoadableTypes)
            .Where(type => type.IsPublic)
            .Where(type => !IsTestType(type))
            .Where(type =>
                type.Name.Contains("Save", StringComparison.OrdinalIgnoreCase) ||
                (type.Namespace?.Contains("Save", StringComparison.OrdinalIgnoreCase) ?? false));
    }

    private static IEnumerable<Assembly> GetCandidateAssemblies()
    {
        var assemblies = new Dictionary<string, Assembly>(StringComparer.OrdinalIgnoreCase);

        foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies().Where(assembly => !assembly.IsDynamic))
        {
            var assemblyName = assembly.GetName().Name;
            if (string.IsNullOrWhiteSpace(assemblyName) || IsTestAssemblyName(assemblyName))
            {
                continue;
            }

            assemblies[assemblyName] = assembly;
        }

        foreach (var path in Directory.EnumerateFiles(AppContext.BaseDirectory, "Game.*.dll"))
        {
            var assemblyName = Path.GetFileNameWithoutExtension(path);
            if (string.IsNullOrWhiteSpace(assemblyName) || IsTestAssemblyName(assemblyName))
            {
                continue;
            }

            if (assemblies.ContainsKey(assemblyName))
            {
                continue;
            }

            try
            {
                assemblies[assemblyName] = AssemblyLoadContext.Default.LoadFromAssemblyPath(path);
            }
            catch
            {
            }
        }

        return assemblies.Values;
    }

    private static IEnumerable<Type> GetLoadableTypes(Assembly assembly)
    {
        try
        {
            return assembly.GetExportedTypes();
        }
        catch (ReflectionTypeLoadException exception)
        {
            return exception.Types.Where(type => type != null).Cast<Type>();
        }
    }

    private static bool IsTestType(Type type)
    {
        var assemblyName = type.Assembly.GetName().Name ?? string.Empty;
        if (IsTestAssemblyName(assemblyName))
        {
            return true;
        }

        return type.Namespace?.Contains(".Tests", StringComparison.OrdinalIgnoreCase) ?? false;
    }

    private static bool IsTestAssemblyName(string assemblyName)
    {
        return assemblyName.EndsWith(".Tests", StringComparison.OrdinalIgnoreCase)
               || assemblyName.Equals("Game.Core.Tests", StringComparison.OrdinalIgnoreCase);
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
            var rootPath = Path.Combine(Path.GetTempPath(), "newrouge-save-version-guard-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(rootPath);
            return new SaveServiceSandbox(rootPath);
        }

        public ISaveService CreateService()
        {
            return new SaveService(new NoOpDataStore(), new DirectoryInfo(RootPath));
        }

        public void Seed(string relativePath, string content)
        {
            var absolutePath = GetAbsolutePath(relativePath);
            Directory.CreateDirectory(Path.GetDirectoryName(absolutePath)!);
            File.WriteAllText(absolutePath, content);
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
