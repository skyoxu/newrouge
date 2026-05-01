using System;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts.Save;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class ContinueLoadValidationServiceCoverageTests
{
    private static readonly DateTimeOffset FixedSavedAt = new(2026, 5, 1, 12, 0, 0, TimeSpan.Zero);

    [Fact]
    public void ShouldBlockInvalidStructure_WhenEnvelopeMissingMalformedOrNotObject()
    {
        var service = new ContinueLoadValidationService();
        var metadata = BuildMatchingMetadata("run-1", "node-1", BuildStateJson(), FixedSavedAt);

        service.Evaluate(null, metadata).ErrorCode.Should().Be("invalid_structure");
        service.Evaluate("   ", metadata).ErrorCode.Should().Be("invalid_structure");
        service.Evaluate("{", metadata).ErrorCode.Should().Be("invalid_structure");
        service.Evaluate("[]", metadata).ErrorCode.Should().Be("invalid_structure");
    }

    [Fact]
    public void ShouldBlockInvalidMetadata_WhenEnvelopeMissingRequiredFields()
    {
        var service = new ContinueLoadValidationService();
        var envelopeJson = JsonSerializer.Serialize(new
        {
            run_id = "run-1",
            schema_version = "1.0.0",
            save_point_id = "node-1",
            state_json = BuildStateJson(),
            saved_at = FixedSavedAt,
        });
        var metadata = BuildMatchingMetadata("run-1", "node-1", BuildStateJson(), FixedSavedAt);

        var result = service.Evaluate(envelopeJson, metadata);

        result.ContinueAllowed.Should().BeFalse();
        result.ErrorCode.Should().Be("invalid_metadata");
    }

    [Fact]
    public void ShouldBlockInvalidMetadata_WhenSchemaVersionUnsupported()
    {
        var service = new ContinueLoadValidationService();
        var stateJson = BuildStateJson();
        var envelopeJson = BuildEnvelopeJson(
            runId: "run-1",
            savePointId: "node-1",
            schemaVersion: "2.0.0",
            stateJson: stateJson,
            savedAt: FixedSavedAt,
            integrityHash: ComputeHash(stateJson));
        var metadata = BuildMatchingMetadata("run-1", "node-1", stateJson, FixedSavedAt);

        var result = service.Evaluate(envelopeJson, metadata);

        result.ContinueAllowed.Should().BeFalse();
        result.ErrorCode.Should().Be("invalid_metadata");
    }

    [Fact]
    public void ShouldBlockInvalidMetadata_WhenMetadataIsNullOrMismatched()
    {
        var service = new ContinueLoadValidationService();
        var stateJson = BuildStateJson();
        var envelopeJson = BuildEnvelopeJson(
            runId: "run-1",
            savePointId: "node-1",
            schemaVersion: "1.0.0",
            stateJson: stateJson,
            savedAt: FixedSavedAt,
            integrityHash: ComputeHash(stateJson));

        var nullMetadataResult = service.Evaluate(envelopeJson, null);
        nullMetadataResult.ErrorCode.Should().Be("invalid_metadata");

        var mismatchedMetadata = BuildMatchingMetadata("run-2", "node-1", stateJson, FixedSavedAt);
        var mismatchedResult = service.Evaluate(envelopeJson, mismatchedMetadata);
        mismatchedResult.ErrorCode.Should().Be("invalid_metadata");
    }

    [Fact]
    public void ShouldBlockInvalidMetadata_WhenDifficultySnapshotCannotBeParsed()
    {
        var service = new ContinueLoadValidationService();
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty = new
            {
                difficulty_id = 3,
                label_key = "difficulty.label.hard",
            },
        });
        var envelopeJson = BuildEnvelopeJson(
            runId: "run-1",
            savePointId: "node-1",
            schemaVersion: "1.0.0",
            stateJson: stateJson,
            savedAt: FixedSavedAt,
            integrityHash: ComputeHash(stateJson));
        var metadata = BuildMatchingMetadata("run-1", "node-1", BuildStateJson(), FixedSavedAt);

        var result = service.Evaluate(envelopeJson, metadata);

        result.ContinueAllowed.Should().BeFalse();
        result.ErrorCode.Should().Be("invalid_metadata");
    }

    [Fact]
    public void ShouldBlockInvalidIntegrity_WhenEnvelopeHashOrMetadataHashMismatched()
    {
        var service = new ContinueLoadValidationService();
        var stateJson = BuildStateJson();
        var envelopeJson = BuildEnvelopeJson(
            runId: "run-1",
            savePointId: "node-1",
            schemaVersion: "1.0.0",
            stateJson: stateJson,
            savedAt: FixedSavedAt,
            integrityHash: "tampered");
        var metadata = BuildMatchingMetadata("run-1", "node-1", stateJson, FixedSavedAt);

        var result = service.Evaluate(envelopeJson, metadata);
        result.ErrorCode.Should().Be("invalid_integrity");

        var wrongMetadataHash = new ContinueMetadata(
            RunId: metadata.RunId,
            DifficultyId: metadata.DifficultyId,
            LabelKey: metadata.LabelKey,
            DescriptionKey: metadata.DescriptionKey,
            RulesetId: metadata.RulesetId,
            Act: metadata.Act,
            NodeId: metadata.NodeId,
            IntegrityHash: "wrong-hash",
            UpdatedAt: metadata.UpdatedAt);
        var validEnvelope = BuildEnvelopeJson(
            runId: "run-1",
            savePointId: "node-1",
            schemaVersion: "1.0.0",
            stateJson: stateJson,
            savedAt: FixedSavedAt,
            integrityHash: ComputeHash(stateJson));
        var metadataHashResult = service.Evaluate(validEnvelope, wrongMetadataHash);
        metadataHashResult.ErrorCode.Should().Be("invalid_integrity");
    }

    [Fact]
    public void ShouldAllowContinue_WhenEnvelopeAndMetadataAreConsistent()
    {
        var service = new ContinueLoadValidationService();
        var stateJson = BuildStateJson(difficultyIdAsString: true);
        var hash = ComputeHash(stateJson);
        var envelopeJson = BuildEnvelopeJson(
            runId: "run-1",
            savePointId: "node-1",
            schemaVersion: "1.0.0",
            stateJson: stateJson,
            savedAt: FixedSavedAt,
            integrityHash: hash);
        var metadata = new ContinueMetadata(
            RunId: "run-1",
            DifficultyId: 3,
            LabelKey: "difficulty.label.hard",
            DescriptionKey: "difficulty.description.hard",
            RulesetId: "ruleset.hard",
            Act: 0,
            NodeId: "node-1",
            IntegrityHash: hash,
            UpdatedAt: FixedSavedAt);

        var result = service.Evaluate(envelopeJson, metadata);

        result.ContinueAllowed.Should().BeTrue();
        result.ErrorCode.Should().BeNull();
        result.ErrorMessage.Should().BeNull();
    }

    [Fact]
    public void ShouldAllowContinue_WhenDifficultySnapshotIsAtRootAndOwnerFieldsStillMatch()
    {
        var service = new ContinueLoadValidationService();
        var stateJson = JsonSerializer.Serialize(new
        {
            difficulty_id = 3,
            label_key = "difficulty.label.hard",
            description_key = "difficulty.description.hard",
            ruleset_id = "ruleset.hard",
        });
        var hash = ComputeHash(stateJson);
        var envelopeJson = BuildEnvelopeJson(
            runId: "run-root",
            savePointId: "node-root",
            schemaVersion: "1.0.0",
            stateJson: stateJson,
            savedAt: FixedSavedAt,
            integrityHash: hash);
        var metadata = new ContinueMetadata(
            RunId: "run-root",
            DifficultyId: 3,
            LabelKey: "difficulty.label.hard",
            DescriptionKey: "difficulty.description.hard",
            RulesetId: "ruleset.hard",
            Act: 0,
            NodeId: "node-root",
            IntegrityHash: hash,
            UpdatedAt: FixedSavedAt);

        var result = service.Evaluate(envelopeJson, metadata);

        result.ContinueAllowed.Should().BeTrue();
        result.ErrorCode.Should().BeNull();
        result.ErrorMessage.Should().BeNull();
    }

    private static ContinueMetadata BuildMatchingMetadata(string runId, string savePointId, string stateJson, DateTimeOffset savedAt)
    {
        using var document = JsonDocument.Parse(stateJson);
        var difficulty = document.RootElement.TryGetProperty("difficulty", out var difficultyNode)
            ? difficultyNode
            : document.RootElement;
        var difficultyId = difficulty.GetProperty("difficulty_id").ValueKind == JsonValueKind.String
            ? int.Parse(difficulty.GetProperty("difficulty_id").GetString()!)
            : difficulty.GetProperty("difficulty_id").GetInt32();
        var labelKey = difficulty.GetProperty("label_key").GetString()!;
        var descriptionKey = difficulty.GetProperty("description_key").GetString()!;
        var rulesetId = difficulty.GetProperty("ruleset_id").GetString()!;
        return new ContinueMetadata(
            RunId: runId,
            DifficultyId: difficultyId,
            LabelKey: labelKey,
            DescriptionKey: descriptionKey,
            RulesetId: rulesetId,
            Act: 0,
            NodeId: savePointId,
            IntegrityHash: ComputeHash(stateJson),
            UpdatedAt: savedAt);
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
            schema_version = schemaVersion,
            save_point_id = savePointId,
            state_json = stateJson,
            integrity_hash = integrityHash,
            saved_at = savedAt,
        });
    }

    private static string BuildStateJson(bool difficultyIdAsString = false)
    {
        return difficultyIdAsString
            ? JsonSerializer.Serialize(new
            {
                difficulty = new
                {
                    difficulty_id = "3",
                    label_key = "difficulty.label.hard",
                    description_key = "difficulty.description.hard",
                    ruleset_id = "ruleset.hard",
                },
            })
            : JsonSerializer.Serialize(new
            {
                difficulty = new
                {
                    difficulty_id = 3,
                    label_key = "difficulty.label.hard",
                    description_key = "difficulty.description.hard",
                    ruleset_id = "ruleset.hard",
                },
            });
    }

    private static string ComputeHash(string content)
    {
        var bytes = Encoding.UTF8.GetBytes(content);
        return Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    }
}
