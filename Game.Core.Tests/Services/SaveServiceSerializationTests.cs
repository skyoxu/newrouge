using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts.Save;
using Game.Core.Ports;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

[Trait("task", "T12")]
[Trait("adr", "ADR-0032")]
[Trait("adr", "ADR-0023")]
public sealed class SaveServiceSerializationTests
{
    private const int DefaultPayloadSizeLimitBytes = 4 * 1024;
    private const int ConfiguredPayloadSizeLimitBytes = 256;

    // ACC:T12.4
    [Fact]
    public async Task ShouldKeepRequiredSavePayloadFieldsStable_WhenWritingAutosave()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var offerLocks = CreateOfferLocks();
        var snapshot = CreateSnapshot(schemaVersion: "3", savePointId: "reward_open", offerLocks);

        await service.WriteAutosaveAsync(snapshot);

        using var document = JsonDocument.Parse(sandbox.ReadPersistedEnvelope());
        var root = document.RootElement;

        root.TryGetProperty("schema_version", out var schemaVersionElement).Should().BeTrue();
        root.TryGetProperty("save_point_id", out var savePointIdElement).Should().BeTrue();
        root.TryGetProperty("offer_locks", out var offerLocksElement).Should().BeTrue();

        schemaVersionElement.ValueKind.Should().Be(JsonValueKind.String);
        savePointIdElement.ValueKind.Should().Be(JsonValueKind.String);
        offerLocksElement.ValueKind.Should().Be(JsonValueKind.Array);

        schemaVersionElement.GetString().Should().Be(snapshot.SchemaVersion);
        savePointIdElement.GetString().Should().Be(snapshot.SavePointId);
        offerLocksElement.EnumerateArray().Select(item => item.GetString()).Should().Equal(offerLocks);
    }

    // ACC:T12.6
    [Fact]
    public async Task ShouldRoundTripSchemaVersionSavePointIdAndOfferLocks_WhenWritingAndReadingAutosave()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService();
        var offerLocks = CreateOfferLocks();
        var snapshot = CreateSnapshot(schemaVersion: "7", savePointId: "shop_enter", offerLocks);

        await service.WriteAutosaveAsync(snapshot);
        var roundTripped = await service.ReadAutosaveAsync();

        roundTripped.Should().NotBeNull();
        roundTripped!.RunId.Should().Be(snapshot.RunId);
        roundTripped.SchemaVersion.Should().Be(snapshot.SchemaVersion);
        roundTripped.SavePointId.Should().Be(snapshot.SavePointId);

        using var stateDocument = JsonDocument.Parse(roundTripped.StateJson);
        var persistedOfferLocks = stateDocument.RootElement
            .GetProperty("offer_locks")
            .EnumerateArray()
            .Select(item => item.GetString())
            .ToArray();

        persistedOfferLocks.Should().Equal(offerLocks);
    }

    // ACC:T12.13
    [Fact]
    public async Task ShouldRejectPayloadsOverConfiguredSizeLimit_WhenWritingAutosave()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var service = sandbox.CreateService(ConfiguredPayloadSizeLimitBytes);
        var oversizedOfferLocks = CreateOversizedOfferLocks();
        var snapshot = CreateSnapshot(schemaVersion: "9", savePointId: "event_choice_committed", oversizedOfferLocks);

        var act = () => service.WriteAutosaveAsync(snapshot);

        var exception = (await act.Should().ThrowAsync<InvalidOperationException>()).Which;
        exception.Message.Should().Contain("configured size limit");
        exception.Data["configured_size_limit_bytes"].Should().Be(ConfiguredPayloadSizeLimitBytes);
        exception.Data["actual_payload_bytes"].Should().NotBeNull();
        sandbox.GetPersistedFiles().Should().BeEmpty();
    }

    private static AutosaveSnapshot CreateSnapshot(string schemaVersion, string savePointId, params string[] offerLocks)
    {
        var stateJson = JsonSerializer.Serialize(new
        {
            hp = 60,
            floor = 2,
            offer_locks = offerLocks,
        });

        return new AutosaveSnapshot(
            RunId: "run-serialization-1",
            SavePointId: savePointId,
            SchemaVersion: schemaVersion,
            StateJson: stateJson,
            SavedAt: new DateTimeOffset(2026, 3, 6, 12, 0, 0, TimeSpan.Zero));
    }

    private static string[] CreateOfferLocks()
    {
        return new[]
        {
            "offer-stable-alpha",
            "offer-stable-beta",
            "offer-stable-gamma",
        };
    }

    private static string[] CreateOversizedOfferLocks()
    {
        return Enumerable.Range(0, 24)
            .Select(index => $"offer-{index:00}-{new string('x', 48)}")
            .ToArray();
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
            var rootPath = Path.Combine(Path.GetTempPath(), "newrouge-save-serialization-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(rootPath);
            return new SaveServiceSandbox(rootPath);
        }

        public SaveService CreateService(int maxPayloadBytes = DefaultPayloadSizeLimitBytes)
        {
            return new SaveService(new NoOpDataStore(), new DirectoryInfo(RootPath), maxPayloadBytes);
        }

        public string ReadPersistedEnvelope()
        {
            var files = GetPersistedFiles();
            files.Should().ContainSingle();
            return File.ReadAllText(Path.Combine(RootPath, files[0]));
        }

        public string[] GetPersistedFiles()
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
