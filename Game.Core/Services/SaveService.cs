using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Game.Core.Contracts;
using Game.Core.Contracts.Events;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Save;
using Game.Core.Ports;

namespace Game.Core.Services;

public sealed class SaveService : ISaveService
{
    private const string DefaultRelativeSavePath = "saves/autosave.json";
    private const int DefaultPayloadSizeLimitBytes = 4 * 1024;
    private const string TestUserRootEnvVar = "NEWROUGE_SAVE_TEST_USER_ROOT";
    private const string TestRelativePathEnvVar = "NEWROUGE_SAVE_TEST_RELATIVE_PATH";

    private static readonly string[] AllowedExtensions = { ".json", ".save" };
    private static readonly UTF8Encoding Utf8WithoutBom = new(false);

    private readonly IDataStore _dataStore;
    private readonly IEventBus? _eventBus;
    private readonly ILogger? _logger;
    private readonly JsonSerializerOptions _serializerOptions;
    private readonly string _userSavePath;
    private readonly string? _physicalUserRoot;
    private readonly int _maxPayloadBytes;

    public SaveService(
        IDataStore dataStore,
        DirectoryInfo rootDirectory,
        IEventBus? eventBus = null,
        ILogger? logger = null,
        JsonSerializerOptions? serializerOptions = null)
        : this(dataStore, rootDirectory, DefaultPayloadSizeLimitBytes, eventBus, logger, serializerOptions)
    {
    }

    public SaveService(
        IDataStore dataStore,
        DirectoryInfo rootDirectory,
        int maxPayloadBytes,
        IEventBus? eventBus = null,
        ILogger? logger = null,
        JsonSerializerOptions? serializerOptions = null)
    {
        ArgumentNullException.ThrowIfNull(dataStore);
        ArgumentNullException.ThrowIfNull(rootDirectory);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(maxPayloadBytes);

        _dataStore = dataStore;
        _eventBus = eventBus;
        _logger = logger;
        _serializerOptions = serializerOptions ?? new JsonSerializerOptions(JsonSerializerDefaults.Web);
        _userSavePath = NormalizeUserSavePath(Environment.GetEnvironmentVariable(TestRelativePathEnvVar));
        _physicalUserRoot = GetFullPathOrNull(rootDirectory.FullName) ?? GetFullPathOrNull(Environment.GetEnvironmentVariable(TestUserRootEnvVar));
        _maxPayloadBytes = maxPayloadBytes;
    }

    public SaveService(IDataStore dataStore)
        : this(dataStore, new DirectoryInfo(Environment.GetEnvironmentVariable(TestUserRootEnvVar) ?? Path.GetTempPath()))
    {
    }

    public async Task WriteAutosaveAsync(AutosaveSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);

        var envelope = BuildEnvelope(snapshot);
        var serializedEnvelope = JsonSerializer.Serialize(envelope, _serializerOptions);
        EnsurePayloadDoesNotExceedConfiguredLimit(serializedEnvelope);

        if (!string.IsNullOrWhiteSpace(_physicalUserRoot))
        {
            WritePhysicalAtomically(snapshot, serializedEnvelope);
        }
        else
        {
            await WriteViaDataStoreAsync(snapshot, serializedEnvelope).ConfigureAwait(false);
        }

        await PublishSaveWriteSucceededAsync(envelope).ConfigureAwait(false);
    }

    public async Task<AutosaveSnapshot?> ReadAutosaveAsync()
    {
        var envelope = await ReadEnvelopeAsync(publishLoadedEvent: true).ConfigureAwait(false);
        return envelope is null
            ? null
            : new AutosaveSnapshot(
                RunId: envelope.RunId,
                SavePointId: envelope.SavePointId,
                SchemaVersion: envelope.SchemaVersion,
                StateJson: envelope.StateJson,
                SavedAt: envelope.SavedAt);
    }

    public async Task<ContinueMetadata?> ReadContinueMetadataAsync()
    {
        var envelope = await ReadEnvelopeAsync(publishLoadedEvent: false).ConfigureAwait(false);
        return envelope is null
            ? null
            : new ContinueMetadata(
                RunId: envelope.RunId,
                DifficultyId: 0,
                Act: 0,
                NodeId: envelope.SavePointId,
                IntegrityHash: envelope.IntegrityHash,
                UpdatedAt: envelope.SavedAt);
    }

    private async Task<SaveEnvelope?> ReadEnvelopeAsync(bool publishLoadedEvent)
    {
        var serializedEnvelope = await ReadSerializedEnvelopeAsync().ConfigureAwait(false);
        if (string.IsNullOrWhiteSpace(serializedEnvelope))
        {
            return null;
        }

        try
        {
            var envelope = JsonSerializer.Deserialize<SaveEnvelope>(serializedEnvelope, _serializerOptions);
            if (!IsEnvelopeUsable(envelope))
            {
                return null;
            }

            if (publishLoadedEvent)
            {
                await PublishSaveLoadedAsync(envelope!).ConfigureAwait(false);
            }

            return envelope;
        }
        catch (JsonException jsonException)
        {
            _logger?.Warn($"Failed to deserialize autosave envelope: {jsonException.Message}");
            return null;
        }
    }

    private async Task<string?> ReadSerializedEnvelopeAsync()
    {
        if (!string.IsNullOrWhiteSpace(_physicalUserRoot))
        {
            var targetPath = GetPhysicalTargetPath();
            return File.Exists(targetPath)
                ? File.ReadAllText(targetPath, Utf8WithoutBom)
                : null;
        }

        return await _dataStore.LoadAsync(_userSavePath).ConfigureAwait(false);
    }

    private void WritePhysicalAtomically(AutosaveSnapshot snapshot, string serializedEnvelope)
    {
        var targetPath = GetPhysicalTargetPath();
        var tempPath = targetPath + ".tmp";
        var directoryPath = Path.GetDirectoryName(targetPath);
        if (!string.IsNullOrWhiteSpace(directoryPath))
        {
            Directory.CreateDirectory(directoryPath);
        }

        try
        {
            File.WriteAllText(tempPath, serializedEnvelope, Utf8WithoutBom);
        }
        catch (Exception exception)
        {
            TryDelete(tempPath);
            throw CreatePersistenceException(
                reasonCode: "temp_write_failed",
                action: "write_temp",
                snapshot: snapshot,
                targetPath: _userSavePath,
                tempPath: tempPath,
                innerException: exception);
        }

        try
        {
            if (File.Exists(targetPath))
            {
                File.Move(tempPath, targetPath, overwrite: true);
            }
            else
            {
                File.Move(tempPath, targetPath);
            }
        }
        catch (Exception exception)
        {
            TryDelete(tempPath);
            throw CreatePersistenceException(
                reasonCode: "atomic_replace_failed",
                action: "replace_target",
                snapshot: snapshot,
                targetPath: _userSavePath,
                tempPath: tempPath,
                innerException: exception);
        }
    }

    private async Task WriteViaDataStoreAsync(AutosaveSnapshot snapshot, string serializedEnvelope)
    {
        try
        {
            await _dataStore.SaveAsync(_userSavePath, serializedEnvelope).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            throw CreatePersistenceException(
                reasonCode: "save_failed",
                action: "save_store",
                snapshot: snapshot,
                targetPath: _userSavePath,
                tempPath: null,
                innerException: exception);
        }
    }

    private void EnsurePayloadDoesNotExceedConfiguredLimit(string serializedEnvelope)
    {
        var payloadSizeInBytes = Encoding.UTF8.GetByteCount(serializedEnvelope);
        if (payloadSizeInBytes <= _maxPayloadBytes)
        {
            return;
        }

        var exception = new InvalidOperationException(
            $"Serialized save payload exceeds configured size limit of {_maxPayloadBytes} bytes.");
        exception.Data["configured_size_limit_bytes"] = _maxPayloadBytes;
        exception.Data["actual_payload_bytes"] = payloadSizeInBytes;
        exception.Data["caller"] = nameof(SaveService);
        throw exception;
    }


    private string GetPhysicalTargetPath()
    {
        if (string.IsNullOrWhiteSpace(_physicalUserRoot))
        {
            throw new InvalidOperationException("A physical user root is required for atomic save writes.");
        }

        var relativePath = _userSavePath["user://".Length..]
            .Replace('/', Path.DirectorySeparatorChar)
            .TrimStart(Path.DirectorySeparatorChar);

        return Path.Combine(_physicalUserRoot, relativePath);
    }

    private static SaveEnvelope BuildEnvelope(AutosaveSnapshot snapshot)
    {
        using var document = JsonDocument.Parse(snapshot.StateJson);
        var root = document.RootElement;

        var offerLocks = root.TryGetProperty("offer_locks", out var offerLocksElement) && offerLocksElement.ValueKind == JsonValueKind.Array
            ? offerLocksElement.EnumerateArray()
                .Select(static item => item.GetString())
                .Where(static item => !string.IsNullOrWhiteSpace(item))
                .Cast<string>()
                .ToArray()
            : Array.Empty<string>();

        return new SaveEnvelope(
            RunId: snapshot.RunId,
            SavePointId: snapshot.SavePointId,
            SchemaVersion: snapshot.SchemaVersion,
            SavedAt: snapshot.SavedAt,
            StateJson: snapshot.StateJson,
            OfferLocks: offerLocks,
            IntegrityHash: ComputeHash(snapshot.StateJson));
    }

    private static bool IsEnvelopeUsable(SaveEnvelope? envelope)
    {
        return envelope is not null
            && !string.IsNullOrWhiteSpace(envelope.RunId)
            && !string.IsNullOrWhiteSpace(envelope.SavePointId)
            && !string.IsNullOrWhiteSpace(envelope.SchemaVersion)
            && !string.IsNullOrWhiteSpace(envelope.StateJson)
            && !string.IsNullOrWhiteSpace(envelope.IntegrityHash);
    }

    private static string NormalizeUserSavePath(string? configuredRelativePath)
    {
        var rawInputPath = configuredRelativePath;
        var candidate = string.IsNullOrWhiteSpace(configuredRelativePath)
            ? DefaultRelativeSavePath
            : configuredRelativePath.Replace("\\", "/").Trim();

        if (candidate.StartsWith("user://", StringComparison.OrdinalIgnoreCase))
        {
            candidate = candidate["user://".Length..];
        }

        if (Path.IsPathRooted(candidate) || candidate.StartsWith("/", StringComparison.Ordinal) || candidate.StartsWith("//", StringComparison.Ordinal))
        {
            throw CreatePathValidationException(
                reasonCode: "path_outside_user_scope",
                inputPath: rawInputPath,
                normalizedPath: candidate,
                extension: null,
                message: "Save path must stay within user:// scope.");
        }

        var segments = candidate.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (segments.Length == 0 || segments.Any(static segment => segment is "." or ".."))
        {
            throw CreatePathValidationException(
                reasonCode: "path_contains_traversal",
                inputPath: rawInputPath,
                normalizedPath: candidate,
                extension: null,
                message: "Save path contains traversal-like segments.");
        }

        foreach (var segment in segments)
        {
            if (segment.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
            {
                throw CreatePathValidationException(
                    reasonCode: "path_contains_invalid_file_name_characters",
                    inputPath: rawInputPath,
                    normalizedPath: candidate,
                    extension: null,
                    message: "Save path contains invalid file-name characters.");
            }
        }

        var normalizedRelativePath = string.Join("/", segments);
        var extension = Path.GetExtension(normalizedRelativePath);
        if (string.IsNullOrWhiteSpace(extension) || !AllowedExtensions.Contains(extension, StringComparer.OrdinalIgnoreCase))
        {
            throw CreatePathValidationException(
                reasonCode: "extension_not_allowed",
                inputPath: rawInputPath,
                normalizedPath: normalizedRelativePath,
                extension: extension,
                message: "Save path must use an allowed extension.");
        }

        return "user://" + normalizedRelativePath;
    }

    private static InvalidOperationException CreatePathValidationException(
        string reasonCode,
        string? inputPath,
        string normalizedPath,
        string? extension,
        string message)
    {
        var effectiveInputPath = string.IsNullOrWhiteSpace(inputPath)
            ? DefaultRelativeSavePath
            : inputPath!;

        var exception = new InvalidOperationException(message);
        exception.Data["reason"] = reasonCode;
        exception.Data["input_path"] = effectiveInputPath;
        exception.Data["normalized_path"] = normalizedPath;
        exception.Data["write_intent"] = "none";
        exception.Data["caller"] = nameof(SaveService);
        if (!string.IsNullOrWhiteSpace(extension))
        {
            exception.Data["extension"] = extension;
        }

        return exception;
    }

    private InvalidOperationException CreatePersistenceException(
        string reasonCode,
        string action,
        AutosaveSnapshot snapshot,
        string targetPath,
        string? tempPath,
        Exception innerException)
    {
        var message = $"Save write failed for run_id={snapshot.RunId}, save_point_id={snapshot.SavePointId}, reason_code={reasonCode}, target={targetPath}";
        var exception = new InvalidOperationException(message, innerException);
        exception.Data["ts"] = DateTimeOffset.UtcNow.ToString("O");
        exception.Data["action"] = action;
        exception.Data["reason"] = reasonCode;
        exception.Data["target"] = targetPath;
        exception.Data["caller"] = nameof(SaveService);
        exception.Data["run_id"] = snapshot.RunId;
        exception.Data["schema_version"] = snapshot.SchemaVersion;
        exception.Data["save_point_id"] = snapshot.SavePointId;
        if (!string.IsNullOrWhiteSpace(tempPath))
        {
            exception.Data["temp_path"] = tempPath;
        }

        return exception;
    }

    private async Task PublishSaveWriteSucceededAsync(SaveEnvelope envelope)
    {
        if (_eventBus is null)
        {
            return;
        }

        var payload = new SaveWriteSucceededEvent(
            RunId: envelope.RunId,
            SavePointId: envelope.SavePointId,
            SchemaVersion: envelope.SchemaVersion,
            IntegrityHash: envelope.IntegrityHash,
            WrittenAt: envelope.SavedAt);
        await PublishDomainEventAsync(EventTypes.SaveWriteSucceeded, payload).ConfigureAwait(false);
    }

    private async Task PublishSaveLoadedAsync(SaveEnvelope envelope)
    {
        if (_eventBus is null)
        {
            return;
        }

        var payload = new SaveLoadedEvent(
            RunId: envelope.RunId,
            SavePointId: envelope.SavePointId,
            SchemaVersion: envelope.SchemaVersion,
            LoadedAt: DateTimeOffset.UtcNow);
        await PublishDomainEventAsync(EventTypes.SaveLoaded, payload).ConfigureAwait(false);
    }

    private async Task PublishDomainEventAsync(string eventType, object payload)
    {
        try
        {
            var serializedPayload = JsonSerializer.Serialize(payload, _serializerOptions);
            await _eventBus!.PublishAsync(new DomainEvent(
                Type: eventType,
                Source: nameof(SaveService),
                DataJson: serializedPayload,
                Timestamp: DateTimeOffset.UtcNow,
                Id: $"{eventType}-{Guid.NewGuid():N}")).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            _logger?.Warn($"Save event publish failed: {exception.Message}");
        }
    }

    private static string ComputeHash(string content)
    {
        var bytes = Encoding.UTF8.GetBytes(content);
        return Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    }

    private static string? GetFullPathOrNull(string? path)
    {
        return string.IsNullOrWhiteSpace(path) ? null : Path.GetFullPath(path);
    }

    private static void TryDelete(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch
        {
        }
    }

    private sealed record SaveEnvelope(
        [property: JsonPropertyName("run_id")] string RunId,
        [property: JsonPropertyName("save_point_id")] string SavePointId,
        [property: JsonPropertyName("schema_version")] string SchemaVersion,
        [property: JsonPropertyName("saved_at")] DateTimeOffset SavedAt,
        [property: JsonPropertyName("state_json")] string StateJson,
        [property: JsonPropertyName("offer_locks")] string[] OfferLocks,
        [property: JsonPropertyName("integrity_hash")] string IntegrityHash);
}
