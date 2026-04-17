using System;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Game.Core.Contracts.Save;

namespace Game.Core.Services;

/// <summary>
/// Validates autosave envelope + continue metadata for single-slot continue entry.
/// </summary>
public sealed class ContinueLoadValidationService
{
    private const string SupportedSchemaVersion = "1.0.0";

    public ContinueLoadValidationResult Evaluate(string? autosaveEnvelopeJson, ContinueMetadata? metadata)
    {
        if (string.IsNullOrWhiteSpace(autosaveEnvelopeJson))
        {
            return Blocked("invalid_structure");
        }

        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(autosaveEnvelopeJson);
        }
        catch (JsonException)
        {
            return Blocked("invalid_structure");
        }

        using (doc)
        {
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                return Blocked("invalid_structure");
            }

            if (!TryReadRequiredEnvelope(root, out var runId, out var schemaVersion, out var savePointId, out var stateJson, out var integrityHash, out var savedAt))
            {
                return Blocked("invalid_metadata");
            }
            if (!IsSupportedSchemaVersion(schemaVersion))
            {
                return Blocked("invalid_metadata");
            }

            if (!IsMetadataUsable(metadata))
            {
                return Blocked("invalid_metadata");
            }

            if (!TryReadDifficultySnapshot(stateJson, out var difficultyId, out var labelKey, out var descriptionKey, out var rulesetId))
            {
                return Blocked("invalid_metadata");
            }

            if (!string.Equals(metadata!.RunId, runId, StringComparison.Ordinal)
                || !string.Equals(metadata.NodeId, savePointId, StringComparison.Ordinal)
                || metadata.UpdatedAt != savedAt
                || metadata.DifficultyId != difficultyId
                || !string.Equals(metadata.LabelKey, labelKey, StringComparison.Ordinal)
                || !string.Equals(metadata.DescriptionKey, descriptionKey, StringComparison.Ordinal)
                || !string.Equals(metadata.RulesetId, rulesetId, StringComparison.Ordinal))
            {
                return Blocked("invalid_metadata");
            }

            var expectedHash = ComputeHash(stateJson);
            if (!string.Equals(expectedHash, integrityHash, StringComparison.Ordinal)
                || !string.Equals(metadata.IntegrityHash, integrityHash, StringComparison.Ordinal))
            {
                return Blocked("invalid_integrity");
            }

            return new ContinueLoadValidationResult(true, null, null);
        }
    }

    private static bool TryReadRequiredEnvelope(
        JsonElement root,
        out string runId,
        out string schemaVersion,
        out string savePointId,
        out string stateJson,
        out string integrityHash,
        out DateTimeOffset savedAt)
    {
        runId = string.Empty;
        schemaVersion = string.Empty;
        savePointId = string.Empty;
        stateJson = string.Empty;
        integrityHash = string.Empty;
        savedAt = default;

        if (!TryReadRequiredString(root, "run_id", out runId)
            || !TryReadRequiredString(root, "schema_version", out schemaVersion)
            || !TryReadRequiredString(root, "save_point_id", out savePointId)
            || !TryReadRequiredString(root, "state_json", out stateJson)
            || !TryReadRequiredString(root, "integrity_hash", out integrityHash))
        {
            return false;
        }

        if (!root.TryGetProperty("saved_at", out var savedAtNode)
            || savedAtNode.ValueKind != JsonValueKind.String
            || !DateTimeOffset.TryParse(savedAtNode.GetString(), out savedAt))
        {
            return false;
        }

        return true;
    }

    private static bool IsMetadataUsable(ContinueMetadata? metadata)
    {
        return metadata is not null
            && !string.IsNullOrWhiteSpace(metadata.RunId)
            && metadata.DifficultyId >= 1
            && metadata.DifficultyId <= 10
            && !string.IsNullOrWhiteSpace(metadata.LabelKey)
            && !string.IsNullOrWhiteSpace(metadata.DescriptionKey)
            && !string.IsNullOrWhiteSpace(metadata.RulesetId)
            && metadata.Act >= 0
            && !string.IsNullOrWhiteSpace(metadata.NodeId)
            && !string.IsNullOrWhiteSpace(metadata.IntegrityHash);
    }

    private static bool TryReadDifficultySnapshot(
        string stateJson,
        out int difficultyId,
        out string labelKey,
        out string descriptionKey,
        out string rulesetId)
    {
        difficultyId = 0;
        labelKey = string.Empty;
        descriptionKey = string.Empty;
        rulesetId = string.Empty;
        if (string.IsNullOrWhiteSpace(stateJson))
        {
            return false;
        }

        try
        {
            using var stateDoc = JsonDocument.Parse(stateJson);
            if (stateDoc.RootElement.ValueKind != JsonValueKind.Object)
            {
                return false;
            }

            var source = ResolveDifficultySource(stateDoc.RootElement);
            if (!TryReadDifficultyId(source, out difficultyId)
                || !TryReadRequiredString(source, "label_key", out labelKey)
                || !TryReadRequiredString(source, "description_key", out descriptionKey)
                || !TryReadRequiredString(source, "ruleset_id", out rulesetId))
            {
                return false;
            }

            return difficultyId >= 1 && difficultyId <= 10;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static JsonElement ResolveDifficultySource(JsonElement root)
    {
        if (root.TryGetProperty("difficulty", out var difficultyNode) && difficultyNode.ValueKind == JsonValueKind.Object)
        {
            return difficultyNode;
        }

        return root;
    }

    private static bool TryReadDifficultyId(JsonElement source, out int value)
    {
        value = 0;
        if (!source.TryGetProperty("difficulty_id", out var node))
        {
            return false;
        }

        return node.ValueKind switch
        {
            JsonValueKind.Number => node.TryGetInt32(out value),
            JsonValueKind.String => int.TryParse(node.GetString(), out value),
            _ => false,
        };
    }

    private static bool TryReadRequiredString(JsonElement root, string propertyName, out string value)
    {
        value = string.Empty;
        if (!root.TryGetProperty(propertyName, out var node) || node.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        var text = node.GetString();
        if (string.IsNullOrWhiteSpace(text))
        {
            return false;
        }

        value = text;
        return true;
    }

    private static ContinueLoadValidationResult Blocked(string reasonCode)
    {
        return new ContinueLoadValidationResult(false, reasonCode, reasonCode);
    }

    private static bool IsSupportedSchemaVersion(string schemaVersion)
    {
        return string.Equals(schemaVersion, SupportedSchemaVersion, StringComparison.Ordinal);
    }

    private static string ComputeHash(string content)
    {
        var bytes = Encoding.UTF8.GetBytes(content);
        return Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    }
}
