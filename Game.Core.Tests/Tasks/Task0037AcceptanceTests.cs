using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts.Save;
using Game.Core.Ports;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

[Trait("task", "T37")]
public sealed class Task0037AcceptanceTests
{
    private const int TaskmasterId = 37;
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0037AcceptanceTests.cs";

    // ACC:T37.1
    [Fact]
    [Trait("acceptance", "ACC:T37.1")]
    public async Task ShouldLoadRuntimeMetadataAndEvaluateContinueAvailability_WhenSingleSlotSaveIsValid()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateSaveService();
        var validator = new ContinueLoadValidationService();
        var savedAt = new DateTimeOffset(2026, 4, 16, 9, 30, 0, TimeSpan.Zero);
        var snapshot = CreateSnapshot(
            runId: "run-37",
            savePointId: "node-11",
            savedAt: savedAt,
            difficultyId: 2,
            labelKey: "difficulty.label.hard",
            descriptionKey: "difficulty.description.hard",
            rulesetId: "ruleset.hard");

        await saveService.WriteAutosaveAsync(snapshot);
        var metadata = await saveService.ReadContinueMetadataAsync();

        metadata.Should().NotBeNull();
        metadata!.RunId.Should().Be("run-37");
        metadata.DifficultyId.Should().Be(2);
        metadata.NodeId.Should().Be("node-11");
        metadata.UpdatedAt.Should().Be(savedAt);
        metadata.IntegrityHash.Should().NotBeNullOrWhiteSpace();
        metadata.Act.Should().Be(0);

        var envelope = sandbox.ReadAutosaveEnvelope();
        var result = validator.Evaluate(envelope, metadata);
        result.ContinueAllowed.Should().BeTrue();
        result.ErrorCode.Should().BeNull();
        result.ErrorMessage.Should().BeNull();
        sandbox.ReadAutosaveEnvelope().Should().Be(envelope);
    }

    // ACC:T37.2
    [Fact]
    [Trait("acceptance", "ACC:T37.2")]
    public async Task ShouldBlockContinueAndKeepStoredContentUnchanged_WhenIntegrityValidationFails()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateSaveService();
        var validator = new ContinueLoadValidationService();
        var snapshot = CreateSnapshot(
            runId: "run-stable",
            savePointId: "node-1",
            savedAt: DateTimeOffset.UnixEpoch.AddHours(1),
            difficultyId: 3,
            labelKey: "difficulty.label.normal",
            descriptionKey: "difficulty.description.normal",
            rulesetId: "ruleset.normal");

        await saveService.WriteAutosaveAsync(snapshot);

        var originalEnvelope = sandbox.ReadAutosaveEnvelope();
        var metadata = await saveService.ReadContinueMetadataAsync();
        metadata.Should().NotBeNull();

        var tamperedEnvelope = TamperStateJsonAndKeepIntegrityHash(originalEnvelope);
        var result = validator.Evaluate(tamperedEnvelope, metadata!);

        result.ContinueAllowed.Should().BeFalse();
        result.ErrorCode.Should().Be("invalid_integrity");
        result.ErrorMessage.Should().Be("invalid_integrity");
        sandbox.ReadAutosaveEnvelope().Should().Be(originalEnvelope);
    }

    // ACC:T37.3
    [Fact]
    [Trait("acceptance", "ACC:T37.3")]
    public async Task ShouldReturnAllowAndBlockOutcomes_WhenContinueGateEvaluatesMetadataAndEnvelope()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateSaveService();
        var validator = new ContinueLoadValidationService();
        var snapshot = CreateSnapshot(
            runId: "run-gate",
            savePointId: "node-2",
            savedAt: DateTimeOffset.UnixEpoch.AddMinutes(30),
            difficultyId: 4,
            labelKey: "difficulty.label.normal",
            descriptionKey: "difficulty.description.normal",
            rulesetId: "ruleset.normal");

        await saveService.WriteAutosaveAsync(snapshot);
        var metadata = await saveService.ReadContinueMetadataAsync();
        metadata.Should().NotBeNull();

        var allowResult = validator.Evaluate(sandbox.ReadAutosaveEnvelope(), metadata!);

        var invalidMetadata = new ContinueMetadata(
            RunId: metadata!.RunId,
            DifficultyId: metadata.DifficultyId,
            LabelKey: metadata.LabelKey,
            DescriptionKey: metadata.DescriptionKey,
            RulesetId: metadata.RulesetId,
            Act: -1,
            NodeId: metadata.NodeId,
            IntegrityHash: metadata.IntegrityHash,
            UpdatedAt: metadata.UpdatedAt);
        var blockResult = validator.Evaluate(sandbox.ReadAutosaveEnvelope(), invalidMetadata);
        var missingMetadataResult = validator.Evaluate(sandbox.ReadAutosaveEnvelope(), null);

        allowResult.ContinueAllowed.Should().BeTrue();
        allowResult.ErrorCode.Should().BeNull();
        allowResult.ErrorMessage.Should().BeNull();
        blockResult.ContinueAllowed.Should().BeFalse();
        blockResult.ErrorCode.Should().Be("invalid_metadata");
        blockResult.ErrorMessage.Should().Be("invalid_metadata");
        missingMetadataResult.ContinueAllowed.Should().BeFalse();
        missingMetadataResult.ErrorCode.Should().Be("invalid_metadata");
        missingMetadataResult.ErrorMessage.Should().Be("invalid_metadata");
    }

    // ACC:T37.4
    [Theory]
    [Trait("acceptance", "ACC:T37.4")]
    [InlineData(null, "structure")]
    [InlineData("", "structure")]
    [InlineData("{bad", "structure")]
    [InlineData("[]", "structure")]
    [InlineData("{}", "metadata")]
    [InlineData("{\"run_id\":\"run-37\"}", "metadata")]
    public async Task ShouldFailContinueValidationWhenEnvelopeViolatesStructureOrMetadataSchema(
        string? payload,
        string expectedErrorKind)
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateSaveService();
        var snapshot = CreateSnapshot(
            runId: "run-structure",
            savePointId: "node-structure",
            savedAt: DateTimeOffset.UnixEpoch.AddMinutes(3),
            difficultyId: 2,
            labelKey: "difficulty.label.hard",
            descriptionKey: "difficulty.description.hard",
            rulesetId: "ruleset.hard");
        await saveService.WriteAutosaveAsync(snapshot);
        var before = sandbox.ReadAutosaveEnvelope();
        var validator = new ContinueLoadValidationService();
        var metadata = new ContinueMetadata(
            RunId: "run-37",
            DifficultyId: 2,
            LabelKey: "difficulty.label.hard",
            DescriptionKey: "difficulty.description.hard",
            RulesetId: "ruleset.hard",
            Act: 0,
            NodeId: "node-11",
            IntegrityHash: "hash-37",
            UpdatedAt: DateTimeOffset.UnixEpoch.AddMinutes(1));

        var result = validator.Evaluate(payload, metadata);

        result.ContinueAllowed.Should().BeFalse();
        result.ErrorCode.Should().Be(expectedErrorKind switch
        {
            "structure" => "invalid_structure",
            "metadata" => "invalid_metadata",
            _ => "invalid_integrity",
        });
        result.ErrorMessage.Should().Be(expectedErrorKind switch
        {
            "structure" => "invalid_structure",
            "metadata" => "invalid_metadata",
            _ => "invalid_integrity",
        });
        sandbox.ReadAutosaveEnvelope().Should().Be(before);
    }

    [Theory]
    [Trait("acceptance", "ACC:T37.4")]
    [Trait("acceptance", "ACC:T37.7")]
    [InlineData("run_id_mismatch")]
    [InlineData("difficulty_id_mismatch")]
    [InlineData("label_key_mismatch")]
    [InlineData("description_key_mismatch")]
    [InlineData("ruleset_id_mismatch")]
    [InlineData("node_id_mismatch")]
    [InlineData("updated_at_mismatch")]
    public async Task ShouldBlockContinueWithInvalidMetadataWhenMetadataFieldsMismatch(
        string caseId)
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateSaveService();
        var validator = new ContinueLoadValidationService();
        var savedAt = DateTimeOffset.UnixEpoch.AddMinutes(11);
        var snapshot = CreateSnapshot(
            runId: "run-37",
            savePointId: "node-11",
            savedAt: savedAt,
            difficultyId: 2,
            labelKey: "difficulty.label.hard",
            descriptionKey: "difficulty.description.hard",
            rulesetId: "ruleset.hard");
        await saveService.WriteAutosaveAsync(snapshot);

        var envelope = sandbox.ReadAutosaveEnvelope();
        var before = sandbox.ReadAutosaveEnvelope();
        var baseMetadata = await saveService.ReadContinueMetadataAsync();
        baseMetadata.Should().NotBeNull();
        var metadata = BuildMismatchedMetadata(baseMetadata!, caseId, savedAt);

        var result = validator.Evaluate(envelope, metadata);

        result.ContinueAllowed.Should().BeFalse(caseId);
        result.ErrorCode.Should().Be("invalid_metadata", caseId);
        result.ErrorMessage.Should().Be("invalid_metadata", caseId);
        sandbox.ReadAutosaveEnvelope().Should().Be(before, caseId);
    }

    [Theory]
    [Trait("acceptance", "ACC:T37.4")]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("999.0.0")]
    public async Task ShouldBlockContinueWithInvalidMetadata_WhenSchemaVersionIsMissingBlankOrUnsupported(string schemaVersion)
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateSaveService();
        var validator = new ContinueLoadValidationService();
        var snapshot = CreateSnapshot(
            runId: "run-schema",
            savePointId: "node-schema",
            savedAt: DateTimeOffset.UnixEpoch.AddMinutes(13),
            difficultyId: 2,
            labelKey: "difficulty.label.hard",
            descriptionKey: "difficulty.description.hard",
            rulesetId: "ruleset.hard");
        await saveService.WriteAutosaveAsync(snapshot);

        var baselineEnvelope = sandbox.ReadAutosaveEnvelope();
        using var baselineDoc = JsonDocument.Parse(baselineEnvelope);
        var root = baselineDoc.RootElement;
        var modifiedEnvelope = JsonSerializer.Serialize(new Dictionary<string, object?>
        {
            ["run_id"] = root.GetProperty("run_id").GetString(),
            ["schema_version"] = schemaVersion,
            ["save_point_id"] = root.GetProperty("save_point_id").GetString(),
            ["saved_at"] = root.GetProperty("saved_at").GetString(),
            ["state_json"] = root.GetProperty("state_json").GetString(),
            ["offer_locks"] = root.TryGetProperty("offer_locks", out var offerLocks)
                ? offerLocks.EnumerateArray().Select(item => item.GetString()).ToArray()
                : Array.Empty<string>(),
            ["integrity_hash"] = root.GetProperty("integrity_hash").GetString(),
        });

        var metadata = await saveService.ReadContinueMetadataAsync();
        metadata.Should().NotBeNull();
        var result = validator.Evaluate(modifiedEnvelope, metadata);

        result.ContinueAllowed.Should().BeFalse();
        result.ErrorCode.Should().Be("invalid_metadata");
        result.ErrorMessage.Should().Be("invalid_metadata");
    }

    [Fact]
    [Trait("acceptance", "ACC:T37.4")]
    public async Task ShouldBlockContinueWithInvalidMetadata_WhenSavedAtIsUnparseable()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateSaveService();
        var validator = new ContinueLoadValidationService();
        var snapshot = CreateSnapshot(
            runId: "run-saved-at",
            savePointId: "node-saved-at",
            savedAt: DateTimeOffset.UnixEpoch.AddMinutes(17),
            difficultyId: 2,
            labelKey: "difficulty.label.hard",
            descriptionKey: "difficulty.description.hard",
            rulesetId: "ruleset.hard");
        await saveService.WriteAutosaveAsync(snapshot);

        var baselineEnvelope = sandbox.ReadAutosaveEnvelope();
        using var baselineDoc = JsonDocument.Parse(baselineEnvelope);
        var root = baselineDoc.RootElement;
        var modifiedEnvelope = JsonSerializer.Serialize(new Dictionary<string, object?>
        {
            ["run_id"] = root.GetProperty("run_id").GetString(),
            ["schema_version"] = root.GetProperty("schema_version").GetString(),
            ["save_point_id"] = root.GetProperty("save_point_id").GetString(),
            ["saved_at"] = "not-a-date-time",
            ["state_json"] = root.GetProperty("state_json").GetString(),
            ["offer_locks"] = root.TryGetProperty("offer_locks", out var offerLocks)
                ? offerLocks.EnumerateArray().Select(item => item.GetString()).ToArray()
                : Array.Empty<string>(),
            ["integrity_hash"] = root.GetProperty("integrity_hash").GetString(),
        });

        var metadata = await saveService.ReadContinueMetadataAsync();
        metadata.Should().NotBeNull();
        var result = validator.Evaluate(modifiedEnvelope, metadata);

        result.ContinueAllowed.Should().BeFalse();
        result.ErrorCode.Should().Be("invalid_metadata");
        result.ErrorMessage.Should().Be("invalid_metadata");
    }

    [Theory]
    [Trait("acceptance", "ACC:T37.4")]
    [InlineData("", 2, "difficulty.label.hard", "difficulty.description.hard", "ruleset.hard", "node-11", "hash-37", "run_id_blank")]
    [InlineData("run-37", 0, "difficulty.label.hard", "difficulty.description.hard", "ruleset.hard", "node-11", "hash-37", "difficulty_too_low")]
    [InlineData("run-37", 11, "difficulty.label.hard", "difficulty.description.hard", "ruleset.hard", "node-11", "hash-37", "difficulty_too_high")]
    [InlineData("run-37", 2, "", "difficulty.description.hard", "ruleset.hard", "node-11", "hash-37", "label_blank")]
    [InlineData("run-37", 2, "difficulty.label.hard", "", "ruleset.hard", "node-11", "hash-37", "description_blank")]
    [InlineData("run-37", 2, "difficulty.label.hard", "difficulty.description.hard", "", "node-11", "hash-37", "ruleset_blank")]
    [InlineData("run-37", 2, "difficulty.label.hard", "difficulty.description.hard", "ruleset.hard", "", "hash-37", "node_blank")]
    [InlineData("run-37", 2, "difficulty.label.hard", "difficulty.description.hard", "ruleset.hard", "node-11", "", "integrity_hash_blank")]
    public void ShouldRejectInvalidContinueMetadataContractWhenFieldsAreBlankOrOutOfRange(
        string runId,
        int difficultyId,
        string labelKey,
        string descriptionKey,
        string rulesetId,
        string nodeId,
        string integrityHash,
        string caseId)
    {
        Action act = () => _ = new ContinueMetadata(
            RunId: runId,
            DifficultyId: difficultyId,
            LabelKey: labelKey,
            DescriptionKey: descriptionKey,
            RulesetId: rulesetId,
            Act: 0,
            NodeId: nodeId,
            IntegrityHash: integrityHash,
            UpdatedAt: DateTimeOffset.UnixEpoch.AddMinutes(1));

        if (difficultyId is <= 0 or > 10)
        {
            act.Should().Throw<ArgumentOutOfRangeException>(caseId);
        }
        else
        {
            act.Should().Throw<ArgumentException>(caseId);
        }
    }

    // ACC:T37.5
    [Fact]
    [Trait("acceptance", "ACC:T37.5")]
    public async Task ShouldAllowContinueWithNullErrorAndUnchangedStoredContent_WhenEnvelopeAndMetadataAreValid()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateSaveService();
        var validator = new ContinueLoadValidationService();
        var snapshot = CreateSnapshot(
            runId: "run-valid",
            savePointId: "node-valid",
            savedAt: DateTimeOffset.UnixEpoch.AddMinutes(5),
            difficultyId: 5,
            labelKey: "difficulty.label.expert",
            descriptionKey: "difficulty.description.expert",
            rulesetId: "ruleset.expert");

        await saveService.WriteAutosaveAsync(snapshot);
        var before = sandbox.ReadAutosaveEnvelope();
        var metadata = await saveService.ReadContinueMetadataAsync();
        metadata.Should().NotBeNull();

        var result = validator.Evaluate(before, metadata);
        result.ContinueAllowed.Should().BeTrue();
        result.ErrorCode.Should().BeNull();
        result.ErrorMessage.Should().BeNull();
        sandbox.ReadAutosaveEnvelope().Should().Be(before);
    }

    // Regression: keep a direct allow/block pair sanity check without duplicating acceptance anchors.
    [Fact]
    public async Task ShouldAssertRealContinueGateBehavior_WhenXunitAcceptanceIsEvaluated()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateSaveService();
        var validator = new ContinueLoadValidationService();
        var snapshot = CreateSnapshot(
            runId: "run-xunit",
            savePointId: "node-xunit",
            savedAt: DateTimeOffset.UnixEpoch.AddMinutes(7),
            difficultyId: 6,
            labelKey: "difficulty.label.master",
            descriptionKey: "difficulty.description.master",
            rulesetId: "ruleset.master");
        await saveService.WriteAutosaveAsync(snapshot);

        var envelope = sandbox.ReadAutosaveEnvelope();
        var metadata = await saveService.ReadContinueMetadataAsync();
        metadata.Should().NotBeNull();

        var allowResult = validator.Evaluate(envelope, metadata);
        allowResult.ContinueAllowed.Should().BeTrue();
        allowResult.ErrorCode.Should().BeNull();
        allowResult.ErrorMessage.Should().BeNull();

        var blockResult = validator.Evaluate(envelope, null);
        blockResult.ContinueAllowed.Should().BeFalse();
        blockResult.ErrorCode.Should().Be("invalid_metadata");
        blockResult.ErrorMessage.Should().Be("invalid_metadata");
    }

    // ACC:T37.6
    [Fact]
    [Trait("acceptance", "ACC:T37.6")]
    public async Task ShouldBlockContinueAndKeepStoredContentUnchanged_WhenInvalidStructureDetected()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateSaveService();
        var validator = new ContinueLoadValidationService();
        var snapshot = CreateSnapshot(
            runId: "run-structure-acc7",
            savePointId: "node-structure-acc7",
            savedAt: DateTimeOffset.UnixEpoch.AddMinutes(19),
            difficultyId: 2,
            labelKey: "difficulty.label.hard",
            descriptionKey: "difficulty.description.hard",
            rulesetId: "ruleset.hard");
        await saveService.WriteAutosaveAsync(snapshot);
        var before = sandbox.ReadAutosaveEnvelope();
        var metadata = await saveService.ReadContinueMetadataAsync();
        metadata.Should().NotBeNull();

        var result = validator.Evaluate("[]", metadata);

        result.ContinueAllowed.Should().BeFalse();
        result.ErrorCode.Should().Be("invalid_structure");
        result.ErrorMessage.Should().Be("invalid_structure");
        sandbox.ReadAutosaveEnvelope().Should().Be(before);
    }

    // ACC:T37.7
    [Fact]
    [Trait("acceptance", "ACC:T37.7")]
    public async Task ShouldEvaluateContinueValidationThroughLoadEntry_WhenContinueValidationIsRequested()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateSaveService();
        var snapshot = CreateSnapshot(
            runId: "run-entry",
            savePointId: "node-entry",
            savedAt: DateTimeOffset.UnixEpoch.AddMinutes(23),
            difficultyId: 3,
            labelKey: "difficulty.label.normal",
            descriptionKey: "difficulty.description.normal",
            rulesetId: "ruleset.normal");

        await saveService.WriteAutosaveAsync(snapshot);
        var success = await saveService.ValidateContinueLoadAsync();

        success.ContinueAllowed.Should().BeTrue();
        success.ErrorCode.Should().BeNull();
        success.ErrorMessage.Should().BeNull();

        var tampered = TamperStateJsonAndKeepIntegrityHash(sandbox.ReadAutosaveEnvelope());
        sandbox.WriteAutosaveEnvelope(tampered);
        var failure = await saveService.ValidateContinueLoadAsync();

        failure.ContinueAllowed.Should().BeFalse();
        failure.ErrorCode.Should().Be("invalid_integrity");
        failure.ErrorMessage.Should().Be("invalid_integrity");
    }

    [Fact]
    [Trait("acceptance", "ACC:T37.7")]
    public async Task ShouldReturnInvalidMetadataThroughLoadEntry_WhenEnvelopeSchemaVersionIsUnsupported()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateSaveService();
        var snapshot = CreateSnapshot(
            runId: "run-entry-metadata",
            savePointId: "node-entry-metadata",
            savedAt: DateTimeOffset.UnixEpoch.AddMinutes(29),
            difficultyId: 3,
            labelKey: "difficulty.label.normal",
            descriptionKey: "difficulty.description.normal",
            rulesetId: "ruleset.normal");

        await saveService.WriteAutosaveAsync(snapshot);

        var baselineEnvelope = sandbox.ReadAutosaveEnvelope();
        using var baselineDoc = JsonDocument.Parse(baselineEnvelope);
        var root = baselineDoc.RootElement;
        var invalidMetadataEnvelope = JsonSerializer.Serialize(new Dictionary<string, object?>
        {
            ["run_id"] = root.GetProperty("run_id").GetString(),
            ["schema_version"] = "999.0.0",
            ["save_point_id"] = root.GetProperty("save_point_id").GetString(),
            ["saved_at"] = root.GetProperty("saved_at").GetString(),
            ["state_json"] = root.GetProperty("state_json").GetString(),
            ["offer_locks"] = root.TryGetProperty("offer_locks", out var offerLocks)
                ? offerLocks.EnumerateArray().Select(item => item.GetString()).ToArray()
                : Array.Empty<string>(),
            ["integrity_hash"] = root.GetProperty("integrity_hash").GetString(),
        });
        sandbox.WriteAutosaveEnvelope(invalidMetadataEnvelope);

        var result = await saveService.ValidateContinueLoadAsync();

        result.ContinueAllowed.Should().BeFalse();
        result.ErrorCode.Should().Be("invalid_metadata");
        result.ErrorMessage.Should().Be("invalid_metadata");
    }

    [Fact]
    [Trait("acceptance", "ACC:T37.7")]
    public async Task ShouldReturnInvalidStructureThroughLoadEntry_WhenEnvelopeStructureIsInvalid()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var saveService = sandbox.CreateSaveService();
        var snapshot = CreateSnapshot(
            runId: "run-entry-structure",
            savePointId: "node-entry-structure",
            savedAt: DateTimeOffset.UnixEpoch.AddMinutes(31),
            difficultyId: 3,
            labelKey: "difficulty.label.normal",
            descriptionKey: "difficulty.description.normal",
            rulesetId: "ruleset.normal");

        await saveService.WriteAutosaveAsync(snapshot);
        sandbox.WriteAutosaveEnvelope("[]");

        var result = await saveService.ValidateContinueLoadAsync();

        result.ContinueAllowed.Should().BeFalse();
        result.ErrorCode.Should().Be("invalid_structure");
        result.ErrorMessage.Should().Be("invalid_structure");
    }

    [Fact]
    public void ShouldContainAdr0032AndAdr0029AcrossTaskView_WhenAdrTraceabilityIsEvaluated()
    {
        var task = ReadTaskNodeByTaskmasterId(TaskmasterId);
        var adrRefs = ReadStringArray(task, "adr_refs");

        adrRefs.Should().Contain(new[] { "ADR-0032", "ADR-0029" });
    }

    [Fact]
    public void ShouldKeepTaskTestRefsAligned_WhenAcceptanceEvidenceIsEnumerated()
    {
        var task = ReadTaskNodeByTaskmasterId(TaskmasterId);
        var refs = ReadStringArray(task, "test_refs");

        refs.Should().ContainSingle(reference => string.Equals(reference, ThisTaskTestRef, StringComparison.Ordinal));
    }

    private static AutosaveSnapshot CreateSnapshot(
        string runId,
        string savePointId,
        DateTimeOffset savedAt,
        int difficultyId,
        string labelKey,
        string descriptionKey,
        string rulesetId)
    {
        var stateJson = JsonSerializer.Serialize(new
        {
            hp = 60,
            difficulty = new
            {
                difficulty_id = difficultyId,
                label_key = labelKey,
                description_key = descriptionKey,
                ruleset_id = rulesetId,
            },
            marker = "task37",
        });

        return new AutosaveSnapshot(
            RunId: runId,
            SavePointId: savePointId,
            SchemaVersion: "1.0.0",
            StateJson: stateJson,
            SavedAt: savedAt);
    }

    private static string TamperStateJsonAndKeepIntegrityHash(string autosaveEnvelopeJson)
    {
        using var doc = JsonDocument.Parse(autosaveEnvelopeJson);
        var root = doc.RootElement;
        var stateJson = root.GetProperty("state_json").GetString();
        using var stateDoc = JsonDocument.Parse(stateJson ?? "{}");
        var stateRoot = stateDoc.RootElement;
        var existingDifficulty = stateRoot.GetProperty("difficulty");
        var tamperedStateJson = JsonSerializer.Serialize(new
        {
            hp = 1,
            difficulty = new
            {
                difficulty_id = existingDifficulty.GetProperty("difficulty_id").GetInt32(),
                label_key = existingDifficulty.GetProperty("label_key").GetString(),
                description_key = existingDifficulty.GetProperty("description_key").GetString(),
                ruleset_id = existingDifficulty.GetProperty("ruleset_id").GetString(),
            },
            marker = "tampered",
        });

        var payload = new Dictionary<string, object?>
        {
            ["run_id"] = root.GetProperty("run_id").GetString(),
            ["save_point_id"] = root.GetProperty("save_point_id").GetString(),
            ["schema_version"] = root.GetProperty("schema_version").GetString(),
            ["saved_at"] = root.GetProperty("saved_at").GetString(),
            ["state_json"] = tamperedStateJson,
            ["offer_locks"] = root.TryGetProperty("offer_locks", out var offerLocks)
                ? offerLocks.EnumerateArray().Select(item => item.GetString()).ToArray()
                : Array.Empty<string>(),
            ["integrity_hash"] = root.GetProperty("integrity_hash").GetString(),
        };

        return JsonSerializer.Serialize(payload);
    }

    private static ContinueMetadata BuildMismatchedMetadata(ContinueMetadata baseline, string caseId, DateTimeOffset savedAt)
    {
        return caseId switch
        {
            "run_id_mismatch" => new ContinueMetadata(
                RunId: "run-37-mismatch",
                DifficultyId: baseline.DifficultyId,
                LabelKey: baseline.LabelKey,
                DescriptionKey: baseline.DescriptionKey,
                RulesetId: baseline.RulesetId,
                Act: baseline.Act,
                NodeId: baseline.NodeId,
                IntegrityHash: baseline.IntegrityHash,
                UpdatedAt: baseline.UpdatedAt),
            "difficulty_id_mismatch" => new ContinueMetadata(
                RunId: baseline.RunId,
                DifficultyId: baseline.DifficultyId == 2 ? 3 : 2,
                LabelKey: baseline.LabelKey,
                DescriptionKey: baseline.DescriptionKey,
                RulesetId: baseline.RulesetId,
                Act: baseline.Act,
                NodeId: baseline.NodeId,
                IntegrityHash: baseline.IntegrityHash,
                UpdatedAt: baseline.UpdatedAt),
            "label_key_mismatch" => new ContinueMetadata(
                RunId: baseline.RunId,
                DifficultyId: baseline.DifficultyId,
                LabelKey: baseline.LabelKey + ".changed",
                DescriptionKey: baseline.DescriptionKey,
                RulesetId: baseline.RulesetId,
                Act: baseline.Act,
                NodeId: baseline.NodeId,
                IntegrityHash: baseline.IntegrityHash,
                UpdatedAt: baseline.UpdatedAt),
            "description_key_mismatch" => new ContinueMetadata(
                RunId: baseline.RunId,
                DifficultyId: baseline.DifficultyId,
                LabelKey: baseline.LabelKey,
                DescriptionKey: baseline.DescriptionKey + ".changed",
                RulesetId: baseline.RulesetId,
                Act: baseline.Act,
                NodeId: baseline.NodeId,
                IntegrityHash: baseline.IntegrityHash,
                UpdatedAt: baseline.UpdatedAt),
            "ruleset_id_mismatch" => new ContinueMetadata(
                RunId: baseline.RunId,
                DifficultyId: baseline.DifficultyId,
                LabelKey: baseline.LabelKey,
                DescriptionKey: baseline.DescriptionKey,
                RulesetId: baseline.RulesetId + ".changed",
                Act: baseline.Act,
                NodeId: baseline.NodeId,
                IntegrityHash: baseline.IntegrityHash,
                UpdatedAt: baseline.UpdatedAt),
            "node_id_mismatch" => new ContinueMetadata(
                RunId: baseline.RunId,
                DifficultyId: baseline.DifficultyId,
                LabelKey: baseline.LabelKey,
                DescriptionKey: baseline.DescriptionKey,
                RulesetId: baseline.RulesetId,
                Act: baseline.Act,
                NodeId: baseline.NodeId + "-changed",
                IntegrityHash: baseline.IntegrityHash,
                UpdatedAt: baseline.UpdatedAt),
            "updated_at_mismatch" => new ContinueMetadata(
                RunId: baseline.RunId,
                DifficultyId: baseline.DifficultyId,
                LabelKey: baseline.LabelKey,
                DescriptionKey: baseline.DescriptionKey,
                RulesetId: baseline.RulesetId,
                Act: baseline.Act,
                NodeId: baseline.NodeId,
                IntegrityHash: baseline.IntegrityHash,
                UpdatedAt: savedAt.AddMinutes(1)),
            _ => throw new ArgumentOutOfRangeException(nameof(caseId), caseId, "Unknown metadata mismatch case."),
        };
    }

    private static JsonElement ReadTaskNodeByTaskmasterId(int taskmasterId)
    {
        var repoRoot = ResolveRepoRoot();
        var taskFilePath = Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_gameplay.json");
        using var document = JsonDocument.Parse(File.ReadAllText(taskFilePath));
        var taskNode = document.RootElement
            .EnumerateArray()
            .First(node =>
                node.TryGetProperty("taskmaster_id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.GetInt32() == taskmasterId);
        return taskNode.Clone();
    }

    private static string[] ReadStringArray(JsonElement node, string propertyName)
    {
        node.TryGetProperty(propertyName, out var property).Should().BeTrue();
        property.ValueKind.Should().Be(JsonValueKind.Array);
        return property
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(value => value!)
            .ToArray();
    }

    private static string ResolveRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, ".taskmaster")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root.");
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
            var rootPath = Path.Combine(Path.GetTempPath(), "newrouge-task0037-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(rootPath);
            return new SaveServiceSandbox(rootPath);
        }

        public SaveService CreateSaveService()
        {
            return new SaveService(new NoOpDataStore(), new DirectoryInfo(RootPath));
        }

        public string ReadAutosaveEnvelope()
        {
            var filePath = Path.Combine(RootPath, "saves", "autosave.json");
            File.Exists(filePath).Should().BeTrue();
            return File.ReadAllText(filePath);
        }

        public void WriteAutosaveEnvelope(string content)
        {
            var filePath = Path.Combine(RootPath, "saves", "autosave.json");
            File.Exists(filePath).Should().BeTrue();
            File.WriteAllText(filePath, content);
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
