using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

[Trait("task", "T38")]
[Trait("adr", "ADR-0019")]
[Trait("adr", "ADR-0003")]
public sealed class AuditLoggerJsonlSchemaTests
{
    private static readonly string[] RequiredFields = { "ts", "action", "reason", "target", "caller" };

    // ACC:T38.1
    [Fact]
    public void ShouldAppendAuditRecords_WhenSecurityEventsAreLoggedToSsoTPath()
    {
        using var sandbox = new RepoSandbox();
        var logger = new AuditLogger(sandbox.RootPath);
        var first = new DateTimeOffset(2026, 4, 18, 9, 0, 0, TimeSpan.Zero);
        var second = first.AddSeconds(1);

        logger.RecordSave("slot-01", "SaveService.WriteAutosaveAsync", first);
        logger.RecordLoad("slot-01", "SaveService.ReadAutosaveAsync", second);

        var relativePath = logger.BuildRelativePath(first);
        relativePath.Should().Be("logs/ci/2026-04-18/security-audit.jsonl");
        var absolutePath = sandbox.GetAbsolutePath(relativePath);

        File.Exists(absolutePath).Should().BeTrue();
        var lines = SplitLines(File.ReadAllText(absolutePath));
        lines.Should().HaveCount(2);
    }

    // ACC:T38.2
    [Fact]
    public void ShouldValidateJsonlObjectLines_WhenWindowsAuditFlowProducesSecurityAuditFile()
    {
        using var sandbox = new RepoSandbox();
        var logger = new AuditLogger(sandbox.RootPath);
        var ts = new DateTimeOffset(2026, 4, 18, 9, 0, 0, TimeSpan.Zero);

        logger.RecordSave("slot-01", "SaveService.WriteAutosaveAsync", ts);
        logger.RecordDeny("policy_block", "https://example.com", "Security.OpenExternalUrl", ts.AddSeconds(1));

        var relativePath = logger.BuildRelativePath(ts);
        var absolutePath = sandbox.GetAbsolutePath(relativePath);
        var lines = SplitLines(File.ReadAllText(absolutePath));

        lines.Should().HaveCount(2);
        foreach (var line in lines)
        {
            using var document = JsonDocument.Parse(line);
            document.RootElement.ValueKind.Should().Be(JsonValueKind.Object);
        }
    }

    // ACC:T38.3
    [Fact]
    public void ShouldReturnTraceableEvidence_WhenAuditJsonlValidationCompletes()
    {
        using var sandbox = new RepoSandbox();
        var logger = new AuditLogger(sandbox.RootPath);
        var ts = new DateTimeOffset(2026, 4, 18, 9, 0, 0, TimeSpan.Zero);

        logger.RecordOfferLock("offer-01", "RewardOfferLockingService.Lock", ts);

        var relativePath = logger.BuildRelativePath(ts);
        var absolutePath = sandbox.GetAbsolutePath(relativePath);
        var result = ValidateJsonl(File.ReadAllText(absolutePath), relativePath);

        result.IsValid.Should().BeTrue();
        result.EvidencePath.Should().Be("logs/ci/2026-04-18/security-audit.jsonl");
        result.PathCheck.Should().Be("pass");
        result.FieldCheck.Should().Equal(RequiredFields);
        result.ErrorCodes.Should().BeEmpty();
    }

    // ACC:T38.4
    [Fact]
    public void ShouldFailValidation_WhenAnyRequiredFieldIsMissingInAuditRecord()
    {
        var relativePath = "logs/ci/2026-04-18/security-audit.jsonl";
        var missingFieldLine = JsonSerializer.Serialize(new Dictionary<string, string>
        {
            ["ts"] = "2026-04-18T09:00:00Z",
            ["action"] = "save",
            ["reason"] = "ok",
            ["target"] = "slot-01"
        });

        var result = ValidateJsonl(missingFieldLine, relativePath);

        result.IsValid.Should().BeFalse();
        result.ErrorCodes.Should().Contain("line_1_missing_caller");
    }

    // ACC:T38.6
    [Theory]
    [InlineData("logs/ci/2026-04-18/security/security-audit.jsonl", "{\"ts\":\"2026-04-18T00:00:00Z\"}", "path_mismatch")]
    [InlineData("logs/ci/2026-04-18/security-audit.jsonl", "not-a-json-object", "line_1_invalid_json")]
    public void ShouldFailValidation_WhenPathOrJsonlShapeIsInvalid(string filePath, string jsonlContent, string expectedErrorCode)
    {
        var result = ValidateJsonl(jsonlContent, filePath);

        result.IsValid.Should().BeFalse();
        result.ErrorCodes.Should().Contain(expectedErrorCode);
    }

    // ACC:T38.7
    [Fact]
    public void ShouldEmitRequiredFields_WhenAuditLoggerEntryPointWritesJsonlRecord()
    {
        using var sandbox = new RepoSandbox();
        var logger = new AuditLogger(sandbox.RootPath);
        var ts = new DateTimeOffset(2026, 4, 18, 9, 0, 0, TimeSpan.Zero);

        logger.RecordDeny("policy_block", "https://example.com", "Security.OpenExternalUrl", ts);

        var absolutePath = logger.BuildAbsolutePath(ts);
        File.Exists(absolutePath).Should().BeTrue();

        var line = SplitLines(File.ReadAllText(absolutePath)).Single();
        using var document = JsonDocument.Parse(line);

        foreach (var field in RequiredFields)
        {
            document.RootElement.TryGetProperty(field, out var value).Should().BeTrue();
            value.ValueKind.Should().Be(JsonValueKind.String);
            value.GetString().Should().NotBeNullOrWhiteSpace();
        }
    }

    // ACC:T38.8
    [Fact]
    public void ShouldFailTraceability_WhenEitherRequiredAdrReferenceIsMissing()
    {
        var presentAdrIds = new[] { "ADR-0019" };

        var result = ValidateTraceability(presentAdrIds);

        result.IsValid.Should().BeFalse();
        result.MissingAdrIds.Should().Contain("ADR-0003");
    }

    private static ValidationResult ValidateJsonl(string jsonlContent, string filePath)
    {
        var errorCodes = new List<string>();
        var parsedLineCount = 0;
        var pathCheck = IsExpectedPath(filePath) ? "pass" : "fail";
        if (pathCheck == "fail")
        {
            errorCodes.Add("path_mismatch");
        }

        if (string.IsNullOrWhiteSpace(jsonlContent))
        {
            errorCodes.Add("jsonl_empty");
            return new ValidationResult(false, parsedLineCount, filePath, pathCheck, RequiredFields, errorCodes);
        }

        var lines = SplitLines(jsonlContent);
        for (var i = 0; i < lines.Length; i++)
        {
            try
            {
                using var document = JsonDocument.Parse(lines[i]);
                if (document.RootElement.ValueKind != JsonValueKind.Object)
                {
                    errorCodes.Add($"line_{i + 1}_not_object");
                    continue;
                }

                foreach (var field in RequiredFields)
                {
                    if (!document.RootElement.TryGetProperty(field, out var value) ||
                        value.ValueKind != JsonValueKind.String ||
                        string.IsNullOrWhiteSpace(value.GetString()))
                    {
                        errorCodes.Add($"line_{i + 1}_missing_{field}");
                    }
                }

                parsedLineCount++;
            }
            catch (JsonException)
            {
                errorCodes.Add($"line_{i + 1}_invalid_json");
            }
        }

        var isValid = errorCodes.Count == 0;
        return new ValidationResult(isValid, parsedLineCount, filePath, pathCheck, RequiredFields, errorCodes);
    }

    private static TraceabilityValidationResult ValidateTraceability(IEnumerable<string> presentAdrIds)
    {
        var requiredAdrIds = new[] { "ADR-0019", "ADR-0003" };
        var presentSet = new HashSet<string>(presentAdrIds, StringComparer.Ordinal);
        var missingAdrIds = requiredAdrIds.Where(id => !presentSet.Contains(id)).ToArray();
        return new TraceabilityValidationResult(missingAdrIds.Length == 0, missingAdrIds);
    }

    private static bool IsExpectedPath(string filePath)
    {
        var segments = filePath.Split('/');
        if (segments.Length != 4)
        {
            return false;
        }

        if (!string.Equals(segments[0], "logs", StringComparison.Ordinal) ||
            !string.Equals(segments[1], "ci", StringComparison.Ordinal) ||
            !string.Equals(segments[3], "security-audit.jsonl", StringComparison.Ordinal))
        {
            return false;
        }

        return DateTime.TryParseExact(
            segments[2],
            "yyyy-MM-dd",
            CultureInfo.InvariantCulture,
            DateTimeStyles.None,
            out _);
    }

    private static string[] SplitLines(string content)
    {
        return content
            .Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
    }

    private sealed class ValidationResult
    {
        public ValidationResult(
            bool isValid,
            int parsedLineCount,
            string evidencePath,
            string pathCheck,
            IReadOnlyList<string> fieldCheck,
            IReadOnlyList<string> errorCodes)
        {
            IsValid = isValid;
            ParsedLineCount = parsedLineCount;
            EvidencePath = evidencePath;
            PathCheck = pathCheck;
            FieldCheck = fieldCheck;
            ErrorCodes = errorCodes;
        }

        public bool IsValid { get; }

        public int ParsedLineCount { get; }

        public string EvidencePath { get; }

        public string PathCheck { get; }

        public IReadOnlyList<string> FieldCheck { get; }

        public IReadOnlyList<string> ErrorCodes { get; }
    }

    private sealed class TraceabilityValidationResult
    {
        public TraceabilityValidationResult(bool isValid, IReadOnlyList<string> missingAdrIds)
        {
            IsValid = isValid;
            MissingAdrIds = missingAdrIds;
        }

        public bool IsValid { get; }

        public IReadOnlyList<string> MissingAdrIds { get; }
    }

    private sealed class RepoSandbox : IDisposable
    {
        public RepoSandbox()
        {
            RootPath = Path.Combine(Path.GetTempPath(), "newrouge-task38-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(RootPath);
        }

        public string RootPath { get; }

        public string GetAbsolutePath(string relativePath)
        {
            var normalized = relativePath.Replace('/', Path.DirectorySeparatorChar);
            return Path.Combine(RootPath, normalized);
        }

        public void Dispose()
        {
            try
            {
                if (Directory.Exists(RootPath))
                {
                    Directory.Delete(RootPath, recursive: true);
                }
            }
            catch
            {
                // best effort
            }
        }
    }
}
